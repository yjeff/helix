# Helix 数据结构设计

状态：实现设计草案。  
对应：[design.md](design.md)、[semantics.md](semantics.md)。

---

## 1. 命名约定

```text
time        float，仿真时间
seq         int，全局事件序号
batch       int，同一时刻 CEL 批次
entity_id   int，实体 id
node_label  str，节点标签
priority    float，实体优先级，越大越优先
```

所有时间单位由模型统一，不混用。

---

## 2. 词法与语法结构

### Token

```text
Token
  kind: str          IDENT/NUMBER/STRING/KEYWORD/COLON/ARROW/...
  text: str          原始文本
  value: object      解析值
  line: int
  col: int
  index: int
```

Token 只用于编译期和 DEBUG。

### AST Program

```text
Program
  version: "2"
  project: str
  declarations: list[Declaration]
  equations: list[Equation]
  network: list[NetworkItem]
```

### Declaration

```text
VarDecl
  name: str
  label: str
  low: float | None
  high: float | None
  default: float = 0

ContinuousDecl
  method: str
  min_step: float
  save_step: float
  max_step: float

ResourceDecl
  name: str
  capacity: int

GateDecl
  name: str
  state: OPEN | CLOSED

DetectDecl
  name: str
  when: Expr
  edge: RISING | FALLING | ANY
  tol: float = 0.01

SevntDecl
  code: int
  when: Expr
```

### NetworkItem

```text
NodeDecl
  label: str | None
  kind: str
  args: dict[str, Expr]
  line: int

EdgeDecl
  source: str
  target: str
  line: int

IfBlock
  label: str | None
  branches: list[WhenBranch]
  else_target: str

WhenBranch
  condition: Expr
  target: str

ParallelBlock
  label: str | None
  paths: list[str]

SplitBlock
  label: str | None
  parts: list[str]
  paths: dict[str, str]
```

---

## 3. Model IR

### Model

```text
Model
  version: int = 2
  project: str
  variables: dict[str, VarSpec]
  continuous: ContinuousSpec | None
  resources: dict[str, ResourceSpec]
  gates: dict[str, GateSpec]
  detects: list[DetectSpec]
  sevnts: list[SevntSpec]
  nodes: dict[str, NodeSpec]
  order: list[str]
  edges: list[EdgeSpec]
  source_hash: str
```

`Model` 只读；`initialize` 创建 `Scenario`。

### NodeSpec

```text
NodeSpec
  label: str
  kind: NodeKind
  params: dict[str, Value]
  outgoing: list[str]
  line: int
```

`NodeKind`：

```text
CREATE
QUEUE
ACTIVITY
TERMINATE
ASSIGN
AWAIT
FREE
ALTER
OPEN
CLOSE
PREEMPT
EVENT
MATCH
DETECT
IF
PARALLEL
SPLIT
JOIN
MERGE
SELECT
```

### EdgeSpec

```text
EdgeSpec
  source: str
  target: str
  kind: DEFAULT | EXPLICIT | BRANCH | SERVER
```

### VarSpec

```text
VarSpec
  name: str
  label: str
  low: float | None
  high: float | None
  initial_default: float = 0
```

### ResourceSpec

```text
ResourceSpec
  name: str
  capacity: int
  mode: POOL | RESTOCK
```

### GateSpec

```text
GateSpec
  name: str
  initial_state: OPEN | CLOSED
```

### ContinuousSpec

```text
ContinuousSpec
  method: RK4
  min_step: float
  save_step: float
  max_step: float
```

---

## 4. Scenario

```text
Scenario
  model: Model
  initial: dict[str, float]
  constants: dict[str, float]
  initial_entities: dict[str, list[EntityInit]]
```

### EntityInit

```text
EntityInit
  attrs: dict[str, float]
  priority: float = 0
```

`Scenario` 是运行模板，可多次 `run`。

---

## 5. Entity

```text
Entity
  id: int
  created_at: float
  priority: float
  attrs: dict[str, Value]
  current_node: str | None
  status: EntityStatus
  origin_id: int | None
  part: str | None

  held: dict[str, int]
  waiting_for: WaitReason | None
  activity_token: int
  remaining_time: float | None
  resume_node: str | None
  last_queue: str | None
```

