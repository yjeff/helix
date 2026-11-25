"""Helix 示例：Port Operations with Storm and Priority Wait Files。"""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix


MODEL = Path(__file__).with_name("model.helix")
OUT = Path(__file__).resolve().parent / "out"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    model = helix.Model.from_file(str(MODEL))
    result = model.initialize().run(end=8640, seed=args.seed)

    print(result.summary())
    for item in result.awaits:
        print(f"WAIT FILE {item.label}: avg={item.average_length:.4f} "
              f"std={item.std_length:.4f} max={item.max_length}")
    OUT.mkdir(exist_ok=True)
    report = OUT / f"report_seed{args.seed}.md"
    result.report(report)
    print("report:", report)


if __name__ == "__main__":
    main()
