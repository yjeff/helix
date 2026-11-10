# Quarry Operations（SLAM II 对照案例）

来源：SLAM II Quarry Operations（Figure 6-?，C. D. Pegden）。

## 模型

```text
HELIX 1

PROJECT "QUARRY OPERATIONS"

VAR id ENTITY
VAR tons ENTITY
VAR svltime ENTITY
VAR crsrtime ENTITY
VAR rettime ENTITY

NETWORK
  CREATE(count=9,
         id=[1,1,2,2,3,3,1,2,3],
         tons=[20,20,20,20,20,20,50,50,50],
         svltime=[5,5,5,5,5,5,10,10,10],
         crsrtime=[2,2,2,2,2,2,4,4,4],
         rettime=[1.5,1.5,1.5,1.5,1.5,1.5,2.0,2.0,2.0])

  Loop: IF id = 1 -> SVL1
  ELSE IF id = 2 -> SVL2
  ELSE -> SVL3

  SVL1: QUEUE()
        LOAD1: ACTIVITY(duration=EXPON(svltime)) -> ENDL

  SVL2: QUEUE()
        LOAD2: ACTIVITY(duration=EXPON(svltime)) -> ENDL

  SVL3: QUEUE()
        LOAD3: ACTIVITY(duration=EXPON(svltime)) -> ENDL

  ENDL: ACTIVITY(duration=rettime, servers=9)

  CRSR: QUEUE(order=HIGH(tons))
        CRUSH: ACTIVITY(duration=EXPON(crsrtime))
        RETURN: ACTIVITY(duration=rettime) -> Loop
END
```

## 这个案例展示的 Helix 规则

- `CREATE(count=9, ...)`：在 t=0 批量创建 9 个实体。
- `CREATE` 属性列表：`id`、`tons`、`svltime`、`crsrtime`、`rettime`
  都必须是已声明的 `ENTITY` 变量。
- `IF id = ...`：按实体属性分支，`=` 表示相等。
- `ACTIVITY(duration=EXPON(svltime))`：分布参数取自当前实体的属性。
- `QUEUE(order=HIGH(tons))`：CRSR 按吨位高值优先。
- `ACTIVITY(duration=rettime, servers=9)`：ENDL 是 regular activity，
  不是单服务台；`servers` 至少等于实体数。
- `RETURN: ACTIVITY(duration=rettime) -> Loop`：显式回边。

## 关键语义

```text
LOAD1/LOAD2/LOAD3 的 service time = svltime
CRUSH 的 service time = crsrtime
RETURN 的 service time = rettime
ENDL 的 service time = rettime
```

最常见的两个错误：

```text
CRSR 误用 svltime，而不是 crsrtime
ENDL 误写 duration=rettime+1 且默认 servers=1
```

后者会把 ENDL 变成瓶颈，压低 CRSR 队列长度。

## 运行

```bash
cd helix
python examples/quarry_operations/run.py
```

或：

```bash
helix run examples/quarry_operations/model.helix --end 480 --seed 0 \
  --report out/report.md
```

模型没有 `EXIT()` / `TERMINATE()`，9 个实体在 `Loop` 中持续循环，
所以默认报告只有 `QUEUE STATISTICS` 和 `SERVICE ACTIVITY STATISTICS`，
不会出现 `TIME IN SYSTEM`。

## 与书中结果对比

书中（单次运行）：

```text
SVL1 avg length = 0.6269
SVL2 avg length = 0.5687
SVL3 avg length = 0.5037
CRSR avg length = 2.8531

LOAD1 avg util = 0.7340
LOAD2 avg util = 0.6354
LOAD3 avg util = 0.7554
CRUSH avg util = 0.8682
ENDL  avg util = 0.5458
```

Helix（`end=480, seed=0`）：

```text
SVL1 avg length = 0.5214
SVL2 avg length = 0.7981
SVL3 avg length = 0.6770
CRSR avg length = 2.5044

LOAD1 avg util = 0.7518
LOAD2 avg util = 0.8005
LOAD3 avg util = 0.6593
CRUSH avg util = 0.8850
ENDL  avg util = 0.5354
RETURN avg util = 0.5177
```

量级一致；剩余差异来自随机 seed 和单次运行波动。
`ENDL` 的 `servers=9` 是当前 Helix 对“regular activity 不限并发”的建模方式；
如果实体数改变，应同步调整 `servers`。
