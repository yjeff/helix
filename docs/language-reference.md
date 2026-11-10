# Helix 语言参考与案例对比

状态：`helix` 当前实现。  
目标：模型只描述模型；运行控制放在 Python。

---

## 0. 当前语法速查

### 转移

```text
A -> B
A GOTO B
```

`->` 与 `GOTO` 等价。

### IF

```text
IF condition -> A
ELSE IF condition2 -> B
ELSE -> C
```

不再使用 `WHEN` 和 `END IF`。

### 块结束

```text
EQUATION
  ...
END

NETWORK
  ...
END
```

`END` 关闭当前块。旧的 `END EQUATION` / `END NETWORK` 仍兼容。

### 常用简写

```text
ACTIVITY(5)
AWAIT(DOCK)
FREE(DOCK)
QUEUE(4)
CREATE(1.0)
RESOURCE R(2)
GATE L(OPEN)
OBSERVE("NAME", value)
EXIT()
```

### DD / SS

```text
DD(TEMP) = ...
SS(MAX_TEMP) = ...
```

必须使用变量名；不支持 `DD(1)` / `SS(1)`。

---

## 1. 文件结构

```text
HELIX 1

PROJECT "PROJECT NAME"

; 顶层声明
VAR ...
CONTINUOUS ...
RESOURCE ...
GATE ...
DETECT ...
SEVNT ...

EQUATION
  DD(...) = ...
  SS(...) = ...
END

NETWORK
  ...
END
```

只有两个块：

```text
EQUATION ... END
NETWORK  ... END
```

`END` 关闭当前块；旧的 `END EQUATION` / `END NETWORK` 仍兼容但不推荐。

其余是顶层声明。

---

## 2. 行、注释与标签

### 语句

一条语句以换行结束：

```text
CREATE(interval=EXPON(1))
QUEUE(capacity=4)
ACTIVITY(duration=5)
```

不使用分号结束语句。

### 注释

```text
; 从分号到行尾都是注释
```

不使用 `*` 注释。

### 括号续行

括号未闭合时允许自动续行：

```text
ACTIVITY(
  duration=EXPON(0.25),
  servers=2,
)
```

### 标签

```text
Q1: QUEUE(capacity=4)
A1: ACTIVITY(duration=EXPON(0.25))
```

规则：

```text
只有需要被引用时才加 label
label 与语句之间用冒号
不要给每条顺序语句都加 label
```

推荐排版：

```text
VLDZ:    ASSIGN(LOAD_START=TNOW)
DOCKWAIT: AWAIT(DOCK)
HOLD:    ACTIVITY(until=PIT_DONE[PIT_INDEX], servers=10)
```

label 列对齐，语句列对齐。

### 顺序与转移

```text
CREATE(EXPON(1))
ACTIVITY(5)
EXIT()
```

默认：

```text
CREATE -> ACTIVITY -> EXIT
```

显式跳转：

```text
RETRY: ACTIVITY(2) -> CHECK
RETRY: ACTIVITY(2) GOTO CHECK
```

`->` 与 `GOTO` 完全等价；独立跳转、IF、PARALLEL、SPLIT、FORK 都支持。

有转移时不再使用默认顺序连接。

默认顺序连接只用于普通线性节点：

```text
CREATE -> QUEUE -> ACTIVITY -> EXIT
```

以下节点不会自动连接下一条：

```text
有显式 -> / GOTO 的节点
TERMINATE / EXIT
IF / PARALLEL / SPLIT 的分支目标
FORK 的 branches 目标
SELECT 引用的 queues / servers
两个相邻的分支根
```

例如：

```text
CHECK: IF ... -> A
ELSE -> B

A: ACTIVITY(1)
B: ACTIVITY(2)
```

`A` 和 `B` 是互斥分支，不会自动连接 `A -> B`。

如果 A 执行完还要进入 B，必须显式写：

```text
A: ACTIVITY(1) -> B
```

