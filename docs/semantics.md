# Helix 语义规范 v1.0

状态：离散核心语义冻结。  
实现：`helix`。  
未列出的高级语义进入后续版本。

---

## 1. 执行模型

一次运行由：

```text
模型
初始状态
常量
初始实体
start
end
seed
```

共同决定。

运行过程：

```text
编译模型
→ initialize 生成场景
→ run 从 start 推进到 end
→ 自动统计
→ report
```

模型对象只读；`initialize` 返回新场景。

---

## 2. 时间与事件顺序

运行时维护两个事件列表：

```text
FEL  Future Event List
CEL  Current Event List
```

### FEL

按：

```text
(time, seq)
```

排序。

存放未来时刻的事件。

### CEL

存放当前仿真时刻的事件。

规则：

```text
1. 仿真时钟只在 CEL 为空时前进
2. 下一个时刻 = min(FEL 最早时间, 连续系统下一时刻, end)
3. 先让连续系统推进到该时刻
4. 再更新统计面积
5. 当前时刻设为实际到达时刻
6. 连续事件先加入 CEL
7. FEL 中 time == 当前时刻的事件按 seq 移入 CEL
8. 依次处理 CEL，先到先处理
9. 处理 CEL 事件时仿真时钟不前进
10. 新事件 time == 当前时刻 → 追加到 CEL 尾部
11. 新事件 time > 当前时刻 → 放入 FEL
12. CEL 清空后才推进到下一个时刻
```

伪代码：

```text
while not finished:
    if CEL empty:
        t_next = min(
            FEL.next_time(),
            continuous.next_time(now, end),
            end,
        )

        ; 连续系统可能因 DETECT 提前返回更早的时刻
        t = continuous.advance_to(t_next)

        statistics.advance_to(t)
        now = t

        CEL.extend(continuous.events_at(now))
        FEL.move_time(now, CEL)

    event = CEL.popleft()
    process(event)

    schedule(event):
        if event.time == now:
            CEL.append(event)
        else:
            FEL.push(event)
```

### 混合仿真接口

核心循环不直接调用积分器，只依赖统一接口：

```text
class TimeSource:
    next_time(now, end) -> float
    advance_to(t) -> float
    events_at(t) -> list[Event]
```

离散侧：

```text
FELSource
    next_time = FEL.peek_time()
    advance_to = no-op
    events_at = []
```

连续侧：

```text
ContinuousSource
    next_time = min(now + MAX_STEP, next_save, end)
    advance_to(t) = 积分到 t，返回实际到达时刻
    events_at(t) = DETECT/SEVNT 生成的连续事件
```

`ContinuousSource` 必须满足：

```text
允许 advance_to 返回 t' < t
如果步内检测到状态事件，在 t' 截断
不越过 t
不修改 FEL/CEL
只返回该时刻的连续事件
```

这样增加连续系统时不需要改：

```text
CEL/FEL 结构
事件调度
统计推进
DEBUG 事件格式
```

只需要接入新的 `TimeSource`。

### 连续事件插入顺序

同一时刻：

```text
连续事件先进入 CEL
FEL 同刻事件后进入 CEL
```

即：

```text
DETECT/SEVNT 先处理
离散事件后处理
```

这样连续状态穿越阈值时，先看到的是连续系统状态，而不是已被离散事件修改过的状态。

### 同一时刻事件

```text
同一时刻的事件全部进入 CEL
按进入 CEL 的顺序处理
处理期间 now 不变
新产生的同一时刻事件追加到 CEL 尾部
```

这样：

```text
不会出现同一时刻的事件被时钟推进拆开
时间加权统计只会在时钟真正前进时更新
同一时刻的统计不会产生虚假的时间差
```

### 顺序仍然重要

CEL 保证的是：

```text
同一时刻的事件不会被时间推进打断
```

但它不消除事件顺序影响：

```text
释放资源后唤醒等待者
创建实体后立即入队
活动完成与 CREATE 同时发生
```

这些顺序仍然按 CEL 的进入顺序决定，因此必须保持确定性。

### seq

