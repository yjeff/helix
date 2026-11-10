"""Helix 示例：Quarry Operations。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix


MODEL = Path(__file__).with_name("model.helix")
OUT = Path(__file__).resolve().parent / "out"


def main() -> None:
    model = helix.Model.from_file(str(MODEL))
    result = model.initialize().run(end=480, seed=0)

    print(result.summary())
    OUT.mkdir(exist_ok=True)
    result.report(OUT / "report.md")
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