`Lost` 分支的 `RECORD` 和 `MARK` 都属于分支目标；如果 `RECORD` 后要继续到 `MARK`，必须写：

```text
RECORD: OBSERVE("Customer Lost", TNOW - LAST_OBS) -> MARK
```

---

## 3. VAR

### 普通声明

```text
VAR TANKER_LEVEL
VAR LOAD_AVAIL GLOBAL
VAR LOAD_START ENTITY
```

字段：

```text
GLOBAL  全局变量
ENTITY  实体属性
省略    自动推断
```

推断：

```text
出现在 EQUATION/DETECT/SEVNT 中 → GLOBAL
其余 → ENTITY
```

### 标签和范围

```text
VAR LEVEL AS "LEVEL" RANGE 0..100
```

### 数组

```text
VAR TEMP[10]
VAR ACTIVE[10] GLOBAL
```

规则：

```text
数组只支持 GLOBAL
下标从 1 开始
未初始化元素默认 0
```

使用：

```text
DD(TEMP[1]) = ...
ASSIGN(TEMP[PIT]=400)
SUM(ACTIVE)
```

### 初始化

固定初始资源建议直接写在模型里，避免只读模型时漏掉资源数量：

```text
CREATE(count=4) -> TRKS
CREATE(count=2) -> LDER
```

`CREATE(count=N)` 没有 `interval` 时，在开始时刻一次创建 N 个实体。

需要做场景实验时，再在 Python 中覆盖初始实体：

```python
model.initialize(entities={
    "TRKS": [{} for _ in range(truck_count)],
    "LDER": [{}, {}],
})
```

全局变量：

```python
model.initialize(initial={
    "TEMPERATURE": 12.5,
    "ACTIVE": [1, 1, 0, 0],
})
```

实体属性：

```python
model.initialize(entities={
    "Q1": [{"PIT_INDEX": 1}, {"PIT_INDEX": 2}],
    "WAIT_PIT": [{"LOAD_START": 0.0, "LOAD_TEMP": 550.0}],
})
```

`entities` 的 key 可以是任意网络节点 label，不再只限于 QUEUE；实体直接进入该节点。

#### 初始队列长度

队列启动时默认为空：

```python
model.initialize()
```

所有队列初始长度都是 0，不需要显式写。

显式写 0 也可以，但没有额外效果：

```python
model.initialize(entities={"Q1": []})
```

初始 1 个实体：

```python
model.initialize(entities={"Q1": [{}]})
```

初始 3 个实体：

```python
model.initialize(entities={
    "Q1": [
        {"ID": 1, "VALUE": 10},
        {"ID": 2, "VALUE": 20},
        {"ID": 3, "VALUE": 30},
    ],
})
```

规则：

```text
队列初始长度 = entities 中该队列的 list 长度
不写 entities  = 0
list 为空      = 0
list 有 N 项   = N
```

不要与队列容量混淆：

```text
QUEUE(capacity=0)   无界容量
Q1: [{}]            初始 1 个实体
```

`capacity` 是最大容纳能力，不是初始实体数量。

### ATTR 已移除

```text
ATTR LOAD_START
```

现在写成：

```text
VAR LOAD_START ENTITY
```

---

## 4. CONTINUOUS

```text
CONTINUOUS METHOD=RK4, MIN_STEP=0.001,
           SAVE_STEP=0.1, MAX_STEP=0.1

CONTINUOUS METHOD=RKF45, MIN_STEP=0.0001,
           SAVE_STEP=0.1, MAX_STEP=0.1, TOL=1e-6
```

字段：

```text
METHOD
MIN_STEP
SAVE_STEP
MAX_STEP
TOL
```

`CONTINUOUS` 只保留为兼容默认值。新的场景配置应放在 `initialize`：

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
result = scenario.run(end=500, seed=1)
```

同一模型可以换不同求解器运行，不需要修改 `.helix`。

---

## 5. EQUATION

```text
EQUATION
  SS(MAX_TEMP) = MAX(TEMP[1], TEMP[2], ...)
  DD(TEMP[1]) = ((FURNACE - TEMP[1]) * ACTIVE[1]) * C[1]
  DD(FURNACE) = (2600.0 - FURNACE) * 0.2
