"""应用配置。

这个文件只负责两件事：
1. 定义项目会用到哪些配置项。
2. 从 `.env` 和环境变量里读取配置，生成统一的 `AppConfig`。

这样做的好处是：其他模块只依赖 `AppConfig`，不用到处手动读环境变量。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_LISTING_URL = "https://arxiv.org/list/cs.CV/recent"
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_OUTPUT_DIR = "output/daily"
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 6008
DEFAULT_RAG_TOP_K = 20
DEFAULT_PAPER_DATASET_DIR = "paper_datasets"
DEFAULT_PREFERENCE_OUTPUT_DIR = "output/preferences"
DEFAULT_RESULT_OUTPUT_DIR = "output/results"
DEFAULT_PDF_EXTRACT_PAGES = 5
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOTENV_PATH = PROJECT_ROOT / ".env"


def _load_dotenv(dotenv_path: Path = DOTENV_PATH) -> None:
    """把 `.env` 文件里的键值对加载到当前进程环境变量中。

    这里只做最基础的解析，满足本项目自己的 `.env` 文件格式即可。
    如果某个环境变量已经在系统里存在，就不覆盖它，保证命令行显式传入
    的环境值优先级更高。
    """

    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    """应用运行时配置。

    字段说明：
    - `listing_url`: arXiv 列表页地址，默认抓取 `cs.CV/recent`
    - `output_dir`: Markdown 缓存输出目录
    - `latest_filename`: “最新缓存”文件名，页面默认总是读这个文件
    - `latest_archive_pattern`: 按日期归档时使用的文件名模板
    - `server_host / server_port`: Gradio 服务监听地址
    - `request_timeout_seconds`: 请求外部接口时的超时时间
    - `siliconflow_*`: 生成中文简介时使用的模型配置
    """

    listing_url: str = DEFAULT_LISTING_URL
    output_dir: Path = Path(DEFAULT_OUTPUT_DIR)
    latest_filename: str = "cs_cv_latest.md"
    latest_archive_pattern: str = "cs_cv_{date_slug}.md"
    server_host: str = DEFAULT_SERVER_HOST
    server_port: int = DEFAULT_SERVER_PORT
    request_timeout_seconds: int = 30
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = DEFAULT_BASE_URL
    siliconflow_model: str = ""
    siliconflow_embedding_model: str = ""
    rag_top_k: int = DEFAULT_RAG_TOP_K
    rag_vector_cache_dir: Path = Path(DEFAULT_OUTPUT_DIR) / ".rag"
    paper_dataset_dir: Path = Path(DEFAULT_PAPER_DATASET_DIR)
    preference_output_dir: Path = Path(DEFAULT_PREFERENCE_OUTPUT_DIR)
    result_output_dir: Path = Path(DEFAULT_RESULT_OUTPUT_DIR)
    preference_profile_filename: str = "profile_latest.md"
    keyword_result_filename: str = "keyword_latest.md"
    preference_result_filename: str = "preference_latest.md"
    pdf_extract_pages: int = DEFAULT_PDF_EXTRACT_PAGES

    @property
    def latest_markdown_path(self) -> Path:
        """返回“最新缓存”文件的完整路径。"""

        return self.output_dir / self.latest_filename

    def archive_markdown_path(self, date_slug: str) -> Path:
        """根据日期生成归档 Markdown 文件路径。"""

        return self.output_dir / self.latest_archive_pattern.format(date_slug=date_slug)

    @property
    def preference_profile_path(self) -> Path:
        """返回整体偏好画像 Markdown 路径。"""

        return self.preference_output_dir / self.preference_profile_filename

    @property
    def keyword_result_path(self) -> Path:
        """返回关键词模式最终推荐结果路径。"""

        return self.result_output_dir / self.keyword_result_filename

    @property
    def preference_result_path(self) -> Path:
        """返回偏好模式最终推荐结果路径。"""

        return self.result_output_dir / self.preference_result_filename

    @property
    def summarize_enabled(self) -> bool:
        """只有同时配置了 API Key 和模型名，才允许生成中文简介。"""

        return bool(self.siliconflow_api_key and self.siliconflow_model)

    @property
    def rag_enabled(self) -> bool:
        """只有同时配置了 API Key、总结模型和 embedding 模型，才允许搜索。"""

        return bool(
            self.siliconflow_api_key
            and self.siliconflow_model
            and self.siliconflow_embedding_model
        )


def load_config(
    *,
    listing_url: str = DEFAULT_LISTING_URL,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    server_host: str | None = None,
    server_port: int | None = None,
) -> AppConfig:
    """读取当前环境并生成统一配置对象。"""

    _load_dotenv()
    env_host = os.getenv("ARXIV_AGENT_HOST", DEFAULT_SERVER_HOST)
    env_port = int(os.getenv("ARXIV_AGENT_PORT", str(DEFAULT_SERVER_PORT)))

    return AppConfig(
        listing_url=listing_url,
        output_dir=Path(output_dir),
        server_host=server_host or env_host,
        server_port=server_port or env_port,
        siliconflow_api_key=os.getenv("SILICONFLOW_API_KEY", "").strip(),
        siliconflow_base_url=os.getenv("SILICONFLOW_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        siliconflow_model=os.getenv("SILICONFLOW_MODEL", "").strip(),
        siliconflow_embedding_model=os.getenv("SILICONFLOW_EMBEDDING_MODEL", "").strip(),
        rag_top_k=DEFAULT_RAG_TOP_K,
        rag_vector_cache_dir=Path(output_dir) / ".rag",
        paper_dataset_dir=Path(os.getenv("ARXIV_AGENT_PAPER_DATASET_DIR", DEFAULT_PAPER_DATASET_DIR)),
        preference_output_dir=Path(os.getenv("ARXIV_AGENT_PREFERENCE_OUTPUT_DIR", DEFAULT_PREFERENCE_OUTPUT_DIR)),
        result_output_dir=Path(os.getenv("ARXIV_AGENT_RESULT_OUTPUT_DIR", DEFAULT_RESULT_OUTPUT_DIR)),
        pdf_extract_pages=max(
            1,
            int(os.getenv("ARXIV_AGENT_PDF_EXTRACT_PAGES", str(DEFAULT_PDF_EXTRACT_PAGES))),
        ),
    )
