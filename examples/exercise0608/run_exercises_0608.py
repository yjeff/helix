"""Port Operations 全回路案例。"""
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
var load_time entity
var rank entity
var pob global
var last_time entity

resource berth(capacity=3)
resource tug(capacity=1)
network
		; Tanker Arrival Segment
		create(interval=unfrm(4.0,18.0))
		assign(pob = unfrm(0,1))
		if pob <=0.25 -> arv1
		else if pob <= 0.80 -> arv2
		else -> arv3
arv1:	assign(load_time = unfrm(16.0,20.0), id = 1) -> port
arv2:	assign(load_time = unfrm(21.0,27.0), id = 2) -> port
arv3:	assign(load_time = unfrm(32.0,40.0), id = 3) -> port
		create(interval=48, first=0, count=5)
arv4:	assign(load_time = unfrm(18.0,24.0), id = 4) -> port

		; Port Operation Segment
port:	assign(last_time = TNOW)
		await(resource=berth,priority=0)
		await(resource=tug,priority=2)
		activity(duration=1.0)
		free(resource=tug)
		activity(duration=load_time, servers=3)
		await(resource=tug, priority=1)
		activity(duration=1)
		free(berth)
		free(tug)
		if id = 1 -> dpt1
		else if id = 2 -> dpt2
		else if id = 3 -> dpt3
		else -> dpt4
dpt1:	observe("T1 IN PORT TIME", TNOW-last_time)
		assign(last_time = TNOW)
		exit
dpt2:	observe("T2 IN PORT TIME", TNOW-last_time)
		assign(last_time = TNOW)
		exit
dpt3:	observe("T3 IN PORT TIME", TNOW-last_time)
		assign(last_time = TNOW)
		exit
dpt4:	observe("T4 IN PORT TIME", TNOW-last_time)
		assign(last_time = TNOW)
		activity(duration=unfrm(216.0,264.0),servers=5) -> arv4
		
        ;Storm Segment
		create(count=1)
        activity(duration=expon(48.0))     ; storm wait time
storm:	alter(resource=tug, capacity=0)
		activity(duration=unfrm(2.0,6.0))
		alter(resource=tug, capacity=1)
        activity(duration=expon(48.0)) -> storm
end
"""

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1、先构造模型，便于在运行前检查语句/节点；也可以直接 
    # model = SLAM.Model.from_file(str(MODEL))
    model = helix.Model.from_source(str(MODEL))
    # 2、然后初始化变量和参数
    scenerio = model.initialize(
        initial={'pob':0}
        )
    # 3、再运行
    result = scenerio.run(end=8640, seed=4)
    OUT.mkdir(exist_ok=True)
    # 4、最后生成报告
    result.report(
        str(OUT / "report.md"),
        project="Port Operations",
    )
    print("report:", OUT / "report.md")

if __name__ == "__main__":
    main()