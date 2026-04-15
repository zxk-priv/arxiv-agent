"""基于 LangChain 的本地论文检索服务。

这个模块负责 RAG 中最靠近“检索”本身的部分，职责可以分成两段：

1. 建索引
   - 从当天已经落盘的 Markdown 缓存中拿到论文列表
   - 把每篇论文转换成 LangChain `Document`
   - 用 embedding 模型把这些文档向量化
   - 交给 FAISS 建立向量索引

2. 执行检索
   - 把用户查询也做 embedding
   - 从 FAISS 中找一批最相近的候选
   - 再叠加一个“轻量关键词匹配分数”做混合排序
   - 返回最终排序后的 arXiv id 列表

注意：
- 这里没有实现真正的 BM25。
- 当前所谓“混合检索”，是“向量检索 + 手工关键词打分”的混合。
- 这样做的原因是实现简单、依赖少，同时对短查询词和专有词更稳。
"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from arxiv_agent.clients import SiliconFlowEmbeddings
from arxiv_agent.config import AppConfig
from arxiv_agent.models import DailyDigest, PaperEntry


TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


class RagService:
    """负责基于当天缓存论文建立向量索引并执行混合检索。

    这里的服务只关心“检索”：
    - 不负责抓论文
    - 不负责读写 Markdown
    - 不负责生成中文简介

    它的输入是 `DailyDigest`，输出是“按相关性排序的 arXiv id 列表”。
    后续要不要为这些论文生成中文简介，由 `DigestService` 再接着处理。
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._documents_by_id: dict[str, Document] = {}
        self._vectorstore: FAISS | None = None
        self._indexed_date_slug = ""
        self._embeddings = (
            SiliconFlowEmbeddings.from_config(config)
            if config.rag_enabled
            else None
        )

    @property
    def is_configured(self) -> bool:
        """当前是否已具备构建向量索引所需的 embedding 配置。"""

        return self._embeddings is not None

    def build_index(self, digest: DailyDigest) -> None:
        """基于最新 digest 全量重建当天索引。

        当前实现选择“全量重建”，而不是增量更新，原因是：
        - 每天论文量级只有几百篇
        - 重建逻辑更简单，状态更不容易乱
        - 刷新当天论文后，直接全量重建能保证索引和缓存完全一致

        建索引步骤：
        1. 把每篇论文转成 `Document`
        2. 对所有文档调用 embedding
        3. 用 FAISS.from_documents(...) 建立内存索引
        4. 把索引保存到本地目录，便于观察和调试
        """

        if self._embeddings is None:
            self._vectorstore = None
            self._documents_by_id = {}
            self._indexed_date_slug = ""
            return

        documents = [self._paper_to_document(paper) for paper in digest.papers]
        self._documents_by_id = {
            document.metadata["arxiv_id"]: document
            for document in documents
        }
        self._vectorstore = FAISS.from_documents(documents, self._embeddings)
        self._indexed_date_slug = digest.date_slug
        self._persist_index(digest.date_slug)

    def search_paper_ids(self, query: str, *, top_k: int | None = None) -> list[str]:
        """执行混合检索，返回按相关性排序的论文编号列表。

        当前检索流程不是“先 BM25 再向量检索”，而是：

        1. 先做向量检索
           - 用 query 的 embedding 去 FAISS 找最近邻
           - 候选数量不是最终结果数，而是 `top_k * 4`
           - 这样做是为了给后续 rerank 留足够候选

        2. 再做关键词打分
           - 对所有文档做一次轻量字符串匹配
           - 标题命中加分更高，摘要命中加分更低

        3. 最后做混合排序
           - `total_score = vector_score * 10 + keyword_score`
           - 然后取最终前 `top_k`

        默认 `top_k` 取配置里的 `rag_top_k`，目前是 20。
        所以当前默认行为是：
        - 向量阶段先拿最多 80 个候选
        - 混排后最终返回前 20 个结果
        """

        normalized_query = query.strip()
        if not normalized_query:
            return []
        if self._vectorstore is None:
            raise RuntimeError("RAG 索引尚未构建。")

        result_limit = max(1, top_k or self.config.rag_top_k)
        # 这里故意把向量候选数放大到最终展示数的 4 倍。
        # 目的不是多展示，而是给后续关键词 rerank 留空间：
        # 有些论文语义相近但专有词命中弱，有些论文相反；
        # 如果向量阶段只拿前 20，混排空间会太小。
        vector_candidate_limit = min(
            len(self._documents_by_id),
            max(result_limit * 4, result_limit),
        )

        vector_scores = self._search_vector_scores(
            normalized_query,
            candidate_limit=vector_candidate_limit,
        )
        keyword_scores = {
            arxiv_id: self._keyword_score(normalized_query, document)
            for arxiv_id, document in self._documents_by_id.items()
        }
        candidate_ids = set(vector_scores) | {
            arxiv_id
            for arxiv_id, keyword_score in keyword_scores.items()
            if keyword_score > 0
        }
        if not candidate_ids:
            return []

        # 排序元组里同时保留 total / keyword / vector 三个值，
        # 是为了在 total_score 相同时，让 Python 的元组排序继续按照
        # keyword_score、vector_score 再往下比较，得到稳定顺序。
        scored_ids: list[tuple[float, float, float, str]] = []
        for arxiv_id in candidate_ids:
            vector_score = vector_scores.get(arxiv_id, 0.0)
            keyword_score = keyword_scores.get(arxiv_id, 0.0)
            total_score = vector_score * 10 + keyword_score
            if total_score <= 0:
                continue
            scored_ids.append((total_score, keyword_score, vector_score, arxiv_id))

        scored_ids.sort(reverse=True)
        return [arxiv_id for _, _, _, arxiv_id in scored_ids[:result_limit]]

    def _paper_to_document(self, paper: PaperEntry) -> Document:
        """把论文对象转换成 LangChain 文档。

        为什么把“标题 + 英文摘要”拼成一个 `page_content`：
        - 标题通常高度浓缩任务关键词
        - 摘要提供更完整的语义上下文
        - 两者拼起来做 embedding，通常比只嵌入标题更稳

        `metadata` 里保留链接和 arXiv id，
        这样检索阶段只需要返回 id，后续 UI 就能从 digest 中恢复完整论文对象。
        """

        search_text = "\n".join(
            [
                f"Title: {paper.title}",
                f"Abstract: {paper.english_abstract.strip() or 'No abstract available.'}",
            ]
        )
        return Document(
            page_content=search_text,
            metadata={
                "arxiv_id": paper.arxiv_id,
                "title": paper.title,
                "pdf_url": paper.pdf_url,
                "html_url": paper.html_url,
                "abs_url": paper.abs_url,
            },
        )

    def _search_vector_scores(
        self,
        query: str,
        *,
        candidate_limit: int,
    ) -> dict[str, float]:
        """从 FAISS 中取一批向量候选，并转换成可混合排序的分数。

        `similarity_search_with_score(...)` 返回的是“文档 + 距离”。
        这里没有直接把原始距离拿去和关键词分数相加，而是先做了两层归一化：

        1. `distance_score`
           - 通过 `1 / (1 + distance)` 映射到 0~1 左右的范围
           - 距离越小，分数越高

        2. `rank_score`
           - 借助候选中的排序名次补一个稳定分
           - 防止距离分布特别接近时，排序太敏感

        最终：
        - 70% 看距离
        - 30% 看名次

        这仍然是启发式打分，不是严格概率分数。
        它的目标只是给混排提供一个稳定、可比较的向量相关性量纲。
        """

        if self._vectorstore is None:
            return {}

        results = self._vectorstore.similarity_search_with_score(query, k=candidate_limit)
        scores: dict[str, float] = {}

        for rank, (document, distance) in enumerate(results):
            arxiv_id = str(document.metadata["arxiv_id"])
            rank_score = 1.0 - (rank / max(candidate_limit, 1))
            distance_score = 1.0 / (1.0 + max(float(distance), 0.0))
            scores[arxiv_id] = max(
                scores.get(arxiv_id, 0.0),
                distance_score * 0.7 + rank_score * 0.3,
            )

        return scores

    def _keyword_score(self, query: str, document: Document) -> float:
        """对标题和摘要做轻量关键词匹配打分。

        这里不是 BM25，而是很直接的启发式规则：
        - 整个 query 完整出现在标题里：+12
        - 整个 query 完整出现在摘要里：+5
        - query 拆词后，单个 token 在标题里命中：每个 +3
        - query 拆词后，单个 token 在摘要里命中：每个 +1

        这种规则的好处：
        - 实现非常简单
        - 对短语、缩写、专有名词会比较直接
        - 能弥补纯向量检索有时对字面命中不够敏感的问题

        局限也很明确：
        - 没有词频、逆文档频率这些 BM25 的统计信息
        - 没有做 stemming、停用词处理
        - 多语言和复杂 query 支持一般
        """

        title_text = str(document.metadata.get("title", "")).lower()
        abstract_text = document.page_content.lower()
        normalized_query = query.lower()
        tokens = list(dict.fromkeys(TOKEN_PATTERN.findall(normalized_query)))

        score = 0.0
        if normalized_query in title_text:
            score += 12.0
        if normalized_query in abstract_text:
            score += 5.0

        for token in tokens:
            if len(token) < 2:
                continue
            if token in title_text:
                score += 3.0
            if token in abstract_text:
                score += 1.0

        return score

    def _persist_index(self, date_slug: str) -> None:
        """把当天索引持久化到本地目录。

        当前页面每次启动仍然会重新构建内存索引，
        所以这里的本地落盘更偏向“缓存和调试资产”，
        不是严格依赖它来恢复运行状态。
        """

        if self._vectorstore is None:
            return

        index_dir = self._index_dir(date_slug)
        index_dir.mkdir(parents=True, exist_ok=True)
        self._vectorstore.save_local(str(index_dir))

    def _index_dir(self, date_slug: str) -> Path:
        """返回指定日期的索引缓存目录。"""

        return self.config.rag_vector_cache_dir / date_slug
