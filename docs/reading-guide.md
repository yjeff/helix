# Helix 源码阅读指南

本文给第一次阅读 Helix 实现的人一条可执行的路线。目标不是“从第一行读到最后一行”，而是先建立正确的运行时模型，再按功能追踪代码。

---

## 0. 先建立三个基本判断

阅读代码前先记住：

```text
.helix 文件是模型语义
Model 是编译后的只读模型
Scenario 是一次运行的初值和常量
Kernel / DiscreteRuntime 是每次运行新建的运行时
RunResult 是运行结束后的统计快照
```

因此：

```text
Model 可以被多次 initialize/run
每次 run 有独立的运行时状态
ALTER 的覆盖值属于当前运行，不写回 Model
```

如果这三点混淆，阅读 `ALTER`、`--replicas`、统计清零时很容易误判。

---

## 1. 30 分钟快速路径

### 第 1 步：先运行案例

```bash
cd helix
python -m helix check examples/serial_workstations/model.helix
python -m helix run examples/serial_workstations/model.helix --end 50 --seed 1
```

再看一个混合模型：

```bash
python -m helix run examples/liquid_level/model.helix --end 80 --seed 1
```

先观察命令行输出和 `out/report.md`，建立“输入模型 → 输出统计”的直觉。

### 第 2 步：读最小的模型

看：

```text
examples/serial_workstations/model.helix
examples/serial_workstations/run.py
```

确认以下语法各自对应什么：

```text
CREATE
QUEUE
ACTIVITY
TERMINATE / EXIT
```

### 第 3 步：读四步 API

文件：

```text
src/helix/__init__.py
src/helix/scenario.py
```

重点看：

```python
model = helix.Model.from_file(...)
scenario = model.initialize(...)
result = scenario.run(...)
result.report(...)
```

以及新增的：

```python
scenario.run_replicas(...)
result.manifest()
```

### 第 4 步：读 Kernel 主循环

文件：

```text
src/helix/kernel.py
```

只看一个方法：

```text
Kernel.run()
```

阅读时回答三个问题：

```text
1. FEL 和 CEL 分别是什么？
2. 时钟什么时候前进？
3. 同一时刻的事件如何保持顺序？
```

不要一开始读所有统计推进代码。

### 第 5 步：读节点分发表

文件：

```text
src/helix/runtime/discrete.py
```

先看：

```text
DiscreteRuntime.handle()
DiscreteRuntime._route()
DiscreteRuntime._route_node()
```

`_route_node()` 是整份运行时最好的目录：

```text
QUEUE
ACTIVITY
ASSIGN
IF
AWAIT
FREE
ALTER
PREEMPT
TERMINATE
...
```

遇到某个节点，先从这里找到处理函数，再读具体函数。

### 第 6 步：读统计和报告

文件：

```text
src/helix/runtime/state.py
```

先看：

```text
RunResult
RunResult.report()
Observation
ResourceStat / ServiceStat / QueueStat
```

理解：

```text
area / duration = 时间加权平均
Observation = Welford 在线统计
```

### 第 7 步：读测试

测试是最好的行为规范。推荐顺序：

```text
tests/test_helix.py
tests/test_resources.py
tests/test_report.py
tests/test_replicas.py
tests/test_cli.py
tests/test_case_port.py
```

---

## 2. 推荐的整体架构图

```text
.helix source
    ↓
lexer.py
    ↓
parser.py
    ↓
ast.py
    ↓
model.py / compile_program()
    ↓
Model IR（只读）
    ↓
scenario.py
    ↓
kernel.py
    ├── runtime/discrete.py
    ├── continuous/source.py
    ├── runtime/state.py
    └── debug.py
    ↓
RunResult
    ├── report()
    ├── manifest()
    └── replicas.py
```

核心边界：

```text
Kernel 不知道 QUEUE / ACTIVITY / RK4 的语义
Kernel 只管理时间、事件和调度
DiscreteRuntime 决定节点如何改变实体状态
State 负责统计，不负责调度
```

