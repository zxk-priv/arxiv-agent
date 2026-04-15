"""负责把推荐工作流渲染成 HTML / Markdown。"""

from __future__ import annotations

import html

from arxiv_agent.models import (
    DailyDigest,
    PreferenceProfile,
    ProgressEvent,
    RecommendationItem,
    RecommendationResult,
    RECOMMENDATION_MODE_KEYWORD,
    RECOMMENDATION_MODE_PREFERENCE,
)

from .styles import CARD_STYLE


def render_workspace_html(
    *,
    mode: str,
    digest: DailyDigest | None,
    profile: PreferenceProfile | None,
    result: RecommendationResult | None,
    search_enabled: bool,
    disabled_reason: str = "",
) -> str:
    """渲染工作台主区域。

    这个区域承担三种状态：
    - 初始空态
    - 偏好模式概览
    - 最终推荐结果卡片
    """

    mode_title = "关键词模式" if mode == RECOMMENDATION_MODE_KEYWORD else "论文库偏好模式"
    body_html = render_empty_panel(mode, search_enabled=search_enabled, disabled_reason=disabled_reason)
    if result is not None:
        body_html = render_result_panel(result)
    elif mode == RECOMMENDATION_MODE_PREFERENCE and profile is not None:
        body_html = render_profile_panel(profile)

    return f"""
    {CARD_STYLE}
    <div class="app-shell">
      <section class="hero-block">
        <p class="hero-kicker">arXiv cs.CV</p>
        <h1 class="hero-title">双模式论文推荐工作台</h1>
        <p class="hero-subtitle">当前模式：{html.escape(mode_title)}。工程会优先复用本地缓存；关键词模式直接检索当天论文，论文库偏好模式会先分析 <code>paper_datasets/</code> 下的 PDF 偏好，再去检索当天论文。</p>
        {render_digest_stats(digest)}
        {render_profile_stats(profile)}
      </section>
      {body_html}
    </div>
    """


def render_digest_stats(digest: DailyDigest | None) -> str:
    """渲染当天论文缓存统计。"""

    if digest is None:
        return ""

    return f"""
    <div class="stats-grid">
      <div class="stat-card"><span class="stat-label">日期分组</span><span class="stat-value">{html.escape(digest.heading)}</span></div>
      <div class="stat-card"><span class="stat-label">论文总数</span><span class="stat-value">{len(digest.papers)}</span></div>
      <div class="stat-card"><span class="stat-label">已缓存中文总结</span><span class="stat-value">{digest.ready_count}</span></div>
      <div class="stat-card"><span class="stat-label">待补中文总结</span><span class="stat-value">{digest.missing_count}</span></div>
      <div class="stat-card"><span class="stat-label">生成失败</span><span class="stat-value">{digest.failed_count}</span></div>
    </div>
    """


def render_profile_stats(profile: PreferenceProfile | None) -> str:
    """渲染本地 PDF 偏好画像统计。"""

    if profile is None:
        return ""

    return f"""
    <div class="stats-grid profile-grid">
      <div class="stat-card"><span class="stat-label">论文库 PDF 总数</span><span class="stat-value">{profile.source_pdf_count}</span></div>
      <div class="stat-card"><span class="stat-label">偏好分析成功</span><span class="stat-value">{profile.ready_count}</span></div>
      <div class="stat-card"><span class="stat-label">偏好分析失败</span><span class="stat-value">{profile.failed_count}</span></div>
      <div class="stat-card"><span class="stat-label">主导方向</span><span class="stat-value small">{html.escape(' / '.join(profile.dominant_fields) or '暂无')}</span></div>
    </div>
    """


