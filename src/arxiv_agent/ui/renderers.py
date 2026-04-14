"""负责把抓取结果渲染成 HTML。"""

from __future__ import annotations

import html

from arxiv_agent.models import (
    DailyDigest,
    PaperEntry,
    SUMMARY_STATUS_FAILED,
    SUMMARY_STATUS_MISSING,
    SUMMARY_STATUS_READY,
)

from .styles import CARD_STYLE


STATUS_LABELS = {
    SUMMARY_STATUS_READY: "已完成",
    SUMMARY_STATUS_MISSING: "待补全",
    SUMMARY_STATUS_FAILED: "失败",
}


def summary_preview(paper: PaperEntry) -> str:
    """优先展示中文简介，没有的话展示英文摘要。"""

    if paper.zh_summary.strip():
        return paper.zh_summary
    if paper.english_abstract.strip():
        return paper.english_abstract
    return "暂未抓取到简介内容。"


def render_stats(digest: DailyDigest) -> str:
    """渲染顶部统计信息卡片。"""

    return f"""
    <div class="stats-grid">
      <div class="stat-card"><span class="stat-label">日期分组</span><span class="stat-value">{html.escape(digest.heading)}</span></div>
      <div class="stat-card"><span class="stat-label">论文总数</span><span class="stat-value">{len(digest.papers)}</span></div>
      <div class="stat-card"><span class="stat-label">已生成中文简介</span><span class="stat-value">{digest.ready_count}</span></div>
      <div class="stat-card"><span class="stat-label">待补全</span><span class="stat-value">{digest.missing_count}</span></div>
      <div class="stat-card"><span class="stat-label">抓取失败</span><span class="stat-value">{digest.failed_count}</span></div>
    </div>
    """


def render_paper_card(paper: PaperEntry) -> str:
    """渲染单篇论文卡片。"""

    html_link = ""
    if paper.html_url:
        html_link = (
            f'<a class="paper-link secondary" href="{html.escape(paper.html_url)}" '
            'target="_blank" rel="noopener noreferrer">HTML</a>'
        )

    error_html = ""
    if paper.error_message:
        error_html = (
            '<div class="error-box"><strong>错误信息</strong>'
            f'<p>{html.escape(paper.error_message)}</p></div>'
        )

    updated_at_html = ""
    if paper.updated_at_utc:
        updated_at_html = f'<span class="updated-at">更新于 {html.escape(paper.updated_at_utc)}</span>'

    preview = html.escape(summary_preview(paper))
    abstract = html.escape(paper.english_abstract or "暂未抓取到英文摘要。")
    title = html.escape(paper.title)
    arxiv_id = html.escape(paper.arxiv_id)
    pdf_url = html.escape(paper.pdf_url)
    status_code = html.escape(paper.summary_status)
    status_label = html.escape(STATUS_LABELS.get(paper.summary_status, paper.summary_status))

    return f"""
    <article class="paper-card">
      <div class="paper-head">
        <div>
          <p class="paper-id">{arxiv_id}</p>
          <h2 class="paper-title">{title}</h2>
        </div>
        <div class="paper-actions">
          <a class="paper-link" href="{pdf_url}" target="_blank" rel="noopener noreferrer">PDF</a>
          {html_link}
        </div>
      </div>
      <div class="paper-meta">
        <span class="status-chip status-{status_code}">{status_label}</span>
        {updated_at_html}
      </div>
      <section class="paper-section">
        <h3>English Abstract</h3>
        <p>{abstract}</p>
      </section>
      <section class="paper-section">
        <h3>简介预览</h3>
        <p>{preview}</p>
      </section>
      {error_html}
    </article>
    """


def render_digest_html(digest: DailyDigest) -> str:
    """把整天论文结果渲染成完整 HTML 页面片段。"""

    cards = "\n".join(render_paper_card(paper) for paper in digest.papers)
    return f"""
    {CARD_STYLE}
    <div class="app-shell">
      <section class="hero-block">
        <p class="hero-kicker">arXiv cs.CV</p>
        <h1 class="hero-title">最新一天论文卡片流</h1>
        <p class="hero-subtitle">当前页面默认不自动调用 SiliconFlow。每篇论文会展示标题、PDF 链接、HTML 链接、英文摘要，以及优先显示中文简介、否则回退到英文摘要的简介预览区域。</p>
        {render_stats(digest)}
        <div class="notice">页面展示以本地缓存文档 <code>output/daily/cs_cv_latest.md</code> 为准。刷新按钮会先补全缺失的英文摘要，再重新从 Markdown 读取页面内容。AI 总结按钮会把前 N 篇论文的中文简介写回同一份缓存文件。</div>
      </section>
      <section class="paper-grid">{cards}</section>
    </div>
    """
