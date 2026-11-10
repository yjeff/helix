# Helix 语法规范 v1.0

状态：语法草案，对应语义规范 v1.0。  
实现：`helix`。  
不兼容旧 SLAM 语法。

---

## 1. 总体结构

只有两个块：

```text
NETWORK ... END
EQUATION ... END
```

`END` 关闭当前块，不需要重复块名。  
旧的 `END NETWORK` / `END EQUATION` 仍可解析，但不再推荐。

其余全部是顶层声明语句。

```text
HELIX 1

PROJECT "TANKER FLEET"

VAR TANKER_LEVEL AS "TANKER LEVEL" RANGE 0..300
VAR STORAGE_LEVEL AS "STORAGE LEVEL" RANGE 0..2000
VAR LOAD_AVAIL

CONTINUOUS METHOD=RK4, MIN_STEP=0.0025, SAVE_STEP=0.25, MAX_STEP=0.25

RESOURCE DOCK(capacity=1)
GATE LIGHT1(state=CLOSED)

DETECT name=HI, when=TANKER_LEVEL >= 80
SEVNT code=1, when=TANKER_LEVEL > 95

EQUATION
  DD(TANKER_LEVEL) = ...
END

NETWORK
  CREATE(interval=EXPON(0.4))
  QUEUE(capacity=4, on_full=BALK(SUB))
  ACTIVITY(duration=EXPON(0.25))
  TERMINATE()

  SUB: TERMINATE()
END
```

---

## 2. 行与注释

语句以换行结束，不再使用分号作为语句结束符。

```text
CREATE(interval=EXPON(0.4))
QUEUE(capacity=4)
ACTIVITY(duration=EXPON(0.25))
```

括号未闭合时自动续行：

```text
BEGN: SELECT(
  queue_rule=ASM,
  server_rule=LIT,
  queues=[LOAD, TRKS, LDER],
  servers=[LOAD1, LOAD2],
)
```

注释：

```text
; 后到行尾都是注释
```

示例：

```text
; TV inspection
CREATE(interval=UNFRM(3.5, 7.5))   ; 到达间隔
```

不使用 `*` 注释。

---

## 3. 标识符与标签

标识符：

```text
字母、数字、下划线
不能以数字开头
```

标签：

```text
LABEL:
```

示例：

```text
Q1: QUEUE(capacity=4)
A1: ACTIVITY(duration=EXPON(0.25))
```

规则：

```text
只有被引用时才需要标签
标签后面用冒号
不使用 LABEL =
= 只用于参数和方程
```

匿名节点：

```text
QUEUE(capacity=4)
ACTIVITY(duration=EXPON(0.25))
TERMINATE()
```

---

## 4. 顺序默认与转移覆盖

线性网络直接顺序书写：

```text
CREATE(interval=EXPON(0.4))
QUEUE(capacity=4, on_full=BALK(SUB))
ACTIVITY(duration=EXPON(0.25))
TERMINATE()
```

默认连接：

```text
CREATE -> QUEUE -> ACTIVITY -> TERMINATE
```

需要跳转时，`->` 和 `GOTO` 等价：

```text
A2: ACTIVITY(duration=EXPON(0.5))
  -> Q1
```

```text
A2: ACTIVITY(duration=EXPON(0.5))
  GOTO Q1
```

也可以写在同一行：

```text
A2: ACTIVITY(duration=EXPON(0.5)) GOTO Q1
```

规则：

```text
没有转移 → 连接下一条网络语句
有转移   → 使用显式目标，不再默认连接
-> 与 GOTO 完全等价
```

但“连接下一条”只适用于普通线性节点。以下情况不会自动连接：

```text
有显式 -> / GOTO
TERMINATE / EXIT
IF / PARALLEL / SPLIT 的分支目标
FORK 的 branches 目标
SELECT 引用的 queues / servers
两个相邻的分支根之间
```

例如：

```text
CHECK: IF ... -> A
ELSE -> B

A: ACTIVITY(1)
B: ACTIVITY(2)
```

`A` 和 `B` 是互斥分支，不会自动形成 `A -> B`。

如果某个分支目标执行完还要继续到另一个节点，必须显式写：

```text
A: ACTIVITY(1) -> B
```

同样：

```text
Lost: IF HAS_OBS = 1 -> RECORD
      ELSE -> MARK

RECORD: OBSERVE("Customer Lost", TNOW - LAST_OBS) -> MARK
MARK:   ASSIGN(LAST_OBS=TNOW, HAS_OBS=1)
```