END
```

规则：

```text
DD 是微分方程
SS 是代数方程
DD/SS 必须使用变量名，不支持 DD(1)/SS(1)
SS 按书写顺序求值
DD 使用当前 SS 值
```

表达式支持：

```text
+ - * / ** %
比较、AND/OR/NOT
IF(cond, a, b)
SIN COS TAN SQRT EXP LOG ABS
MIN MAX SUM(array)
TNOW PRIORITY PI
AVAILABLE(resource) CAPACITY(resource) HELD(resource)
```

内置只读变量：

```text
TNOW       当前仿真时刻
PRIORITY   当前实体的 priority
PI         圆周率
```

用户声明的 GLOBAL 变量、ENTITY 属性和连续状态变量也可以直接按名称访问。

---

## 6. RESOURCE / GATE

### RESOURCE

```text
RESOURCE DOCK(capacity=1)
RESOURCE TOOL(capacity=2)
RESOURCE radio(capacity=72, mode=RESTOCK)

RESOURCE DOCK(1)
RESOURCE TOOL(2)
```

`RESOURCE NAME(n)` 是 `capacity=n` 的简写。

`mode` 可选：

```text
POOL      默认，可借还资源，维护持有者账本
RESTOCK   库存资源，只维护可用量，不要求持有者账本
```

### POOL 模式

```text
AWAIT  -> available 减少，held 记录到当前实体
FREE   -> 当前实体归还，held 减少，available 增加
```

适合工具、设备、可抢占资源。

### RESTOCK 模式

```text
AWAIT  -> available 直接减少
FREE   -> available 直接增加，最多到 capacity
```

RESTOCK 模式：

```text
不要求 FREE 前先 AWAIT
不记录 held_by
不支持 PREEMPT
HELD(x) = CAPACITY(x) - AVAILABLE(x)
```

适合仓库库存、消耗品、补货：

```text
RESOURCE radio(capacity=72, mode=RESTOCK)

AWAIT(radio, units=1)
...
FREE(resource=radio, units=50)
```

`FREE` 在 RESTOCK 中表示“入库/补货”，会直接增加可用量，并封顶到容量。

运行时资源查询函数：

```text
AVAILABLE(RADIO)      当前剩余容量
CAPACITY(RADIO)       声明容量
HELD(RADIO)           当前已持有量
```

这些函数可用于 `IF`、`OBSERVE`、`ASSIGN`、活动持续时间等表达式：

```text
IF AVAILABLE(RADIO) > 0 -> USE_RADIO
ELSE -> WAIT_RADIO

OBSERVE("RADIO FREE", AVAILABLE(RADIO))
ASSIGN(RADIO_FREE=AVAILABLE(RADIO))
ACTIVITY(duration=HELD(RADIO))
```

规则：

```text
资源名大小写不敏感
AVAILABLE = CAPACITY - HELD
查询只读取状态，不改变资源
```

### GATE

```text
GATE LIGHT1(state=CLOSED)
GATE LIGHT2(state=OPEN)

