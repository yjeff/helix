# Helix 详细设计

状态：实现设计草案。  
目标：实现 Helix 语法与语义 v1.0。  
旧项目：`slam_v2`，仅作参考。

---

## 1. 目标

```text
模型只读
场景独立
事件内核与物理模型解耦
离散、连续、混合共用同一个内核
自动统计
DEBUG 可回放、可驱动动画
```

非目标：

```text
兼容旧 SLAM 语法
运行时加载 Python STATE 回调
在模型中写报告配置
```

---

## 2. 分层架构

```text
Source
  ↓
Lexer
  ↓
Parser
  ↓
AST
  ↓
Compiler (model.py)
  ↓
Model IR (frozen)
  ↓
Scenario
  ↓
Kernel
  ├── DiscreteRuntime (runtime/discrete.py)
  ├── ContinuousSource (continuous/source.py)
  ├── Statistics / RunResult (runtime/state.py)
  └── DebugRecorder (debug.py)
  ↓
RunResult
  ↓
Report / Animation
```

职责：

| 层 | 当前实现 | 职责 |
|---|---|---|
| Lexer | `lexer.py` | 字符 → Token |
| Parser | `parser.py` | Token → AST |
| Compiler | `model.py` 的 `compile_program()` | AST → Model IR、名字解析、静态校验、freeze |
| Scenario | `scenario.py` | 初值、常量、初始实体 |
| Kernel | `kernel.py` | FEL/CEL、时间推进、事件调度 |
| DiscreteRuntime | `runtime/discrete.py` | CREATE/QUEUE/ACTIVITY/资源等全部离散节点处理器 |
| ContinuousSource | `continuous/source.py` | DD/SS 推进、DETECT/SEVNT |
| Statistics | `runtime/state.py` | 自动统计、`RunResult` |
| DebugRecorder | `debug.py` | 结构化 DEBUG |
| Report | `runtime/state.py` 的 `RunResult.report()` | track/plot/输出 |

`kernel.py` 会构造 `DiscreteRuntime`，但不在 Kernel 内按节点类型分支；
节点语义仍由 `DiscreteRuntime._route_node()` 分派。连续模型由
`ContinuousSource` 提供时间推进，Kernel 只处理事件和时钟。

---

## 3. 当前模块布局

以下目录与 `src/helix/` 的实际文件一致：

```text
src/helix/
  __init__.py
  __main__.py
  errors.py
  tokens.py
  lexer.py
  ast.py
  parser.py
  model.py              # AST -> Model IR、validate、freeze
  scenario.py
  kernel.py             # FEL/CEL 和事件调度
  events.py
  replicas.py
  debug.py
  animate.py
  cli.py
  runtime/
    __init__.py
    discrete.py         # 所有离散节点处理器
    state.py            # 运行时状态、Stat、RunResult、report
  continuous/
    __init__.py
    expressions.py
    equations.py        # RK4/RKF45
    source.py           # ContinuousSource、DETECT/SEVNT
```

职责说明：

```text
model.py
  compile_program / validate / freeze
  没有独立的 compiler.py

runtime/discrete.py
  CREATE / QUEUE / ACTIVITY / AWAIT / FREE / ALTER / ...
  没有 queues.py / activities.py / resources.py / gates.py /
  select.py / branching.py 这些拆分文件

runtime/state.py
  QueueState / ActivityState / ResourceState / GateState
  QueueStat / ServiceStat / ResourceStat / GateStat
  RunResult / report
  没有独立的 stats.py 或 report.py

continuous/
  source.py 包含连续推进和 DETECT/SEVNT
  equations.py 包含积分器
  没有 integrator.py 或 detect.py

kernel.py
  Kernel + FEL/CEL
  没有独立的 time_source.py
```

早期设计曾计划拆分 `compiler.py`、`stats.py`、`report.py`、
`time_source.py` 以及更细的 runtime/continuous 模块，但没有落地。
这些文件不应出现在导入路径或新文档中。

如果未来进行模块拆分，必须同步更新本节和
`docs/reading-guide.md` 的源码入口表。

---

## 4. 编译流程

```text
Model.from_file(path)
  → read_text
  → parse (lexer + parser)
  → compile_program
  → validate
  → freeze
  → Model
```

编译期完成：

```text
标签唯一性
未定义引用
缺失 ELSE
count/until 互斥
on_full 目标存在
SELECT queues/servers 存在
资源/门声明
方程变量存在
边合法性
顺序默认边生成
```

编译期不执行：

```text
不抽样
不创建实体
不初始化变量
```

编译完成后 `Model.freeze()` 把节点参数、边、变量表转为只读结构；
运行期修改会直接报错或通过结构指纹发出警告。

---

## 5. 场景初始化

```python
model = Model.from_file("model.helix")

scenario = model.initialize(
    initial={...},
    constants={...},
    entities={...},
)
```

`initialize`：

```text
持有已冻结 Model 的只读引用
规范化并复制 initial / constants / entities
校验 initial 标签和数组初值
创建 Scenario
```

不修改 `model`；Model 在 `Scenario` 创建前已经 `freeze()`。

多次运行：

```text
scenario.run(seed=1)
scenario.run(seed=2)
```

每次都从同一初始状态开始，互不污染。

---

## 6. 事件内核

### 6.1 数据结构

```text
FEL：最小堆，按 (time, seq)
CEL：deque，按进入顺序
now：当前仿真时刻
seq：全局事件序号
batch：同一时刻的 CEL 批次号
```

### 6.2 主循环

