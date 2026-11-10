# SLAM → Helix 转换

工具：

```text
src/helix/convert.py
```

CLI：

```bash
helix convert old.slam -o model.helix
```

默认查找同级目录下的：

```text
../slam_v2
```

也可以指定：

```bash
helix convert old.slam \
  --slam-root path/to/slam_v2 \
  -o model.helix
```

不写 `-o` 时输出到标准输出。

---

## 支持的旧语句

```text
NETWORK / ENDNETWORK
CONTINUOUS
VAR
EQUATION
RESOURCE
GATE
CREATE
QUEUE
ACTIVITY
AWAIT
FREE
ASSIGN
DETECT
TERMINATE
COLCT          跳过并生成注释
GOON           跳过
EVENT          跳过并生成注释
```

## 名称映射

旧写法：

```text
SS(1)
XX(1)
ATRIB(1)
C(1)
T
```

转换为：

```text
SS(1) -> VAR 中声明的短名，例如 P
XX(1) -> VAR 中声明的短名，例如 LA
ATRIB(1) -> ATTR_1（ENTITY）
C(1) -> C_1（ENTITY）
T -> TNOW
```

旧 `VAR`：

```text
VAR,SS(1),P,PLANTS;
```

转换为：

```text
VAR P GLOBAL AS "PLANTS"
```

旧方程：

```text
SS(6) = ...
DD(1) = ...
```

转换为：

```text
SS(S) = ...
DD(P) = ...
```

---

## 已知限制

```text
COLCT 统计不会自动生成 OBSERVE
GOON 被折叠
EVENT 被折叠
ACCUM / SELECT 不支持
PREEMPT 只保留资源名，不保证旧优先级语义
ACTIVITY 的旧条件 cond 不支持
CREATE 无 interval 时按单实体处理
```

转换后必须用：

```bash
helix check model.helix
```

验证。

---

## 示例

```bash
helix convert \
  ../slam_v2/examples/discrete/serial_workstations.slam \
  -o examples/converted_serial.helix

helix check examples/converted_serial.helix
```

转换结果会保留 warning 注释：

```text
; conversion warnings:
;   ACT15: 无 duration 的 ACTIVITY 转为 duration=0
```

warning 不会阻止生成，但需要人工确认语义。
