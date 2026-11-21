"""命令行入口：生成 A4 可打印的万花尺描摹画册。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from .model import (
    DEFAULT_SEED,
    MAX_CURVES,
    MIN_CURVES,
    Params,
    SpirodrawError,
    generate_params,
)
from .render import page_count, render_html


def _curves_count(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("曲线数量必须是整数：%s" % text) from exc
    if not MIN_CURVES <= value <= MAX_CURVES:
        raise argparse.ArgumentTypeError(
            "曲线数量必须在 %d~%d 之间" % (MIN_CURVES, MAX_CURVES)
        )
    return value


def _seed_value(text: str) -> int:
    try:
        return int(text, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("随机种子必须是整数：%s" % text) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spirodraw",
        description="万花尺描摹画册：用参数方程生成 A4 可打印的内摆线画册",
    )
    parser.add_argument("--version", action="version", version="spirodraw 0.1.0")
    parser.add_argument(
        "--curves",
        type=_curves_count,
        default=6,
        help="曲线数量（%d~%d，默认 6）" % (MIN_CURVES, MAX_CURVES),
    )
    parser.add_argument(
        "--seed",
        type=_seed_value,
        default=DEFAULT_SEED,
        help="随机种子（默认 %d，同种子结果一致）" % DEFAULT_SEED,
    )
    parser.add_argument(
        "--title", default="万花尺描摹画册", help="画册标题"
    )
    parser.add_argument(
        "-o", "--output", default="万花尺画册.html", help="输出 HTML 路径"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        params_list: Sequence[Params] = generate_params(
            args.curves, seed=args.seed
        )
        page = render_html(params_list, title=args.title)
    except SpirodrawError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 2

    try:
        Path(args.output).write_text(page, encoding="utf-8")
    except OSError as exc:
        print("错误: 写入文件失败: %s" % exc, file=sys.stderr)
        return 1

    print(
        "已生成 %s：%d 条曲线，共 %d 页 A4"
        % (args.output, len(params_list), page_count(len(params_list)))
    )
    print("最后一页是「自制万花尺」说明，抄下参数即可用真实画板复现")
    print("用浏览器打开后按 Ctrl/Cmd + P，纸张选 A4 纵向即可打印")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
