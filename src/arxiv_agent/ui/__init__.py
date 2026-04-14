"""界面层。

这里负责两类事情：
- 把论文数据渲染成 HTML。
- 组装 Gradio 页面和按钮交互。

业务逻辑不要直接堆在 UI 文件里，避免页面代码越来越难读。
"""

from .gradio_app import create_blocks

__all__ = ["create_blocks"]
