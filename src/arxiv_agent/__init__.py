"""arxiv-agent 包入口。

这个项目的核心能力很简单：
1. 抓取 arXiv `cs.CV/recent` 最新一天的论文。
2. 把结果写入本地 Markdown 缓存。
3. 通过 Gradio 页面展示论文卡片。
4. 可选地调用 SiliconFlow 生成中文简介。

为了让结构更容易维护，内部已经按 `clients / services / storage / ui`
做了分层。外部入口仍然统一暴露为 `main`，方便命令行脚本继续使用。
"""

from .cli import main

__all__ = ["main"]
