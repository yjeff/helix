"""Truck Hauling Helix 全回路案例。

关键迁移点：
- SELECT ASM 保存 LOAD/TRKS/LDER 成员；
- FORK 复用原始卡车/装载机实体；
- 旧版对无 QUEUE 上游的 ACTIVITY 没有严格容量限制，
  因此 Helix 中 HAUL/DUMP/RETURN 显式设为 4 个并行服务台，
  LOADER_REST 设为 2 个，匹配 4 辆车、2 台装载机的实际资源。
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
    scenario = model.initialize(entities={
        "TRKS": [{}, {}, {}, {}],
        "LDER": [{}, {}],
    })

    result = scenario.run(
        start=0,
        end=560,
        seed=1230,
        debug=True,
        debug_path=str(OUT / "debug"),
    )

    print(result.summary())
    OUT.mkdir(exist_ok=True)
    result.report(
        str(OUT / "report.md"),
        project="TRUCK HAULING",
        track={
            "LOAD LENGTH": "QUEUE.LOAD.LENGTH",
            "TRUCK LENGTH": "QUEUE.TRKS.LENGTH",
            "LOADER LENGTH": "QUEUE.LDER.LENGTH",
            "LOADER1 UTIL": "ACTIVITY.L1.UTIL",
            "LOADER2 UTIL": "ACTIVITY.L2.UTIL",
        },
        plot=[],
    )
    print("report:", OUT / "report.md")


if __name__ == "__main__":
    main()
