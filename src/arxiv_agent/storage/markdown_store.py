"""Markdown 缓存读写。

这个项目把抓取结果保存为 Markdown 文件，原因有两个：
1. 人可以直接打开查看，不需要额外工具。
2. 页面和命令行都能复用同一份本地缓存。

代价是解析时需要遵守固定格式，因此这里的解析器是“面向本项目生成结果”
设计的，而不是一个通用 Markdown 解析器。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from arxiv_agent.models import DailyDigest, PaperEntry, SUMMARY_STATUS_MISSING


PAPER_PATTERN = re.compile(
    r"^## \[(?P<arxiv_id>[^\]]+)\] (?P<title>[^\n]+)\n"
    r"- PDF: (?P<pdf_url>[^\n]*)\n"
    r"- HTML: (?P<html_url>[^\n]*)\n"
    r"- Abstract URL: (?P<abs_url>[^\n]*)\n"
    r"- Status: (?P<status>[^\n]*)\n"
    r"- Error: (?P<error_message>[^\n]*)\n"
    r"- Updated At \(UTC\): (?P<updated_at_utc>[^\n]*)\n"
    r"\n### English Abstract\n"
    r"(?P<english_abstract>.*?)\n"
    r"### 中文简介\n"
    r"(?P<zh_summary>.*?)(?=^## \[|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _split_front_matter(content: str) -> tuple[dict, str]:
    """拆出 YAML front matter 和正文。"""

    if not content.startswith("---\n"):
        raise RuntimeError("Markdown 文件缺少 YAML front matter。")

    end = content.find("\n---\n", 4)
    if end == -1:
        raise RuntimeError("Markdown 文件 front matter 未正确关闭。")

    front_matter_text = content[4:end]
    body = content[end + len("\n---\n") :].lstrip("\n")
    data = yaml.safe_load(front_matter_text) or {}
    return data, body


def load_digest(path: Path) -> DailyDigest | None:
    """从 Markdown 文件中加载抓取结果。

    如果文件不存在，返回 `None`，方便上层决定是报错还是重新抓取。
    """

    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    metadata, body = _split_front_matter(content)

    papers: list[PaperEntry] = []
    for match in PAPER_PATTERN.finditer(body):
        papers.append(
            PaperEntry(
                arxiv_id=match.group("arxiv_id").strip(),
                title=match.group("title").strip(),
                pdf_url=match.group("pdf_url").strip(),
                html_url=match.group("html_url").strip(),
                abs_url=match.group("abs_url").strip(),
                english_abstract=match.group("english_abstract").strip(),
                zh_summary=match.group("zh_summary").strip(),
                summary_status=match.group("status").strip() or SUMMARY_STATUS_MISSING,
                updated_at_utc=match.group("updated_at_utc").strip(),
                error_message=match.group("error_message").strip(),
            )
        )

    return DailyDigest(
        source_url=str(metadata.get("source_url", "")),
        heading=str(metadata.get("heading", "")),
        date_slug=str(metadata.get("date_slug", "")),
        fetched_at_utc=str(metadata.get("fetched_at_utc", "")),
        papers=papers,
    )


def render_digest_markdown(digest: DailyDigest) -> str:
    """把内存中的抓取结果渲染成 Markdown 文本。"""

    metadata = {
        "source_url": digest.source_url,
        "heading": digest.heading,
        "date_slug": digest.date_slug,
        "fetched_at_utc": digest.fetched_at_utc,
        "paper_count": len(digest.papers),
        "ready_count": digest.ready_count,
        "missing_count": digest.missing_count,
        "failed_count": digest.failed_count,
    }

    lines = [
        "---",
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip(),
        "---",
        "",
        "# arXiv cs.CV 最新一天论文导览",
        "",
        f"- 日期分组: {digest.heading}",
        f"- 论文总数: {len(digest.papers)}",
        f"- 已生成简介: {digest.ready_count}",
        f"- 待生成简介: {digest.missing_count}",
        f"- 生成失败: {digest.failed_count}",
        "",
    ]

    for paper in digest.papers:
        lines.extend(
            [
                f"## [{paper.arxiv_id}] {paper.title}",
                f"- PDF: {paper.pdf_url}",
                f"- HTML: {paper.html_url}",
                f"- Abstract URL: {paper.abs_url}",
                f"- Status: {paper.summary_status}",
                f"- Error: {paper.error_message}",
                f"- Updated At (UTC): {paper.updated_at_utc}",
                "",
                "### English Abstract",
                paper.english_abstract.strip(),
                "### 中文简介",
                paper.zh_summary.strip(),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_digest(path: Path, digest: DailyDigest) -> None:
    """把抓取结果写入 Markdown 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_digest_markdown(digest), encoding="utf-8")
