"""外部服务客户端层。

这一层只负责和外部系统通信，不负责业务编排：
- `ArxivClient` 负责抓取 arXiv 页面与摘要。
- `SiliconFlowClient` 负责调用大模型生成中文简介。

业务层如果需要组合这些能力，应当在 `services` 层里完成。
"""

from .arxiv_client import ArxivClient, now_utc_iso
from .siliconflow_client import SiliconFlowClient

__all__ = ["ArxivClient", "SiliconFlowClient", "now_utc_iso"]
