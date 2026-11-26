"""Helix 命令行入口。

用法：
    helix check model.helix
    helix run model.helix --end 500 --seed 1
    helix run model.helix --initial FURNACE=1650 --report out/report.md
"""
from __future__ import annotations

import argparse
import math
import statistics
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
    run.add_argument("--replicas", type=int, default=1,
                     help="独立重复运行次数；输出 95%% 半宽")
    run.add_argument("--keep-samples", action="store_true",
                     help="保留原始观测样本（默认只保留在线统计）")
    run.add_argument("--rng", choices=("substreams", "global"),
                     default="substreams",
                     help="随机数流模式；global 仅用于兼容旧基线")
    run.add_argument("--max-events", type=int, default=1_000_000,
                     help="总事件数上限")
    run.add_argument("--max-same-time-events", type=int, default=100_000,
                     help="同一时刻事件数上限")
    run.add_argument("--clear-time", type=float, default=None)
    run.add_argument("--initial", action="append", default=[],
                     metavar="NAME=VALUE")
    run.add_argument("--constant", action="append", default=[],
                     metavar="NAME=VALUE")
    run.add_argument("--report", type=Path, default=None)
    run.add_argument("--manifest", type=Path, default=None,
                     help="写出本次运行的 JSON manifest")
    run.add_argument("--debug", action="store_true")
    run.add_argument("--debug-path", type=Path, default=None)

    compare = sub.add_parser(
        "compare", help="用相同的运行设置对比两个模型")
    compare.add_argument("models", nargs=2, type=Path,
                         metavar=("MODEL_A", "MODEL_B"))
    compare.add_argument("--start", type=float, default=0.0)
    compare.add_argument("--end", type=float, default=None)
    compare.add_argument("--seed", type=int, default=0)
    compare.add_argument("--replicas", type=int, default=10,
                         help="每个模型独立重复运行次数")
    compare.add_argument("--clear-time", type=float, default=None)
    compare.add_argument("--initial", action="append", default=[],
                         metavar="NAME=VALUE")
    compare.add_argument("--constant", action="append", default=[],
                         metavar="NAME=VALUE")
    compare.add_argument("--rng", choices=("substreams", "global"),
                         default="substreams")
    compare.add_argument("--independent", action="store_true",
                         help="不按相同 seed 配对，分别计算置信区间")
    compare.add_argument("--max-events", type=int, default=1_000_000)
    compare.add_argument("--max-same-time-events", type=int, default=100_000)
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


def _t95(df: int) -> float:
    table = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    }
    return table.get(df, 1.96)


