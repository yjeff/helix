"""Liquid Level Control 全回路案例。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"


def main() -> None:
    model = helix.Model.from_file(str(BASE / "model.helix"))
    result = model.initialize(
        initial={"LEVEL": 60.0, "PUMP_ON": 0.0},
        constants={"QIN": 3.0, "QOUT": 4.0},
    ).run(end=80.0, seed=1)

    levels = [row["values"]["LEVEL"] for row in result.continuous]
    highs = sum(1 for a, b in zip(levels, levels[1:])
                if a <= 80.0 < b)
    lows = sum(1 for a, b in zip(levels, levels[1:])
               if a >= 20.0 > b)

    print("LIQUID LEVEL CONTROL")
    print("final LEVEL:", round(result.continuous_final["LEVEL"], 4))
    print("max LEVEL:", round(max(levels), 4))
    print("min LEVEL:", round(min(levels), 4))
    print("high crossings:", highs)
    print("low crossings:", lows)
    print("PUMP_ON:", result.continuous_final["PUMP_ON"])

    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="LIQUID LEVEL CONTROL",
        track={
            "LEVEL": "VAR.LEVEL",
            "PUMP ON": "VAR.PUMP_ON",
        },
        plot=["LEVEL", "PUMP_ON"],
    )
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
