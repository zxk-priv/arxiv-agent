"""PDF 偏好分析缓存的 Markdown 读写。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from arxiv_agent.models import PdfPreferenceEntry, PreferenceProfile


def load_preference_profile(path: Path) -> PreferenceProfile | None:
    """从 Markdown 缓存中读取整体偏好画像。

    当前实现把“整体画像”和“单篇 PDF 分析条目”都存进同一份 Markdown：
    - front matter 负责承载结构化字段，便于程序恢复
    - body 负责承载可直接阅读的摘要，便于人查看
    """

    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise RuntimeError("偏好缓存缺少 YAML front matter。")

    end = content.find("\n---\n", 4)
    if end == -1:
        raise RuntimeError("偏好缓存 front matter 未正确关闭。")

    metadata_text = content[4:end]
    metadata = yaml.safe_load(metadata_text) or {}
    entries: list[PdfPreferenceEntry] = []
    for raw_item in metadata.get("entries", []) or []:
        entries.append(
            PdfPreferenceEntry(
                source_pdf=str(raw_item.get("source_pdf", "")),
                paper_title=str(raw_item.get("paper_title", "")),
                source_file_size=int(raw_item.get("source_file_size", 0) or 0),
                source_modified_at_utc=str(raw_item.get("source_modified_at_utc", "")),
                extracted_page_count=int(raw_item.get("extracted_page_count", 0) or 0),
                extracted_text_preview=str(raw_item.get("extracted_text_preview", "")),
                tech_fields=[str(item) for item in raw_item.get("tech_fields", []) or []],
                methods=[str(item) for item in raw_item.get("methods", []) or []],
                tasks=[str(item) for item in raw_item.get("tasks", []) or []],
                zh_summary=str(raw_item.get("zh_summary", "")),
                status=str(raw_item.get("status", "")),
                updated_at_utc=str(raw_item.get("updated_at_utc", "")),
                error_message=str(raw_item.get("error_message", "")),
            )
        )

    return PreferenceProfile(
        generated_at_utc=str(metadata.get("generated_at_utc", "")),
        source_pdf_count=int(metadata.get("source_pdf_count", 0) or 0),
        dominant_fields=[str(item) for item in metadata.get("dominant_fields", []) or []],
        method_keywords=[str(item) for item in metadata.get("method_keywords", []) or []],
        task_keywords=[str(item) for item in metadata.get("task_keywords", []) or []],
        research_focus_summary=str(metadata.get("research_focus_summary", "")),
        retrieval_query=str(metadata.get("retrieval_query", "")),
        entries=entries,
    )


def render_preference_markdown(profile: PreferenceProfile) -> str:
    """把整体偏好画像渲染成 Markdown 文本。"""

    metadata = {
        "generated_at_utc": profile.generated_at_utc,
        "source_pdf_count": profile.source_pdf_count,
        "ready_count": profile.ready_count,
        "failed_count": profile.failed_count,
        "dominant_fields": profile.dominant_fields,
        "method_keywords": profile.method_keywords,
        "task_keywords": profile.task_keywords,
        "research_focus_summary": profile.research_focus_summary,
        "retrieval_query": profile.retrieval_query,
        "entries": [asdict(entry) for entry in profile.entries],
    }

    lines = [
        "---",
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip(),
        "---",
        "",
        "# PDF 论文库偏好分析",
        "",
        f"- PDF 总数: {profile.source_pdf_count}",
        f"- 分析成功: {profile.ready_count}",
        f"- 分析失败: {profile.failed_count}",
        "",
        "## 最近研究方向",
        profile.research_focus_summary.strip(),
        "",
        "## 推荐检索查询",
        profile.retrieval_query.strip(),
        "",
        f"## 主导技术领域\n{', '.join(profile.dominant_fields) or '暂无'}",
        "",
        f"## 高频方法\n{', '.join(profile.method_keywords) or '暂无'}",
        "",
        f"## 高频任务\n{', '.join(profile.task_keywords) or '暂无'}",
        "",
    ]

    for entry in profile.entries:
        lines.extend(
            [
                f"## {entry.paper_title or entry.source_pdf}",
                f"- Source PDF: {entry.source_pdf}",
                f"- Status: {entry.status}",
                f"- Updated At (UTC): {entry.updated_at_utc}",
                f"- Tech Fields: {', '.join(entry.tech_fields) or '暂无'}",
                f"- Methods: {', '.join(entry.methods) or '暂无'}",
                f"- Tasks: {', '.join(entry.tasks) or '暂无'}",
                f"- Error: {entry.error_message}",
                "",
                "### 中文总结",
                entry.zh_summary.strip() or "暂无",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_preference_profile(path: Path, profile: PreferenceProfile) -> None:
    """把整体偏好画像写入 Markdown 缓存。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_preference_markdown(profile), encoding="utf-8")
