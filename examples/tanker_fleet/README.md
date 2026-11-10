# Tanker Fleet（统计完成）

模型：

- [model.helix](helix/examples/tanker_fleet/model.helix)
- [run.py](helix/examples/tanker_fleet/run.py)

初始条件按书中：

```text
STORAGE=1000（半满）
```

运行：

```text
seed=1,end=365,clear_time=65
```

## Figure 11-7 对比

| 指标 | 书中 | Helix | 差异 |
|---|---:|---:|---:|
| WAITING mean | 1.366 | 1.367 | 0.1% |
| WAITING std | 1.239 | 1.231 | 0.6% |
| WAITING count | 317 | 323 | +1.9% |
| TRIP mean | 14.27 | 13.93 | -2.4% |
| TRIP std | 2.158 | 2.309 | +7% |
| TRIP count | 312 | 320 | +2.6% |
| STORAGE mean | 1766 | 1719 | -2.7% |
| STORAGE std | 176.3 | 230.2 | +30% |
| STORAGE min | 986 | 877 | -11% |
| STORAGE max | 2005 | 1999 | -0.3% |
| STORAGE current | 1925 | 1922 | -0.2% |
| DOCK util | 0.9071 | 0.8972 | -1.1% |
| REFN input avail | 1.0 | 1.0 | 0 |

## 活动计数

| 活动 | 书中 | Helix |
|---|---:|---:|
| 1 | 313 | 320 |
| 2 | 317 | 324 |
| 3 | 316 | 323 |
| 4 | 312 | 320 |

## 期末状态

```text
书中 SS1=121.3  SS2=1986
Helix   SS1=84.9   SS2=1922
```

期末 TANKER_LEVEL 仍有相位差，但统计量已经接近。

## 修复的统计 bug

连续模型先积分再调用 `runtime.advance` 时，`kernel.now` 已经改变，导致：

```text
dt = target - kernel.now = 0
```

队列/活动/资源面积全部为 0。

已修复为显式传入统计起点：

```python
self.runtime.advance(actual, start=start)
```

修复后：

```text
VOY avg active=3.211
TRANSIT avg active=5.101
OFFLOAD avg active=0.897
RET avg active=4.313
DOCK util=0.8972
```

与书中：

```text
3.125, 5.419, 0.907, 4.106
DOCK util=0.907
```

已经接近。
