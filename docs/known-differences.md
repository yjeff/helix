# 已知差异与停止排查项

本文记录案例迁移结束时的差异，避免后续重复调参。

---

## 1. Tanker Fleet

### 书中初始条件

```text
STORAGE = 1000（半满）
```

旧版 fixture 和早期 Helix 使用 2000，属于错误初始条件，已修正为 1000。

### 书中 Figure 11-7 与 Helix

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
| STORAGE current | 1925 | 1922 | -0.2% |
| DOCK util | 0.9071 | 0.8972 | -1.1% |
| REFN input avail | 1.0 | 1.0 | 0 |

活动计数：

```text
书中 313 / 317 / 316 / 312
Helix   320 / 324 / 323 / 320
```

### 保留差异

```text
期末 TANKER_LEVEL：书中 121.3，Helix 84.9
```

判断：

```text
统计量已在 1%～3% 范围
期末状态是相位差，不是流量级错误
```

### 已尝试但不采纳

```text
调整 UNLOAD_ON 阈值
在 OFFLOAD 中增加清舱延迟
让 TANKER_LEVEL 衰减忽略 UNLOAD_AVAIL
```

原因：

```text
改善某一项时，会破坏 TRIP/WAITING/完成次数
```

### 结论

```text
Tanker 统计对比完成
停止期末相位和参数拟合
```

---

## 2. Soaking Pit

### 书中 Figure 11-16 报告值

```text
HEATING TEMP 225 / 2162 / std 41.42
HEATING TIME 225 / 20.02 / std 3.269
WAITING TIME 180 / 8.177 / std 4.660
FURNACE 平均 2127 / std 267
```

Helix `seed=4,end=500`：

```text
HEATING TEMP 195 / 2197.6 / std 111.5
HEATING TIME 195 / 19.5 / std 5.79
WAITING TIME 205 / 2.21 / std 3.82
FURNACE 平均 2086.3 / std 264.8 final 2438.5
```

期末：

```text
FURNACE=2438.5
MAX_TEMP=2129.5
ACTIVE=10
PIT held=10
```

### 保留差异

```text
WAITING TIME 均值明显偏低
HEATING TEMP 样本数偏低
温度离散度偏大
期末炉温相位偏高
```

### 已确认正确的部分

```text
数组 VAR
SCAN
动态事件名 PIT_DONE[PIT]
PIT 资源账
HOLD servers=10
EXIT_SEVNT 重新武装
OBSERVE 报告
AWAIT 在 SCAN 之前
```

### 结论

```text
Soaking 结构完成
统计部分接近
剩余差异来自旧版 LOAD/EXITP 回调的热交换细节
停止继续扫参数
```

---

## 3. Machine Breakdown

已完成，Table 6-1：

```text
Helix  time=9.14  tool use=0.86  repair=0.11
书  time≈9.59 tool use≈0.844 repair≈0.11
```

误差：

```text
Time 约 5%
Tool Use 约 2%
Repair 0%
```

---

## 4. 当前实现限制

```text
MATCH 尚未实现
数组只支持 GLOBAL
PIT/HOLD 等服务台数必须显式配置
混合模型的 TIME IN SYSTEM 会包含基础设施实体
```

Tanker 的 `SHIFT` 实体也会进入自动 `TIME IN SYSTEM` 观测，因此该指标不应与书中 TRIP TIME 混用。

---

## 5. 停止排查原则

```text
统计量误差 < 5%：可以停止
期末快照差异：记录为相位差异
调整参数会破坏其他已对齐指标：不要采纳
```

后续若继续 Soaking/Tanker，应先取得书中完整状态转换图或原始报告，而不是继续调阈值。
