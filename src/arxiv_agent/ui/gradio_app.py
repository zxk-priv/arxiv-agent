"""Gradio 页面组装。"""

from __future__ import annotations

import gradio as gr

from arxiv_agent.config import AppConfig
from arxiv_agent.models import DailyDigest
from arxiv_agent.services import DigestService

from .renderers import render_digest_html


def create_blocks(
    config: AppConfig,
    digest_service: DigestService | None = None,
) -> gr.Blocks:
    """创建 Gradio 页面。

    UI 层只关心页面交互，不直接拼装底层抓取逻辑。真正的数据刷新和摘要生成
    都委托给 `DigestService`。
    """

    service = digest_service or DigestService(config)
    initial_digest = service.load_or_refresh_for_ui()

    with gr.Blocks(title="arXiv cs.CV 最新论文卡片流") as demo:
        digest_state = gr.State(initial_digest)

        gr.Markdown("# arXiv cs.CV 最新论文卡片流")
        gr.Markdown(
            "你可以先更新今天最新论文的英文摘要，也可以输入 SiliconFlow API Key、模型名称和前 N 篇数量，为前几篇论文生成中文简介。页面每次都会从本地 Markdown 重新加载。"
        )

        with gr.Row():
            api_key_text = gr.Textbox(
                label="SiliconFlow API Key",
                type="password",
                placeholder="请输入 SiliconFlow API Key",
                value=config.siliconflow_api_key,
            )
            model_text = gr.Textbox(
                label="模型名称",
                placeholder="请输入要使用的模型名称",
                value=config.siliconflow_model,
            )
            paper_count_number = gr.Number(
                label="为前几篇论文生成简介",
                value=5,
                minimum=1,
                precision=0,
            )

        with gr.Row():
            refresh_button = gr.Button("更新今天的最新论文并补全 Abstract", variant="primary")
            summarize_button = gr.Button("AI 总结简介", variant="secondary")

        status_markdown = gr.Markdown(
            value="页面已加载；如果本地缓存缺少英文摘要，启动时会自动补抓。"
        )
        cards_html = gr.HTML(value=render_digest_html(initial_digest))

        def refresh_view(current_digest: DailyDigest | None):
            del current_digest
            digest = service.refresh_latest_digest(
                include_abstracts=True,
                include_summaries=False,
            )
            message = (
                f"已刷新：{digest.heading}，共 {len(digest.papers)} 篇。"
                f" 当前 ready={digest.ready_count}，missing={digest.missing_count}，failed={digest.failed_count}。"
                f" abstract 已写入 {config.latest_markdown_path}，页面已从 Markdown 重新加载。"
            )
            return digest, message, render_digest_html(digest)

        def summarize_view(
            current_digest: DailyDigest | None,
            api_key: str,
            model: str,
            paper_count: float,
        ):
            del current_digest
            digest = service.summarize_first_n_papers(
                api_key=api_key,
                model=model,
                limit=max(1, int(paper_count)),
            )
            message = (
                f"已为前 {min(max(1, int(paper_count)), len(digest.papers))} 篇论文生成中文简介。"
                f" 当前 ready={digest.ready_count}，missing={digest.missing_count}，failed={digest.failed_count}。"
                f" 中文简介已写入 {config.latest_markdown_path}，页面已从 Markdown 重新加载。"
            )
            return digest, message, render_digest_html(digest)

        refresh_button.click(
            fn=refresh_view,
            inputs=[digest_state],
            outputs=[digest_state, status_markdown, cards_html],
        )

        summarize_button.click(
            fn=summarize_view,
            inputs=[digest_state, api_key_text, model_text, paper_count_number],
            outputs=[digest_state, status_markdown, cards_html],
        )

    return demo
