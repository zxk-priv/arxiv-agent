"""arXiv 抓取客户端。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from arxiv_agent.models import DailyDigest, PaperEntry


ARXIV_BASE_URL = "https://arxiv.org"
USER_AGENT = "arxiv-agent/0.2.0 (+https://arxiv.org/list/cs.CV/recent)"


def now_utc_iso() -> str:
    """返回当前 UTC 时间，格式固定为 ISO 字符串。"""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_full_listing_url(url: str) -> str:
    """把 arXiv recent 页面扩展为“尽量展示完整列表”的 URL。

    arXiv 的 recent 页面默认可能只展示部分条目，这里主动补上 `show=2000`
    和 `skip=0`，减少因为分页导致的遗漏。
    """

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["show"] = "2000"
    query["skip"] = "0"
    return urlunparse(parsed._replace(query=urlencode(query)))


def extract_heading_label(heading_text: str) -> str:
    """去掉标题中括号后的附加说明，只保留日期标签主体。"""

    return heading_text.split("(", 1)[0].strip()


def extract_date_slug(heading_text: str) -> str:
    """从 arXiv 标题中提取 `YYYY-MM-DD` 日期字符串。"""

    label = extract_heading_label(heading_text)
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", label)
    if not match:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    day, month_abbr, year = match.groups()
    parsed_date = datetime.strptime(f"{year} {month_abbr} {day}", "%Y %b %d")
    return parsed_date.strftime("%Y-%m-%d")


class ArxivClient:
    """负责访问 arXiv 页面并解析数据。"""

    def __init__(self, *, timeout: int = 30, session: requests.Session | None = None) -> None:
        self.timeout = timeout
        self.session = session or self.build_requests_session()

    @staticmethod
    def build_requests_session() -> requests.Session:
        """创建带有统一 User-Agent 的请求会话。"""

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        return session

    def close(self) -> None:
        """关闭底层网络会话。"""

        self.session.close()

    def __enter__(self) -> "ArxivClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def fetch_latest_digest(self, listing_url: str) -> DailyDigest:
        """抓取 arXiv recent 页面中“最新一天”的论文列表。"""

        full_listing_url = build_full_listing_url(listing_url)
        response = self.session.get(full_listing_url, timeout=self.timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.find("dl", id="articles")
        if not isinstance(articles, Tag):
            raise RuntimeError("未找到论文列表节点 dl#articles，页面结构可能已变化。")

        first_heading = articles.find("h3")
        if not isinstance(first_heading, Tag):
            raise RuntimeError("未找到最近日期分组标题 h3，页面结构可能已变化。")

        heading_text = " ".join(first_heading.get_text(" ", strip=True).split())
        papers = self._extract_papers_under_heading(first_heading)
        if not papers:
            raise RuntimeError("未解析到任何论文条目，页面结构可能已变化。")

        return DailyDigest(
            source_url=full_listing_url,
            heading=heading_text,
            date_slug=extract_date_slug(heading_text),
            fetched_at_utc=now_utc_iso(),
            papers=papers,
        )

    def fetch_english_abstract(self, paper: PaperEntry) -> str:
        """按“abs 页面优先、HTML 页面兜底”的顺序抓取英文摘要。"""

        try:
            return self._fetch_abstract_from_abs(paper)
        except Exception as abs_error:
            try:
                return self._fetch_abstract_from_html(paper)
            except Exception as html_error:
                raise RuntimeError(
                    f"abs 抓取失败: {abs_error}; html 抓取失败: {html_error}"
                ) from html_error

    def _extract_papers_under_heading(self, first_heading: Tag) -> list[PaperEntry]:
        """读取最新日期分组下的所有论文条目。"""

        papers: list[PaperEntry] = []
        pending_item: dict[str, str] | None = None

        for sibling in first_heading.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            if sibling.name == "h3":
                break

            if sibling.name == "dt":
                pending_item = self._parse_dt_row(sibling)
                continue

            if sibling.name == "dd" and pending_item:
                paper = self._parse_dd_row(sibling, pending_item)
                if paper is not None:
                    papers.append(paper)
                pending_item = None

        return papers

    def _parse_dt_row(self, row: Tag) -> dict[str, str] | None:
        """解析 `dt` 行，提取论文链接和 arXiv 编号。"""

        abs_link = row.find("a", title="Abstract")
        if not isinstance(abs_link, Tag):
            return None

        arxiv_id = abs_link.get_text(strip=True).replace("arXiv:", "")
        abs_href = abs_link.get("href", "").strip()

        pdf_link = row.find("a", title="Download PDF")
        html_link = row.find("a", title="View HTML")
        return {
            "arxiv_id": arxiv_id,
            "abs_url": self._normalize_url(abs_href),
            "pdf_url": self._normalize_url(pdf_link.get("href", "").strip()) if isinstance(pdf_link, Tag) else "",
            "html_url": self._normalize_url(html_link.get("href", "").strip()) if isinstance(html_link, Tag) else "",
        }

    def _parse_dd_row(self, row: Tag, pending_item: dict[str, str]) -> PaperEntry | None:
        """解析 `dd` 行，补齐标题并组装成 `PaperEntry`。"""

        title_div = row.find("div", class_="list-title")
        if not isinstance(title_div, Tag):
            return None

        descriptor = title_div.find("span", class_="descriptor")
        if isinstance(descriptor, Tag):
            descriptor.extract()

        title = " ".join(title_div.get_text(" ", strip=True).split())
        if not title:
            return None

        return PaperEntry(
            arxiv_id=pending_item["arxiv_id"],
            title=title,
            pdf_url=pending_item["pdf_url"],
            html_url=pending_item["html_url"],
            abs_url=pending_item["abs_url"],
        )

    def _fetch_abstract_from_abs(self, paper: PaperEntry) -> str:
        """从 arXiv 标准 `abs` 页面提取摘要。"""

        response = self.session.get(paper.abs_url, timeout=self.timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        meta_abstract = soup.find("meta", attrs={"name": "citation_abstract"})
        if isinstance(meta_abstract, Tag):
            content = meta_abstract.get("content", "").strip()
            if content:
                return " ".join(content.split())

        abstract_block = soup.find("blockquote", class_="abstract")
        if isinstance(abstract_block, Tag):
            descriptor = abstract_block.find("span", class_="descriptor")
            if isinstance(descriptor, Tag):
                descriptor.extract()

            text = " ".join(abstract_block.get_text(" ", strip=True).split())
            if text:
                return text

        raise RuntimeError(f"未能从 abs 页面提取摘要: {paper.abs_url}")

    def _fetch_abstract_from_html(self, paper: PaperEntry) -> str:
        """如果 abs 页面失败，则尝试从 HTML 论文页面提取摘要。"""

        if not paper.html_url:
            raise RuntimeError(f"论文缺少 HTML 链接: {paper.arxiv_id}")

        response = self.session.get(paper.html_url, timeout=self.timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        abstract_block = soup.find(id="abstract1")
        if not isinstance(abstract_block, Tag):
            abstract_block = soup.find("div", class_="ltx_abstract")
        if not isinstance(abstract_block, Tag):
            raise RuntimeError(f"未能从 HTML 页面提取摘要: {paper.html_url}")

        heading = abstract_block.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if isinstance(heading, Tag):
            heading.extract()

        text = " ".join(abstract_block.get_text(" ", strip=True).split())
        if not text:
            raise RuntimeError(f"HTML 摘要内容为空: {paper.html_url}")
        return text

    @staticmethod
    def _normalize_url(href: str) -> str:
        """把相对路径补全成完整 arXiv 链接。"""

        return urljoin(ARXIV_BASE_URL, href)