```text
while not finished:
    if CEL empty:
        t_next = next_time()

        if t_next is None:
            break

        t_actual = continuous.advance_to(t_next)

        statistics.advance_to(t_actual)
        now = t_actual

        CEL.extend(continuous.events_at(now))
        FEL.move_time(now, CEL)

        batch += 1

    event = CEL.popleft()
    dispatch(event)

    schedule(event):
        if event.time == now:
            CEL.append(event)
        else:
            FEL.push(event)
```

### 6.3 next_time

```text
t_fel = FEL.peek_time()
t_cont = continuous.next_time(now, end)

t_next = min(t_fel, t_cont, end)
```

没有连续系统：

```text
t_cont = end
```

没有 FEL：

```text
t_fel = end
```

### 6.4 连续推进

```text
continuous.advance_to(t_next) -> t_actual
```

允许：

```text
t_actual < t_next
```

原因：

```text
积分步内检测到 DETECT/SEVNT
在事件发生时刻截断
```

约束：

```text
t_actual >= now
t_actual <= t_next
不修改 FEL/CEL
```

### 6.5 同刻顺序

```text
连续事件先加入 CEL
FEL 同刻事件后加入 CEL
CEL 内 FIFO
新产生的同刻事件追加尾部
```

### 6.6 结束

```text
t > end 的事件不执行
t == end 的事件执行
CEL 清空后统计推进到 end
```

### 6.7 死锁

FEL/CEL 都为空后仍有实体等待：

```text
资源
GATE
SELECT 队列
JOIN 分支
```

生成 `deadlock.json`，不自动释放资源。

---

## 7. TimeSource 接口

```text
class TimeSource:
    def next_time(now, end) -> float
    def advance_to(t) -> float
    def events_at(t) -> list[Event]
```

离散：

```text
FELSource
  next_time = FEL.peek_time()
  advance_to = no-op
  events_at = []
```

连续：

```text
ContinuousSource
  next_time = min(now + MAX_STEP, next_save, end)
  advance_to = 积分并返回实际时刻
  events_at = DETECT/SEVNT 事件
```

未来扩展：

```text
外部实时源
联合仿真源
GPU 批量源
```

不需要改 Kernel。

---

## 8. 离散运行时

### 8.1 事件类型

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

### 8.2 处理器注册

```text
HANDLERS = {
  "CREATE": on_create,
  "END_ACTIVITY": on_end_activity,
  ...
}
```

Kernel 只调用 `dispatch(event)`，不关心具体节点。

### 8.3 同步动作

以下动作在事件处理内立即完成：

```text
入队
启动服务
释放资源
唤醒等待者
```

它们可以递归产生更多同刻 CEL 事件。

### 8.4 队列

见 `data-structures.md` 的 `QueueState`。

---

## 9. 连续运行时

### 9.1 方程

```text
SS 代数方程
DD 微分方程
```

规则：

```text
SS 按书写顺序求值
DD 使用当前 SS
检测代数环
```

### 9.2 积分器

```text
RK4
MIN_STEP
SAVE_STEP
MAX_STEP
```

`next_time`：

```text
min(now + MAX_STEP, next_save_time, end)
```

`advance_to`：

```text
按 MIN_STEP/MAX_STEP 细分
不越过目标时刻
检测 DETECT
```

### 9.3 DETECT

```text
edge=RISING / FALLING / ANY
tol=0.01
```

触发后生成连续事件：

```text
Event(time=t, kind=DETECT, ...)
```

由 Kernel 放入 CEL。

### 9.4 采样

```text
SAVE_STEP 只影响输出
不影响积分精度
```

---

## 10. 统计

统计不依赖模型声明。

自动收集：

```text
TIME IN SYSTEM
QUEUE.WAIT
QUEUE.LENGTH
ACTIVITY.UTIL
ACTIVITY.BLOCK
RESOURCE.UTIL
GATE.WAIT
BALK
SS/XX 历史
```

时间加权：

```text
value × dt
```

在 `statistics.advance_to(t)` 中更新。

观测：

```text
在事件发生时 add(value)
```

---

## 11. DEBUG

### 编译期

```text
tokens.ndjson
parse.ndjson
ast.json
```

### 仿真期

```text
run.json
model.json
events.ndjson
states.ndjson
```

DEBUG 不得改变：

```text
RNG
CEL/FEL
统计
```

事件记录带：

```text
t
seq
batch
type
entity
node
```

---

## 12. 错误处理

### 编译错误

```text
文件
行
列
期望
实际
```

### 运行错误

```text
队列满且 ERROR
未知资源
未知节点
资源单位不足
```

### 死锁

```text
deadlock.json
```

错误类型：

```text
HelixSyntaxError
HelixCompileError
HelixRuntimeError
HelixDeadlockError
```

---

## 13. 确定性

```text
同一 model
同一 scenario
同一 seed
→ 同一事件序列
→ 同一统计
```

保证：

```text
FEL/CEL 顺序固定
RNG 单一流
无系统时间依赖
无哈希顺序依赖
```

---

## 14. 报告

```python
result.report(
    path,
    track=[...],
    plot=[...],
    project=...,
    analyst=...,
)
```

模型不参与报告配置。

---

## 15. 测试

```text
lexer/parser 单元测试
Kernel 同刻事件测试
BALK/BLOCK 测试
JOIN/SELECT 规则测试
资源唤醒测试
连续 DD/SS 测试
DEBUG 重放测试
案例 golden test
```

---

## 16. 实现顺序

```text
1. tokens/lexer/parser
2. Model IR / compiler
3. Scenario
4. Kernel + FEL/CEL
5. DiscreteRuntime 基础节点
6. 自动统计
7. DEBUG
8. IF/分支
9. PARALLEL/SPLIT/JOIN/MERGE
10. SELECT
11. 资源/GATE/PREEMPT
12. 连续 DD/SS
13. 案例迁移
```