`EntityStatus`：

```text
ACTIVE
WAITING_QUEUE
WAITING_RESOURCE
WAITING_GATE
WAITING_SELECT
WAITING_JOIN
BLOCKED
TERMINATED
BALKED
```

不变量：

```text
id 唯一
created_at <= now
priority 默认 0
held 中单位数 >= 0
```

---

## 6. 事件

### Event

```text
Event
  time: float
  seq: int
  kind: EventKind
  entity_id: int | None
  node: str | None
  data: dict[str, object]
  source: DISCRETE | CONTINUOUS
```

`EventKind`：

```text
CREATE
ENQUEUE
START_ACTIVITY
END_ACTIVITY
UNBLOCK
TERMINATE
ASSIGN
AWAIT
FREE
OPEN
CLOSE
PREEMPT
SELECT
JOIN
MERGE
DETECT
SEVNT
```

### FEL

```text
FEL
  heap: list[(time, seq, Event)]
  next_time() -> float | None
  push(event)
  move_time(t, cel)
```

不变量：

```text
堆按 (time, seq)
不允许 time < now
```

### CEL

```text
CEL
  deque[Event]
```

不变量：

```text
所有事件 time == now
FIFO
新同刻事件追加尾部
```

---

## 7. Kernel

```text
Kernel
  model: Model
  scenario: Scenario
  discrete: DiscreteRuntime
  continuous: ContinuousRuntime
  statistics: Statistics
  debug: DebugRecorder | None

  now: float
  end: float
  seq: int
  batch: int
  fel: FEL
  cel: CEL
  finished: bool
```

方法：

```text
run()
next_time() -> float | None
advance_to(t)
schedule(event)
dispatch(event)
check_deadlock()
```

不变量：

```text
CEL 非空时 now 不变
FEL 中事件 time >= now
seq 单调递增
batch 只在 now 前进时增加
```

---

## 8. TimeSource

```text
TimeSource
  next_time(now, end) -> float
  advance_to(t) -> float
  events_at(t) -> list[Event]
```

`FELSource`：

```text
next_time = FEL.peek_time or end
advance_to = no-op
events_at = []
```

`ContinuousSource`：

```text
next_time = min(now + max_step, next_save, end)
advance_to = 积分并返回实际时刻
events_at = DETECT/SEVNT
```

---

## 9. Discrete Runtime State

### QueueState

```text
QueueState
  node: NodeSpec
  items: deque[Entity]
  capacity: int
  order: QueueOrder
  on_full: FullAction

  area: float
  max_length: int
  current_length: int

  wait_sum: float
  wait_count: int
  balk_count: int
  blocked_upstream: int
```

不变量：

```text
len(items) <= capacity（capacity > 0）
current_length == len(items)
area 单调不减
```

### QueueOrder

```text
FIFO
LIFO
PRIORITY
LOW_PRIORITY
HIGH_ATTR
LOW_ATTR
```

### FullAction

```text
ERROR
BLOCK
BALK(target)
```

### ServerState

```text
ServerState
  index: int
  status: IDLE | BUSY | BLOCKED
  entity_id: int | None
  start_time: float | None
  end_time: float | None

  idle_since: float
  busy_since: float

  max_idle: float
  max_idle_index: int
  max_busy: float
  max_busy_index: int
```

不变量：

```text
index in 1..capacity
BUSY 时 entity_id 非空
IDLE 时 entity_id 为空
BLOCKED 单独统计
```

### ActivityState

```text
ActivityState
  node: NodeSpec
  servers: list[ServerState]

  active: int
  completed: int
  blocked: int

  area: float
  blocked_area: float
```

不变量：

```text
active == count(BUSY)
blocked == count(BLOCKED)
active + blocked <= capacity
```

### ResourceState

```text
ResourceState
  name: str
  capacity: int
  available: int
  mode: POOL | RESTOCK
  held_by: dict[int, int]
  waiters: list[Entity]

  area: float
  area2: float
  max_held: int
```

资源不变量：