def render_empty_panel(mode: str, *, search_enabled: bool, disabled_reason: str) -> str:
    """渲染模式空态说明。"""

    if not search_enabled and disabled_reason:
        title = "搜索暂不可用"
        description = disabled_reason
    elif mode == RECOMMENDATION_MODE_KEYWORD:
        title = "输入关键词后开始检索"
        description = "系统会直接在最新一天的论文标题与摘要中做混合检索，并对命中论文生成中文总结。"
    else:
        title = "点击开始检索后分析论文库偏好"
        description = "系统会先读取 paper_datasets 下的 PDF 前几页，分析你的研究方向，再用偏好去检索当天论文。"

    return f"""
    <section class="empty-state">
      <h2>{html.escape(title)}</h2>
      <p>{html.escape(description)}</p>
    </section>
    """


def render_profile_panel(profile: PreferenceProfile) -> str:
    """在偏好模式下渲染当前研究偏好概览。"""

    return f"""
    <section class="summary-panel">
      <h2>当前研究偏好画像</h2>
      <p>{html.escape(profile.research_focus_summary or '暂无偏好画像。')}</p>
      <div class="tag-cloud">
        {_render_tag_items(profile.dominant_fields)}
        {_render_tag_items(profile.method_keywords)}
        {_render_tag_items(profile.task_keywords)}
      </div>
      <div class="notice">系统会把上面的偏好总结进一步转换成英文检索查询，再去当天论文缓存中做推荐。</div>
    </section>
    """


def render_result_panel(result: RecommendationResult) -> str:
    """渲染最终推荐结果卡片。"""

    cards = "\n".join(render_recommendation_card(item) for item in result.items)
    summary = result.query or result.preference_focus_summary or "未提供额外摘要"
    return f"""
    <section class="summary-panel">
      <h2>推荐结果概览</h2>
      <p>{html.escape(summary)}</p>
      <div class="stats-grid result-grid">
        <div class="stat-card"><span class="stat-label">推荐模式</span><span class="stat-value small">{html.escape(result.mode)}</span></div>
        <div class="stat-card"><span class="stat-label">结果数量</span><span class="stat-value">{len(result.items)}</span></div>
        <div class="stat-card"><span class="stat-label">生成时间</span><span class="stat-value small">{html.escape(result.generated_at_utc)}</span></div>
      </div>
    </section>
    <section class="paper-grid">{cards}</section>
    """


def render_recommendation_card(item: RecommendationItem) -> str:
    """渲染单篇推荐论文卡片。"""

    html_link = ""
    if item.html_url:
        html_link = (
            f'<a class="paper-link secondary" href="{html.escape(item.html_url)}" '
            'target="_blank" rel="noopener noreferrer">HTML</a>'
        )

    return f"""
    <article class="paper-card">
      <div class="paper-head">
        <div>
          <p class="paper-id">{html.escape(item.arxiv_id)}</p>
          <h2 class="paper-title">{html.escape(item.title)}</h2>
        </div>
        <div class="paper-actions">
          <a class="paper-link" href="{html.escape(item.pdf_url)}" target="_blank" rel="noopener noreferrer">PDF</a>
          {html_link}
        </div>
      </div>
      <section class="paper-section">
        <h3>English Abstract</h3>
        <p>{html.escape(item.english_abstract or '暂无英文摘要。')}</p>
      </section>
      <section class="paper-section">
        <h3>中文总结</h3>
        <p>{html.escape(item.zh_summary or '暂无中文总结。')}</p>
      </section>
    </article>
    """


def render_progress_markdown(current_stage: str, logs: list[ProgressEvent]) -> tuple[str, str]:
    """把当前步骤和阶段日志渲染成 Markdown。"""

    current_stage_markdown = f"**当前步骤**\n\n`{current_stage}`"

    if not logs:
        return current_stage_markdown, "**阶段日志**\n\n尚未开始。"

    log_lines = ["**阶段日志**", ""]
    for event in logs:
        log_lines.append(
            f"- `{event.created_at_utc}` [{event.stage}] {event.message}"
        )
    return current_stage_markdown, "\n".join(log_lines)


def _render_tag_items(items: list[str]) -> str:
    """渲染标签云。"""

    return "".join(
        f'<span class="tag-chip">{html.escape(item)}</span>'
        for item in items
        if item.strip()
    )