GATE LIGHT1(CLOSED)
GATE LIGHT2(OPEN)
```

`GATE NAME(OPEN)` / `GATE NAME(CLOSED)` 是 `state=` 的简写。

### AWAIT

申请资源：

```text
AWAIT(resource=DOCK, units=1)
AWAIT(DOCK)
```

申请门：

```text
AWAIT(gate=LIGHT1)
```

规则：

```text
AWAIT(DOCK) 等价于 AWAIT(resource=DOCK, units=1)
units 必须是表达式，可使用当前实体属性/全局变量
units 必须 >= 1
资源不足时整个实体等待，不做部分分配
等待顺序按 priority 降序，再按进入顺序
AWAIT 成功后实体继续到下一节点
AWAIT 只申请，不自动释放
```

### FREE

释放资源：

```text
FREE(resource=DOCK, units=1)
FREE(DOCK)
```

规则：

```text
FREE(DOCK) 等价于 FREE(resource=DOCK, units=1)
units 是表达式，可使用当前实体属性/全局变量
释放量最多不超过该实体当前持有量
释放后按优先级唤醒等待者
AWAIT 与 FREE 应成对使用
```

RESTOCK 模式下 `FREE` 不要求先 `AWAIT`，直接增加 `available`。

### OPEN / CLOSE

```text
OPEN(gate=LIGHT1)
CLOSE(gate=LIGHT1)
```

控制 GATE 状态；关闭后 `AWAIT(gate=...)` 的实体等待。

### ALTER

```text
ALTER(resource=TOOL, capacity=2)
ALTER(create=ARRIVALS, interval=UNFRM(1, 3))
ALTER(activity=SERVICE, duration=UNFRM(5, 10))
```

`ALTER(resource=..., capacity=...)` 的容量也支持运行时表达式：

```text
ALTER(resource=radio, capacity=CAPACITY(radio) + ordernum)
```

这是设置**总容量**，不是增量；补货时用“当前容量 + 本次补货量”。

规则：

```text
ALTER 三选一：resource / create / activity
只影响后续抽样或后续启动
已经排入 FEL 的事件不会取消或重算
activity 只支持 duration 型
```

完整资源示例：

```text
RESOURCE DOCK(1)

NETWORK
  CREATE(interval=EXPON(10))
  AWAIT(DOCK)
  ACTIVITY(duration=UNFRM(5, 8))
  FREE(DOCK)
  EXIT()
END
```

---

## 7. DETECT

### 顶层事件

```text
DETECT name=HI, when=LEVEL >= 80
DETECT name=LO, when=LEVEL <= 20, edge=FALLING
```

默认：

```text
edge=RISING
tol=0.01
```

方向：

```text
RISING
FALLING
ANY
```

### 网络 DETECT 节点

```text
ENDU: DETECT(when=TANKER_LEVEL > 7.5, edge=FALLING)
  -> ENDSIG
```

触发时：

```text
释放等待 ENDU 的 ACTIVITY(until=ENDU)
向后继发送一个信号实体
```

### 事件名唯一

```text
DETECT name
DETECT 节点 label
SEVNT name
```

共享同一个事件命名空间，不能重名。

---

## 8. SEVNT

```text
SEVNT name=DUMP_READY, code=2,
       when=STORAGE_LEVEL > 50,
       action=SET_FLAG