```text
seq 在事件调度时分配
单调递增
同一时刻的 CEL 保持进入顺序
```

不设置隐藏的事件类型优先级。

### 时间边界

```text
t == end 的事件仍然执行
t > end 的事件丢弃
CEL 清空后推进统计面积到 end
```

### 防护

```text
同一时刻 CEL 事件数设置上限
超过上限报错，避免零时间死循环
```


---

## 3. 随机数

每个 run 使用一个独立随机流：

```text
seed → RNG
```

随机抽取只发生在：

```text
CREATE 的 interval
ACTIVITY 的 duration
IF 中的 RANDOM()
显式分布函数
```

规则：

```text
同一 seed、同一模型、同一初始状态 → 同一事件序列
```

`RANDOM()`：

```text
返回 [0, 1)
只在 IF 节点入口抽取
一个 IF 节点只抽取一次
同一个 IF 的所有 ELSE IF 共用这次抽样
```

示例：

```text
IF RANDOM() < 0.20 -> A
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
IF ID = 1 -> SVL1
ELSE IF ID = 2 -> SVL2
ELSE -> SVL3
```

```text
支持 =、<>、<、<=、>、>= 和 AND / OR / NOT
属性条件不抽取随机数
= 表示相等，不是赋值
```

`RANDOM()` 不允许出现在普通表达式、方程、属性赋值中。

---

## 4. 实体

实体包含：

```text
id
created_time
priority
attributes
current_node
```

规则：

```text
id 在一次 run 内唯一
created_time 在创建时记录
priority 默认 0
```

属性访问的用户语法暂缓，内部可以使用下标。

---

## 5. 网络与顺序

网络节点按书写顺序默认连接：

```text
A
B
C
```

等价于：

```text
A -> B -> C
```

显式箭头覆盖默认：

```text
A -> X;
```

此时 `A` 不再自动连接下一条语句。

规则：

```text
1. 普通节点没有箭头 → 连接下一条网络节点
2. 普通节点有箭头 → 使用显式目标
3. 分支块 IF/PARALLEL/SPLIT/SELECT 不使用默认连接
4. TERMINATE 没有后继
5. 最后一条普通节点没有后继时，允许作为终点
6. 两个相邻的分支根之间不自动连接
```

分支根包括：

```text
IF / ELSE 的目标
PARALLEL 的 PATH 目标
SPLIT 的 PATH 目标
FORK 的 branches 目标
SELECT 引用的 queue/server label
```

例如：

```text
CHECK: IF ... -> A
ELSE -> B

A: ACTIVITY(1)
B: ACTIVITY(2)
```

不会自动形成：

```text
A -> B
```

因为 A、B 是互斥分支。

如果确实要执行完 A 再进入 B，必须写：

```text
A: ACTIVITY(1) -> B
```

同样，`Lost` 分支中：

```text
Lost: IF ... -> RECORD
      ELSE -> MARK

RECORD: OBSERVE(...) -> MARK
```

`RECORD` 和 `MARK` 是相邻的分支根，必须显式连接 `RECORD -> MARK`。

---

## 6. CREATE

```text
START: CREATE(
  interval=EXPON(0.4),
  first=0,
  priority=0,
  until=480,
);
```

或：

```text
START: CREATE(
  interval=EXPON(0.4),
  count=100,
);
```

规则：

```text
interval 可选；省略时只创建一次
first 默认 0
priority 默认 0
count 和 until 互斥
count=创建数量上限
until=创建时间上限
省略 interval 时，count 表示本次批量创建数
```

例如：

```text
CREATE(count=4)
```

一次创建 4 个实体；`CREATE()` 等价于创建一个。

创建：

```text
t = start + first
```

若 `first < 0`，在 `start` 时刻创建。

`priority` 在创建时求值一次。

---

## 7. QUEUE

```text
Q1: QUEUE(
  capacity=4,
  order=FIFO,
  on_full=BALK(SUB),
);
```

字段：

```text
capacity
order
on_full
```

规则：

```text
capacity 缺省或 0 → 无界
order 缺省 FIFO
on_full 缺省 ERROR
```

排序：

