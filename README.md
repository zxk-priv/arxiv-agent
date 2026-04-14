# arxiv-agent

`arxiv-agent` 是一个面向初学者也能读懂的小型 Python 工程。

它会抓取 arXiv `cs.CV/recent` 页面中“最新一天”的论文，把结果写入本地 Markdown 缓存，并通过 Gradio 页面展示为论文卡片流。可选地，它还可以通过 `openai` Python SDK 调用 SiliconFlow 的 OpenAI 兼容接口，为论文生成中文简介。

## 这个项目能做什么

- 抓取最新一天的 `cs.CV` 论文列表
- 提取每篇论文的标题、PDF 链接、HTML 链接和英文摘要
- 把结果保存为本地 Markdown 文件，方便人直接查看
- 启动 Gradio 页面，把论文展示成卡片流
- 按需为前 N 篇论文生成中文简介

默认情况下，页面不会自动调用大模型；如果论文没有中文简介，就优先显示英文摘要作为“简介预览”。

## 项目结构

整理后的工程按“职责分层”组织，阅读顺序建议从 `cli -> services -> clients/storage -> ui`：

```text
arxiv-agent/
├── README.md
├── pyproject.toml
├── .env.example
└── src/
    └── arxiv_agent/
        ├── __init__.py
        ├── __main__.py
        ├── cli.py                  # 命令行入口
        ├── config.py               # 配置读取与统一配置对象
        ├── models.py               # 核心数据模型
        ├── clients/
        │   ├── arxiv_client.py     # arXiv 页面抓取
        │   └── siliconflow_client.py # 基于 openai SDK 的 SiliconFlow 客户端
        ├── services/
        │   └── digest_service.py   # 业务主流程编排
        ├── storage/
        │   └── markdown_store.py   # Markdown 缓存读写
        └── ui/
            ├── gradio_app.py       # Gradio 页面组装
            ├── renderers.py        # HTML 渲染
            └── styles.py           # 页面样式
```

### 各层分别负责什么

- `cli.py`
  负责解析命令行参数，并把命令分发到业务层。
- `config.py`
  负责读取 `.env` 和环境变量，生成统一的 `AppConfig`。
- `clients/`
  只负责访问外部服务，不处理业务判断。
- `services/`
  负责决定“什么时候抓取、什么时候补摘要、什么时候写缓存”。
- `storage/`
  负责把抓取结果保存为 Markdown，并从 Markdown 恢复为 Python 对象。
- `ui/`
  负责页面展示和按钮交互，不直接承担底层业务逻辑。

## 运行环境

项目使用 `uv` 管理依赖和虚拟环境：

```bash
uv sync
```

如果只想抓取论文和启动页面，不需要配置大模型。

如果你想生成中文简介，可以复制 `.env.example` 为 `.env`，再填写 SiliconFlow 配置。

这里虽然接的是 SiliconFlow，但代码层使用的是 `openai` 官方 Python SDK；本质上是把 `base_url` 指向 SiliconFlow 的 OpenAI 兼容接口地址：

```bash
cp .env.example .env
```

```env
SILICONFLOW_API_KEY=your_api_key
SILICONFLOW_MODEL=your_model_name
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
```

## 常用命令

只抓取最新一天论文的基础信息，并更新 Markdown 缓存：

```bash
uv run arxiv-agent fetch
```

补全英文摘要，并在已配置 SiliconFlow 时生成中文简介：

```bash
uv run arxiv-agent summarize
```

如果你只想验证 API 是否可用，推荐只处理 1 篇论文，避免浪费 token：

```bash
uv run arxiv-agent summarize --limit 1
```

启动 Gradio 页面：

```bash
uv run arxiv-agent serve
```

自定义输出目录和端口：

```bash
uv run arxiv-agent --output-dir output/daily serve --host 127.0.0.1 --port 8001
```

如果你更习惯 Python 模块方式，也可以这样启动：

```bash
uv run python -m arxiv_agent serve
```

## 缓存文件说明

程序会把缓存写入：

- `output/daily/cs_cv_latest.md`
- `output/daily/cs_cv_YYYY-MM-DD.md`

含义分别是：

- `cs_cv_latest.md`
  始终指向“最近一次可展示的最新缓存”，Gradio 页面默认读取它。
- `cs_cv_YYYY-MM-DD.md`
  是按日期归档的历史缓存，方便回看某一天抓到了什么。

## 数据流怎么走

项目的主流程如下：

1. `cli.py` 读取命令行参数。
2. `config.py` 生成 `AppConfig`。
3. `services/digest_service.py` 调用 `clients/arxiv_client.py` 抓取最新论文。
4. 如果本地已经有同一天缓存，就合并已有的摘要和中文简介。
5. 结果通过 `storage/markdown_store.py` 写回 Markdown。
6. `ui/gradio_app.py` 读取 Markdown 并渲染为卡片页面。

## 适合二次修改的入口

如果你后面想继续扩展这个项目，最常见的入口是：

- 想改抓取逻辑：看 `clients/arxiv_client.py`
- 想改缓存格式：看 `storage/markdown_store.py`
- 想改业务流程：看 `services/digest_service.py`
- 想改页面样式：看 `ui/styles.py`
- 想改页面布局：看 `ui/renderers.py` 和 `ui/gradio_app.py`
