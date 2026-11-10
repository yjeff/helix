"""Cedar Bog Lake 全连续案例。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

INITIAL = {
    "PLANTS": 0.83,
    "HERBIVORES": 0.003,
    "CARNIVORES": 0.0001,
    "ORGANIC": 0.0,
    "ENVIRONMENT": 0.0,
}


def main() -> None:
    model = helix.Model.from_file(str(BASE / "model.helix"))
    result = model.initialize(initial=INITIAL).run(end=2.0)
    print("samples:", len(result.continuous), "t:", result.now)
    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="CEDAR BOG LAKE",
        track={
            "PLANTS": "VAR.PLANTS",
            "HERBIVORES": "VAR.HERBIVORES",
            "CARNIVORES": "VAR.CARNIVORES",
        },
        plot=["PLANTS", "HERBIVORES", "CARNIVORES"],
    )
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
