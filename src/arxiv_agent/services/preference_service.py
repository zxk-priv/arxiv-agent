"""基于 `paper_datasets/` 的 PDF 偏好分析服务。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

from arxiv_agent.clients import SiliconFlowClient, now_utc_iso
from arxiv_agent.config import AppConfig
from arxiv_agent.models import (
    PdfPreferenceEntry,
    PreferenceProfile,
    ProgressEvent,
    SUMMARY_STATUS_FAILED,
    SUMMARY_STATUS_READY,
)
from arxiv_agent.storage import load_preference_profile, write_preference_profile


ProgressCallback = Callable[[str, str], None]


class PreferenceService:
    """负责从 `paper_datasets/` 构建 PDF 偏好缓存与整体画像。

    这个服务只做“本地 PDF -> 偏好标签/总结 -> 整体偏好画像”这一段：
    - 不负责抓 arXiv
    - 不负责当天论文检索
    - 不负责页面展示
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build_or_refresh_profile(
        self,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> PreferenceProfile:
        """扫描 `paper_datasets/` 并构建或刷新偏好画像。"""

        self._emit(progress_callback, "扫描 paper_datasets", "开始扫描本地 PDF 论文库。")
        pdf_paths = self._list_pdf_paths()
        cached_profile = load_preference_profile(self.config.preference_profile_path)
        cached_entries = {
            entry.source_pdf: entry
            for entry in (cached_profile.entries if cached_profile else [])
        }

        summarizer = SiliconFlowClient.from_config(self.config)
        entries: list[PdfPreferenceEntry] = []

        for pdf_path in pdf_paths:
            self._emit(progress_callback, "解析 PDF 前几页", f"检查缓存：{pdf_path.name}")
            cached_entry = cached_entries.get(pdf_path.name)
            if cached_entry and self._entry_matches_file(cached_entry, pdf_path) and cached_entry.is_ready:
                entries.append(cached_entry)
                self._emit(progress_callback, "解析 PDF 前几页", f"复用 PDF 偏好缓存：{pdf_path.name}")
                continue

            self._emit(progress_callback, "生成单篇 PDF 偏好总结", f"分析 PDF：{pdf_path.name}")
            entries.append(self._analyze_single_pdf(pdf_path, summarizer))

        self._emit(progress_callback, "汇总整体研究偏好", "开始汇总整体研究偏好画像。")
        profile = self._summarize_profile(entries, summarizer)
        write_preference_profile(self.config.preference_profile_path, profile)
        self._emit(progress_callback, "汇总整体研究偏好", "偏好画像已写入本地缓存。")
        return profile

    def _list_pdf_paths(self) -> list[Path]:
        """列出本地论文库中的 PDF 文件。"""

        dataset_dir = self.config.paper_dataset_dir
        dataset_dir.mkdir(parents=True, exist_ok=True)
        return sorted(path for path in dataset_dir.glob("*.pdf") if path.is_file())

    def _analyze_single_pdf(
        self,
        pdf_path: Path,
        summarizer: SiliconFlowClient,
    ) -> PdfPreferenceEntry:
        """读取单篇 PDF 的前几页文本，并让模型输出结构化总结。"""

        file_stat = pdf_path.stat()
        modified_at = datetime.fromtimestamp(file_stat.st_mtime, timezone.utc).isoformat()
        extracted_text = ""
        extracted_pages = 0
        try:
            extracted_text, extracted_pages = self._extract_pdf_preview(pdf_path)
            if not extracted_text.strip():
                raise RuntimeError("未从 PDF 前几页提取到可用文本。")

            parsed = summarizer.summarize_pdf_preference(
                source_pdf=pdf_path.name,
                extracted_text=extracted_text,
            )
            return PdfPreferenceEntry(
                source_pdf=pdf_path.name,
                paper_title=str(parsed.get("paper_title", "")).strip(),
                source_file_size=file_stat.st_size,
                source_modified_at_utc=modified_at,
                extracted_page_count=extracted_pages,
                extracted_text_preview=extracted_text[:3000],
                tech_fields=self._normalize_list(parsed.get("tech_fields")),
                methods=self._normalize_list(parsed.get("methods")),
                tasks=self._normalize_list(parsed.get("tasks")),
                zh_summary=str(parsed.get("zh_summary", "")).strip(),
                status=SUMMARY_STATUS_READY,
                updated_at_utc=now_utc_iso(),
                error_message="",
            )
        except Exception as exc:
            return PdfPreferenceEntry(
                source_pdf=pdf_path.name,
                paper_title="",
                source_file_size=file_stat.st_size,
                source_modified_at_utc=modified_at,
                extracted_page_count=extracted_pages,
                extracted_text_preview=extracted_text[:3000],
                tech_fields=[],
                methods=[],
                tasks=[],
                zh_summary="",
                status=SUMMARY_STATUS_FAILED,
                updated_at_utc=now_utc_iso(),
                error_message=str(exc),
            )

    def _extract_pdf_preview(self, pdf_path: Path) -> tuple[str, int]:
        """只提取 PDF 前几页文本。

        这里故意不读全文：
        - 当前目标是做“研究偏好归纳”，不需要完整正文
        - 前几页通常已经包含标题、摘要、引言和方法概览
        - 这样更快，也更不容易被长文中的噪声拖慢
        """

        reader = PdfReader(str(pdf_path))
        page_count = min(len(reader.pages), self.config.pdf_extract_pages)
        texts: list[str] = []
        for index in range(page_count):
            page_text = reader.pages[index].extract_text() or ""
            if page_text.strip():
                texts.append(page_text.strip())
        return "\n\n".join(texts).strip(), page_count

    def _summarize_profile(
        self,
        entries: list[PdfPreferenceEntry],
        summarizer: SiliconFlowClient,
    ) -> PreferenceProfile:
        """把多篇 PDF 的结构化总结再汇总成整体研究偏好。"""

        ready_entries = [entry for entry in entries if entry.is_ready]
        if not ready_entries:
            return PreferenceProfile(
                generated_at_utc=now_utc_iso(),
                source_pdf_count=len(entries),
                dominant_fields=[],
                method_keywords=[],
                task_keywords=[],
                research_focus_summary="未能从本地 PDF 论文库中提取出可用的偏好信息。",
                retrieval_query="",
                entries=entries,
            )

        profile_input_lines: list[str] = []
        for entry in ready_entries:
            profile_input_lines.extend(
                [
                    f"论文标题: {entry.paper_title or entry.source_pdf}",
                    f"技术领域: {', '.join(entry.tech_fields)}",
                    f"方法关键词: {', '.join(entry.methods)}",
                    f"任务关键词: {', '.join(entry.tasks)}",
                    f"中文总结: {entry.zh_summary}",
                    "",
                ]
            )

        parsed = summarizer.summarize_preference_profile(
            entry_summaries="\n".join(profile_input_lines).strip(),
        )
        return PreferenceProfile(
            generated_at_utc=now_utc_iso(),
            source_pdf_count=len(entries),
            dominant_fields=self._normalize_list(parsed.get("dominant_fields")),
            method_keywords=self._normalize_list(parsed.get("method_keywords")),
            task_keywords=self._normalize_list(parsed.get("task_keywords")),
            research_focus_summary=str(parsed.get("research_focus_summary", "")).strip(),
            retrieval_query=str(parsed.get("retrieval_query", "")).strip(),
            entries=entries,
        )

    def _entry_matches_file(self, entry: PdfPreferenceEntry, pdf_path: Path) -> bool:
        """判断缓存条目是否仍然对应当前磁盘文件。"""

        file_stat = pdf_path.stat()
        modified_at = datetime.fromtimestamp(file_stat.st_mtime, timezone.utc).isoformat()
        return (
            entry.source_file_size == file_stat.st_size
            and entry.source_modified_at_utc == modified_at
        )

    def _emit(
        self,
        callback: ProgressCallback | None,
        stage: str,
        message: str,
    ) -> None:
        """统一派发阶段日志。"""

        if callback is not None:
            callback(stage, message)

    def _normalize_list(self, value: object) -> list[str]:
        """把模型返回的字段统一转换成字符串列表。"""

        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if str(item).strip()]
            return list(dict.fromkeys(normalized))
        return [str(value).strip()] if str(value).strip() else []