`RECORD` 和 `MARK` 都是 `Lost` 的分支根，必须显式写 `RECORD -> MARK`。

`GOTO` 同样适用于：

```text
A GOTO B
IF ... GOTO TARGET
ELSE IF ... GOTO TARGET
ELSE GOTO TARGET
PATH GOTO TARGET
PATH part GOTO TARGET
FORK(branches=[ROLE GOTO TARGET])
```

---

## 5. 声明语句

### PROJECT

```text
PROJECT "TV INSPECTION"
```

### VAR

```text
VAR TANKER_LEVEL AS "TANKER LEVEL" RANGE 0..300
VAR LOAD_AVAIL
VAR LOAD_START ENTITY
VAR SYSTEM_OPEN GLOBAL
VAR TEMP[10]
```

规则：

```text
一条 VAR 声明一个变量
AS 后是报告标签
RANGE 可选
GLOBAL 显式全局变量
ENTITY 显式实体属性
NAME[n] 声明全局数组，下标 1..n
不写作用域时按使用位置推断
```

数组：

```text
VAR TEMP[10]
DD(TEMP[1]) = ...
TEMP[2] = ... 或 ASSIGN(TEMP[2]=...)
SUM(ACTIVE) 返回数组所有元素之和
```

数组只支持 GLOBAL。

推断规则：

```text
出现在 EQUATION/DETECT/SEVNT 中 → GLOBAL
其余 → ENTITY
```

实体初值由 `entities` 提供；全局初值由 Python `initial` 提供。

### CONTINUOUS

```text
CONTINUOUS METHOD=RK4, MIN_STEP=0.001, SAVE_STEP=0.1, MAX_STEP=0.1
```

或自适应：

```text
CONTINUOUS METHOD=RKF45, MIN_STEP=0.0001,
           SAVE_STEP=0.1, MAX_STEP=0.1, TOL=1e-6
```

字段：

```text
METHOD     RK4 / RKF45
MIN_STEP
SAVE_STEP
MAX_STEP
TOL        RKF45 相对误差容限
```

`CONTINUOUS` 是兼容用的默认值。推荐在 `initialize` 中覆盖：

```python
scenario = model.initialize(
    continuous={
        "method": "RKF45",
        "min_step": 1e-4,
        "save_step": 0.1,
        "max_step": 0.1,
        "tol": 1e-6,
    },
)
scenario.run(end=500)
```

### RESOURCE

```text
RESOURCE DOCK(capacity=1)
RESOURCE TOOL(capacity=2)
RESOURCE radio(capacity=72, mode=RESTOCK)
```

单参数简写：

```text
RESOURCE DOCK(1)
RESOURCE TOOL(2)
```

等价于 `capacity=`。

模式：

```text
POOL     默认，可借还，维护持有者
RESTOCK  库存，只维护 available，不要求先 AWAIT 再 FREE
```

RESTOCK：

```text
AWAIT = available -= units
FREE  = available += units，最多到 capacity
不支持 PREEMPT
HELD = capacity - available
```

运行时查询：

```text
AVAILABLE(DOCK)
CAPACITY(DOCK)
HELD(DOCK)
```

```text
AVAILABLE = CAPACITY - HELD
只读，不改变资源
可用于 IF / OBSERVE / ASSIGN / duration
```

### GATE

```text
GATE LIGHT1(state=CLOSED)
GATE LIGHT2(state=OPEN)
```

单参数简写：

```text
GATE LIGHT1(CLOSED)
GATE LIGHT2(OPEN)
```

等价于 `state=`。

### DETECT

```text
DETECT name=HI, when=TANKER_LEVEL >= 80
DETECT name=LO, when=TANKER_LEVEL <= 20, edge=FALLING
```

默认：

```text
edge=RISING
tol=0.01
```

网络中的 DETECT 节点：

```text
ENDU: DETECT(when=TANKER_LEVEL > 7.5, edge=FALLING)
  -> TERM
```

触发后：

```text
释放等待该事件名的 ACTIVITY(until=...)
向节点后继发送一个信号实体
```

### SEVNT

```text
SEVNT name=DUMP_READY, code=2, when=STORAGE_LEVEL > 50
```

普通等待事件必须有 `name`：

```text
SEVNT name=DUMP_READY, code=2, when=STORAGE_LEVEL > 50
```

可选动作：

```text
SEVNT name=DUMP_READY, code=2, when=..., action=SET_FLAG
```

