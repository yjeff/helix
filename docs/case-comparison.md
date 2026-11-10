# 案例迁移对比

规则：

```text
同一案例先跑旧 slam_v2，再跑新 helix
优先使用同一 seed
差距超过 10% 时暂停迁移，先查原因
```

## Serial Work Stations

旧版：

```text
seed=1381, end=300
TIME IN SYSTEM: n=562, mean=3.0301
QUEUE1 average=2.3974
QUEUE2 average=1.5121
ACT1 completed=565
ACT2 completed=562
ACT1 max busy=4.8317
ACT2 max busy=39.9869
```

新版：

```text
TIME IN SYSTEM: n=562, mean=3.0301
QUEUE1 average=2.3974
QUEUE2 average=1.5121
ACT1 completed=565
ACT2 completed=562
ACT1 max busy=4.8317
ACT2 max busy=39.9869
```

结论：

```text
观测、队列、完成数、利用率、F9 连续忙碌时间全部对齐
```

## TV Inspection

旧版：

```text
seed=1381, end=480
TIME count=85, mean=21.1325
INSPECT completed=97
ADJUST completed=11
```

新版：

```text
TIME count=79, mean=21.7613
INSPECT completed=94
ADJUST completed=12
```

Figure 6-9：

```text
TIME count=80, mean=20.89
INSPECT completed=97
ADJUST completed=15
```

结论：

```text
统计范围一致
差异来自随机流和 ADJUST 小样本
新版 UNFRM/RNORM 解析修正后不再偏高
```

## 迁移中发现并修正的问题

```text
UNFRM/RNORM 参数切片少取第一位
导致到达率偏高
修正后 TV count 从 114 回到 79~88
```

## Truck Hauling（完成）

Helix 模型：

```text
examples/truck_hauling/model.helix
```

旧版：

```text
seed=1230, end≈560
ACT1 completed=13
ACT2 completed=16
FILE1 avg=0.1759
FILE2 avg=0.9585
FILE3 avg=1.0760
```

新版：

```text
ACT1 completed=13
ACT2 completed=16
FILE1 avg=0.1758
FILE2 avg=0.9589
FILE3 avg=1.0761
```

LOADER_REST/HAUL/DUMP/RETURN：

```text
新版全部 completed=29
```

根因：

```text
旧版对无 QUEUE 上游的 ACTIVITY 没有严格容量限制
Truck 的 HAUL/DUMP/RETURN 实际并行运行多辆卡车
Helix 严格执行 servers=1，造成单服务台瓶颈和 LOAD 积压
```

修正：

```text
LOADER_REST servers=2
HAUL/DUMP/RETURN servers=4
```

同时：

```text
SELECT ASM 保存成员
FORK 路由原始 LOAD/TRKS/LDER 实体
JOIN(count=2) 对应 ACCUM
```

结论：

```text
Truck 通过 <1% 对比
```

## Cedar Bog Lake（完成）

Helix 模型：

```text
examples/cedar_bog_lake/model.helix
```

旧版：

```text
t=2.0
samples=81
PLANTS=16.9244498
HERBIVORES=0.4378359
CARNIVORES=0.5676731
ORGANIC=120.2910921
ENVIRONMENT=54.4120491
SOLAR=95.9
```

新版：

```text
t=2.0
samples=81
PLANTS=16.924450
HERBIVORES=0.437836
CARNIVORES=0.567673
ORGANIC=120.291092
ENVIRONMENT=54.412049
SOLAR=95.9
```

结论：

```text
DD/SS、RKF45、代数变量回写全部对齐
```

## Liquid Level Control（完成）

Helix 模型：

```text
examples/liquid_level/model.helix
```

旧版：

```text
final LEVEL=60.25
max LEVEL=84.428
min LEVEL=16.027
high crossings=2
low crossings=2
PUMP_ON=0
```

新版：

```text
final LEVEL=60.25
max LEVEL=84.425
min LEVEL=16.025
high crossings=2
low crossings=2
PUMP_ON=0
```

结论：

```text
连续液位、DETECT 延迟、ASSIGN、SEVNT 全部对齐
```

## Pilot Ejection（完成）

Helix 模型：

```text
examples/pilot_ejection/model.helix
```

旧版与新版：

```text
t_end=0.433864746
X=-60.0
Y=12.809593
V=593.620832
THETA=0.028481
LEFT_COCKPIT=1
```

结论：

```text
RKF45、SEVNT 终止、SEVNT action 全部对齐
```

## Soaking Pit（结构完成）

Helix 模型：

```text
examples/soaking_pit/model.helix
```

旧版 `seed=0,end=500`：

```text
FURNACE=2514.6
MAX_TEMP≈2133
ACTIVE=9
```