---

## 3. 按层阅读

### 3.1 语言表面

```text
src/helix/lexer.py
src/helix/parser.py
src/helix/ast.py
src/helix/model.py
```

阅读顺序：

```text
Lexer
→ Parser
→ AST
→ Model / compile_program
→ validate
```

重点：

```text
parser 只负责“看懂语法”
model 负责“跨节点校验和 IR”
runtime 才负责“实际行为”
```

不要在 parser 里寻找运行时语义。

### 3.2 场景与运行入口

```text
src/helix/scenario.py
```

重点：

```text
initialize()
run()
run_replicas()
```

`Scenario` 是“模型 + 本次实验参数”的组合，不持有运行时资源账本。

### 3.3 事件内核

```text
src/helix/events.py
src/helix/kernel.py
```

重点：

```text
Event
Entity
Kernel.run()
Kernel.advance_statistics()
```

需要理解：

```text
FEL = future event list
CEL = current event list
同一时刻的事件先进入 CEL
统计面积只在时钟真正前进时累计
```

### 3.4 离散运行时

```text
src/helix/runtime/discrete.py
```

建议按节点族阅读，而不是从头到尾：

```text
CREATE / TERMINATE：创建与结束
QUEUE / ACTIVITY：流动与服务
AWAIT / FREE / ALTER / PREEMPT：资源
ASSIGN / OBSERVE / IF / SCAN / EVENT：控制
PARALLEL / SPLIT / FORK / JOIN / MERGE：同步
SELECT：装配
```

核心函数：

```text
handle()
_route()
_route_node()
_on_create()
_start_activity()
_await()
_free()
_alter()
_enter_if()
_terminate()
result()
```

### 3.5 统计与报告

```text
src/helix/runtime/state.py
```

重点区分：

```text
QueueState / ActivityState / ResourceState
   运行时累计状态

QueueStat / ServiceStat / ResourceStat / AwaitStat
   运行结束后的只读统计

RunResult
   报告、manifest、track 的数据源
```

活动与资源的利用率列名已经区分：

```text
Activity: AVG SVC UTIL.
Resource: AVG OCCUPANCY
```

### 3.6 重复运行

```text
src/helix/replicas.py
```

重点：

```text
ReplicaResult
ReplicaMetric
run_replicas()
```

它不复制模型，而是对同一个 Scenario 做多次独立 run。

### 3.7 连续与混合

```text
src/helix/continuous/source.py
src/helix/continuous/equations.py
src/helix/continuous/expressions.py
```

建议先读：

```text
ContinuousSource.advance_to()
ContinuousModel
DETECT / SEVNT 的事件生成
```

### 3.8 CLI / DEBUG / 动画

```text
src/helix/cli.py
src/helix/debug.py
src/helix/animate.py
```

CLI 只是薄封装，真正行为仍在 `scenario`、`kernel`、`runtime`。

---

## 4. 源码入口表

| 路径 | 入口 | 阅读目的 |
|---|---|---|
| `src/helix/lexer.py` | `Lexer` | 字符如何变成逻辑行 |
| `src/helix/parser.py` | `Parser` / `parse` | 语句如何变成 AST |
| `src/helix/ast.py` | `Program` | AST 结构 |
| `src/helix/model.py` | `Model.from_source` / `freeze` / `validate` | 编译为 Model IR，检查引用并冻结 |
| `src/helix/scenario.py` | `initialize` / `run` / `run_replicas` | 场景和运行入口 |
| `src/helix/events.py` | `Event` / `Entity` | 调度和实体数据 |
| `src/helix/kernel.py` | `Kernel.run` | FEL/CEL、时间推进 |
| `src/helix/runtime/discrete.py` | `handle` / `_route_node` | 节点行为总入口 |
| `src/helix/runtime/state.py` | `RunResult` / `report` | 统计和报告 |
| `src/helix/replicas.py` | `ReplicaResult` | 置信区间聚合 |
| `src/helix/cli.py` | `main` / `_run` / `_compare` | CLI 参数 |
| `src/helix/continuous/source.py` | `advance_to` | 连续推进 |
| `src/helix/debug.py` | `DebugRecorder` | DEBUG 文件 |
| `src/helix/animate.py` | `build_player` | HTML 动画 |

