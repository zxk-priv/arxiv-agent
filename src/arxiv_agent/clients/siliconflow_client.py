"""SiliconFlow 客户端。

这里虽然接的是 SiliconFlow，但底层不手写 HTTP 请求，而是直接复用
`openai` 官方 Python SDK。原因是 SiliconFlow 提供的是 OpenAI 兼容接口：
- URL 结构兼容
- Chat Completions 请求格式兼容
- Embeddings 请求格式兼容

所以工程内部只要统一处理 prompt 和响应解析，就能把它当成一个标准的
OpenAI-compatible 模型服务使用。
"""

from __future__ import annotations

import yaml
from openai import OpenAI

from arxiv_agent.config import AppConfig, DEFAULT_BASE_URL


SUMMARY_SYSTEM_PROMPT = (
    "你是一个严谨的论文助手。请基于给定英文 abstract 生成简洁中文简介。"
    "要求：2到4句；忠于原文；优先说明研究任务、核心方法、主要结果或贡献；不要编造。"
)

PDF_PREFERENCE_SYSTEM_PROMPT = (
    "你是一个严谨的科研偏好分析助手。"
    "现在会给你一篇论文 PDF 前几页提取出的文本，请你概括该论文的中文标题、技术领域、核心方法、任务方向和简洁总结。"
    "必须只依据输入文本，不要编造。"
    "请严格输出 YAML，字段必须包含："
    "paper_title, tech_fields, methods, tasks, zh_summary。"
    "其中 tech_fields/methods/tasks 必须是字符串列表。"
)

PREFERENCE_PROFILE_SYSTEM_PROMPT = (
    "你是一个科研兴趣画像助手。"
    "现在会给你多篇论文的结构化总结，请归纳我最近主要研究的技术方向。"
    "请严格输出 YAML，字段必须包含："
    "dominant_fields, method_keywords, task_keywords, research_focus_summary, retrieval_query。"
    "其中前三个字段必须是字符串列表；"
    "research_focus_summary 用中文写 3 到 6 句；"
    "retrieval_query 用英文写成一段适合检索相关 arXiv 论文的查询文本。"
)


class SiliconFlowClient:
    """调用 SiliconFlow OpenAI 兼容接口完成工程中的各类文本分析任务。"""

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
        """基于标题和英文摘要生成简洁中文简介。"""

        return self._complete_text(
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            user_prompt=(
                f"论文标题：{title}\n\n"
                f"英文摘要：{abstract}\n\n"
                "请输出中文简介。"
            ),
            timeout=timeout,
        )

    def summarize_pdf_preference(
        self,
        *,
        source_pdf: str,
        extracted_text: str,
        timeout: int = 120,
    ) -> dict:
        """基于 PDF 前几页文本生成结构化偏好条目。"""

        content = self._complete_text(
            system_prompt=PDF_PREFERENCE_SYSTEM_PROMPT,
            user_prompt=(
                f"PDF 文件名：{source_pdf}\n\n"
                "以下是该论文 PDF 前几页提取出的文本，请基于这些内容进行总结：\n\n"
                f"{extracted_text}\n"
            ),
            timeout=timeout,
        )
        return self._parse_yaml_response(content, required_keys=[
            "paper_title",
            "tech_fields",
            "methods",
            "tasks",
            "zh_summary",
        ])

    def summarize_preference_profile(
        self,
        *,
        entry_summaries: str,
        timeout: int = 120,
    ) -> dict:
        """基于多篇 PDF 的结构化总结生成整体研究偏好画像。"""

        content = self._complete_text(
            system_prompt=PREFERENCE_PROFILE_SYSTEM_PROMPT,
            user_prompt=(
                "下面是多篇论文的结构化分析结果，请归纳整体研究偏好：\n\n"
                f"{entry_summaries}\n"
            ),
            timeout=timeout,
        )
        return self._parse_yaml_response(content, required_keys=[
            "dominant_fields",
            "method_keywords",
            "task_keywords",
            "research_focus_summary",
            "retrieval_query",
        ])

    def _complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        timeout: int,
    ) -> str:
        """执行一次通用 Chat Completions 调用并返回文本内容。"""

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=timeout,
        )

        if not response.choices:
            raise RuntimeError("模型响应中缺少 choices。")

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise RuntimeError("模型响应为空。")
        return content

    def _parse_yaml_response(self, content: str, required_keys: list[str]) -> dict:
        """解析模型返回的 YAML 文本，并校验必要字段。"""

        normalized_content = content.strip()
        if normalized_content.startswith("```"):
            normalized_lines = normalized_content.splitlines()
            if normalized_lines:
                normalized_lines = normalized_lines[1:]
            if normalized_lines and normalized_lines[-1].strip() == "```":
                normalized_lines = normalized_lines[:-1]
            normalized_content = "\n".join(normalized_lines).strip()

        parsed = yaml.safe_load(normalized_content)
        if not isinstance(parsed, dict):
            raise RuntimeError("模型未返回可解析的 YAML 字典。")

        missing_keys = [key for key in required_keys if key not in parsed]
        if missing_keys:
            raise RuntimeError(f"模型返回缺少必要字段: {', '.join(missing_keys)}")
        return parsed