`code=1` 保留为系统停止事件，不需要 `name`。`code` 只用于运行期事件编号，不进入用户等待语法。

等待该事件：

```text
ACTIVITY(until=DUMP_READY)
```

---

## 6. EQUATION

```text
EQUATION
  DD(TANKER_LEVEL) = ...
  DD(STORAGE_LEVEL) = ...
  SS(ALGEBRAIC) = ...
END
```

规则：

```text
只放 DD/SS 方程
DD/SS 后必须使用变量名，不支持 DD(1)/SS(1)
SS 代数方程按书写顺序求值
DD 使用当前 SS
检测到代数环 → 报错
```

不支持：

```text
Python STATE 回调
derivatives= 参数
在 .helix 中 import Python
```

---

## 7. NETWORK

### CREATE

```text
CREATE(
  interval=EXPON(0.4),
  first=0,
  priority=0,
  until=480,
)
```

或：

```text
CREATE(
  interval=EXPON(0.4),
  count=100,
)
```

单参数简写：

```text
CREATE(EXPON(0.4))
```

等价于 `interval=EXPON(0.4)`。

规则：

```text
interval 可选
first 默认 0
priority 默认 0
count 和 until 互斥
count = 创建数量上限
until = 创建时间上限
```

无 `interval` 时，`count` 直接表示本次批量创建数：

```text
CREATE(count=4)     一次创建 4 个
CREATE(count=1)     一次创建 1 个
```

批量初始属性：

```text
CREATE(
  count=5,
  ID=[1, 2, 3, 4, 5],
  VALUE=[10, 20, 30, 40, 50],
)
```

规则：

```text
属性名必须是已声明的 ENTITY 变量
属性值必须是列表
count 必须等于列表长度
省略 count 时由列表长度推断
没有 interval：一次批量产生全部实体
有 interval：每次 CREATE 事件按顺序取一个属性
```

示例：

```text
CREATE(ID=[1, 2, 3])
```

等价于：

```text
count=3
一次创建 3 个实体
```

### QUEUE

```text
Q1: QUEUE(
  capacity=4,
  order=FIFO,
  on_full=BALK(SUB),
)
```

单参数简写：

```text
Q1: QUEUE(4)
```

等价于 `capacity=4`。`QUEUE()` 仍表示无界。

字段：

```text
capacity
order
on_full
```

规则：

```text
capacity 缺省或 0 = 无界
order 缺省 FIFO
on_full 缺省 ERROR
```

排序：

```text
FIFO
LIFO
PRIORITY
LOW_PRIORITY
HIGH(i)
LOW(i)
```

满队列：

```text
on_full=BALK(target)
on_full=BLOCK
on_full=ERROR
```

不再使用 `file=`。

### ACTIVITY

```text
A1: ACTIVITY(
  duration=EXPON(0.25),
  servers=2,
)
```

单参数简写：

```text
A1: ACTIVITY(EXPON(0.25))
A2: ACTIVITY(5)
```

等价于：

```text
A1: ACTIVITY(duration=EXPON(0.25))
A2: ACTIVITY(duration=5)
```

持续时间可以使用实体属性：

```text
SVL1: ACTIVITY(duration=svltime)
SVL2: ACTIVITY(duration=crsrtime + 2)
SVL3: ACTIVITY(duration=EXPON(svltime))
```

属性必须已经由 `CREATE` 属性列表或 `ASSIGN` 写入实体；分布参数也可以是属性。

字段：

```text
duration
servers
until
```

`servers` 默认 1。

`until`：

```text
ACTIVITY(until=ENDU)
ACTIVITY(until=DUMP_READY)
```

含义：

```text
等待同名事件
事件可以来自 DETECT 节点/声明，也可以来自 SEVNT name
REL/STOPA 写法已移除
```

### TERMINATE

```text
DONE: TERMINATE(code=0)
DONE: EXIT()
```

`EXIT()` 与 `TERMINATE()` 等价。

### ASSIGN

```text
SET: ASSIGN(LOAD_AVAIL=LOAD_AVAIL-1, TANKER_LEVEL=150)
```

规则：

```text
每个参数就是一次赋值
逗号分隔多个赋值
VAR 的 scope=ENTITY 写入当前实体
VAR 的 scope=GLOBAL 写入共享/连续状态
右侧是表达式或分布
支持 UNFRM/RNORM/EXPON/EXP/ERLNG 抽样
旧写法 ASSIGN(set={...}) 已移除
```

