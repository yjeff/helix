# Inventory System with Lost Sales and Backorders

来源：SLAM II Example 6-5（C. D. Pegden）。

## 模型

```text
HELIX 1

PROJECT "INVENTORY PROBLEM"

VAR invposition GLOBAL
VAR reorderpos GLOBAL
VAR invcontrolpos GLOBAL
VAR orderqty GLOBAL
VAR LAST_LOST GLOBAL
VAR HAS_LOST GLOBAL

RESOURCE radio(capacity=72, mode=RESTOCK)

NETWORK
  CREATE(interval=EXPON(0.2))

  CHECK: IF AVAILABLE(radio) > 0 OR RANDOM() <= 0.2 -> BUY
  ELSE -> LOST

  BUY: ASSIGN(invposition=invposition-1)
       AWAIT(resource=radio, units=1)
       EXIT()

  LOST: IF HAS_LOST = 1 -> RECORD
  ELSE -> MARK
  RECORD: OBSERVE("TIME BETWEEN LOST SALES", TNOW - LAST_LOST) -> MARK
  MARK: ASSIGN(LAST_LOST=TNOW, HAS_LOST=1)
        EXIT()

  CREATE(interval=4)
  REVIEW_CHECK: IF invposition <= reorderpos -> REVIEW
  ELSE -> SKIP
  REVIEW: ASSIGN(orderqty=invcontrolpos-invposition,
                 invposition=invcontrolpos)
          ACTIVITY(duration=3)
          OBSERVE("SAFETY STOCK", AVAILABLE(radio))
          FREE(resource=radio, units=orderqty)
          EXIT()
  SKIP: EXIT()
END
```

## 关键语义

```text
radio 是库存型资源：mode=RESTOCK
AWAIT 减少 available
FREE 增加 available，最多到 capacity
FREE 不需要之前 AWAIT
```

补货的 `FREE(resource=radio, units=orderqty)` 中，`orderqty` 是当前
全局变量，不是初始常量。这个案例依赖 AWAIT/FREE 的动态 units 求值。

库存政策：

```text
每 4 周检查一次
invposition <= 18 时订货
订货量 = 72 - invposition
lead time = 3 周
到货时先统计 SAFETY STOCK，再 FREE 入库
```

顾客：

```text
有现货 -> 购买
无现货 -> 20% 欠单等待，80% 流失（lost sale）
```

## 运行

```bash
cd helix
python examples/inventory_problem/run.py
```

或：

```bash
helix run examples/inventory_problem/model.helix \
  --end 312 --seed 1 \
  --initial invposition=72 --initial reorderpos=18 \
  --initial invcontrolpos=72 \
  --report out/report.md
```

统计窗口：

```text
end=312
clear_time=52
```

`run.py` 使用：

```python
model.initialize(initial={
    "invposition": 72,
    "reorderpos": 18,
    "invcontrolpos": 72,
    "LAST_LOST": 0,
    "HAS_LOST": 0,
}).run(end=312, clear_time=52, seed=1)
```

## 与书中结果对比

书中：

```text
TIME BETWEEN LOST SALES
  n=101, mean=2.652, std=7.52, min=0.006865, max=48.86

SAFETY STOCK
  n=19, mean=10.0, std=2.0, max=70

RESOURCE RADIO
  average utilization(held)=43.0141 / 72
  average on-hand=28.9859
  current held=10
```

Helix `seed=1`：

```text
TIME BETWEEN LOST SALES
  n=117, mean=2.3875, std=6.0179, min=0.0036, max=34.9135

SAFETY STOCK
  n=20, mean=0.5000, std=1.2354, max=4

RESOURCE RADIO
  average held=44.5085 / 72
  average utilization=0.6182
  current held=12
```

对比：

```text
lost sale 次数/均值/库存资源平均持有量：接近书中量级
SAFETY STOCK 仍明显偏低：Helix 的订单到货时现货更接近 0
```

这是因为 `SAFETY STOCK` 是**到货瞬间**的 `AVAILABLE(radio)`，
对订单触发时机和随机到货时间非常敏感；剩余差异仍需要继续校准
`lead time / review timing / order position` 的统计口径。

## 这个案例展示的 Helix 规则

- `mode=RESTOCK` 库存资源
- `AWAIT` 减少库存，`FREE` 补货增加库存
- `FREE` 的 `units` 支持动态全局变量
- `IF` 属性条件与 `RANDOM()` 组合
- `OBSERVE` 统计两次 lost sale 间隔
- `clear_time` 模拟 `MONTR,CLEAR`
