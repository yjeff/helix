"""Televison and Adjustment 全回路案例。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

MODEL = """
HELIX 1

network
		        create(interval=unfrm(3.5, 7.5))
insp:	        queue()
inspection:		activity(duration=unfrm(6.0,12.0),servers=2)
		        if random() > 0.15 goto dprt
                else goto adjt
adjt:	        queue()
adjustion:      activity(duration=unfrm(20.0,40.0)) -> insp
dprt:	        exit
end
"""

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 先构造模型，便于在运行前检查语句/节点；也可以直接 
    # model = SLAM.Model.from_file(str(MODEL))
    model = helix.Model.from_source(str(MODEL))
    # 然后初始化变量和参数
    scenerio = model.initialize(
        )
    # 再运行
    for seed in range(10):
        result = model.initialize().run(end=480, seed=seed)
        services = {s.activity: s for s in result.services}
        queues = {q.label: q for q in result.queues}
        print(seed,
              services["inspection"].completed,
              services["adjustion"].completed,
              services["adjustion"].average_utilization,
              queues["adjt"].average_length)
    
    result = scenerio.run(end=480.0, seed=1381)
 
    OUT.mkdir(exist_ok=True)
    # 最后生成报告
    result.report(
        str(OUT / "report.md"),
        project="Televison and Adjustment",
    )
    print("report:", OUT / "report.md")

if __name__ == "__main__":
    main()