---

## 5. 三条追踪练习

### 练习 A：最小 CREATE → EXIT

模型：

```text
HELIX 1
NETWORK
  CREATE(count=1) -> DONE
  DONE: EXIT()
END
```

追踪：

```text
1. Kernel 产生 CREATE 事件
2. DiscreteRuntime.handle() 处理
3. _on_create() 创建 Entity
4. _route() 到 DONE
5. _route_node() 识别 TERMINATE
6. _terminate() 记录 TIME IN SYSTEM
7. Kernel.run() 汇总 RunResult
```

### 练习 B：QUEUE → ACTIVITY → FREE

模型：

```text
CREATE(count=1) -> Q
Q: QUEUE() -> A
A: ACTIVITY(duration=2) -> DONE
DONE: EXIT()
```

重点看：

```text
_enqueue()
_start_activity()
_on_end_activity()
_release_waiting()
```

回答：

```text
实体什么时候进入队列？
服务台什么时候变 BUSY？
活动结束后如何唤醒队列？
```

### 练习 C：IF 与 ALTER

模型：

```text
CREATE(count=1) -> CHECK
CHECK: IF RANDOM() < 0.5 -> A
ELSE -> B
B: ALTER(activity=A, duration=1) -> DONE
A: ACTIVITY(duration=5) -> DONE
DONE: EXIT()
```

重点：

```text
_enter_if()
_alter()
_route_node()
```

要确认：

```text
ALTER 覆盖值只存在于当前运行
不写回 Model.nodes[...].args
```

### 练习 D：连续 DETECT

模型：

```text
CONTINUOUS METHOD=RK4 ...
EQUATION
  DD(X) = -X
END
NETWORK
  DETECT(when=X < 1, edge=FALLING) -> DONE
  DONE: EXIT()
END
```

重点：

```text
ContinuousSource.advance_to()
DETECT 事件生成
Kernel 把连续事件放入 CEL
```

---

## 6. 用 DEBUG 阅读

运行：

```bash
python -m helix run examples/tv_inspection/model.helix \
  --end 480 --seed 1 \
  --debug --debug-path out/debug
```

输出：

```text
out/debug/run.json
out/debug/model.json
out/debug/events.ndjson
out/debug/states.ndjson
```

建议先看：

```text
run.json       本次运行的 seed、模型哈希、配置
events.ndjson  事件顺序
states.ndjson  每个事件前的状态
```

动画：

```bash
python -m helix animate out/debug -o out/player.html
```

调试时不要只看最终报告；优先定位“哪个事件开始偏离预期”。

---

## 7. 如何新增一个节点

顺序不要反：

```text
1. parser.py       识别语法
2. ast.py          AST 数据结构
3. model.py        编译和校验
4. runtime/discrete.py  运行时 handler
5. state.py        是否产生新统计
6. tests/          行为测试
7. docs/           用户文档
```

实现新 handler 时：

```text
在 _route_node() 注册
不要修改 Model 的只读参数
需要跨运行变化的数据放在 RuntimeState
需要时间加权统计时在 advance() 中累计
需要报告时在 result() 中生成只读 Stat
```

---

## 8. 测试地图

