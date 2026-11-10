"""Inventory Problem 全回路案例。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import helix

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"

MODEL1 = """
HELIX 1

var		    invposition global
var		    reorderpos  global
var		    invcontrolpos global
var		    ordernum global
VAR         LAST_OBS GLOBAL
VAR         HAS_OBS GLOBAL
resource	radio(capacity=72,mode=restock)
network
		; Customer arrival process
        ; -------------------------
		create(interval=expon(0.2))
		if AVAILABLE(radio) > 0 OR random() <= 0.2 -> G
		else goto Lost
G:		assign(invposition=invposition-1)
		await(radio)
		exit
Lost:	IF HAS_OBS = 1 -> RECORD
        ELSE -> MARK
RECORD: OBSERVE("Customer Lost", TNOW - LAST_OBS) -> MARK
MARK:   ASSIGN(LAST_OBS=TNOW, HAS_OBS=1)
		exit

		;Inventory review process
        ;------------------------
		create(interval=4)
		if invposition <= reorderpos -> R
        else -> E
R:		assign(ordernum=invcontrolpos - invposition, invposition = invcontrolpos)
		activity(duration=3)
		OBSERVE(name="Safety Stock", value=AVAILABLE(radio))
		free(resource=radio, units=ordernum)
E:		exit
		end
"""

MODEL = """
HELIX 1
PROJECT "INVENTORY PROBLEM"
; 库存位置、再订货点、库存控制水平、本次订货量
VAR 		invposition GLOBAL
VAR 		reorderpos GLOBAL
VAR 		invcontrolpos GLOBAL
VAR 		orderqty GLOBAL
; 用于统计两次 lost sale 之间的时间
VAR 		LAST_LOST GLOBAL
VAR 		HAS_LOST GLOBAL
; 书店中的 RADIO 现货资源。RESTOCK 模式只维护 available：
; AWAIT 减少 available，FREE 增加 available，不要求持有者账本。
RESOURCE radio(capacity=72, mode=RESTOCK)
NETWORK
  		    ; 顾客到达过程
  		    CREATE(interval=EXPON(0.2))
  		    ; 有现货，或者顾客愿意欠单（20%）才进入购买路径
  CHECK: 	IF AVAILABLE(radio) > 0 OR RANDOM() <= 0.2 -> BUY
  		    ELSE -> LOST
  BUY: 	    ASSIGN(invposition=invposition-1)
       		AWAIT(resource=radio, units=1)
       		EXIT()
            ; 80% 的缺货顾客流失
  LOST: 	IF HAS_LOST = 1 -> RECORD
  		    ELSE -> MARK
  RECORD:   OBSERVE("TIME BETWEEN LOST SALES", TNOW - LAST_LOST) -> MARK
  MARK: 	ASSIGN(LAST_LOST=TNOW, HAS_LOST=1)
        	EXIT()
            ; 每四周一次的库存检查
  		    CREATE(interval=4)
  REVIEW_CHECK: IF invposition <= reorderpos -> REVIEW
  		    ELSE -> SKIP
  REVIEW:   ASSIGN(orderqty=invcontrolpos-invposition,
                 invposition=invcontrolpos)
          	ACTIVITY(duration=3)
          	OBSERVE("SAFETY STOCK", AVAILABLE(radio))
          	FREE(resource=radio, units=orderqty)
          	EXIT()
  SKIP: 	EXIT()
END
"""

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1、先构造模型，便于在运行前检查语句/节点；也可以直接 
    # model = SLAM.Model.from_file(str(MODEL))
    model = helix.Model.from_source(str(MODEL))
    # 2、然后初始化变量和参数
    scenerio = model.initialize(
        initial={'invposition':72, 'reorderpos':18, 'invcontrolpos':72,'LAST_LOST':0, 'HAS_LOST':0}
        )
    # 3、再运行
    result = scenerio.run(end=312, clear_time=52, seed=1)
    OUT.mkdir(exist_ok=True)
    # 4、最后生成报告
    result.report(
        str(OUT / "report.md"),
        project="Inventory Problem",
    )
    print("report:", OUT / "report.md")

if __name__ == "__main__":
    main()