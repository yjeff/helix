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
Compiler
  ↓
Model IR
  ↓
Scenario
  ↓
Kernel
  ├── DiscreteRuntime
  ├── ContinuousRuntime
  ├── Statistics
  └── DebugRecorder
  ↓
RunResult
  ↓
Report / Animation
```

职责：

| 层 | 职责 |
|---|---|
| Lexer | 字符 → Token |
| Parser | Token → AST |
| Compiler | AST → Model IR、名字解析、静态校验 |
| Scenario | 初值、常量、初始实体 |
| Kernel | FEL/CEL、时间推进、事件调度 |
| DiscreteRuntime | CREATE/QUEUE/ACTIVITY/资源等处理器 |
| ContinuousRuntime | DD/SS、RK4、DETECT |
| Statistics | 自动统计 |
| DebugRecorder | 结构化 DEBUG |
| Report | track/plot/输出 |

Kernel 不知道：

```text
QUEUE 是什么
RK4 是什么
实体属性是什么
```

Kernel 只知道：

```text
时间
事件
TimeSource
事件处理器
```

---

## 3. 模块建议

```text
src/helix/
  __init__.py
  errors.py
  tokens.py
  lexer.py
  ast.py
  parser.py
  compiler.py
  model.py
  scenario.py
  kernel.py
  events.py
  time_source.py
  runtime/
    __init__.py
    discrete.py
    queues.py
    activities.py
    resources.py
    gates.py
    select.py
    branching.py
  continuous/
    __init__.py
    integrator.py
    equations.py
    detect.py
  stats.py
  debug.py
  report.py
```

`kernel.py` 不导入 `runtime/discrete.py` 的内部类，只依赖处理器注册表。

---

## 4. 编译流程

```text
Model.from_file(path)
  → read_text
  → lex
  → parse
  → compile
  → validate
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
深拷贝 Model
解析 initial 标签
校验 constants
生成初始实体
保存运行前状态
```

不修改 `model`。

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
