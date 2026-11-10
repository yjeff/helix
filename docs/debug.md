# DEBUG 与动画数据规范 v0.1

状态：设计草案，尚未实现。

## 目标

DEBUG 不只是文本日志，而是：

```text
可回放
可检查
可驱动动画
可跨语言读取
```

## API

```python
result = scenario.run(
    start=0,
    end=480,
    seed=1,
    debug=True,
    debug_path="out/debug",
)
```

或：

```python
scenario.debug = True
scenario.debug_path = "out/debug"
```

默认：

```text
debug=False
debug_path=None
```

## 输出目录

```text
out/debug/
  run.json
  model.json
  tokens.ndjson       可选
  parse.ndjson        可选
  ast.json            可选
  events.ndjson
  states.ndjson
```

`states.ndjson` 是动画播放器的数据源。

## 动画播放器

生成单文件 HTML：

```bash
helix animate out/debug -o out/player.html
```

浏览器打开即可：

```text
播放 / 暂停 / 单步
时间滑条
实体在节点间的移动
队列、活动、资源状态
```

`states.ndjson` 每行包含：

```text
t
batch
event
entities
queues
activities
resources
```

## 编译期 DEBUG

Token 和 parser 发生在 `Model.from_file`，所以编译期 DEBUG 放在模型加载阶段：

```python
model = helix.Model.from_file(
    "model.helix",
    debug_parse=True,
    debug_path="out/debug",
)
```

或者：

```python
model = helix.parse(
    source,
    debug_parse=True,
    debug_path="out/debug",
)
```

### tokens.ndjson

```json
{"i": 0, "type": "KEYWORD", "value": "HELIX", "line": 1, "col": 1}
{"i": 1, "type": "NUMBER", "value": "1", "line": 1, "col": 7}
{"i": 2, "type": "IDENT", "value": "Q1", "line": 5, "col": 3}
{"i": 3, "type": "COLON", "value": ":", "line": 5, "col": 5}
```

### parse.ndjson

```json
{"seq": 1, "action": "program", "value": "HELIX 1"}
{"seq": 2, "action": "node", "label": "Q1", "kind": "QUEUE", "line": 5}
{"seq": 3, "action": "edge", "source": "A1", "target": "Q1", "line": 12}
```

### ast.json

```json
{
  "project": "TV INSPECTION",
  "nodes": [...],
  "edges": [...]
}
```

## 仿真期 DEBUG

```python
result = scenario.run(
    start=0,
    end=480,
    seed=1,
    debug=True,
    debug_path="out/debug",
)
```

`events.ndjson` 只记录仿真事件，不混入 token/parser 记录。

## DEBUG 级别

```text
debug_parse=False       不记录 tokens/parser
debug_parse=True        记录 tokens/parser/ast
debug=True              记录仿真事件
debug=True,
debug_parse=True        全部记录
```

这样可以：

```text
普通用户：只看仿真事件
语言开发：打开 token/parser trace
动画：只读 model/events
```


### run.json

```json
{
  "format": "helix-debug",
  "version": 1,
  "project": "TV INSPECTION",
  "seed": 1,
  "start": 0.0,
  "end": 480.0,
  "model_hash": "...",
  "initial": {},
  "constants": {},
  "entities": {}
}
```

### model.json

```json
{
  "nodes": [
    {"label": "Q1", "kind": "QUEUE", "params": {"capacity": 4}},
    {"label": "A1", "kind": "ACTIVITY", "params": {"servers": 2}}
  ],
  "edges": [
    {"source": "START", "target": "Q1"}
  ]
}
```

### events.ndjson

每行一个事件：

```json
{"t": 3.2, "seq": 17, "batch": 4, "type": "ENTER_QUEUE", "entity": 5, "node": "Q1", "queue_length": 3}
{"t": 3.2, "seq": 18, "batch": 4, "type": "START_ACTIVITY", "entity": 5, "node": "A1", "server": 2, "active": 2}
{"t": 4.1, "seq": 19, "batch": 5, "type": "END_ACTIVITY", "entity": 5, "node": "A1", "server": 2, "active": 1}
```

`batch` 表示同一仿真时刻的 CEL 批次：

```text
同一个 batch 内 t 相同
动画可整批推进
不会在同一时刻产生时间跳跃
```

## 事件类型

```text
CREATE
ENTER_QUEUE
LEAVE_QUEUE
BALK
BLOCK
UNBLOCK
START_ACTIVITY
END_ACTIVITY
SEIZE_RESOURCE
RELEASE_RESOURCE
OPEN_GATE
CLOSE_GATE
ASSIGN
SPLIT
JOIN
DETECT
STATE_EVENT
TERMINATE
```

## 事件公共字段

| 字段 | 含义 |
|---|---|
| `t` | 仿真时间 |
| `seq` | 事件序号，保证排序 |
| `batch` | 同一仿真时刻的 CEL 批次 |
| `type` | 事件类型 |
| `entity` | 实体 id |
| `node` | 当前节点标签 |
| `server` | 服务台序号，可选 |
| `queue_length` | 队列长度，可选 |
| `active` | 活动当前实体数，可选 |
| `blocked` | 阻塞数，可选 |
| `attrs` | 属性快照，可选 |
| `priority` | 实体优先级，可选 |

## 回放与动画

动画播放器读取：

```text
model.json    画节点和边
events.ndjson 事件列表
states.ndjson 每个事件后的运行快照
run.json      项目、种子、时间范围
```

生成播放器：

```bash
helix animate out/debug -o out/player.html
```

`states.ndjson` 每行包含：

```text
t
batch
event
entities
queues
activities
resources
```

播放器支持：

```text
播放 / 暂停
上一状态 / 下一状态
时间滑条
速度选择
实体节点位置
队列、活动、资源状态表
```

播放器是单文件 HTML，不依赖额外 JavaScript 库。

## 确定性

DEBUG 数据必须可复现：

```text
记录 seed
记录 initial/constants/entities
记录 model_hash
记录事件序号
不依赖系统时间或随机哈希
```

## 与旧版关系

保留旧版 DEBUG 能力：

```text
debug=True
debug_path=...
```

格式升级为结构化数据，不再只有文本日志。
