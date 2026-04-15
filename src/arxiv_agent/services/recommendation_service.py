"""统一编排关键词模式与偏好模式的推荐工作流。"""

from __future__ import annotations

from collections.abc import Iterator

from arxiv_agent.clients import now_utc_iso
from arxiv_agent.config import AppConfig
from arxiv_agent.models import (
    DailyDigest,
    PreferenceProfile,
    ProgressEvent,
    RecommendationItem,
    RecommendationResult,
    RECOMMENDATION_MODE_KEYWORD,
    RECOMMENDATION_MODE_PREFERENCE,
    WorkflowSnapshot,
)
from arxiv_agent.services.digest_service import DigestService
from arxiv_agent.services.preference_service import PreferenceService
from arxiv_agent.services.rag_service import RagService
from arxiv_agent.storage import write_recommendation_result


class RecommendationService:
    """对外提供两种推荐模式的统一工作流。

    这个服务做的是“编排”，而不是具体算法：
    - `DigestService` 负责当天论文抓取和中文总结
    - `PreferenceService` 负责 PDF 偏好分析
    - `RagService` 负责当天论文检索

    它把上面几段串成一条可观察、可落盘、可在 CLI 和 Gradio 复用的完整流程。
    """

    def __init__(
        self,
        config: AppConfig,
        *,
        digest_service: DigestService | None = None,
        rag_service: RagService | None = None,
        preference_service: PreferenceService | None = None,
    ) -> None:
        self.config = config
        self.digest_service = digest_service or DigestService(config)
        self.rag_service = rag_service or RagService(config)
        self.preference_service = preference_service or PreferenceService(config)

    def run_keyword_workflow(self, query: str) -> Iterator[WorkflowSnapshot]:
        """执行关键词模式推荐流程，并在每个阶段产出快照。"""

        mode = RECOMMENDATION_MODE_KEYWORD
        logs: list[ProgressEvent] = []
        digest: DailyDigest | None = None
        result: RecommendationResult | None = None

        yield self._snapshot(mode, "准备环境", logs, digest=digest, result=result)
        self._log(logs, "检查当天论文缓存", "开始检查今天的最新论文缓存。")
        digest = self.digest_service.ensure_today_digest()
        yield self._snapshot(mode, "读取/刷新最新一天论文", logs, digest=digest, result=result)

        self._log(logs, "构建 / 刷新当天论文索引", "开始构建当天论文向量索引。")
        self.rag_service.build_index(digest)
        yield self._snapshot(mode, "构建 / 刷新当天论文索引", logs, digest=digest, result=result)

        normalized_query = query.strip()
        self._log(logs, "检索当天论文", f"开始按关键词检索：{normalized_query}")
        matched_ids = self.rag_service.search_paper_ids(normalized_query, top_k=self.config.rag_top_k)
        yield self._snapshot(mode, "检索当天论文", logs, digest=digest, result=result)

        self._log(logs, "生成命中论文中文总结", f"命中 {len(matched_ids)} 篇论文，开始补中文总结。")
        digest, matched_papers, _generated_count = self.digest_service.summarize_papers_by_ids(
            api_key=self.config.siliconflow_api_key,
            model=self.config.siliconflow_model,
            arxiv_ids=matched_ids,
        )
        result = self._build_result(
            mode=mode,
            digest=digest,
            papers=matched_papers,
            query=normalized_query,
            preference_focus_summary="",
        )
        yield self._snapshot(mode, "生成命中论文中文总结", logs, digest=digest, result=result)

        self._log(logs, "写入结果 Markdown", "开始写入关键词模式最终推荐结果。")
        write_recommendation_result(self.config.keyword_result_path, result)
        yield self._snapshot(mode, "完成", logs, digest=digest, result=result)

    def run_preference_workflow(self) -> Iterator[WorkflowSnapshot]:
        """执行论文库偏好模式推荐流程，并在每个阶段产出快照。"""

        mode = RECOMMENDATION_MODE_PREFERENCE
        logs: list[ProgressEvent] = []
        digest: DailyDigest | None = None
        profile: PreferenceProfile | None = None
        result: RecommendationResult | None = None

        yield self._snapshot(mode, "准备环境", logs, digest=digest, profile=profile, result=result)
        self._log(logs, "扫描 paper_datasets", "开始基于本地 PDF 论文库构建偏好画像。")
        profile = self.preference_service.build_or_refresh_profile(
            progress_callback=lambda stage, message: self._log(logs, stage, message),
        )
        yield self._snapshot(mode, "汇总整体研究偏好", logs, digest=digest, profile=profile, result=result)

        self._log(logs, "检查当天论文缓存", "开始检查今天的最新论文缓存。")
        digest = self.digest_service.ensure_today_digest()
        yield self._snapshot(mode, "读取/刷新最新一天论文", logs, digest=digest, profile=profile, result=result)

        self._log(logs, "构建 / 刷新当天论文索引", "开始构建当天论文向量索引。")
        self.rag_service.build_index(digest)
        yield self._snapshot(mode, "构建 / 刷新当天论文索引", logs, digest=digest, profile=profile, result=result)

        preference_query = profile.retrieval_query.strip()
        self._log(logs, "构造偏好检索查询", preference_query or "偏好画像未生成有效检索查询。")
        yield self._snapshot(mode, "构造偏好检索查询", logs, digest=digest, profile=profile, result=result)

        matched_ids = []
        if preference_query:
            self._log(logs, "检索当天论文", "开始按偏好画像检索当天论文。")
            matched_ids = self.rag_service.search_paper_ids(preference_query, top_k=self.config.rag_top_k)
        else:
            self._log(logs, "检索当天论文", "偏好画像缺少检索查询，跳过检索。")
        yield self._snapshot(mode, "检索当天论文", logs, digest=digest, profile=profile, result=result)

        self._log(logs, "生成命中论文中文总结", f"命中 {len(matched_ids)} 篇论文，开始补中文总结。")
        digest, matched_papers, _generated_count = self.digest_service.summarize_papers_by_ids(
            api_key=self.config.siliconflow_api_key,
            model=self.config.siliconflow_model,
            arxiv_ids=matched_ids,
        )
        result = self._build_result(
            mode=mode,
            digest=digest,
            papers=matched_papers,
            query=preference_query,
            preference_focus_summary=profile.research_focus_summary if profile else "",
        )
        yield self._snapshot(mode, "生成命中论文中文总结", logs, digest=digest, profile=profile, result=result)

        self._log(logs, "写入结果 Markdown", "开始写入偏好模式最终推荐结果。")
        write_recommendation_result(self.config.preference_result_path, result)
        yield self._snapshot(mode, "完成", logs, digest=digest, profile=profile, result=result)

    def _build_result(
        self,
        *,
        mode: str,
        digest: DailyDigest,
        papers: list,
        query: str,
        preference_focus_summary: str,
    ) -> RecommendationResult:
        """把命中的论文集合转换成最终推荐结果对象。"""

        items = [
            RecommendationItem(
                arxiv_id=paper.arxiv_id,
                title=paper.title,
                pdf_url=paper.pdf_url,
                html_url=paper.html_url,
                abs_url=paper.abs_url,
                english_abstract=paper.english_abstract,
                zh_summary=paper.zh_summary,
            )
            for paper in papers
        ]
        return RecommendationResult(
            mode=mode,
            generated_at_utc=now_utc_iso(),
            source_digest_date_slug=digest.date_slug,
            source_digest_heading=digest.heading,
            query=query,
            preference_focus_summary=preference_focus_summary,
            items=items,
        )

    def _log(self, logs: list[ProgressEvent], stage: str, message: str) -> None:
        """向工作流日志中追加一条进度事件。"""

        logs.append(
            ProgressEvent(
                stage=stage,
                message=message,
                created_at_utc=now_utc_iso(),
            )
        )

    def _snapshot(
        self,
        mode: str,
        current_stage: str,
        logs: list[ProgressEvent],
        *,
        digest: DailyDigest | None = None,
        profile: PreferenceProfile | None = None,
        result: RecommendationResult | None = None,
    ) -> WorkflowSnapshot:
        """生成当前阶段的工作流快照。"""

        return WorkflowSnapshot(
            mode=mode,
            current_stage=current_stage,
            logs=list(logs),
            digest=digest,
            profile=profile,
            result=result,
        )