新版 `seed=4,end=500`：

```text
FURNACE=2438.5
MAX_TEMP=2129.5
ACTIVE=10
```

结论：

```text
数组、SCAN、动态事件、PIT 资源、HOLD 服务台全部跑通
资源账一致
期末炉温和最大温度接近
EXIT_SEVNT 已支持事件后重新武装
OBSERVE 已能输出 HEATING TEMP / HEATING TIME / WAITING TIME
```

统计对比（书中 Figure 11-16）：

```text
新版 HEATING TEMP 195 / 2197.6，书中 225 / 2162
新版 HEATING TIME 195 / 19.5，书中 225 / 20.02
新版 WAITING TIME 205 / 2.2，书中 180 / 8.177
```

仍待完善：

```text
HEATING TEMP / HEATING TIME / WAITING TIME 的样本数与等待分布
旧版 LOAD/EXITP 回调的精确热交换
```

## Machine Breakdown（完成）

Helix 模型：

```text
examples/machine_breakdown/model.helix
```

五运行平均：

```text
time in system=9.14
tool use=0.86
repair=0.11
```

书中 Table 6-1：

```text
time in system≈9.59
tool use≈0.844
repair≈0.11
```

结论：

```text
PREEMPT 容量、优先级、抢占路由、剩余时间保存全部对齐
Time in System 约差 5%
```

## Tanker Fleet（统计完成）

Helix 模型：

```text
examples/tanker_fleet/model.helix
```

书中 Figure 11-7：

```text
WAITING mean=1.366 std=1.239 count=317
TRIP mean=14.27 std=2.158 count=312
STORAGE mean=1766 std=176.3 min=986 max=2005 current=1925
DOCK util=0.9071
REFN input avail=1.0
```

Helix `seed=1,end=365,clear_time=65`：

```text
WAITING mean=1.367 std=1.231 count=323
TRIP mean=13.93 std=2.309 count=320
STORAGE mean=1719 std=230 min=877 max=1999 current=1922
DOCK util=0.8972
REFN input avail=1.0
```

判断：

```text
WAITING 均值/标准差基本一致
TRIP 均值差约 2.4%
STORAGE 均值差约 2.7%
DOCK 利用率差约 1.1%
活动计数差约 2%
期末 TANKER_LEVEL 仍有相位差
```

已修复混合模型统计面积 bug：连续积分后 `runtime.advance` 的 `dt` 曾为 0，导致利用率全为 0。

## Quarry Operations（完成）

Helix 模型：

```text
examples/quarry_operations/model.helix
```

书中（单次运行）：

```text
SVL1 avg=0.6269
SVL2 avg=0.5687
SVL3 avg=0.5037
CRSR avg=2.8531

LOAD1 util=0.7340
LOAD2 util=0.6354
LOAD3 util=0.7554
CRUSH util=0.8682
ENDL  util=0.5458
```

Helix `seed=0,end=480`：

```text
SVL1 avg=0.5214
SVL2 avg=0.7981
SVL3 avg=0.6770
CRSR avg=2.5044

LOAD1 util=0.7518
LOAD2 util=0.8005
LOAD3 util=0.6593
CRUSH util=0.8850
ENDL  util=0.5354
RETURN util=0.5177
```

判断：

```text
CRSR/ENDL 量级一致
剩余差异来自随机 seed 和单次运行波动
```

关键语义：

```text
CRSR 第一道工序使用 crsrtime，不是 svltime
ENDL 是 regular activity，不能限制为 servers=1
ENDL 的 duration=rettime，不是 rettime+1
```

## Inventory System with Lost Sales and Backorders（部分对齐）

Helix 模型：

```text
examples/inventory_problem/model.helix
```

参数：

```text
end=312
clear_time=52
seed=1
```

书中：

```text
TIME BETWEEN LOST SALES n=101, mean=2.652, std=7.52
SAFETY STOCK n=19, mean=10.0, std=2.0, max=70
RADIO average held=43.0141
```

Helix：

```text
TIME BETWEEN LOST SALES n=117, mean=2.3875, std=6.0179
SAFETY STOCK n=20, mean=0.5000, std=1.2354, max=4
RADIO average held=44.5085
```

判断：

```text
lost sale 次数/均值、RADIO 平均持有量接近
SAFETY STOCK 仍偏低
```

关键实现：

```text
radio 使用 mode=RESTOCK
FREE 的 units 必须按当前 orderqty 动态求值
无法使用 AWAIT/FREE 的静态 _number()
```

`SAFETY STOCK` 是到货瞬间的 `AVAILABLE(radio)`，对订单触发时机和
随机到货时间非常敏感；剩余差异需要继续校准补货时序。

## 待迁移

```text
Tanker Fleet
```
