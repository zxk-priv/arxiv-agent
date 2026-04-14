"""论文抓取与摘要生成的业务编排层。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from arxiv_agent.clients import ArxivClient, SiliconFlowClient, now_utc_iso
from arxiv_agent.config import AppConfig
from arxiv_agent.models import (
    DailyDigest,
    PaperEntry,
    SUMMARY_STATUS_FAILED,
    SUMMARY_STATUS_MISSING,
    SUMMARY_STATUS_READY,
)
from arxiv_agent.storage import load_digest, write_digest


MISSING_SUMMARIZER_CONFIG_ERROR = "未配置 SILICONFLOW_API_KEY 或 SILICONFLOW_MODEL。"


def digest_needs_abstract_refresh(digest: DailyDigest) -> bool:
    """判断当前缓存里是否还有缺失的英文摘要。"""

    return any(not paper.has_abstract for paper in digest.papers)


class DigestService:
    """负责组织项目的主流程。

    简单理解：
    - `clients` 只会“访问外部世界”
    - `storage` 只会“读写本地文件”
    - 本类负责决定“什么时候抓取、什么时候复用缓存、什么时候补摘要”
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def refresh_latest_digest(
        self,
        *,
        include_abstracts: bool,
        include_summaries: bool,
    ) -> DailyDigest:
        """抓取最新一天论文，并按需补全摘要和中文简介。"""

        with ArxivClient(timeout=self.config.request_timeout_seconds) as arxiv_client:
            scraped_digest = arxiv_client.fetch_latest_digest(self.config.listing_url)

        existing_digest = self._load_existing_digest(scraped_digest.date_slug)
        digest = self._merge_scraped_with_cache(scraped_digest, existing_digest)

        if include_abstracts:
            self._fetch_missing_abstracts(digest)

        self._fill_missing_summaries(
            digest,
            include_summaries=include_summaries,
            summarizer=self._build_config_summarizer() if include_summaries else None,
        )
        self._persist_digest(digest)
        return digest

    def ensure_latest_digest(self) -> DailyDigest:
        """保证“最新缓存”存在；不存在时自动抓取。"""

        digest = load_digest(self.config.latest_markdown_path)
        if digest is not None:
            return digest

        return self.refresh_latest_digest(
            include_abstracts=True,
            include_summaries=False,
        )

    def load_or_refresh_for_ui(self) -> DailyDigest:
        """页面启动时优先读缓存；如果摘要不完整，则自动补抓。"""

        digest = load_digest(self.config.latest_markdown_path)
        if digest is not None and not digest_needs_abstract_refresh(digest):
            return digest

        return self.refresh_latest_digest(
            include_abstracts=True,
            include_summaries=False,
        )

    def load_latest_digest_or_raise(self) -> DailyDigest:
        """严格读取最新缓存；不存在时直接报错。"""

        digest = load_digest(self.config.latest_markdown_path)
        if digest is None:
            raise RuntimeError(f"未找到缓存文件: {self.config.latest_markdown_path}")
        return digest

    def summarize_first_n_papers(
        self,
        *,
        api_key: str,
        model: str,
        limit: int,
    ) -> DailyDigest:
        """只为前 N 篇论文生成中文简介。

        这个方法适合两类场景：
        - 页面里按需只给前几篇论文生成简介
        - 验证外部模型接口是否正常时，只测试 1 篇论文，避免浪费 token
        """

        if limit <= 0:
            raise RuntimeError("前几篇论文的数量必须大于 0。")

        digest = self.ensure_latest_digest()
        selected_papers = digest.papers[:limit]
        self._fetch_missing_abstracts_for_papers(selected_papers)

        summarizer = SiliconFlowClient(
            api_key=api_key,
            model=model,
            base_url=self.config.siliconflow_base_url,
        )

        self._fill_missing_summaries(
            digest,
            include_summaries=True,
            summarizer=summarizer,
            limit=limit,
            only_selected_range=True,
        )
        self._persist_digest(digest)
        return digest

    def _load_existing_digest(self, date_slug: str) -> DailyDigest | None:
        """优先从归档缓存里读取同一天的数据，没有再看最新缓存。"""

        archive_digest = load_digest(self.config.archive_markdown_path(date_slug))
        if archive_digest and archive_digest.date_slug == date_slug:
            return archive_digest

        latest_digest = load_digest(self.config.latest_markdown_path)
        if latest_digest and latest_digest.date_slug == date_slug:
            return latest_digest

        return None

    def _merge_scraped_with_cache(
        self,
        scraped_digest: DailyDigest,
        existing_digest: DailyDigest | None,
    ) -> DailyDigest:
        """把最新抓取结果和已有缓存合并。

        这样做的目的是：列表结构以今天最新抓取为准，但已经抓好的 abstract
        和中文简介不需要每次都重新跑。
        """

        if existing_digest is None:
            return scraped_digest

        existing_by_id = {
            paper.arxiv_id: paper
            for paper in existing_digest.papers
        }
        merged_papers: list[PaperEntry] = []

        for paper in scraped_digest.papers:
            cached_paper = existing_by_id.get(paper.arxiv_id)
            if cached_paper is None:
                merged_papers.append(paper)
                continue

            merged_papers.append(
                replace(
                    paper,
                    english_abstract=cached_paper.english_abstract,
                    zh_summary=cached_paper.zh_summary,
                    summary_status=(
                        SUMMARY_STATUS_READY
                        if cached_paper.has_summary
                        else cached_paper.summary_status
                    ),
                    updated_at_utc=cached_paper.updated_at_utc,
                    error_message=cached_paper.error_message,
                )
            )

        return DailyDigest(
            source_url=scraped_digest.source_url,
            heading=scraped_digest.heading,
            date_slug=scraped_digest.date_slug,
            fetched_at_utc=scraped_digest.fetched_at_utc,
            papers=merged_papers,
        )

    def _fetch_missing_abstracts(self, digest: DailyDigest) -> None:
        """并发补全缺失的英文摘要。"""

        self._fetch_missing_abstracts_for_papers(digest.papers)

    def _fetch_missing_abstracts_for_papers(self, papers: list[PaperEntry]) -> None:
        """只为给定论文集合补全缺失的英文摘要。

        这个辅助方法是为了避免“只想处理 1 篇论文时，却顺手把全量摘要都抓一遍”。
        对页面整页刷新来说，传入全量论文即可；对单篇验证 API 的场景，则只传入
        需要验证的那几篇论文。
        """

        missing_papers = [paper for paper in papers if not paper.has_abstract]
        if not missing_papers:
            return

        max_workers = min(8, len(missing_papers))
        paper_index = {paper.arxiv_id: paper for paper in papers}

        def worker(paper: PaperEntry) -> tuple[str, str | None, str | None]:
            with ArxivClient(timeout=self.config.request_timeout_seconds) as arxiv_client:
                try:
                    abstract = arxiv_client.fetch_english_abstract(paper)
                    return paper.arxiv_id, abstract, None
                except Exception as exc:
                    return paper.arxiv_id, None, str(exc)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(worker, paper): paper.arxiv_id
                for paper in missing_papers
            }

            for future in as_completed(future_map):
                arxiv_id, abstract, error_message = future.result()
                paper = paper_index[arxiv_id]
                paper.updated_at_utc = now_utc_iso()

                if abstract:
                    paper.english_abstract = abstract
                    paper.error_message = ""
                    paper.summary_status = (
                        SUMMARY_STATUS_READY if paper.has_summary else SUMMARY_STATUS_MISSING
                    )
                    continue

                paper.summary_status = SUMMARY_STATUS_FAILED
                paper.error_message = error_message or "摘要抓取失败。"

    def _build_config_summarizer(self) -> SiliconFlowClient | None:
        """根据全局配置创建摘要客户端；配置不完整时返回 `None`。"""

        if not self.config.summarize_enabled:
            return None
        return SiliconFlowClient.from_config(self.config)

    def _fill_missing_summaries(
        self,
        digest: DailyDigest,
        *,
        include_summaries: bool,
        summarizer: SiliconFlowClient | None,
        limit: int | None = None,
        only_selected_range: bool = False,
    ) -> None:
        """按规则填充中文简介状态。

        参数说明：
        - `include_summaries=False` 时，只整理状态，不会真正调用模型。
        - `limit` 用于“只处理前 N 篇论文”。
        - `only_selected_range=True` 时，只修改前 N 篇论文，后面的论文保持原样。
        """

        selected_papers = digest.papers if limit is None else digest.papers[:limit]
        if not selected_papers:
            return

        missing_api_config = include_summaries and summarizer is None

        for paper in selected_papers:
            if paper.has_summary:
                paper.summary_status = SUMMARY_STATUS_READY
                paper.error_message = ""
                continue

            if not include_summaries:
                if paper.error_message == MISSING_SUMMARIZER_CONFIG_ERROR:
                    paper.error_message = ""
                if not paper.has_abstract and not only_selected_range:
                    paper.summary_status = SUMMARY_STATUS_MISSING
                continue

            if missing_api_config:
                paper.summary_status = SUMMARY_STATUS_MISSING
                paper.error_message = MISSING_SUMMARIZER_CONFIG_ERROR
                continue

            if not paper.has_abstract:
                paper.summary_status = SUMMARY_STATUS_FAILED
                paper.error_message = "缺少英文摘要，无法生成中文简介。"
                paper.updated_at_utc = now_utc_iso()
                continue

            try:
                assert summarizer is not None
                paper.zh_summary = summarizer.summarize(
                    title=paper.title,
                    abstract=paper.english_abstract,
                )
                paper.summary_status = SUMMARY_STATUS_READY
                paper.error_message = ""
                paper.updated_at_utc = now_utc_iso()
            except Exception as exc:
                paper.summary_status = SUMMARY_STATUS_FAILED
                paper.error_message = str(exc)
                paper.updated_at_utc = now_utc_iso()

        if only_selected_range:
            return

        for paper in digest.papers[len(selected_papers) :]:
            if paper.has_summary:
                paper.summary_status = SUMMARY_STATUS_READY

    def _persist_digest(self, digest: DailyDigest) -> None:
        """同时写回“最新缓存”和“日期归档缓存”。"""

        write_digest(self.config.latest_markdown_path, digest)
        write_digest(self.config.archive_markdown_path(digest.date_slug), digest)
