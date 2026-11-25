"""Work sttion in series 全回路案例。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

MODEL = """
HELIX 1

VAR LAST_BALK GLOBAL
NETWORK
        CREATE(interval=EXPON(0.4))
  q1:   QUEUE(capacity=4, on_full=BALK(sub))
  A1:   ACTIVITY(duration=EXPON(0.25))
  q2:   QUEUE(capacity=2, on_full=BLOCK)
  A2:   ACTIVITY(duration=EXPON(0.5))
        EXIT
  sub:  OBSERVE("BALK INTERVAL", TNOW - LAST_BALK)
        ASSIGN(LAST_BALK=TNOW)
        EXIT
END
"""

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 先构造模型，便于在运行前检查语句/节点；也可以直接 
    # model = SLAM.Model.from_file(str(MODEL))
    model = helix.Model.from_source(str(MODEL))
    # 然后初始化变量和参数
    scenerio = model.initialize(
            initial={"LAST_BALK": 0}
        )
    # 再运行
    result = scenerio.run(end=300.0, seed=1)
 
    OUT.mkdir(exist_ok=True)
    # 最后生成报告
    result.report(
        str(OUT / "report.md"),
        project="Work Station in Series",
    )
    print("report:", OUT / "report.md")

if __name__ == "__main__":
    main()