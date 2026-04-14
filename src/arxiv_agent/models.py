"""项目中的核心数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


SUMMARY_STATUS_MISSING = "missing"
SUMMARY_STATUS_READY = "ready"
SUMMARY_STATUS_FAILED = "failed"


@dataclass
class PaperEntry:
    """单篇论文的数据结构。

    这个对象会贯穿抓取、缓存、页面展示三个阶段，所以字段相对完整。

    状态字段 `summary_status` 的语义：
    - `missing`: 还没有中文简介，或者英文摘要刚补齐、后续可以继续生成简介
    - `ready`: 中文简介已经准备好
    - `failed`: 本轮处理失败，失败原因记录在 `error_message`
    """

    arxiv_id: str
    title: str
    pdf_url: str
    html_url: str
    abs_url: str
    english_abstract: str = ""
    zh_summary: str = ""
    summary_status: str = SUMMARY_STATUS_MISSING
    updated_at_utc: str = ""
    error_message: str = ""

    @property
    def has_summary(self) -> bool:
        """当前论文是否已经有中文简介。"""

        return bool(self.zh_summary.strip())

    @property
    def has_abstract(self) -> bool:
        """当前论文是否已经有英文摘要。"""

        return bool(self.english_abstract.strip())


@dataclass
class DailyDigest:
    """某一天论文分组的完整抓取结果。"""

    source_url: str
    heading: str
    date_slug: str
    fetched_at_utc: str
    papers: list[PaperEntry] = field(default_factory=list)

    @property
    def ready_count(self) -> int:
        """已生成中文简介的论文数量。"""

        return sum(1 for paper in self.papers if paper.summary_status == SUMMARY_STATUS_READY)

    @property
    def missing_count(self) -> int:
        """还可以继续补全的论文数量。"""

        return sum(1 for paper in self.papers if paper.summary_status == SUMMARY_STATUS_MISSING)

    @property
    def failed_count(self) -> int:
        """处理失败的论文数量。"""

        return sum(1 for paper in self.papers if paper.summary_status == SUMMARY_STATUS_FAILED)