```text
FIFO
LIFO
PRIORITY        实体 priority 高者先
LOW_PRIORITY    实体 priority 低者先
HIGH(i)         ATRIB(i) 高者先
LOW(i)          ATRIB(i) 低者先
```

同值：

```text
先按排序值
再按入队顺序 FIFO
```

到达队列：

```text
1. 队列未满 → 入队
2. 队列已满且 BALK(target) → 实体直接去 target，不入队
3. 队列已满且 BLOCK → 上游活动进入 blocked
4. 队列已满且 ERROR → 运行时报错
```

`BALK` 实体：

```text
不计入正常 TIME IN SYSTEM
计入 BALK 统计
```

---

## 8. ACTIVITY

```text
A1: ACTIVITY(
  duration=EXPON(0.25),
  servers=2,
);
```

规则：

```text
servers 默认 1
duration 每次服务抽样一次
duration 可以是实体属性或表达式
服务台编号 1..servers
```

例如：

```text
SVL1: ACTIVITY(duration=svltime)
SVL2: ACTIVITY(duration=crsrtime + 2)
SVL3: ACTIVITY(duration=EXPON(svltime))
```

`svltime` 必须已经存在于当前实体上；分布参数也按实体上下文求值。

实体进入：

```text
有空闲服务台 → 立即开始服务
没有空闲服务台 → 等待
```

服务完成：

```text
1. 计算后继目标
2. 若后继 QUEUE 已满：
   on_full=BLOCK → 活动进入 blocked，实体暂不路由
   on_full=BALK  → 实体按 BALK 离开，活动完成
   on_full=ERROR → 运行时报错
3. 否则路由实体并释放服务台
4. 释放后立即尝试启动同队列的下一个实体
```

`blocked`：

```text
服务台不可用
不计入 active
单独计入 blockage
空间释放后恢复完成
```

---

## 9. TERMINATE

```text
DONE: TERMINATE(code=0);
```

正常终止：

```text
记录 TIME IN SYSTEM
从系统中移除
```

BALK 终止：

```text
不记录 TIME IN SYSTEM
```

服务次数、终止次数分别统计。

---

## 10. IF

```text
CHECK: IF RANDOM() < 0.85 -> DPRT
ELSE -> ADJT
```

规则：

```text
1. 进入 IF 时抽取一次 RANDOM()
2. 按 IF / ELSE IF 书写顺序判断
3. 第一个为真的分支被选中
4. ELSE 必须存在
5. 选中后立即路由，不继续判断
6. IF 不参与默认顺序连接
7. 不使用 WHEN / END IF
```

普通条件：

```text
IF ATRIB(2) == 1 -> A
ELSE IF ATRIB(2) == 2 -> B
ELSE -> C
```

---

## 11. PARALLEL

```text
P: PARALLEL;
  PATH -> A;
  PATH -> B;
END PARALLEL;
```

规则：

```text
复制实体
每条 PATH 得到独立实体
属性、priority 复制
新实体 id 唯一
origin 记录源实体
```

各副本独立运行，分别统计系统时间。

---

## 12. SPLIT

```text
S: SPLIT(parts=[loader, truck]);
  PATH loader -> LOADER_REST;
  PATH truck -> HAUL;
END SPLIT;
```

规则：

```text
拆分组装实体
每个 part 得到独立实体
保留基础属性
part 名称写入实体
不复制成两个完整实体
```

`SPLIT` 用于 Truck 的 loader/truck 组件。

---

## 13. JOIN

```text
J: JOIN(count=2, merge=FIRST);
```

规则：

```text
等待 count 个实体
全部到达后合并为一个
```

合并规则：

```text
FIRST    第一个到达者属性
LAST     最后一个到达者属性
HIGH(i)  ATRIB(i) 最大者属性
LOW(i)   ATRIB(i) 最小者属性
SUM      属性逐项求和
MULT     属性逐项求积
```

默认：

```text
merge=FIRST
```

priority：

```text
默认取合并结果中优先级最高者
```

---

## 14. MERGE

```text
M: MERGE;
```

规则：

