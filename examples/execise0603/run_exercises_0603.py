"""Truck Hauling Situation 全回路案例。"""
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
		CREATE(count=4) -> trks                                     ; 初始资源: 4 辆卡车、2 台装载机
        CREATE(count=2) -> lder
        CREATE(interval=ERLNG(4.0,2.0), first=0, until=480) -> J    ; 后续到达的装载请求
J:		JOIN(count=2, merge=FIRST) -> load
load:	queue() -> begn
trks:	queue() -> begn
lder:	queue() -> begn
begn:	select(queue_rule=ASM, server_rule=LIT,
			  queues=[load,trks,lder],servers=[load1,load2])
load1:	activity(duration=expon(14.0)) -> F
load2:	activity(duration=expon(12.0)) -> F
F:		FORK(branches=[lder -> L, trks -> T])
L:		activity(duration=5,servers=2) -> lder
T:		activity(duration=rnorm(22.0,3.0),servers=4)		    ; Truck Hauling Time
		activity(duration=unfrm(2.0,8.0),servers=4)		        ; Truck Dumping Time
		activity(duration=rnorm(18.0,3.0),servers=4) -> trks	; Truck Return Time
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
        project="Truck Hauling Situation",
    )
    print("report:", OUT / "report.md")

if __name__ == "__main__":
    main()