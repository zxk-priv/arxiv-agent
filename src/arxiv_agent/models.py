"""项目中的核心数据模型。

当前工程已经不只是“抓当天论文并展示”这一条路径，而是扩展成了两套推荐流：

1. 关键词模式
   - 用户输入关键词
   - 系统检索当天论文
   - 为命中论文生成中文总结

2. 论文库偏好模式
   - 系统读取 `paper_datasets/` 下的 PDF
   - 先分析这些 PDF 反映出的研究偏好
   - 再用偏好去检索当天论文

为了让抓取、缓存、推荐、UI 这几层共用统一的数据结构，这里集中定义：
- 当天论文数据模型
- PDF 偏好分析数据模型
- 推荐结果数据模型
- 工作流进度数据模型
"""

from __future__ import annotations

from dataclasses import dataclass, field


SUMMARY_STATUS_MISSING = "missing"
SUMMARY_STATUS_READY = "ready"
SUMMARY_STATUS_FAILED = "failed"

RECOMMENDATION_MODE_KEYWORD = "keyword"
RECOMMENDATION_MODE_PREFERENCE = "preference"


@dataclass
class PaperEntry:
    """单篇 arXiv 论文的数据结构。

    这个对象用于“当天最新论文缓存”：
    - 抓取层负责把标题、链接、摘要填进来
    - 推荐层负责在命中时补中文总结
    - UI 层直接拿它渲染论文卡片

    `summary_status` 只描述“中文总结生成状态”，不描述抓取状态：
    - `missing`: 还没生成中文总结
    - `ready`: 中文总结已经可用
    - `failed`: 最近一次生成中文总结失败
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
        """当前论文是否已经有中文总结。"""

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
        """已生成中文总结的论文数量。"""

        return sum(1 for paper in self.papers if paper.summary_status == SUMMARY_STATUS_READY)

    @property
    def missing_count(self) -> int:
        """还可以继续补全中文总结的论文数量。"""

        return sum(1 for paper in self.papers if paper.summary_status == SUMMARY_STATUS_MISSING)

    @property
    def failed_count(self) -> int:
        """中文总结生成失败的论文数量。"""

        return sum(1 for paper in self.papers if paper.summary_status == SUMMARY_STATUS_FAILED)


@dataclass
class PdfPreferenceEntry:
    """单篇 PDF 偏好分析结果。

    这个对象对应 `paper_datasets/` 目录下的一份 PDF。

    设计上没有保存“全文解析结果”，而是只保存：
    - 文件元信息
    - 前几页提取出的文本预览
    - 模型总结出的领域 / 方法 / 任务标签
    - 简洁中文总结

    这样既能做偏好画像，也方便面试时直接打开 Markdown 看每篇论文的结构化总结。
    """

    source_pdf: str
    paper_title: str = ""
    source_file_size: int = 0
    source_modified_at_utc: str = ""
    extracted_page_count: int = 0
    extracted_text_preview: str = ""
    tech_fields: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    zh_summary: str = ""
    status: str = SUMMARY_STATUS_MISSING
    updated_at_utc: str = ""
    error_message: str = ""

    @property
    def is_ready(self) -> bool:
        """当前 PDF 是否已经完成偏好分析。"""

        return self.status == SUMMARY_STATUS_READY


@dataclass
class PreferenceProfile:
    """基于 `paper_datasets/` 生成的整体研究偏好画像。"""

    generated_at_utc: str
    source_pdf_count: int
    dominant_fields: list[str] = field(default_factory=list)
    method_keywords: list[str] = field(default_factory=list)
    task_keywords: list[str] = field(default_factory=list)
    research_focus_summary: str = ""
    retrieval_query: str = ""
    entries: list[PdfPreferenceEntry] = field(default_factory=list)

    @property
    def ready_count(self) -> int:
        """成功完成偏好分析的 PDF 数量。"""

        return sum(1 for entry in self.entries if entry.status == SUMMARY_STATUS_READY)

    @property
    def failed_count(self) -> int:
        """偏好分析失败的 PDF 数量。"""

        return sum(1 for entry in self.entries if entry.status == SUMMARY_STATUS_FAILED)


@dataclass
class RecommendationItem:
    """最终推荐结果中的单篇论文。

    这个对象和 `PaperEntry` 很像，但职责不同：
    - `PaperEntry` 是“当天论文缓存”的内部结构
    - `RecommendationItem` 是“最终推荐结果”的展示与落盘结构

    这样做的好处是：
    - 结果缓存不必携带抓取阶段的内部状态字段
    - 关键词模式和偏好模式能共用同一份结果结构
    """

    arxiv_id: str
    title: str
    pdf_url: str
    html_url: str
    abs_url: str
    english_abstract: str
    zh_summary: str


@dataclass
class RecommendationResult:
    """某次推荐运行的最终结果。"""

    mode: str
    generated_at_utc: str
    source_digest_date_slug: str
    source_digest_heading: str
    query: str = ""
    preference_focus_summary: str = ""
    items: list[RecommendationItem] = field(default_factory=list)


@dataclass
class ProgressEvent:
    """工作流中的单条阶段日志。

    页面希望展示“现在进行到哪一步”和“完整阶段日志”，
    所以这里把每条事件都结构化保存，便于：
    - CLI 打印
    - Gradio 渲染
    - 后续如有需要写入调试日志
    """

    stage: str
    message: str
    created_at_utc: str
    level: str = "info"


@dataclass
class WorkflowSnapshot:
    """一次工作流执行到某个阶段时的快照。

    推荐服务会在每个关键阶段产出一个快照，UI 可以据此增量刷新：
    - 当前步骤标题
    - 阶段日志
    - 是否已有最终推荐结果
    """

    mode: str
    current_stage: str
    logs: list[ProgressEvent] = field(default_factory=list)
    digest: DailyDigest | None = None
    profile: PreferenceProfile | None = None
    result: RecommendationResult | None = None
