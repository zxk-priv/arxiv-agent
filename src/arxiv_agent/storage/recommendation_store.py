"""最终推荐结果的 Markdown 读写。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from arxiv_agent.models import RecommendationItem, RecommendationResult


def load_recommendation_result(path: Path) -> RecommendationResult | None:
    """从 Markdown 缓存中读取推荐结果。"""

    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise RuntimeError("推荐结果缓存缺少 YAML front matter。")

    end = content.find("\n---\n", 4)
    if end == -1:
        raise RuntimeError("推荐结果缓存 front matter 未正确关闭。")

    metadata = yaml.safe_load(content[4:end]) or {}
    items: list[RecommendationItem] = []
    for raw_item in metadata.get("items", []) or []:
        items.append(
            RecommendationItem(
                arxiv_id=str(raw_item.get("arxiv_id", "")),
                title=str(raw_item.get("title", "")),
                pdf_url=str(raw_item.get("pdf_url", "")),
                html_url=str(raw_item.get("html_url", "")),
                abs_url=str(raw_item.get("abs_url", "")),
                english_abstract=str(raw_item.get("english_abstract", "")),
                zh_summary=str(raw_item.get("zh_summary", "")),
            )
        )

    return RecommendationResult(
        mode=str(metadata.get("mode", "")),
        generated_at_utc=str(metadata.get("generated_at_utc", "")),
        source_digest_date_slug=str(metadata.get("source_digest_date_slug", "")),
        source_digest_heading=str(metadata.get("source_digest_heading", "")),
        query=str(metadata.get("query", "")),
        preference_focus_summary=str(metadata.get("preference_focus_summary", "")),
        items=items,
    )


def render_recommendation_markdown(result: RecommendationResult) -> str:
    """把推荐结果渲染成 Markdown 文本。"""

    metadata = {
        "mode": result.mode,
        "generated_at_utc": result.generated_at_utc,
        "source_digest_date_slug": result.source_digest_date_slug,
        "source_digest_heading": result.source_digest_heading,
        "query": result.query,
        "preference_focus_summary": result.preference_focus_summary,
        "result_count": len(result.items),
        "items": [asdict(item) for item in result.items],
    }

    title = "关键词模式推荐结果" if result.mode == "keyword" else "论文库偏好模式推荐结果"
    lines = [
        "---",
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip(),
        "---",
        "",
        f"# {title}",
        "",
        f"- 日期分组: {result.source_digest_heading}",
        f"- 结果数量: {len(result.items)}",
    ]

    if result.query:
        lines.append(f"- Query: {result.query}")
    if result.preference_focus_summary:
        lines.append(f"- Preference Focus: {result.preference_focus_summary}")

    lines.append("")
    for item in result.items:
        lines.extend(
            [
                f"## [{item.arxiv_id}] {item.title}",
                f"- PDF: {item.pdf_url}",
                f"- HTML: {item.html_url}",
                f"- Abstract URL: {item.abs_url}",
                "",
                "### English Abstract",
                item.english_abstract.strip(),
                "### 中文总结",
                item.zh_summary.strip(),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_recommendation_result(path: Path, result: RecommendationResult) -> None:
    """把推荐结果写入 Markdown。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_recommendation_markdown(result), encoding="utf-8")