```text
任意一个实体到达即可继续
不等待其他路径
不合并属性
```

`JOIN` 是 AND，`MERGE` 是 OR。

---

## 15. SELECT

```text
BEGN: SELECT(
  queue_rule=ASM,
  server_rule=LIT,
  queues=[LOAD, TRKS, LDER],
  servers=[LOAD1, LOAD2],
  save=LOW(3),
)
```

规则：

```text
queue_rule 决定从哪些队列取实体
server_rule 决定选择哪个服务台
服务台由 servers 列表定义
```

`ASM`：

```text
所有 queues 都至少有一个实体
才允许组装
从每个队列各取一个
合并实体
```

其他 queue_rule 从候选队列中选择一个。

`save`：

```text
保留指定实体的属性
规则同 JOIN 的 merge
```

没有空闲服务台：

```text
实体在 SELECT 等待
```

所有队列满：

```text
on_full=BALK(target) / BLOCK / ERROR
```

---

## 16. 资源与门

```text
RESOURCE DOCK(capacity=1);
AWAIT(resource=DOCK, units=1);
FREE(resource=DOCK, units=1);
```

规则：

```text
capacity 默认为 1
AWAIT 申请 units
FREE 释放 units
不足时等待
```

资源模式：

```text
POOL     默认，可借还，维护 held_by
RESTOCK  库存，只维护 available
```

RESTOCK：

```text
RESOURCE radio(capacity=72, mode=RESTOCK);
AWAIT(radio, units=1);
FREE(resource=radio, units=1);
```

```text
AWAIT 直接 available -= units
FREE  直接 available += units，最多到 capacity
不要求 FREE 前先 AWAIT
不记录 held_by
HELD = capacity - available
不支持 PREEMPT
```

GATE：

```text
GATE LIGHT1(state=CLOSED);
OPEN(gate=LIGHT1);
CLOSE(gate=LIGHT1);
```

---

## 17. PREEMPT

```text
P: PREEMPT(
  resource=TOOL,
  preempted_to=DOWN,
  priority=HIGH(ATRIB(2)),
);
```

规则：

```text
当前实体申请资源
资源可用 → 占用并继续
资源被占用 → 按 priority 比较
  当前更高 → 抢占持有者
  当前不更高 → 等待
```

被抢占实体：

```text
剩余服务时间由系统内部保存
preempted_to 省略 → 资源释放后恢复原活动
preempted_to 指定 → 立即路由到目标节点
```

---

## 18. 自动统计

统计区间：

```text
[start, end]
```

时间加权指标：

```text
QUEUE.LENGTH
ACTIVITY.UTIL
RESOURCE.UTIL
```

观测指标：

```text
TIME IN SYSTEM
QUEUE.WAIT
ACTIVITY.SERVICE
BALK.QUEUE
BLOCK.ACTIVITY
```

`TIME IN SYSTEM`：

```text
正常 TERMINATE 才记录
BALK 实体不记录
```

F8/F9：

```text
最大空闲时间 + 服务台序号
最大忙碌时间 + 服务台序号
```

`BLOCKED` 单独统计，不混入 idle/busy。

---

## 19. 初始化与运行

```python
model = Model.from_file("model.helix")

scenario = model.initialize(
    initial={...},
    constants={...},
    entities={...},
)

result = scenario.run(
    start=0,
    end=480,
    seed=1,
)
```

规则：

```text
initial 按变量标签解析
未给出的变量默认 0
未知标签报错
constants 单独提供
entities 按节点/队列标签提供
队列未提供实体时初始长度为 0
entities 列表长度决定初始实体数量
initialize 不修改 model
```

---

## 20. 错误语义

以下情况必须编译/运行时报错：

```text
重复节点
未定义节点
未定义队列/资源/门
count 和 until 同时出现
on_full=BALK 但目标不存在
IF 缺少 ELSE
SELECT 引用了不存在的队列
initial 含未知变量
entities 含未知队列
```

错误信息必须包含：

```text
文件
行
列
节点
原因
```

---

## 21. DEBUG 语义

```text
debug=False 不改变仿真结果
debug=True 只增加记录
debug_parse=True 只增加编译期记录
```