```text
0 <= available <= capacity

POOL:
  sum(held_by.values()) == capacity - available

RESTOCK:
  不维护 held_by
  available 就是当前库存
  HELD = capacity - available
```

### GateState

```text
GateState
  name: str
  state: OPEN | CLOSED
  waiters: list[Entity]

  wait_count: int
  area: float
```

### SelectState

```text
SelectState
  node: NodeSpec
  waiting: list[Entity]
  queue_rule: str
  server_rule: str
  queues: list[str]
  servers: list[str]
  save_rule: MergeRule
```

### JoinState

```text
JoinState
  node: NodeSpec
  count: int
  merge: MergeRule
  groups: dict[int, list[Entity]]
```

### MergeRule

```text
FIRST
LAST
HIGH(i)
LOW(i)
SUM
MULT
```

---

## 10. Statistics

### ObservationAccumulator

```text
ObservationAccumulator
  label: str
  count: int
  sum: float
  sum_sq: float
  min: float
  max: float
  values: list[float] | None   ; 仅 DEBUG
```

方法：

```text
add(value)
mean()
std()
```

### TimeWeightedAccumulator

```text
TimeWeightedAccumulator
  area: float
  base_time: float
  current: float
```

方法：

```text
advance(dt, value)
mean(duration)
```

### ServiceStat

```text
ServiceStat
  activity: str
  capacity: int
  average_utilization: float
  std_utilization: float
  current_utilization: int
  average_blockage: float
  max_idle: float
  max_idle_server: int
  max_busy: float
  max_busy_server: int
  completed: int
```

### QueueStat

```text
QueueStat
  queue: str
  average_length: float
  std_length: float
  max_length: int
  current_length: int
  balk_count: int
```

### ResourceStat

```text
ResourceStat
  name: str
  capacity: int
  available: int
  average_held: float
  maximum_held: int
  current_held: int
  average_utilization: float
  std_utilization: float
  maximum_utilization: float
  current_utilization: float
  wait_count: int
  average_wait: float
  max_wait: float
```

POOL 模式的 `current_held` 是当前已持有量；RESTOCK 模式的
`current_held` 是 `capacity - available`，`available` 是当前库存。

### RunResult

```text
RunResult
  project: str
  now: float
  observations: list[ObservationStat]
  queues: list[QueueStat]
  services: list[ServiceStat]
  resources: list[ResourceStat]
  continuous: ContinuousHistory | None
  debug_path: str | None
```

---

## 11. Continuous State

```text
ContinuousState
  variables: dict[str, float]
  derivatives: dict[str, float]
  time: float
```

### ContinuousHistory

```text
ContinuousHistory
  samples: list[Sample]
  step_count: int
  rejected_steps: int
```

### Sample

```text
Sample
  t: float
  values: dict[str, float]
```

### DetectState

```text
DetectState
  name: str
  edge: RISING | FALLING | ANY
  tol: float
  armed: bool
  last_value: float
```

---

## 12. DebugRecord

```text
DebugRecord
  t: float
  seq: int
  batch: int
  type: str
  entity: int | None
  node: str | None
  server: int | None
  queue_length: int | None
  active: int | None
  blocked: int | None
  attrs: dict[str, float] | None
  priority: float | None
```

---

## 13. 不变量总表

```text
FEL 按 (time, seq) 有序
FEL 事件 time >= now
CEL 事件 time == now
CEL FIFO
seq 单调递增
batch 只在 now 前进时增加

Entity.id 唯一
Entity.created_at <= now

Queue.current_length == len(Queue.items)
Queue.area 单调不减

Activity.active == BUSY 服务台数
Activity.blocked == BLOCKED 服务台数
active + blocked <= capacity

Resource.available + sum(held_by) == capacity

统计面积只在前进时更新
DEBUG 不改变上述任何值
```

---

## 14. 内存策略

```text
普通运行：
  只保存统计累计值
  不保存每个事件
  Entity 可回收

DEBUG：
  事件写入 NDJSON
  states.ndjson 保存动画快照
  不一次性保留全部事件

连续：
  只保存 SAVE_STEP 采样
  不保存每个积分步
```
