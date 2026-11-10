"""Soaking Pit 草稿运行程序。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

TEMPS = [0.0] * 10
ACTIVE = [0.0] * 10
RATES = [0.15] * 10


def main() -> None:
    model = helix.Model.from_file(str(BASE / "model.helix"))
    result = model.initialize(initial={
        "FURNACE": 1650.0,
        "TEMP": TEMPS,
        "ACTIVE": ACTIVE,
        "C": RATES,
    }).run(end=500.0, seed=4)

    final = result.continuous_final
    print("SOAKING PIT")
    print("t_end:", result.now)
    print("FURNACE:", round(final["FURNACE"], 3))
    print("MAX_TEMP:", round(final["MAX_TEMP"], 3))
    print("TEMP:", [round(final[f"TEMP[{i}]"], 1)
                     for i in range(1, 11)])
    print("ACTIVE:", [result.global_values[f"ACTIVE[{i}]"]
                       for i in range(1, 11)])

    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="SOAKING PIT",
        track={"FURNACE": "VAR.FURNACE", "MAX TEMP": "VAR.MAX_TEMP"},
        plot=[],
    )
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