| 测试 | 阅读目的 |
|---|---|
| `test_helix.py` | 语法、编译、基础运行 |
| `test_resources.py` | AWAIT/FREE/POOL/RESTOCK/PREEMPT |
| `test_alter_isolation.py` | ALTER 不跨运行污染 |
| `test_structure_warnings.py` | check 结构 warning |
| `test_event_guard.py` | 事件数和同刻护栏 |
| `test_report.py` | 报告列、track、plot、Welford |
| `test_replicas.py` | run_replicas 和 manifest |
| `test_cli.py` | CLI 参数、replicas、compare |
| `test_rng.py` | 独立随机子流 |
| `test_case_port.py` | Wait File、资源优先级、容量 0 |
| `test_case_*.py` | 书中案例回归 |

读一个功能时，先读对应测试的断言，再读实现。

---

## 9. 常见阅读陷阱

### 9.1 不要按行号阅读

行号会随版本变化。使用符号名、节点名和方法名定位：

```text
_route_node
_on_create
_start_activity
_await
result
report
```

### 9.2 不要把 Model 当运行状态

```text
Model.nodes / Model.resources 是编译后的模型
ResourceState / QueueState / ActivityState 才是运行时状态
```

编译后 Model 会自动 `freeze()`：

```text
节点 args / outgoing / branches / paths 变为只读
Model 的变量、资源、门、节点表变为只读映射
```

`ALTER` 的覆盖值属于当前运行，不写回 Model。
如果外部修改了运行期规范对象（例如 ResourceSpec），
下一次 `run()` 会通过结构指纹发出 `RuntimeWarning`。

### 9.3 不要忽略 FEL / CEL

同一时刻的事件先进入 CEL；时钟只在 CEL 为空时推进。

### 9.4 不要混淆活动和资源利用率

```text
Activity AVG SVC UTIL. = 忙碌服务台 / 服务台总数
Resource AVG OCCUPANCY = held / capacity
```

### 9.5 不要混淆 POOL 和 RESTOCK

```text
POOL: available + held = capacity
RESTOCK: available 是库存，HELD = capacity - available
```

### 9.6 不要忽略自动统计口径

```text
TIME IN SYSTEM 只统计 CUSTOMER
INTERNAL 实体不计入
BALK 实体不计入
```

### 9.7 不要忽略随机流模式

```text
默认 substreams
历史基线才用 global
```

---

## 10. 按角色的阅读路线

### 模型使用者

```text
README.md
→ examples/ 对应案例
→ docs/language-reference.md
→ docs/metrics.md
```

不需要先读 Kernel。

### 运行时开发者

```text
events.py
→ kernel.py
→ runtime/discrete.py
→ runtime/state.py
→ tests/test_resources.py
```

### 连续系统开发者

```text
continuous/expressions.py
→ continuous/equations.py
→ continuous/source.py
→ tests/test_continuous.py
```

### CLI / 工具开发者

```text
cli.py
→ scenario.py
→ replicas.py
→ debug.py
→ animate.py
```

---

## 11. 阅读后的自检问题

读完后应该能回答：

```text
1. Model 和 Scenario 的区别是什么？
2. 一个 CREATE 事件如何变成一个 Entity？
3. Queue 中的实体什么时候开始 Activity？
4. Activity 结束后如何唤醒等待者？
5. AWAIT 等待者按什么顺序被唤醒？
6. ALTER 为什么不会污染下一次 run？
7. run_replicas 的半宽如何计算？
8. TIME IN SYSTEM 为什么不包含 INTERNAL 实体？
9. 同一时刻的事件为什么需要 CEL？
10. 新节点需要修改哪些层？
```

如果这些问题能回答，说明已经建立了完整的 Helix 运行时模型。

---

## 12. 推荐阅读顺序总结

```text
快速上手
  examples/liquid_level
  examples/serial_workstations
  README.md

语言与编译
  lexer.py
  parser.py
  ast.py
  model.py

运行内核
  events.py
  kernel.py
  runtime/discrete.py 的 _route_node
  runtime/state.py

高级能力
  replicas.py
  continuous/
  debug.py / animate.py
  cli.py

验证
  tests/
  docs/known-differences.md
```

一句话：

```text
先看一个事件如何流动，
再看一个节点如何实现，
最后看统计如何形成报告。
```
