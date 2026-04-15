"""数据持久化层。

当前工程使用多份 Markdown 做缓存：
- 当天论文缓存
- PDF 偏好分析缓存
- 最终推荐结果缓存

这里统一导出各类缓存读写接口，便于服务层按职责组合使用。
"""

from .markdown_store import load_digest, render_digest_markdown, write_digest
from .preference_store import load_preference_profile, render_preference_markdown, write_preference_profile
from .recommendation_store import (
    load_recommendation_result,
    render_recommendation_markdown,
    write_recommendation_result,
)

__all__ = [
    "load_digest",
    "render_digest_markdown",
    "write_digest",
    "load_preference_profile",
    "render_preference_markdown",
    "write_preference_profile",
    "load_recommendation_result",
    "render_recommendation_markdown",
    "write_recommendation_result",
]