def _mean_half(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = statistics.mean(values)
    if len(values) < 2:
        return mean, 0.0
    half = _t95(len(values) - 1) * statistics.stdev(values) / math.sqrt(
        len(values))
    return mean, half


def _replica_sections(results) -> list[tuple[str, list[str], list[list[str]]]]:
    sections: list[tuple[str, list[str], list[list[str]]]] = []

    labels = sorted({item.label for result in results
                     for item in result.observations})
    rows = []
    for label in labels:
        values = []
        for result in results:
            item = next((x for x in result.observations
                         if x.label == label), None)
            if item is not None and item.count:
                values.append(item.mean)
        mean, half = _mean_half(values)
        rows.append([label, f"{mean:.4f}", f"±{half:.4f}", str(len(values))])
    if rows:
        sections.append(("OBSERVATIONS (95% half-width)",
                         ["LABEL", "MEAN", "HALF-WIDTH", "RUNS"], rows))

    rows = []
    for name in sorted({x.label for result in results for x in result.queues}):
        values = [x.average_length for result in results
                  for x in result.queues if x.label == name]
        mean, half = _mean_half(values)
        rows.append([name, f"{mean:.4f}", f"±{half:.4f}", str(len(values))])
    if rows:
        sections.append(("QUEUES", ["QUEUE", "AVG LENGTH", "HALF-WIDTH",
                                    "RUNS"], rows))

    rows = []
    for name in sorted({x.activity for result in results
                        for x in result.services}):
        util = [x.average_utilization for result in results
                for x in result.services if x.activity == name]
        completed = [x.completed for result in results
                     for x in result.services if x.activity == name]
        mean, half = _mean_half(util)
        done_mean, done_half = _mean_half([float(x) for x in completed])
        rows.append([name, f"{mean:.4f}", f"±{half:.4f}",
                     f"{done_mean:.1f}", f"±{done_half:.1f}"])
    if rows:
        sections.append(("ACTIVITIES", ["ACTIVITY", "AVG SVC UTIL.",
                                        "HALF-WIDTH", "COMPLETED",
                                        "HALF-WIDTH"], rows))

    rows = []
    for name in sorted({x.name for result in results
                        for x in result.resources}):
        held = [x.average_held for result in results
                for x in result.resources if x.name == name]
        wait = [float(x.wait_count) for result in results
                for x in result.resources if x.name == name]
        mean, half = _mean_half(held)
        wait_mean, wait_half = _mean_half(wait)
        rows.append([name, f"{mean:.4f}", f"±{half:.4f}",
                     f"{wait_mean:.1f}", f"±{wait_half:.1f}"])
    if rows:
        sections.append(("RESOURCES", ["RESOURCE", "AVG HELD", "HALF-WIDTH",
                                       "WAIT COUNT", "HALF-WIDTH"], rows))

    rows = []
    for name in sorted({x.label for result in results
                        for x in result.awaits}):
        values = [x.average_length for result in results
                  for x in result.awaits if x.label == name]
        mean, half = _mean_half(values)
        rows.append([name, f"{mean:.4f}", f"±{half:.4f}", str(len(values))])
    if rows:
        sections.append(("WAIT FILES", ["WAIT FILE", "AVG LENGTH",
                                        "HALF-WIDTH", "RUNS"], rows))
    return sections


def _print_replicas(results) -> None:
    print(f"replicas: {len(results)}")
    for title, headers, rows in _replica_sections(results):
        print(title)
        print("  " + " | ".join(headers))
        for row in rows:
            print("  " + " | ".join(row))


def _run(args: argparse.Namespace) -> int:
    if args.replicas < 1:
        raise ValueError("--replicas 必须 >= 1")
    if args.replicas > 1 and args.debug:
        raise ValueError("--replicas 与 --debug 不能同时使用")

    model = Model.from_file(str(args.model))
    scenario = model.initialize(
        initial=_parse_assignments(args.initial),
        constants=_parse_assignments(args.constant),
    )
    retain_samples = bool(getattr(args, "keep_samples", False))
    if args.replicas == 1:
        result = scenario.run(
            start=args.start,
            end=args.end,
            seed=args.seed,
            clear_time=args.clear_time,
            debug=args.debug,
            debug_path=str(args.debug_path) if args.debug_path else None,
            retain_samples=retain_samples,
            rng_mode=args.rng,
            max_events=args.max_events,
            max_same_time_events=args.max_same_time_events,
        )
        _print_result(result)
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            result.report(str(args.report))
            print(f"report: {args.report}")
        if args.manifest is not None:
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            result.write_manifest(args.manifest)
            print(f"manifest: {args.manifest}")
        return 0

    replica = scenario.run_replicas(
        args.replicas,
        start=args.start,
        end=args.end,
        seed=args.seed,
        clear_time=args.clear_time,
        retain_samples=retain_samples,
        rng_mode=args.rng,
        max_events=args.max_events,
        max_same_time_events=args.max_same_time_events,
    )
    _print_replicas(replica.results)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        replica.report(args.report)
        print(f"report: {args.report}")
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        replica.write_manifest(args.manifest)
        print(f"manifest: {args.manifest}")
    return 0


def _check(args: argparse.Namespace) -> int:
    model = Model.from_file(str(args.model))
    print(f"ok: {model.project or 'HELIX'}")
    print(f"nodes: {len(model.nodes)}")
    print(f"variables: {len(model.variables)}")
    print(f"resources: {len(model.resources)}")
    for warning in model.structure_warnings():
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def _animate(args: argparse.Namespace) -> int:
    from .animate import build_player

    output = args.output or (args.debug_dir / "player.html")
    build_player(args.debug_dir, output, title=args.title)
    print(f"player: {output}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    if args.replicas < 1:
        raise ValueError("--replicas 必须 >= 1")
    initial = _parse_assignments(args.initial)
    constants = _parse_assignments(args.constant)
    runs = []
    for path in args.models:
        model = Model.from_file(str(path))
        scenario = model.initialize(initial=initial, constants=constants)
        results = [
            scenario.run(
                start=args.start,
                end=args.end,
                seed=args.seed + offset,
                clear_time=args.clear_time,
                retain_samples=False,
                rng_mode=args.rng,
                max_events=args.max_events,
                max_same_time_events=args.max_same_time_events,
            )
            for offset in range(args.replicas)
        ]
        runs.append(results)

    left, right = runs
    paired = not args.independent
    print(f"compare: {args.models[0]} vs {args.models[1]}")
    print(f"replicas: {args.replicas} ({'paired' if paired else 'independent'})")

    def diff_interval(a_values, b_values):
        if paired:
            count = min(len(a_values), len(b_values))
            diffs = [a_values[i] - b_values[i] for i in range(count)]
            return _mean_half(diffs)
        a_mean, a_half = _mean_half(a_values)
        b_mean, b_half = _mean_half(b_values)
        return a_mean - b_mean, math.hypot(a_half, b_half)

    labels = sorted({x.label for r in left for x in r.observations}
                    | {x.label for r in right for x in r.observations})
    mode_text = "paired by seed" if paired else "independent"
    print(f"OBSERVATIONS (mean ± 95% half-width, {mode_text})")
    print("  LABEL | A | B | DIFF")
    for label in labels:
        a_values = [x.mean for r in left for x in r.observations
                    if x.label == label and x.count]
        b_values = [x.mean for r in right for x in r.observations
                    if x.label == label and x.count]
        a_mean, a_half = _mean_half(a_values)
        b_mean, b_half = _mean_half(b_values)
        diff_mean, diff_half = diff_interval(a_values, b_values)
        print(f"  {label} | {a_mean:.4f} ±{a_half:.4f} | "
              f"{b_mean:.4f} ±{b_half:.4f} | "
              f"{diff_mean:+.4f} ±{diff_half:.4f}")

    names = sorted({x.name for r in left for x in r.resources}
                   | {x.name for r in right for x in r.resources})
    print("RESOURCES (avg held, mean ± 95% half-width, paired by seed)")
    print("  RESOURCE | A | B | DIFF")
    for name in names:
        a_values = [x.average_held for r in left for x in r.resources
                    if x.name == name]
        b_values = [x.average_held for r in right for x in r.resources
                    if x.name == name]
        a_mean, a_half = _mean_half(a_values)
        b_mean, b_half = _mean_half(b_values)
        diff_mean, diff_half = diff_interval(a_values, b_values)
        print(f"  {name} | {a_mean:.4f} ±{a_half:.4f} | "
              f"{b_mean:.4f} ±{b_half:.4f} | "
              f"{diff_mean:+.4f} ±{diff_half:.4f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "animate":
            return _animate(args)
        if args.command == "compare":
            return _compare(args)
        return _run(args)
    except (HelixError, ValueError, FileNotFoundError) as exc:
        print(f"helix: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
