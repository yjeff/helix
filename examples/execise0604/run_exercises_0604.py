"""Quarry Operations 全回路案例。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

MODEL = """
HELIX 1

var id entity
var tons entity
var svltime entity
var crsrtime entity
var rettime  entity
network
		create(count=9,id=[1,1,2,2,3,3,1,2,3],tons=[20,20,20,20,20,20,50,50,50],
				svltime=[5,5,5,5,5,5,10,10,10],crsrtime=[2,2,2,2,2,2,4,4,4],
				rettime=[1.5,1.5,1.5,1.5,1.5,1.5,2.0,2.0,2.0])
Loop:	if id = 1 goto SVL1
		else if id = 2 goto SVL2
		else goto SVL3
SVL1:	queue()
		activity(duration=expon(svltime)) -> ENDL
SVL2:	queue()
		activity(duration=expon(svltime)) -> ENDL
SVL3:	queue()
		activity(duration=expon(svltime)) -> ENDL
ENDL:	activity(duration=(rettime+1),servers=9)        ; 9个实体单独活动，所以servers=9
CRSR:	queue(order=HIGH(tons))
		activity(duration=expon(crsrtime)) 
		activity(duration=rettime) -> Loop
		end
"""

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1、先构造模型，便于在运行前检查语句/节点；也可以直接 
    # model = SLAM.Model.from_file(str(MODEL))
    model = helix.Model.from_source(str(MODEL))
    # 2、然后初始化变量和参数
    scenerio = model.initialize(
        )
    # 3、再运行
    result = scenerio.run(end=480.0, seed=1381)
    OUT.mkdir(exist_ok=True)
    # 4、最后生成报告
    result.report(
        str(OUT / "report.md"),
        project="Quarry Operations",
    )
    print("report:", OUT / "report.md")

if __name__ == "__main__":
    main()