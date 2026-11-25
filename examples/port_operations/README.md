# Port Operations

来源：SLAM II Example 6-6（C. D. Pegden，Africa Port）。

## 模型

```text
3 个泊位，1 艘拖轮
现有油轮类型 1/2/3：相对频率 25% / 55% / 20%
新增 5 艘 type 4 油轮，每 48 小时投入一艘
靠泊请求优先于离泊请求
风暴期间关闭拖轮
```

关键语句：

```text
RESOURCE berth(capacity=3)
RESOURCE tug(capacity=1)

BERTH_WAIT:  AWAIT(resource=berth, priority=0)
TUG_BERTH:   AWAIT(resource=tug, priority=2)
TUG_DEBERTH: AWAIT(resource=tug, priority=1)

ACTIVITY(duration=load_time, servers=3)
ACTIVITY(duration=UNFRM(216.0, 264.0), servers=5)

ALTER(resource=tug, capacity=0)
ALTER(resource=tug, capacity=1)
```

`AWAIT` 节点 label 对应 SLAM 的等待文件：

```text
BERTH_WAIT   -> file 1
TUG_BERTH    -> file 2
TUG_DEBERTH  -> file 3
```

## 运行

```bash
cd helix
python examples/port_operations/run.py --seed 11
```

输出：

```text
examples/port_operations/out/report_seed11.md
```

## 与书中结果对比

`seed=11`：

| 指标 | 书中 | Helix |
|---|---:|---:|
| T1 IN PORT TIME | 30.68 | 31.19 |
| T2 IN PORT TIME | 36.89 | 36.09 |
| T3 IN PORT TIME | 49.17 | 47.48 |
| T4 IN PORT TIME | 34.54 | 34.48 |
| berth 平均占用 | 2.8285 | 2.8352 |
| tug 平均占用 | 0.2135 | 0.2153 |

等待文件：

| 文件 | 书中 avg | Helix avg | 书中 std | Helix std | 书中 max | Helix max |
|---|---:|---:|---:|---:|---:|---:|
| file 1 / BERTH_WAIT | 1.1349 | 1.0880 | 1.2916 | 1.1527 | 6 | 6 |
| file 2 / TUG_BERTH | 0.0233 | 0.0187 | 0.1537 | 0.1356 | 2 | 1 |
| file 3 / TUG_DEBERTH | 0.0248 | 0.0215 | 0.1729 | 0.1559 | 3 | 2 |

`seed=11` 的结果与书中随机实现非常接近。

## 20 个 seed 平均

| 指标 | 20-seed 平均 |
|---|---:|
| T1 | 38.04 |
| T2 | 43.46 |
| T3 | 55.33 |
| T4 | 40.37 |
| berth 平均占用 | 2.8834 |
| BERTH_WAIT avg length | 1.8765 |
| TUG_BERTH avg length | 0.0196 |
| TUG_DEBERTH avg length | 0.0203 |

单次运行会因随机 seed 波动；书中结果对应较低负载的一次实现。

## 统计口径

Helix 报告：

```text
berth AVG HELD = 2.8352
berth AVG UTIL. = 0.9451
```

书中 `AVERAGE UTILIZATION = 2.8285` 是平均占用泊位数，不是比例。  
应比较：

```text
2.8285 vs 2.8352
```

而不是：

```text
2.8285 vs 0.9451
```

## 风暴

```text
CREATE(count=1) -> STORM_WAIT
STORM_WAIT: ACTIVITY(duration=EXPON(48)) -> STORM
STORM: ALTER(resource=tug, capacity=0)
       ACTIVITY(duration=UNFRM(2,6))
       ALTER(resource=tug, capacity=1)
       ACTIVITY(duration=EXPON(48)) -> STORM_WAIT
```

`capacity=0` 表示拖轮暂时不可用：

```text
新的 AWAIT 等待
已经持有拖轮的作业继续
风暴期间 FREE 不会超过 capacity
风暴结束后恢复 capacity=1
```
