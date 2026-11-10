"""TV Inspection Helix 全回路案例。

覆盖：模型编译 → initialize → run → 自动统计 → track 报告 → DEBUG。
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix


BASE = Path(__file__).resolve().parent
OUT = BASE / "out"


def main() -> None:
    model = helix.Model.from_file(str(BASE / "model.helix"))

    scenario = model.initialize()

    result = scenario.run(
        start=0,
        end=480,
        seed=1,
        debug=True,
        debug_path=str(OUT / "debug"),
    )

    print(result.summary())

    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="TV INSPECTION",
        analyst="Helix USER",
        track={
            "TIME IN SYSTEM": "SYSTEM.TIME",
            "Q1 WAIT": "QUEUE.Q1.WAIT",
            "INSPECT UTIL": "ACTIVITY.INSPECT.UTIL",
            "ADJUST UTIL": "ACTIVITY.ADJUST.UTIL",
        },
        plot=[],
    )
    print("report:", OUT / "report.md")
    print("debug:", OUT / "debug")


if __name__ == "__main__":
    main()
