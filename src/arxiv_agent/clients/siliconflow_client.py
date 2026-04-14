"""SiliconFlow 客户端。

这里虽然接的是 SiliconFlow，但底层并不手写 HTTP 请求，而是直接复用
`openai` 官方 Python SDK。

原因是 SiliconFlow 提供了 OpenAI 兼容接口，只要把 `base_url` 指向
对应地址，就可以继续使用标准的 `chat.completions.create(...)` 调用方式。
"""

from __future__ import annotations

from openai import OpenAI

from arxiv_agent.config import AppConfig, DEFAULT_BASE_URL


SYSTEM_PROMPT = (
    "你是一个严谨的论文助手。请基于给定英文 abstract 生成简洁中文简介。"
    "要求：2到4句；忠于原文；优先说明研究任务、核心方法、主要结果或贡献；不要编造。"
)


class SiliconFlowClient:
    """调用 SiliconFlow OpenAI 兼容接口生成中文简介。

    注意：
    - 服务提供方仍然是 SiliconFlow
    - SDK 使用的是 `openai` Python 包
    - 两者能配合，是因为 SiliconFlow 暴露了兼容 OpenAI 的接口格式
    """

    def __init__(self, *, api_key: str, model: str, base_url: str = DEFAULT_BASE_URL) -> None:
        api_key = api_key.strip()
        model = model.strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY 未配置。")
        if not model:
            raise RuntimeError("SILICONFLOW_MODEL 未配置。")

        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
        )

    @classmethod
    def from_config(cls, config: AppConfig) -> "SiliconFlowClient":
        """从全局配置中创建客户端。"""

        return cls(
            api_key=config.siliconflow_api_key,
            model=config.siliconflow_model,
            base_url=config.siliconflow_base_url,
        )

    def summarize(self, *, title: str, abstract: str, timeout: int = 60) -> str:
        """基于标题和英文摘要生成简洁中文简介。

        这里仍然遵循典型的 Chat Completions 调用方式：
        - `system` 消息定义输出风格和约束
        - `user` 消息提供论文标题和英文摘要
        - `timeout` 限制单次请求等待时间，避免接口长时间卡住
        """

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"论文标题：{title}\n\n"
                        f"英文摘要：{abstract}\n\n"
                        "请输出中文简介。"
                    ),
                },
            ],
            timeout=timeout,
        )

        if not response.choices:
            raise RuntimeError("模型响应中缺少 choices。")

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise RuntimeError("模型响应为空。")
        return content
