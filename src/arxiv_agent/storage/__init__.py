"""数据持久化层。

当前项目只使用 Markdown 文件作为本地缓存，因此这里提供的是
Markdown 的读取、解析、渲染和写回能力。
"""

from .markdown_store import load_digest, render_digest_markdown, write_digest

__all__ = ["load_digest", "render_digest_markdown", "write_digest"]