```

规则：

```text
name    普通等待事件必须有 name
code=1  系统停止事件，不需要 name
action  可选，触发后把信号实体送入动作节点
```

等待：

```text
ACTIVITY(until=DUMP_READY)
```

`SEVNT` 动作执行后会自动重新武装，允许下一次条件为真时再次触发。

---

## 9. 统一事件等待

只使用：

```text
ACTIVITY(until=EVENT_NAME)
```

事件来源：

```text
DETECT 节点 label
顶层 DETECT name
SEVNT name
```

动态事件名：

```text
ACTIVITY(until=PIT_DONE[PIT_INDEX])
EVENT(name=PIT_DONE[PIT])
```

`NAME[expr]` 会按当前上下文计算下标，再拼成事件名。

已移除：

```text
REL(...)
STOPA(...)
```

`ACTIVITY(duration=STOPA(...))` 会报错并提示改为 `until=事件名`。

---

## 10. NETWORK 常用语句

### CREATE

```text
CREATE(interval=EXPON(1), first=0, count=100)
CREATE(interval=EXPON(1), until=480)
CREATE(EXPON(1))
```

`CREATE(interval)` 是只写间隔的简写。

字段：

```text
interval
first
priority
count
until
```

`count` 和 `until` 互斥。

无 `interval` 时：

```text
CREATE(count=4)     一次创建 4 个实体
CREATE(count=1)     一次创建 1 个实体
CREATE()            一次创建 1 个实体
```

有 `interval` 时，`count` 表示最多创建多少个事件。

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

等价于 `count=3`，并一次创建 3 个实体。

### QUEUE

```text
Q1: QUEUE(capacity=4, order=FIFO, on_full=BALK(SUB))
Q1: QUEUE(4)
```

`QUEUE(4)` 是 `capacity=4` 的简写；`QUEUE()` 无界。

字段：

```text
capacity   0/缺省 = 无界
order      FIFO/LIFO/PRIORITY/LOW_PRIORITY
on_full    BALK(target)/BLOCK/ERROR
```

### ACTIVITY

```text
ACTIVITY(duration=EXPON(0.25), servers=2)
ACTIVITY(until=ENDU)
ACTIVITY(until=PIT_DONE[PIT_INDEX], servers=10)
```

单参数简写：

```text
ACTIVITY(EXPON(0.25))
ACTIVITY(5)
```

等价于 `duration=`。

持续时间也可以使用实体属性或表达式：

```text
SVL1: ACTIVITY(duration=svltime)
SVL2: ACTIVITY(duration=crsrtime + 2)
SVL3: ACTIVITY(duration=EXPON(svltime))
```

`svltime` 必须是实体已经拥有的 `ENTITY` 属性，例如由 `CREATE` 属性列表写入。分布参数也可以是实体属性。

字段：

```text
duration
servers
until
```

规则：

```text
servers 默认 1
duration 和 until 二选一
until 活动在事件发生前保持 BUSY
```

### TERMINATE

```text
TERMINATE()
EXIT()
```

`EXIT()` 与 `TERMINATE()` 等价。

### ASSIGN

```text
ASSIGN(LOAD_AVAIL=LOAD_AVAIL-1, TANKER_LEVEL=150)
ASSIGN(PIT_INDEX=PIT, ACTIVE[PIT]=1, TEMP[PIT]=UNFRM(400, 500))
```

规则：

```text
每个 name=expr 是一次赋值
逗号分隔多个赋值
ENTITY 变量写入当前实体
GLOBAL 变量写入共享/连续状态
右侧支持分布抽样
未声明变量会报错
```

支持的分布：

```text
UNFRM
RNORM
EXPON / EXP
ERLNG
```

旧写法已移除：

```text
ASSIGN(set={...})
```

### OBSERVE

```text
OBSERVE(name="HEATING TEMP", value=TEMP[PIT])
OBSERVE("HEATING TEMP", TEMP[PIT])
```

记录一次显式观测，不改变实体状态。

正常的：

```text
CREATE → ... → EXIT/TERMINATE
```

已经自动记录 `TIME IN SYSTEM`，不需要 `OBSERVE`：

```text
包含排队、等待、全部 ACTIVITY 服务时间
BALK 实体不计入
```

BALK 间隔需要显式记录：

```text
VAR LAST_BALK GLOBAL

q1: QUEUE(capacity=4, on_full=BALK(sub))
sub: OBSERVE("BALK INTERVAL", TNOW - LAST_BALK)
     ASSIGN(LAST_BALK=TNOW)
     EXIT()
```

初始值：

```python
model.initialize(initial={"LAST_BALK": 0})
```

如果要统计某个 `ACTIVITY` 的单独服务时间，需要记录进入时刻：

```text
VAR A1_START ENTITY

A1: ACTIVITY(duration=...)
A1_DONE: OBSERVE("A1 TIME", TNOW - A1_START)
```

`OBSERVE` 自动提供：

```text
count / mean / std / min / max
```

默认报告包含自定义观测；使用 `track=` 时，自定义观测需要从 `result.observations` 读取。

### EVENT

```text
EVENT(name=SET_FLAG, action=SET)
```

触发命名事件，可选路由到动作节点。

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
WHERE 为真时执行 DO
DO 可写多条
支持 ASSIGN / EVENT / OBSERVE
STOP 表示找到第一个匹配就退出
不写 STOP 会扫描全部匹配项
```