### EVENT

```text
EVENT(name=SET_FLAG, action=SET)
```

规则：

```text
触发命名事件
可选 action 把当前实体路由到动作节点
不写 action 时继续默认链
```

### OBSERVE

```text
OBSERVE(name="HEATING TEMP", value=TEMP[PIT])
```

单参数简写：

```text
OBSERVE("HEATING TEMP", TEMP[PIT])
```

等价于 `name=..., value=...`。

规则：

```text
记录一次显式观测
不改变实体状态
可写在网络节点或 SCAN 的 DO 中
```

### SCAN

```text
SCAN PIT IN 1..10
  WHERE ACTIVE[PIT] == 0
  DO ASSIGN(PIT_INDEX=PIT, ACTIVE[PIT]=1)
  STOP
END SCAN
```

规则：

```text
按整数范围扫描
WHERE 为真时执行 DO 动作
DO 可写多条
支持 ASSIGN(...)、EVENT(...)、OBSERVE(...)
STOP 表示第一个匹配就退出
不写 STOP 会扫描全部匹配项
```

动态事件名：

```text
EVENT(name=PIT_DONE[PIT])
ACTIVITY(until=PIT_DONE[PIT_INDEX])
```

`NAME[expr]` 会按当前上下文计算下标，再拼成事件名。

### AWAIT

```text
AWAIT(resource=DOCK, units=1)
AWAIT(DOCK)
AWAIT(gate=LIGHT)
```

```text
AWAIT(DOCK) 等价于 units=1
units 是表达式，可使用实体属性/全局变量
units 必须 >= 1
资源不足时整个实体等待，不做部分分配
等待顺序：priority 降序，再按进入顺序
AWAIT 不会自动释放
```

### FREE

```text
FREE(resource=DOCK, units=1)
FREE(DOCK)
```

```text
FREE(DOCK) 等价于 units=1
units 是表达式，可使用实体属性/全局变量
释放量最多不超过当前持有量
释放后唤醒等待者
AWAIT 与 FREE 应成对使用
```

以上是默认 `POOL` 模式。`RESTOCK` 模式下：

```text
AWAIT 直接减少 available
FREE  直接增加 available，最多到 capacity
不要求 FREE 前先 AWAIT
不维护 held_by
不支持 PREEMPT
```

### ALTER / OPEN / CLOSE

```text
ALTER(resource=TOOL, capacity=2)
ALTER(create=ARRIVALS, interval=UNFRM(1, 3))
ALTER(activity=SERVICE, duration=UNFRM(5, 10))
OPEN(gate=LIGHT1)
CLOSE(gate=LIGHT1)
```

资源容量支持表达式：

```text
ALTER(resource=radio, capacity=CAPACITY(radio) + ordernum)
```

这是设置总容量，不是增量。

规则：

```text
ALTER 三选一：resource / create / activity
只影响后续抽样或后续启动
已经排入 FEL 的事件不会取消或重算
activity 必须是 duration 型，不能改 until 型活动
```

### PREEMPT

```text
P: PREEMPT(
  resource=TOOL,
  priority=HIGH(PRIORITY),
  preempted_to=DOWN,
  remaining_at=REMAIN,
)
```

规则：

```text
只支持容量为 1 的资源
HIGH(K)/LOW(K) 比较实体优先级
preempted_to 可选
remaining_at 可选，保存剩余加工时间
省略 preempted_to 时资源恢复后继续原活动
持有其他资源的实体不能被抢占
```

`K` 可以是实体属性或全局变量名。`LOW(K)` 表示 K 越小优先级越高。

### EVENT

```text
E: EVENT(code=2)
```

### MATCH

```text
M: MATCH(natr=1, queues=[Q1, Q2], save=false)
```

`natr` 等内部 ATRIB 接口待定。

---

## 8. IF

```text
CHECK: IF RANDOM() < 0.85 -> DPRT
ELSE -> ADJT
```

规则：

```text
IF 行包含第一个条件
后续多分支用 ELSE IF
最后一个分支必须是 ELSE
不再使用 WHEN
不再使用 END IF
RANDOM() 返回 [0,1)
每个 IF 入口只抽取一次
所有 ELSE IF 共用这次抽样
按书写顺序判断
第一个为真即选中
-> 与 GOTO 等价
```

多分支：

```text
BRANCH: IF RANDOM() < 0.20 -> A
ELSE IF RANDOM() < 0.50 -> B
ELSE -> C
```

