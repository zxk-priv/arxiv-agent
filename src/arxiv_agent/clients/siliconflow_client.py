"""SiliconFlow 客户端。"""

from __future__ import annotations

import requests

from arxiv_agent.config import AppConfig, DEFAULT_BASE_URL


SYSTEM_PROMPT = (
    "你是一个严谨的论文助手。请基于给定英文 abstract 生成简洁中文简介。"
    "要求：2到4句；忠于原文；优先说明研究任务、核心方法、主要结果或贡献；不要编造。"
)


class SiliconFlowClient:
    """调用 SiliconFlow OpenAI 兼容接口生成中文简介。"""

    def __init__(self, *, api_key: str, model: str, base_url: str = DEFAULT_BASE_URL) -> None:
        api_key = api_key.strip()
        model = model.strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY 未配置。")
        if not model:
            raise RuntimeError("SILICONFLOW_MODEL 未配置。")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_config(cls, config: AppConfig) -> "SiliconFlowClient":
        """从全局配置中创建客户端。"""

        return cls(
            api_key=config.siliconflow_api_key,
            model=config.siliconflow_model,
            base_url=config.siliconflow_base_url,
        )

    def summarize(self, *, title: str, abstract: str, timeout: int = 60) -> str:
        """基于标题和英文摘要生成简洁中文简介。"""

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
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
        }
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("模型响应中缺少 choices。")

        message = choices[0].get("message") or {}
        content = message.get("content", "").strip()
        if not content:
            raise RuntimeError("模型响应为空。")
        return content