---

## 11. IF

```text
CHECK: IF RANDOM() < 0.85 -> DPRT
ELSE GOTO ADJT
```

多分支：

```text
CHECK: IF RANDOM() < 0.20 -> A
ELSE IF RANDOM() < 0.50 -> B
ELSE -> C
```

规则：

```text
IF 行包含第一个条件
后续多分支用 ELSE IF
最后一个分支必须是 ELSE
不再使用 WHEN
不再使用 END IF
每个 IF 入口只抽样一次
所有 ELSE IF 共用这次抽样
按书写顺序判断
第一个为真即选中
ELSE 必须存在
IF/ELSE IF/ELSE 后可用 -> 或 GOTO
```

属性/变量条件：

```text
Loop: IF ID = 1 -> SVL1
ELSE IF ID = 2 -> SVL2
ELSE -> SVL3
```

```text
支持 =、<>、<、<=、>、>= 和 AND / OR / NOT
属性名必须是当前实体的 ENTITY 变量
条件中的 = 表示相等，不是赋值
```

概率条件与属性条件可以混用，但每个 `RANDOM()` 仍只在进入 IF 时抽取一次。

例如：

```text
CHECK: IF AVAILABLE(radio) > 0 OR RANDOM() <= 0.2 -> A
ELSE -> B
```

同一个 IF 的所有 `RANDOM()` 使用同一次抽样值。

---

## 12. PARALLEL / SPLIT / FORK / JOIN / MERGE

### PARALLEL

```text
P: PARALLEL
  PATH -> A
  PATH GOTO B
END PARALLEL
```

复制实体，每条 PATH 独立推进。`PATH` 后 `->` 与 `GOTO` 等价。

### SPLIT

```text
S: SPLIT(parts=[loader, truck])
  PATH loader -> LOADER_REST
  PATH truck -> HAUL
END SPLIT
```

拆分实体，每个 part 独立。`PATH part` 后 `->` 与 `GOTO` 等价。

### FORK

```text
S: FORK(branches=[LDER -> LOADER_REST, TRKS -> HAUL])
S: FORK(branches=[LDER GOTO LOADER_REST, TRKS GOTO HAUL])
```

用于 SELECT ASM 之后，把原始成员实体路由回各自链路。

### JOIN

```text
J: JOIN(count=2, merge=FIRST)
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

任一路到达即可继续。

---

## 13. SELECT

```text
BEGN: SELECT(
  queue_rule=ASM,
  server_rule=LIT,
  queues=[LOAD, TRKS, LDER],
  servers=[LOAD1, LOAD2],
  save=LOW(3),
)
```

用途：

```text
从多个 QUEUE 装配成员
选择可用服务台
保存成员供后续 FORK
```

---

## 14. PREEMPT

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
只支持 capacity=1 的资源
HIGH(K)/LOW(K) 比较优先级
preempted_to 可选
remaining_at 可选
省略 preempted_to 时恢复剩余加工时间
持有其他资源的实体不可抢占
```

---

## 15. Python API

```python
import helix

model = helix.Model.from_file("model.helix")

scenario = model.initialize(
    initial={"LEVEL": 60.0},
    constants={"QIN": 3.0, "QOUT": 4.0},
    entities={"Q1": [{}, {}]},
)

result = scenario.run(
    start=0.0,
    end=500.0,
    seed=1,
    clear_time=None,
    debug=False,
    debug_path=None,
)

print(result.now)
print(result.continuous_final)
print(result.global_values)
print(result.observations)
print(result.queues)
print(result.services)
print(result.resources)
```

`clear_time` 对应旧版 `MONTR,CLEAR,t`：

```python
result = scenario.run(end=365, clear_time=65)
```

统计从 65 开始重新累计。

### 15.1 CLI

安装：

