# Soaking Pit（结构完成）

当前模型验证：

```text
数组 VAR
SCAN 扫描
动态事件名 PIT_DONE[PIT]
SEVNT action
ACTIVITY(until=动态事件名)
OBSERVE 报告
PIT 资源
HOLD servers=10
```

最新 `seed=2,end=500`：

```text
FURNACE=2438.5
MAX_TEMP=2129.5
ACTIVE=10
PIT current_held=10
TEMP≈1815..2130
```

旧版 `seed=0,end=500`：

```text
FURNACE=2514.6
MAX_TEMP≈2133
ACTIVE=9
TEMP≈1980..2133
```

期末炉温和最大温度已经接近。

显式观测：

```text
新版 HEATING TEMP 195 / 2197.6
旧版 HEATING TEMP 237 / 2153.8

新版 HEATING TIME 195 / 19.5
旧版 HEATING TIME 237 / 18.1

新版 WAITING TIME 205 / 2.2
旧版 WAITING TIME 175 / 11.3
```

仍待完善：

```text
WAITING TIME 分布
旧版 LOAD/EXITP 回调的精确热交换
```

`seed=2` 的 EXIT_SEVNT 不重复触发问题已经通过事件后重新武装修复。
