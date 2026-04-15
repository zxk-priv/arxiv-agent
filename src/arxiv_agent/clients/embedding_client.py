"""SiliconFlow embedding 客户端。

这个类的作用是把 SiliconFlow 的 OpenAI 兼容 embeddings 接口，
包装成 LangChain 认识的 `Embeddings` 对象。

这样做以后，`FAISS.from_documents(...)` 和后续查询时的向量化，
就都可以直接复用 LangChain 的接口约定，不需要在 RAG 服务里手写
“批量调 embedding 接口、再把结果塞给向量库”的样板代码。
"""

from __future__ import annotations

from openai import OpenAI
from langchain_core.embeddings import Embeddings

from arxiv_agent.config import AppConfig, DEFAULT_BASE_URL


class SiliconFlowEmbeddings(Embeddings):
    """通过 SiliconFlow 的 OpenAI 兼容 embeddings 接口生成向量。

    这里虽然服务端是 SiliconFlow，但客户端继续使用 `openai` Python SDK。
    原因是 SiliconFlow 暴露的是 OpenAI 兼容协议：
    - 路径兼容
    - 请求体结构兼容
    - 响应结构兼容

    所以只要把 `base_url` 指向 SiliconFlow，就能用同一套 SDK。
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        batch_size: int = 32,
    ) -> None:
        api_key = api_key.strip()
        model = model.strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY 未配置。")
        if not model:
            raise RuntimeError("SILICONFLOW_EMBEDDING_MODEL 未配置。")

        self.model = model
        self.batch_size = max(1, batch_size)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )

    @classmethod
    def from_config(cls, config: AppConfig) -> "SiliconFlowEmbeddings":
        """从全局配置创建 embedding 客户端。"""

        return cls(
            api_key=config.siliconflow_api_key,
            model=config.siliconflow_embedding_model,
            base_url=config.siliconflow_base_url,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量。

        LangChain 在建索引时会调用这个方法。

        这里做了分批：
        - 不是因为 LangChain 要求
        - 而是为了避免一次请求塞太多文本，导致请求体过大或响应过慢

        返回顺序必须和输入文本顺序一致，
        所以我们显式按照 `response.data[*].index` 重新排序。
        """

        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            ordered_items = sorted(response.data, key=lambda item: item.index)
            if len(ordered_items) != len(batch):
                raise RuntimeError("embedding 响应数量与请求数量不一致。")
            vectors.extend(item.embedding for item in ordered_items)

        return vectors

    def embed_query(self, text: str) -> list[float]:
        """为单条查询生成向量。

        检索时 LangChain / FAISS 会调用这个方法。
        文档和查询必须使用同一个 embedding 模型，向量空间才可比。
        """

        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        if not response.data:
            raise RuntimeError("embedding 响应为空。")
        return response.data[0].embedding
