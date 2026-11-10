"""Helix 示例：Inventory System with Lost Sales and Backorders。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix


MODEL = Path(__file__).with_name("model.helix")
OUT = Path(__file__).resolve().parent / "out"


def main() -> None:
    model = helix.Model.from_file(str(MODEL))
    result = model.initialize(initial={
        "invposition": 72,
        "reorderpos": 18,
        "invcontrolpos": 72,
        "LAST_LOST": 0,
        "HAS_LOST": 0,
    }).run(end=312, clear_time=52, seed=1)

    print(result.summary())
    OUT.mkdir(exist_ok=True)
    result.report(OUT / "report.md")
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
