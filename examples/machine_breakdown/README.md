# Machine Breakdown（完成）

模型：

- [model.helix](helix/examples/machine_breakdown/model.helix)
- [run.py](helix/examples/machine_breakdown/run.py)

五运行结果：

| run | time in system | tool use | repair |
|---:|---:|---:|---:|
| 0 | 9.58 | 0.83 | 0.12 |
| 1 | 5.12 | 0.83 | 0.13 |
| 2 | 13.31 | 0.88 | 0.09 |
| 3 | 7.54 | 0.87 | 0.11 |
| 4 | 10.14 | 0.85 | 0.10 |
| 平均 | 9.14 | 0.86 | 0.11 |

书中 Table 6-1 五运行平均：

```text
time in system≈9.59
tool use≈0.844
repair≈0.11
```

结论：

```text
Time in System 平均差约 5%
Tool Use 差约 2%
Repair 完全一致
```

PREEMPT 已按书中语义实现：

```text
capacity=1
HIGH(LOW) 优先级
preempted_to
remaining_at
其他资源持有者不可抢占
```
