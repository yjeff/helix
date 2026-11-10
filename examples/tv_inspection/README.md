# TV Inspection（Helix 语法评审案例）

来源：SLAM II TV inspection and adjustment stations。

## 模型

```text
HELIX 1

PROJECT "TV INSPECTION"

NETWORK
  CREATE(interval=UNFRM(3.5, 7.5), first=0)

  Q1: QUEUE()

  ACTIVITY(duration=UNFRM(6.0, 12.0), servers=2)

  CHECK: IF
    WHEN RANDOM() < 0.85 -> DONE
    ELSE -> Q2
  END IF

  Q2: QUEUE()

  ACTIVITY(duration=UNFRM(20.0, 40.0)) -> Q1

  DONE: TERMINATE()
END NETWORK
```

## 这个案例展示的 Helix 规则

- 顺序默认：`Q1 -> A1`、`Q2 -> A2`
- 显式回边：`A2 -> Q1`
- 双服务台：`servers=2`
- 概率分支：`WHEN PROB(0.85)`
- 自动统计：没有 `COLCT`
- 初值和运行参数分离

## Python 侧

```python
model = helix.Model.from_file("model.helix")
scenario = model.initialize()
result = scenario.run(start=0, end=480, seed=1)

result.report(
    "out/report.md",
    track=[
        "SYSTEM.TIME",
        "QUEUE.Q1.WAIT",
        "ACTIVITY.INSPECT.UTIL",
        "ACTIVITY.ADJUST.UTIL",
    ],
    plot=[],
)
```

## 当前实现状态

```text
全回路：
  模型编译
  initialize
  run
  自动统计
  track 报告
  DEBUG 事件
```

`run.py` 为可执行案例。当前结果（seed=1）：

```text
TIME IN SYSTEM: n=79, mean=21.7613
INSPECT completed=94
ADJUST completed=12
Q1.WAIT=2.4636
```
