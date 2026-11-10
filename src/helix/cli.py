"""Helix 命令行入口。

用法：
    helix check model.helix
    helix run model.helix --end 500 --seed 1
    helix run model.helix --initial FURNACE=1650 --report out/report.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import HelixError
from .model import Model


def _parse_value(text: str) -> float | list[float]:
    """解析 NAME=VALUE；逗号分隔的值视为数组。"""
    if "," in text:
        return [float(item.strip()) for item in text.split(",")
                if item.strip()]
    return float(text)


def _parse_assignments(items: list[str]) -> dict[str, float | list[float]]:
    result: dict[str, float | list[float]] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"需要 NAME=VALUE: {item!r}")
        name, value = item.split("=", 1)
        result[name.strip()] = _parse_value(value.strip())
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helix",
        description="Helix modeling and simulation system",
    )
    parser.add_argument(
        "--version", action="version", version=f"helix {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="只编译模型，不运行")
    check.add_argument("model", type=Path)

    convert = sub.add_parser("convert", help="把旧 SLAM 模型转换为 Helix")
    convert.add_argument("source", type=Path)
    convert.add_argument("-o", "--output", type=Path, default=None)
    convert.add_argument("--slam-root", type=Path, default=None,
                         help="slam_v2 目录；默认查找同级目录")

    animate = sub.add_parser(
        "animate", help="把 DEBUG 目录转换为 HTML 动画播放器")
    animate.add_argument("debug_dir", type=Path)
    animate.add_argument("-o", "--output", type=Path, default=None)
    animate.add_argument("--title", default=None)

    run = sub.add_parser("run", help="编译并运行模型")
    run.add_argument("model", type=Path)
    run.add_argument("--start", type=float, default=0.0)
    run.add_argument("--end", type=float, default=None)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--clear-time", type=float, default=None)
    run.add_argument("--initial", action="append", default=[],
                     metavar="NAME=VALUE")
    run.add_argument("--constant", action="append", default=[],
                     metavar="NAME=VALUE")
    run.add_argument("--report", type=Path, default=None)
    run.add_argument("--debug", action="store_true")
    run.add_argument("--debug-path", type=Path, default=None)
    return parser


def _print_result(result) -> None:
    print(f"time: {result.now:.6f}")
    if result.observations:
        print("observations:")
        for item in result.observations:
            print(f"  {item.label}: n={item.count} "
                  f"mean={item.mean:.4f} std={item.std:.4f}")
    if result.queues:
        print("queues:")
        for item in result.queues:
            print(f"  {item.label}: avg={item.average_length:.4f}")
    if result.services:
        print("activities:")
        for item in result.services:
            print(f"  {item.activity}: completed={item.completed} "
                  f"util={item.average_utilization:.4f}")
    if result.resources:
        print("resources:")
        for item in result.resources:
            print(f"  {item.name}: util={item.average_held:.4f} "
                  f"wait={item.wait_count}")
    if result.continuous_final:
        print("continuous:")
        for name, value in result.continuous_final.items():
            print(f"  {name}={value:.6f}")


def _run(args: argparse.Namespace) -> int:
    model = Model.from_file(str(args.model))
    scenario = model.initialize(
        initial=_parse_assignments(args.initial),
        constants=_parse_assignments(args.constant),
    )
    result = scenario.run(
        start=args.start,
        end=args.end,
        seed=args.seed,
        clear_time=args.clear_time,
        debug=args.debug,
        debug_path=str(args.debug_path) if args.debug_path else None,
    )
    _print_result(result)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        result.report(str(args.report))
        print(f"report: {args.report}")
    return 0


def _check(args: argparse.Namespace) -> int:
    model = Model.from_file(str(args.model))
    print(f"ok: {model.project or 'HELIX'}")
    print(f"nodes: {len(model.nodes)}")
    print(f"variables: {len(model.variables)}")
    print(f"resources: {len(model.resources)}")
    return 0


def _convert(args: argparse.Namespace) -> int:
    from .convert import convert_file

    source, warnings = convert_file(
        args.source, slam_root=args.slam_root)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.output is None:
        print(source, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(source, encoding="utf-8")
        print(f"converted: {args.output}")
    return 0


def _animate(args: argparse.Namespace) -> int:
    from .animate import build_player

    output = args.output or (args.debug_dir / "player.html")
    build_player(args.debug_dir, output, title=args.title)
    print(f"player: {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "convert":
            return _convert(args)
        if args.command == "animate":
            return _animate(args)
        return _run(args)
    except (HelixError, ValueError, FileNotFoundError) as exc:
        print(f"helix: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
