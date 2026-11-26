# Helix 自动统计指标

模型只描述结构；统计由运行时自动收集。
`track` 使用带命名空间的指标名，避免把自动指标误认为模型符号。

## SYSTEM

```text
SYSTEM.TIME         正常 TERMINATE 的实体系统时间均值
SYSTEM.TIME.MEAN    同 SYSTEM.TIME
SYSTEM.TIME.COUNT   观测数量
SYSTEM.TIME.STD     样本标准差
SYSTEM.TIME.MIN     最小值
SYSTEM.TIME.MAX     最大值
```

定义：

```text
SYSTEM.TIME = (正常 TERMINATE 时刻 - entity.created_at)
```

BALK 实体不进入该观测。

### 完整路径时间

`CREATE → QUEUE → ACTIVITY → ... → EXIT/TERMINATE` 的正常实体自动统计为 `TIME IN SYSTEM`。

它包含：

```text
创建后等待
队列等待
所有 ACTIVITY 的服务时间
中间等待
```

不需要额外 `OBSERVE`。

### BALK 间隔

BALK 次数是自动统计的：

```text
QUEUE.<QUEUE>.BALK
```

BALK 间隔不是自动统计，需要在 BALK 目标节点用 `OBSERVE`：

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

默认报告会自动出现：

```text
## OBSERVATIONS

- BALK INTERVAL: n=..., mean=..., std=..., min=..., max=...
```

第一次样本是“从 0 到第一次 BALK”的间隔；如果不想记录，可以用 `IF LAST_BALK > 0` 跳过第一次。

## QUEUE

```text
QUEUE.<QUEUE>.WAIT        平均等待时间
QUEUE.<QUEUE>.MAX_WAIT    最大等待时间
QUEUE.<QUEUE>.LENGTH      时间加权平均队长
QUEUE.<QUEUE>.STD_LENGTH  队长标准差
QUEUE.<QUEUE>.MAX_LENGTH  最大队长
QUEUE.<QUEUE>.CURRENT     期末队长
QUEUE.<QUEUE>.BALK        BALK 次数
```

`WAIT` 只统计真正获得服务的实体。

## ACTIVITY

```text
ACTIVITY.<ACTIVITY>.UTIL             时间加权平均服务台占用数
ACTIVITY.<ACTIVITY>.STD_UTIL         服务台占用数标准差
ACTIVITY.<ACTIVITY>.MAX_UTIL         最大同时占用服务台数
ACTIVITY.<ACTIVITY>.BLOCK            时间加权平均阻塞数
ACTIVITY.<ACTIVITY>.MAX_IDLE         最大空闲时间
ACTIVITY.<ACTIVITY>.MAX_IDLE_SERVER  对应服务台序号
ACTIVITY.<ACTIVITY>.MAX_BUSY         最大忙碌时间
ACTIVITY.<ACTIVITY>.MAX_BUSY_SERVER  对应服务台序号
ACTIVITY.<ACTIVITY>.COMPLETED        完成服务数
```

容量 1 时：

```text
UTIL       = 服务台忙碌时间比例
STD_UTIL   = 占用数标准差
MAX_UTIL   = 最大同时占用数
BLOCK      = 平均阻塞数，也就是阻塞率
```

容量大于 1 时：

```text
UTIL / STD_UTIL / MAX_UTIL 是“服务台数量”
不是除以 capacity 的比例
```

## 自定义分段观测

如果需要统计单个 ACTIVITY 的服务时间，记录进入时刻：

```text
VAR A1_START ENTITY

A1: ACTIVITY(duration=...)
A1_DONE: OBSERVE("A1 TIME", TNOW - A1_START)
```

进入 `A1` 前先：

```text
ASSIGN(A1_START=TNOW)
```

`OBSERVE` 会自动提供：

```text
count
mean
std
min
max
```

默认报告会写入：

```text
## OBSERVATIONS
```

如果使用 `track=`，报告只输出被 track 的指标；自定义 `OBSERVE` 不会自动进入该表，需要直接读取：

```python
for item in result.observations:
    print(item.label, item.count, item.mean, item.std)
```

观测统计使用 Welford 在线累计，`count/mean/std/min/max` 不依赖原始样本。
`Observation.values` 只在 `retain_values=True` 时保存；Python API 默认保留，
CLI 默认不保留，需要原始样本时加 `--keep-samples`。

## 重复运行与置信区间

```bash
helix run model.helix --end 8640 --seed 11 --replicas 20
```

输出每个指标的：

```text
mean ± 95% half-width
```

种子为：

```text
seed, seed+1, ..., seed+N-1
```

默认每个节点使用独立随机子流：

```text
--rng substreams
```

旧版单随机流仅用于历史基线：

```text
--rng global
```

Python API：

```python
replica = scenario.run_replicas(20, seed=11, end=8640)
```

可复现 manifest：

```bash
helix run model.helix --end 8640 --seed 11 --manifest out/run.json
```

manifest 包含 model hash、seed、start/end、clear_time、rng_mode、
initial/constants/entities 和观测数量。

方案对比默认按相同 seed 配对，输出差值的半宽：

```bash
helix compare A.helix B.helix --end 8640 --seed 11 --replicas 20
```