概率：

```text
A = 20%
B = 30%
C = 50%
```

属性/变量条件：

```text
Loop: IF ID = 1 -> SVL1
ELSE IF ID = 2 -> SVL2
ELSE -> SVL3
```

```text
支持 =、<>、<、<=、>、>=
支持 AND / OR / NOT
属性名必须是当前实体的 ENTITY 变量
```

`=` 是条件相等，不是赋值。

---

## 9. PARALLEL / SPLIT / JOIN / MERGE

### PARALLEL

```text
P: PARALLEL
  PATH -> A
  PATH -> B
END PARALLEL
```

规则：

```text
复制实体
每条 PATH 独立推进
继承 created_time / priority / attributes
PATH 后可用 -> 或 GOTO
```

### SPLIT

```text
S: SPLIT(parts=[loader, truck])
  PATH loader -> LOADER_REST
  PATH truck -> HAUL
END SPLIT
```

规则：

```text
拆分组装实体
每个 part 独立
保留基础属性
PATH part 后可用 -> 或 GOTO
```

### JOIN

```text
J: JOIN(count=2, merge=LOW(3))
```

规则：

```text
等待 count 个实体
全部到达后合并
```

合并规则：

```text
FIRST
LAST
HIGH(i)
LOW(i)
SUM
MULT
```

### MERGE

```text
M: MERGE
```

规则：

```text
任一路到达即可继续
不等待
不合并属性
```

---

## 10. SELECT

```text
BEGN: SELECT(
  queue_rule=ASM,
  server_rule=LIT,
  queues=[LOAD, TRKS, LDER],
  servers=[LOAD1, LOAD2],
  save=LOW(3),
)
```

入边：

```text
LOAD -> BEGN
TRKS -> BEGN
LDER -> BEGN
```

规则：

```text
queue_rule 决定队列选择
server_rule 决定服务台选择
servers 列出候选服务台
save 决定属性保留规则
```

`ASM`：

```text
所有 queues 非空才组装
每个队列取一个
```

没有空闲服务台：

```text
在 SELECT 等待
```

---

## 11. 自动统计

模型不写：

```text
COLLECT
COLCT
TIMST
RECORD
STAT
```

运行时自动记录：

```text
SYSTEM.TIME
QUEUE.Q1.WAIT
QUEUE.Q1.LENGTH
ACTIVITY.A1.UTIL
ACTIVITY.A1.BLOCK
RESOURCE.R.UTIL
GATE.WAIT
BALK
```

报告阶段选择：

```python
result.report(
    "out/report.md",
    track=[
        "SYSTEM.TIME",
        "QUEUE.Q1.WAIT",
        "ACTIVITY.A1.UTIL",
    ],
    plot=["VAR.TANKER_LEVEL"],
)
```

F8/F9：

```text
最大空闲时间 + 服务台序号
最大忙碌时间 + 服务台序号
```

---

## 12. Python 侧

模型不包含：

```text
初值
常量
初始实体
开始/结束时间
种子
报告元数据
```

```python
model = helix.Model.from_file("model.helix")

scenario = model.initialize(
    initial={"TANKER LEVEL": 0.0, "STORAGE LEVEL": 2000.0},
    constants={"QIN": 3.0},
    entities={"Q1": [{}, {}, {}, {}]},
)

result = scenario.run(start=0, end=365, seed=1)

result.report(
    "out/report.md",
    track=["SYSTEM.TIME"],
    plot=["TANKER LEVEL"],
)
```

初始队列长度：

```python
model.initialize()                          # 所有队列为空
model.initialize(entities={"Q1": []})       # 显式空队列
model.initialize(entities={"Q1": [{}]})     # 1 个初始实体
model.initialize(entities={"Q1": [{}, {}]}) # 2 个初始实体
```

注意：

```text
QUEUE(capacity=0)  表示无界容量
entities 列表长度  表示初始队列长度
```

---

## 13. 明确不兼容

```text
NETWORK: / ENDNETWORK
VARIABLES / END VARIABLES
CONTINUOUS / END CONTINUOUS
RESOURCES / END RESOURCES
GATES / END GATES
EVENTS / END EVENTS
GOON
ACCUM
ACT/1
ACT(2)/1
QUEUE(1),...
SELEC / SELECT,ASM,...
PRIORITY/...
COLCT / COLLECT
TIMST
RECORD
STAT
MONTR
位置参数
分号结束语句
星号注释
```