```bash
pip install -e .
```

检查模型：

```bash
helix check examples/serial_workstations/model.helix
```

运行：

```bash
helix run examples/serial_workstations/model.helix --end 300 --seed 1
```

旧 SLAM 转换：

```bash
helix convert ../slam_v2/examples/discrete/serial_workstations.slam \
  -o examples/converted_serial.helix
```

详见 [slam-conversion.md](slam-conversion.md)。

参数：

```text
--start
--end
--seed
--clear-time
--initial NAME=VALUE
--constant NAME=VALUE
--report PATH
--debug
--debug-path PATH
```

不安装也可以：

```bash
python -m helix check examples/serial_workstations/model.helix
```

动画播放器：

```bash
helix run examples/tv_inspection/model.helix --end 480 --seed 1 \
  --debug --debug-path out/debug
helix animate out/debug -o out/player.html
```

---

## 16. 报告

```python
result.report(
    "report.md",
    project="CASE",
    track={
        "LEVEL": "VAR.LEVEL",
        "WAIT": "QUEUE.Q1.WAIT",
        "UTIL": "ACTIVITY.INSPECT.UTIL",
    },
    plot=["LEVEL"],
)

result.plot("report.svg")
```

规范指标名：

```text
SYSTEM.TIME
QUEUE.<label>.LENGTH
QUEUE.<label>.WAIT
ACTIVITY.<label>.UTIL
RESOURCE.<name>.UTIL
RESOURCE.<name>.AVG_UTIL
RESOURCE.<name>.STD_UTIL
RESOURCE.<name>.MAX_UTIL
RESOURCE.<name>.CURRENT_UTIL
RESOURCE.<name>.AVAILABLE
VAR.<name>
```

模型不写：

```text
COLLECT
TIMST
RECORD
STAT
MONTR
```

---

## 17. DEBUG

```python
result = scenario.run(
    end=500,
    debug=True,
    debug_path="out/debug",
)
```

输出：

```text
run.json
model.json
events.ndjson
```

解析调试：

```text
tokens.ndjson
parse.ndjson
ast.json
```

---

## 18. 关键注意点

### 18.1 只给需要的节点加 label

推荐：

```text
NETWORK
  DETECT(when=LEVEL > 80, edge=RISING)
  ACTIVITY(duration=1.5)
  ASSIGN(PUMP_ON=1)
  TERMINATE()
END
```

只有被引用时才写 label：

```text
HOLD: ACTIVITY(until=PIT_DONE[PIT_INDEX], servers=10)
```

### 18.2 AWAIT 必须早于 SCAN

错误顺序：

```text
SCAN 找空坑
AWAIT(resource=PIT)
```

资源满时可能得到 `PIT_INDEX=0`。

正确顺序：

```text
AWAIT(resource=PIT)
SCAN 找空坑
```

### 18.3 HOLD 服务台数

```text
HOLD: ACTIVITY(until=PIT_DONE[PIT_INDEX], servers=10)
```

如果只剩默认 `servers=1`，多个实体等待同一个活动，其他坑位会占着资源却无法加热。

### 18.4 初始资源账

如果初始数组里已有 ACTIVE 坑位，但对应 PIT 资源没有初始持有量，资源账会不平衡。

当前 Soaking 草稿用空坑启动。

### 18.5 动态事件名

```text
ACTIVITY(until=PIT_DONE[PIT_INDEX])
```

要求实体先写入 `PIT_INDEX`。如果实体没有该属性，会报未知变量。

### 18.6 SEVNT 动作后重新武装

已实现：

```python
self._last_condition[("S", code)] = False
```

否则 SEVNT 动作清空状态后可能不再触发。

### 18.7 实体属性与全局变量

```text
ASSIGN(LOAD_START=TNOW)   ; ENTITY
ASSIGN(TANKER_LEVEL=150)  ; GLOBAL
```

先用 `VAR ... ENTITY/GLOBAL` 声明，不要依赖隐式创建。

