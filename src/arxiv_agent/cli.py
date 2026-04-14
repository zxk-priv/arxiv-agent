"""命令行入口。"""

from __future__ import annotations

import argparse
import socket

from arxiv_agent.config import DEFAULT_LISTING_URL, DEFAULT_OUTPUT_DIR, load_config
from arxiv_agent.services import DigestService
from arxiv_agent.ui import create_blocks


PORT_SCAN_LIMIT = 20


def _find_available_port(host: str, preferred_port: int) -> int:
    """从首选端口开始向后探测一个可用端口。"""

    for port in range(preferred_port, preferred_port + PORT_SCAN_LIMIT + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port

    raise OSError(
        f"无法在 {preferred_port}-{preferred_port + PORT_SCAN_LIMIT} 范围内找到可用端口。"
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(
        description="抓取 arXiv 最新一天论文，并用 Gradio 卡片流展示。",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_LISTING_URL,
        help=f"要抓取的 arXiv recent 页面，默认值: {DEFAULT_LISTING_URL}",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Markdown 缓存目录，默认值: {DEFAULT_OUTPUT_DIR}",
    )

    subparsers = parser.add_subparsers(dest="command", required=False)
    subparsers.add_parser("fetch", help="仅抓取最新一天论文基础信息并更新 Markdown 缓存。")
    summarize_parser = subparsers.add_parser(
        "summarize",
        help="补全英文摘要，并在已配置 SiliconFlow 时生成中文简介。",
    )
    summarize_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只为前 N 篇论文生成中文简介；不传则按原逻辑处理全部论文。",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="启动 Gradio 页面，并在页面交互时补全缺失摘要或生成简介。",
    )
    serve_parser.add_argument(
        "--host",
        default=None,
        help="服务监听地址，默认读取 ARXIV_AGENT_HOST 或 127.0.0.1",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="服务端口，默认读取 ARXIV_AGENT_PORT 或 6008",
    )

    return parser.parse_args()


def main() -> None:
    """命令行主入口。"""

    args = parse_args()
    command = args.command or "serve"
    config = load_config(
        listing_url=args.url,
        output_dir=args.output_dir,
        server_host=getattr(args, "host", None),
        server_port=getattr(args, "port", None),
    )
    digest_service = DigestService(config)

    if command == "fetch":
        digest = digest_service.refresh_latest_digest(
            include_abstracts=False,
            include_summaries=False,
        )
        print(f"已更新基础缓存: {config.latest_markdown_path}")
        print(f"最近分组: {digest.heading}")
        print(f"论文数量: {len(digest.papers)}")
        return

    if command == "summarize":
        summary_limit = getattr(args, "limit", None)
        if summary_limit is None:
            digest = digest_service.refresh_latest_digest(
                include_abstracts=True,
                include_summaries=True,
            )
        else:
            digest = digest_service.summarize_first_n_papers(
                api_key=config.siliconflow_api_key,
                model=config.siliconflow_model,
                limit=summary_limit,
            )
        print(f"已更新摘要缓存: {config.latest_markdown_path}")
        print(f"最近分组: {digest.heading}")
        print(f"已生成简介: {digest.ready_count}")
        print(f"待生成简介: {digest.missing_count}")
        print(f"生成失败: {digest.failed_count}")
        return

    serve_port = _find_available_port(config.server_host, config.server_port)
    if serve_port != config.server_port:
        print(f"端口 {config.server_port} 已被占用，自动切换到 {serve_port}")

    blocks = create_blocks(config, digest_service)
    print(f"Gradio 页面地址: http://{config.server_host}:{serve_port}")
    blocks.launch(
        server_name=config.server_host,
        server_port=serve_port,
        inbrowser=False,
        share=False,
    )