使用 `--independent` 可改为独立区间比较。

## 默认报告

不传 `track` 时，默认报告使用 Markdown 表格式。表头使用短名称，完整含义列在
`## ABBREVIATIONS` 中，避免单行列名过长：

```text
## OBSERVATIONS
LABEL / MEAN / STD. DEV. / COEF. VAR. / MIN / MAX / N

## QUEUE STATISTICS
QUEUE / TYPE / AVG LENGTH / STD. LENGTH / MAX LENGTH /
CURRENT / BALK / AVG WAIT

## SERVICE ACTIVITY STATISTICS
ACTIVITY / SERVERS / AVG SVC UTIL. / STD SVC UTIL. /
MAX SVC UTIL. / CUR SVC UTIL. / AVG BLOCK. /
MAX IDLE TIME / MAX BUSY PERIOD / COMPLETED

## WAIT FILE STATISTICS
WAIT FILE / RESOURCE / AVG LENGTH / STD. LENGTH /
MAX LENGTH / CURRENT / WAIT COUNT / AVG WAIT

## RESOURCE STATISTICS
RESOURCE / CAPACITY / AVAILABLE / AVG OCCUPANCY / STD OCCUPANCY /
MAX OCCUPANCY / CUR OCCUPANCY / AVG HELD / MAX HELD / CURRENT / WAIT COUNT

## GATE STATISTICS
GATE / STATE / WAIT COUNT / AVG WAIT / MAX WAIT

## ABBREVIATIONS
ABBREVIATION / MEANING
```

主要缩写：

```text
SERVERS         = SERVER CAPACITY
AVG SVC UTIL.   = AVERAGE SERVICE UTILIZATION
STD SVC UTIL.   = STD. DEV. OF SERVICE UTILIZATION
MAX SVC UTIL.   = MAXIMUM SERVICE UTILIZATION
CUR SVC UTIL.   = CURRENT SERVICE UTILIZATION
AVG BLOCK.      = AVERAGE BLOCKAGE
MAX IDLE TIME   = MAXIMUM IDLE TIME / SERVER
MAX BUSY PERIOD = MAXIMUM CONTINUOUS BUSY PERIOD / SERVER
COMPLETED       = TRANS. COUNT
AVG OCCUPANCY   = AVERAGE HELD / CAPACITY
STD OCCUPANCY   = STD. DEV. OF HELD / CAPACITY
MAX OCCUPANCY   = MAXIMUM HELD / CAPACITY
CUR OCCUPANCY   = CURRENT HELD / CAPACITY
AVG HELD        = AVERAGE HELD
AVG WAIT        = AVERAGE WAIT
MAX WAIT        = MAXIMUM WAIT
```

这样表头不会撑宽，也不需要依赖 Markdown 查看器是否支持 HTML 换行。

使用 `track=` 时，报告改为：

```text
## TRACKED METRICS
TRACKED METRIC / VALUE
```

`track=` 模式不会输出完整统计表。

## RESOURCE

```text
RESOURCE.<RESOURCE>.UTIL         时间加权平均持有量
RESOURCE.<RESOURCE>.AVG_UTIL     时间加权平均利用率
RESOURCE.<RESOURCE>.UTILIZATION  同 AVG_UTIL
RESOURCE.<RESOURCE>.STD_UTIL     利用率标准差
RESOURCE.<RESOURCE>.MAX_UTIL     最大利用率
RESOURCE.<RESOURCE>.CURRENT_UTIL 期末利用率
RESOURCE.<RESOURCE>.MAX_HELD     最大持有量
RESOURCE.<RESOURCE>.CURRENT      期末持有量
RESOURCE.<RESOURCE>.AVAILABLE    期末剩余容量
RESOURCE.<RESOURCE>.WAIT         等待次数
```

利用率定义：

```text
utilization = held / capacity
```

除 `UTIL` 以外，`AVG_UTIL`、`STD_UTIL`、`MAX_UTIL`、`CURRENT_UTIL`
都是 0～1 的比例；`UTIL` 保留为平均持有量（单位数）。

`AVAILABLE = capacity - CURRENT`。

## GATE

```text
GATE.<GATE>.WAIT         平均 GATE 等待时长
GATE.<GATE>.MAX_WAIT     最大 GATE 等待时长
GATE.<GATE>.WAIT_COUNT   等待次数
GATE.WAIT                单 GATE 模型的兼容简写
```

GATE 的 `WAIT` 与 `WAIT_COUNT` 是两个不同指标，不要混用。
等待时长从实体进入 GATE 的 `AWAIT(gate=...)` 开始，到 GATE 打开后被释放为止。

RESTOCK 模式下：

```text
CURRENT  = 已领用/已消耗（capacity - available）
AVAILABLE = 当前库存
```

资源使用 `mode=RESTOCK` 时不维护持有者账本。

## VAR

```text
VAR.<VAR>        最后一个采样值
VAR.<VAR>.MEAN   采样均值
VAR.<VAR>.MIN    采样最小值
VAR.<VAR>.MAX    采样最大值
```

## 兼容简写

为旧脚本保留：

```text
Q1.WAIT
A1.UTIL
R.UTIL
```

新代码推荐使用完整命名空间。
