# Helix

全新项目：实现 **Helix 语言**。

```text
语言版本：HELIX 1
实现代次：1
旧 SLAM 语法：不兼容
```

## 目标

```text
显式拓扑
命名参数
模型、场景、报告彻底分离
自动统计
可回放的 DEBUG
离散、连续、混合共用事件内核
```

## 目录

```text
docs/grammar.md          Helix 语言规范
docs/language-reference.md 完整语法/案例对比
docs/semantics.md        Helix 语义规范
docs/known-differences.md 已知差异与不再排查项
docs/slam-conversion.md SLAM → Helix 转换
docs/design.md           实现架构
docs/data-structures.md  数据结构
docs/metrics.md          自动统计指标命名
docs/debug.md            DEBUG/动画数据
src/helix/               实现
examples/                新语法案例
tests/                   回归测试
```

## 当前已实现

```text
HELIX 1 / PROJECT
VAR / CONTINUOUS / RESOURCE / GATE / DETECT / SEVNT 声明解析
NETWORK / EQUATION 两个块
分号注释、括号续行
LABEL: 标签
顺序默认 + 箭头覆盖
-> / GOTO 转移别名
CREATE / QUEUE / ACTIVITY / TERMINATE
CREATE 批量属性列表：CREATE(count=5, ID=[...])
ALTER 动态参数：resource/create/activity
ACTIVITY(5) / AWAIT(DOCK) / FREE(DOCK) 单参数简写
QUEUE(4) / CREATE(1.0) / RESOURCE(2) 单参数简写
GATE L(OPEN) / OBSERVE("NAME", value) 简写
EXIT() 作为 TERMINATE() 别名
BALK / BLOCK / on_full=ERROR
IF + RANDOM() 概率分支
IF / ELSE IF / ELSE 紧凑语法
PARALLEL / SPLIT / JOIN / MERGE
SELECT ASM + LIT/POR
RESOURCE / GATE / AWAIT / FREE / ALTER / OPEN / CLOSE
PREEMPT + 剩余时间恢复
DD/SS + RK4/RKF45 + DETECT/SEVNT
VAR GLOBAL/ENTITY/数组 / ASSIGN / DETECT/SEVNT 事件等待
SEVNT action / EVENT 动作 / SCAN 数组扫描 / 动态事件名
run(clear_time=...) 统计清零
track / plot / SVG 报告自动 TIME IN SYSTEM / 队列 / 服务统计
F8/F9 最大空闲/忙碌时间 + 服务台序号
FEL + CEL 内核
DEBUG：run.json / model.json / events.ndjson
DEBUG_PARSE：tokens.ndjson / parse.ndjson / ast.json
```

## 尚未实现

```text
MATCH
更多教材案例
Soaking/Tanker 的期末相位差异
```

## 案例状态

```text
Serial Work Stations   完成
TV Inspection          完成
Truck Hauling          完成
Cedar Bog Lake         完成
Liquid Level Control   完成
Pilot Ejection         完成
Machine Breakdown      完成
Soaking Pit            结构完成，统计接近
Tanker Fleet           统计完成，期末相位有差异
Quarry Operations      完成，量级对齐
Inventory Problem      lost/resource 接近，safety stock 待校准
```

已知差异与不再排查项见：

- [docs/known-differences.md](docs/known-differences.md)

## CLI

安装后：

```bash
pip install -e .
helix check examples/serial_workstations/model.helix
helix run examples/serial_workstations/model.helix --end 300 --seed 1
```

带报告：

```bash
helix run examples/tanker_fleet/model.helix \
  --end 365 --seed 1 --clear-time 65 \
  --report out/report.md
```

不安装也可以：

```bash
python -m helix check examples/serial_workstations/model.helix
```

旧 SLAM 转换：

```bash
helix convert ../slam_v2/examples/discrete/serial_workstations.slam \
  -o examples/converted_serial.helix
```

详见 [docs/slam-conversion.md](docs/slam-conversion.md)。

## 动画播放器

```bash
helix run examples/tv_inspection/model.helix --end 480 --seed 1 \
  --debug --debug-path out/debug

helix animate out/debug -o out/player.html
```

生成单文件 HTML，浏览器直接打开即可播放。

## 运行

```bash
python examples/serial_workstations/run.py
python examples/tv_inspection/run.py
python examples/liquid_level/run.py
python examples/pilot_ejection/run.py
python examples/soaking_pit/run.py
python examples/machine_breakdown/run.py
python examples/tanker_fleet/run.py
python examples/quarry_operations/run.py
python examples/inventory_problem/run.py
```

## 代码结构

```text
src/helix/lexer.py       词法/逻辑语句
src/helix/parser.py      AST parser
src/helix/model.py       Model IR / compiler
src/helix/scenario.py    initialize 场景
src/helix/events.py      Event / Entity
src/helix/kernel.py      FEL/CEL 内核
src/helix/runtime/       离散节点实现
src/helix/cli.py         CLI
src/helix/animate.py     HTML 动画播放器
src/helix/debug.py       DEBUG 记录
```

## 设计原则

```text
模型就是模型
模型不包含初值、终止时间、统计选择、报告元数据
拓扑由顺序默认 + 箭头表达
自动统计不依赖模型声明
DEBUG 不改变仿真结果
```

文档：

- [docs/language-reference.md](docs/language-reference.md)
- [docs/grammar.md](docs/grammar.md)
- [docs/semantics.md](docs/semantics.md)
- [docs/case-comparison.md](docs/case-comparison.md)
- [docs/design.md](docs/design.md)
- [docs/data-structures.md](docs/data-structures.md)
- [docs/metrics.md](docs/metrics.md)
- [docs/debug.md](docs/debug.md)