DEBUG 文件不得影响：

```text
随机数序列
事件顺序
统计结果
```

---

## 22. 本版不实现

```text
命名属性接口
命名变量表达式
连续系统的 DETECT 交叉细节
warm-up / 多 replication
高级 SELECT queue_rule
SAVE 的完整属性合并
动画布局
```
---

## 23. 资源与门（v1.0 补充）

`AWAIT` 是原子申请：

```text
资源足够 → 一次获得全部 units
资源不足 → 整个申请等待
不部分分配
```

等待顺序：

```text
priority 高者先
同 priority FIFO
```

`FREE`：

```text
释放 units
立即唤醒能够满足的最高优先级等待者
```

`ALTER`：

```text
不强制收回已占用资源
容量降低后等待现有持有者释放
```

GATE：

```text
OPEN   通过
CLOSED 等待
```

GATE 等待按 priority，再 FIFO；`OPEN` 时同步唤醒。

---

## 24. PREEMPT（v1.0 补充）

```text
资源可用 → 当前实体占用并继续
资源被占用 → 比较 priority
当前更高 → 抢占
否则 → 等待
```

抢占时：

```text
保存被抢占实体剩余服务时间
保存原活动
按 preempted_to 路由
省略 preempted_to → 进入恢复等待
```

不自动释放无关资源，不自动破解循环等待。

---

## 25. DETECT / SEVNT（v1.0 补充）

```text
DETECT name=HI, when=SS(1) >= 80, tol=0.01;
```

规则：

```text
只在 false → true 时触发
默认 edge=RISING
离开容差带后才允许再次触发
```

方向：

```text
RISING
FALLING
ANY
```

第一版 `SEVNT` 只支持系统停止事件：

```text
code=1 终止仿真
```

普通事件必须提供 `name`：

```text
SEVNT name=DUMP_READY, code=2, when=STORAGE_LEVEL > 50
```

统一等待语法：

```text
ACTIVITY(until=ENDU)
ACTIVITY(until=DUMP_READY)
```

```text
DETECT 节点标签和 SEVNT.name 进入同一个事件命名空间
until 只认事件名，不再区分 REL/STOPA
```

---

## 26. 连续系统（v1.0 补充）

```text
CONTINUOUS METHOD=RK4, MIN_STEP=0.001,
           SAVE_STEP=0.1, MAX_STEP=0.1;
```

规则：

```text
默认 RK4
SS 初值由 Python 提供
DD 由 EQUATION 计算
SS 代数方程按书写顺序求值
DD 使用当前 SS
检测到代数环 → 报错
```

连续/离散耦合：

```text
离散事件在 t
→ 连续积分到 t
→ 处理离散事件
→ 继续积分
```

DETECT：

```text
每个积分步后检查
若条件在步内穿越，用二分法定位根
根搜索使用同一积分器
```

第一版不对非比较条件做根搜索。

`SAVE_STEP` 只控制采样输出，不改变积分精度。

---

## 27. 结束、死锁与停滞（v1.0 补充）

```text
t <= end 的事件执行
t > end 的事件丢弃
CEL 清空后推进统计到 end
```

FEL/CEL 都为空后仍有实体等待：

```text
等待资源
等待 GATE
等待 SELECT 队列
等待 JOIN 分支
```

报告 `deadlock.json`：

```text
时间
实体 id
等待对象
等待原因
资源持有关系
```

不自动释放资源。

没有实体、没有事件：

```text
直接结束，统计为 0
```

---

## 28. 版本与兼容（v1.0 补充）

```text
语言版本：HELIX 1
语义版本：v1.0
DEBUG 格式：helix-debug / version 1
```

未知语法、未知字段、未知 DEBUG 版本必须报错。

---

## 29. v1.0 验收闭环

```text
同 seed 重放完全一致
debug 开/关结果一致
FEL/CEL 同刻顺序稳定
BALK 不计 TIME IN SYSTEM
BLOCK 不污染 idle/busy
JOIN/SELECT 属性规则一致
资源等待与唤醒正确
死锁可报告
```
