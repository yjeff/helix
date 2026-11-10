"""Tanker Fleet 全回路案例（草稿，统计接近）。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

INITIAL = {
    "TANKER_LEVEL": 0.0,
    "STORAGE_LEVEL": 1000.0,
    "LOAD_AVAIL": 1.0,
    "UNLOAD_AVAIL": 1.0,
    "REFINERY_AVAIL": 1.0,
}


def main() -> None:
    model = helix.Model.from_file(str(BASE / "model.helix"))
    result = model.initialize(initial=INITIAL).run(
        end=365.0, seed=1, clear_time=65.0)

    observations = {item.label: item for item in result.observations}
    print("TANKER FLEET")
    print("WAITING TIME:", observations["WAITING TIME"].count,
          round(observations["WAITING TIME"].mean, 4))
    print("TRIP TIME:", observations["TRIP TIME"].count,
          round(observations["TRIP TIME"].mean, 4))
    print("final TANKER_LEVEL:",
          round(result.continuous_final["TANKER_LEVEL"], 3))
    print("final STORAGE_LEVEL:",
          round(result.continuous_final["STORAGE_LEVEL"], 3))

    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="TANKER FLEET",
        track={
            "TANKER LEVEL": "VAR.TANKER_LEVEL",
            "STORAGE LEVEL": "VAR.STORAGE_LEVEL",
        },
        plot=[],
    )
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