### 18.8 数组只支持 GLOBAL

实体属性不支持数组。

### 18.9 注释和分号

```text
; 这是注释
```

不是语句结束符。

### 18.10 不要使用旧语法

```text
ATTR LOAD_START
REL(ENDU)
STOPA(2)
ASSIGN(set={...})
COLLECT
TIMST
RECORD
STAT
MONTR
```

---

## 19. 案例与书中结果对比

### 19.1 Soaking Pit

书中 Figure 11-16 / report fixture：

```text
HEATING TEMP count=225 mean=2162 std=41.42
HEATING TIME count=225 mean=20.02 std=3.269
WAITING TIME count=180 mean=8.177 std=4.660
FURNACE TEMP mean=2127 std=267 final=2125
```

Helix `seed=4,end=500`：

```text
HEATING TEMP count=195 mean=2197.59 std=111.53
HEATING TIME count=195 mean=19.49 std=5.79
WAITING TIME count=205 mean=2.21 std=3.82
FURNACE avg=2086.3 std=264.8 final=2438.5
```

判断：

```text
HEATING TEMP 均值差约 1.6%
HEATING TIME 均值差约 2.6%
WAITING TIME 均值偏低
炉温平均值接近，期末相位偏高
```

### 19.2 Tanker Fleet

书中初始条件：

```text
STORAGE LEVEL 半满 = 1000
```

当前 Helix 使用 1000。

书中 Figure 11-7：

```text
WAITING mean=1.366 std=1.239 count=317
TRIP mean=14.27 std=2.158 count=312
STORAGE mean=1766 std=176.3 min=986 max=2005 current=1925
DOCK util=0.9071
REFN input avail=1.0
```

Helix `seed=1,end=365,clear_time=65`：

```text
VOY=320 TRANSIT=324 OFFLOAD=323 RET=320
WAITING mean=1.367 std=1.231 count=323
TRIP mean=13.93 std=2.309 count=320
STORAGE mean=1719 std=230 min=877 max=1999 current=1922
DOCK util=0.8972
REFN input avail=1.0
```

判断：

```text
WAITING 均值/标准差基本一致
TRIP 均值差约 2.4%
STORAGE 均值差约 2.7%
DOCK 利用率差约 1.1%
活动计数差约 2%
期末 TANKER_LEVEL 仍有相位差
```

期末 TANKER_LEVEL 仍有相位差；统计量已接近。

---

## 20. 当前案例状态

```text
Serial Work Stations   完成
TV Inspection          完成
Truck Hauling          完成
Cedar Bog Lake         完成
Liquid Level Control   完成
Pilot Ejection         完成
Machine Breakdown      完成
Soaking Pit            结构完成，统计接近
Tanker Fleet           草稿，暂停
Quarry Operations      完成，量级对齐
Inventory Problem      部分对齐，safety stock 待校准
```

Machine Breakdown 与 Table 6-1：

```text
Helix 平均 time=9.14 tool use=0.86 repair=0.11
书中    time≈9.59 tool use≈0.844 repair≈0.11
```

---

## 21. 迁移检查清单

```text
[ ] 文件以 HELIX 1 开始
[ ] 注释只用 ;
[ ] 只给被引用节点加 label
[ ] label 列与语句列对齐
[ ] ATTR 改为 VAR NAME ENTITY
[ ] ASSIGN 使用 NAME=expr
[ ] REL/STOPA 改为 ACTIVITY(until=NAME)
[ ] SEVNT 普通事件有 name
[ ] DETECT/SEVNT 事件名唯一
[ ] 数组声明 VAR NAME[n]
[ ] 先 AWAIT 再 SCAN
[ ] HOLD 等并发活动设置 servers
[ ] 初始资源账与 ACTIVE 一致
[ ] 用 clear_time 模拟 MONTR,CLEAR
[ ] 报告指标使用 SYSTEM/QUEUE/ACTIVITY/RESOURCE/VAR 命名空间
```
