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
ACTIVITY / SERVERS / AVG UTIL. / STD. UTIL. / MAX UTIL. /
CUR. UTIL. / AVG BLOCK. / MAX IDLE / MAX BUSY / COMPLETED

## RESOURCE STATISTICS
RESOURCE / CAPACITY / AVAILABLE / AVG UTIL. / STD. UTIL. /
MAX UTIL. / CUR. UTIL. / AVG HELD / MAX HELD / CURRENT / WAIT COUNT

## GATE STATISTICS
GATE / STATE / WAIT COUNT

## ABBREVIATIONS
ABBREVIATION / MEANING
```

主要缩写：

```text
SERVERS     = SERVER CAPACITY
AVG UTIL.   = AVERAGE UTILIZATION
STD. UTIL.  = STANDARD DEVIATION OF UTILIZATION
MAX UTIL.   = MAXIMUM UTILIZATION
CUR. UTIL.  = CURRENT UTILIZATION
AVG BLOCK.  = AVERAGE BLOCKAGE
MAX IDLE    = MAXIMUM IDLE TIME / SERVER
MAX BUSY    = MAXIMUM BUSY TIME / SERVER
COMPLETED   = TRANS. COUNT
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
