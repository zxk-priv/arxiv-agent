"""Gradio 页面组装。"""

from __future__ import annotations

import gradio as gr

from arxiv_agent.config import AppConfig
from arxiv_agent.models import (
    RECOMMENDATION_MODE_KEYWORD,
    RECOMMENDATION_MODE_PREFERENCE,
    WorkflowSnapshot,
)
from arxiv_agent.services import DigestService, PreferenceService, RecommendationService
from arxiv_agent.storage import load_preference_profile

from .renderers import render_progress_markdown, render_workspace_html


def _search_disabled_reason(config: AppConfig) -> str:
    """给出搜索被禁用时的原因说明。"""

    missing_items: list[str] = []
    if not config.siliconflow_api_key:
        missing_items.append("`SILICONFLOW_API_KEY`")
    if not config.siliconflow_model:
        missing_items.append("`SILICONFLOW_MODEL`")
    if not config.siliconflow_embedding_model:
        missing_items.append("`SILICONFLOW_EMBEDDING_MODEL`")

    if not missing_items:
        return ""

    return (
        "当前未配置完整的检索、偏好分析与总结模型，开始检索按钮已禁用。"
        f" 缺少配置项: {', '.join(missing_items)}。"
    )


def create_blocks(
    config: AppConfig,
    digest_service: DigestService | None = None,
) -> gr.Blocks:
    """创建双模式推荐页面。

    页面会把“UI 状态”和“后台工作流”分开：
    - 后台流程由 `RecommendationService` 统一编排
    - 页面只负责把工作流快照渲染出来
    """

    service = digest_service or DigestService(config)
    preference_service = PreferenceService(config)
    recommendation_service = RecommendationService(
        config,
        digest_service=service,
        preference_service=preference_service,
    )
    initial_digest = service.ensure_today_digest()
    initial_profile = load_preference_profile(config.preference_profile_path)
    search_enabled = config.rag_enabled
    disabled_reason = _search_disabled_reason(config)
    initial_mode = RECOMMENDATION_MODE_KEYWORD
    initial_stage, initial_logs = render_progress_markdown("准备环境", [])

    with gr.Blocks(title="arXiv 双模式论文推荐") as demo:
        gr.Markdown("# arXiv 双模式论文推荐工作台")
        gr.Markdown(
            "你可以在“关键词模式”和“论文库偏好模式”之间切换。页面会优先复用本地缓存，并在执行过程中显示详细阶段日志。"
        )

        mode_radio = gr.Radio(
            choices=[
                ("关键词模式", RECOMMENDATION_MODE_KEYWORD),
                ("论文库偏好模式", RECOMMENDATION_MODE_PREFERENCE),
            ],
            value=initial_mode,
            label="推荐模式",
        )

        keyword_text = gr.Textbox(
            label="关键词输入",
            placeholder="例如: feature matching, embodied agents, GUI agents",
            lines=1,
            visible=True,
        )

        with gr.Row():
            start_button = gr.Button(
                "开始检索",
                variant="primary",
                interactive=search_enabled,
            )
            refresh_button = gr.Button(
                "刷新今天论文缓存",
                variant="secondary",
            )

        current_stage_markdown = gr.Markdown(value=initial_stage)
        progress_logs_markdown = gr.Markdown(value=initial_logs)
        result_html = gr.HTML(
            value=render_workspace_html(
                mode=initial_mode,
                digest=initial_digest,
                profile=initial_profile,
                result=None,
                search_enabled=search_enabled,
                disabled_reason=disabled_reason,
            )
        )

        def on_mode_change(mode: str):
            show_keyword = mode == RECOMMENDATION_MODE_KEYWORD
            stage_md, logs_md = render_progress_markdown("准备环境", [])
            return (
                gr.update(visible=show_keyword),
                stage_md,
                logs_md,
                render_workspace_html(
                    mode=mode,
                    digest=service.ensure_today_digest(),
                    profile=load_preference_profile(config.preference_profile_path),
                    result=None,
                    search_enabled=search_enabled,
                    disabled_reason=disabled_reason,
                ),
            )

        def refresh_digest_view(mode: str):
            digest = service.refresh_latest_digest(
                include_abstracts=True,
                include_summaries=False,
            )
            profile = load_preference_profile(config.preference_profile_path)
            stage_md, logs_md = render_progress_markdown(
                "读取/刷新最新一天论文",
                [],
            )
            return (
                stage_md,
                logs_md,
                render_workspace_html(
                    mode=mode,
                    digest=digest,
                    profile=profile,
                    result=None,
                    search_enabled=search_enabled,
                    disabled_reason=disabled_reason,
                ),
            )

        def run_workflow(mode: str, query: str):
            if not search_enabled:
                stage_md, logs_md = render_progress_markdown("准备环境", [])
                yield (
                    stage_md,
                    f"**阶段日志**\n\n- {disabled_reason}",
                    render_workspace_html(
                        mode=mode,
                        digest=service.ensure_today_digest(),
                        profile=load_preference_profile(config.preference_profile_path),
                        result=None,
                        search_enabled=False,
                        disabled_reason=disabled_reason,
                    ),
                )
                return

            if mode == RECOMMENDATION_MODE_KEYWORD and not query.strip():
                stage_md, logs_md = render_progress_markdown("准备环境", [])
                yield (
                    stage_md,
                    logs_md + "\n- 请输入关键词后再开始检索。",
                    render_workspace_html(
                        mode=mode,
                        digest=service.ensure_today_digest(),
                        profile=load_preference_profile(config.preference_profile_path),
                        result=None,
                        search_enabled=True,
                        disabled_reason="",
                    ),
                )
                return

            iterator = (
                recommendation_service.run_keyword_workflow(query)
                if mode == RECOMMENDATION_MODE_KEYWORD
                else recommendation_service.run_preference_workflow()
            )

            for snapshot in iterator:
                yield _render_snapshot(snapshot, search_enabled=search_enabled, disabled_reason=disabled_reason)

        mode_radio.change(
            fn=on_mode_change,
            inputs=[mode_radio],
            outputs=[keyword_text, current_stage_markdown, progress_logs_markdown, result_html],
        )

        refresh_button.click(
            fn=refresh_digest_view,
            inputs=[mode_radio],
            outputs=[current_stage_markdown, progress_logs_markdown, result_html],
        )

        start_button.click(
            fn=run_workflow,
            inputs=[mode_radio, keyword_text],
            outputs=[current_stage_markdown, progress_logs_markdown, result_html],
        )
        keyword_text.submit(
            fn=run_workflow,
            inputs=[mode_radio, keyword_text],
            outputs=[current_stage_markdown, progress_logs_markdown, result_html],
        )

    return demo


def _render_snapshot(
    snapshot: WorkflowSnapshot,
    *,
    search_enabled: bool,
    disabled_reason: str,
) -> tuple[str, str, str]:
    """把工作流快照转换成 Gradio 组件需要的输出。"""

    stage_md, logs_md = render_progress_markdown(snapshot.current_stage, snapshot.logs)
    html_output = render_workspace_html(
        mode=snapshot.mode,
        digest=snapshot.digest,
        profile=snapshot.profile,
        result=snapshot.result,
        search_enabled=search_enabled,
        disabled_reason=disabled_reason,
    )
    return stage_md, logs_md, html_output
