"""Machine Breakdown 5-run comparison case."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"


def main() -> None:
    model = helix.Model.from_file(str(BASE / "model.helix"))
    rows = []
    for seed in range(5):
        result = model.initialize().run(end=1000.0, seed=seed)
        services = {s.activity: s for s in result.services}
        production = (services["ACTIVITY_1"].average_utilization
                      + services["ACTIVITY_2"].average_utilization)
        repair = services["ACTIVITY_3"].average_utilization
        rows.append((seed, result.observations[0].mean,
                     production, repair))

    print("MACHINE BREAKDOWN")
    print("run  time    tool_use  repair")
    for seed, time_in_system, production, repair in rows:
        print(f"{seed:<4} {time_in_system:7.2f} {production:9.2f} "
              f"{repair:7.2f}")
    print("avg time:", round(sum(r[1] for r in rows) / len(rows), 2))
    print("avg tool use:", round(sum(r[2] for r in rows) / len(rows), 2))
    print("avg repair:", round(sum(r[3] for r in rows) / len(rows), 2))

    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="MACHINE BREAKDOWN",
        track={
            "TIME IN SYSTEM": "SYSTEM.TIME",
            "TOOL USE": "ACTIVITY.ACTIVITY_1.UTIL",
        },
        plot=[],
    )
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
