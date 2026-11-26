"""离散运行时的状态对象。

这些对象只保存“当前状态 + 自动统计累计值”，不负责调度。
所有时间推进由 Kernel/DiscreteRuntime 调用 advance()。
"""
from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..events import Entity


def _svg_escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _align_markdown_tables(lines: list[str]) -> list[str]:
    """把连续的 Markdown 表格按列宽补空格，便于直接阅读源文件。"""
    output: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("|"):
            output.append(lines[index])
            index += 1
            continue

        end = index
        while end < len(lines) and lines[end].lstrip().startswith("|"):
            end += 1
        block = lines[index:end]
        rows: list[list[str]] = []
        for line in block:
            text = line.strip()
            if text.startswith("|"):
                text = text[1:]
            if text.endswith("|"):
                text = text[:-1]
            rows.append([cell.strip() for cell in text.split("|")])

        if (len(rows) < 2 or
                any(len(row) != len(rows[0]) for row in rows) or
                not all("-" in cell for cell in rows[1])):
            output.extend(block)
            index = end
            continue

        aligns: list[str] = []
        for cell in rows[1]:
            if cell.startswith(":") and cell.endswith(":"):
                aligns.append("c")
            elif cell.endswith(":"):
                aligns.append("r")
            else:
                aligns.append("l")

        widths = [
            max(len(row[column]) for row in rows)
            for column in range(len(rows[0]))
        ]

        def render(row: list[str]) -> str:
            cells = [
                cell.rjust(width) if align == "r" else cell.ljust(width)
                for cell, width, align in zip(row, widths, aligns)
            ]
            return "| " + " | ".join(cells) + " |"

        separator = []
        for width, align in zip(widths, aligns):
            if align == "c":
                token = ":" + "-" * max(2, width - 2) + ":"
            elif align == "r":
                token = "-" * max(3, width - 1) + ":"
            else:
                token = ":" + "-" * max(3, width - 1)
            separator.append(token.ljust(width))
        output.append(render(rows[0]))
        output.append("| " + " | ".join(separator) + " |")
        for row in rows[2:]:
            output.append(render(row))
        index = end
    return output


def _write_continuous_svg(path: Path, samples: list[dict],
                          series: list[str],
                          labels: dict[str, str]) -> Path | None:
    """写出简单的连续变量时间曲线 SVG。

    不依赖 matplotlib；只画时间—数值折线，足够报告预览。
    """
    if not samples or not series:
        return None

    width, height = 900, 420
    left, right, top, bottom = 70, 20, 30, 55
    plot_w = width - left - right
    plot_h = height - top - bottom
    times = [float(sample["t"]) for sample in samples]
    t_min, t_max = min(times), max(times)
    if t_max <= t_min:
        t_max = t_min + 1.0

    values = [
        float(sample["values"].get(name, 0.0))
        for sample in samples for name in series
    ]
    y_min, y_max = min(values), max(values)
    if y_max <= y_min:
        y_max = y_min + 1.0

    def x(t: float) -> float:
        return left + (t - t_min) / (t_max - t_min) * plot_w

    def y(v: float) -> float:
        return top + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd",
              "#ff7f0e", "#17becf"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="20" font-family="sans-serif" '
        f'font-size="14">CONTINUOUS VARIABLES</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" '
        f'y2="{top + plot_h}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top + plot_h}" '
        f'x2="{left + plot_w}" y2="{top + plot_h}" stroke="#333"/>',
        f'<text x="{left}" y="{height - 15}" font-family="sans-serif" '
        f'font-size="11">t = {t_min:.3f} .. {t_max:.3f}</text>',
        f'<text x="8" y="{top + 10}" font-family="sans-serif" '
        f'font-size="11">{y_max:.3f}</text>',
        f'<text x="8" y="{top + plot_h}" font-family="sans-serif" '
        f'font-size="11">{y_min:.3f}</text>',
    ]
    for index, name in enumerate(series):
        color = colors[index % len(colors)]
        points = " ".join(
            f"{x(float(sample['t'])):.2f},"
            f"{y(float(sample['values'].get(name, 0.0))):.2f}"
            for sample in samples)
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" '
            f'points="{points}"/>')
        legend_y = top + 14 * index
        parts.append(
            f'<text x="{left + 8}" y="{legend_y}" '
            f'font-family="sans-serif" font-size="11" fill="{color}">'
            f'{_svg_escape(labels.get(name, name))}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


@dataclass(slots=True)
class Observation:
    """普通观测样本。

    始终维护在线 count/mean/variance/min/max；``values`` 只在
    ``retain_values=True`` 时保存，避免大样本模型占用过多内存。
    """

    label: str
    retain_values: bool = True
    values: list[float] = field(default_factory=list)
    _count: int = 0
    _mean: float = 0.0
    _m2: float = 0.0
    _minimum: float = 0.0
    _maximum: float = 0.0

    def add(self, value: float) -> None:
        value = float(value)
        self._count += 1
        delta = value - self._mean
        self._mean += delta / self._count
        self._m2 += delta * (value - self._mean)
        if self._count == 1:
            self._minimum = value
            self._maximum = value
        else:
            self._minimum = min(self._minimum, value)
            self._maximum = max(self._maximum, value)
        if self.retain_values:
            self.values.append(value)

    @property
    def count(self) -> int:
        return self._count

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def std(self) -> float:
        if self._count < 2:
            return 0.0
        return math.sqrt(max(0.0, self._m2) / (self._count - 1))

    @property
    def minimum(self) -> float:
        return self._minimum

    @property
    def maximum(self) -> float:
        return self._maximum


@dataclass(slots=True)
class QueueState:
    """QUEUE 的队内状态与时间加权统计。"""

    label: str
    capacity: int
    order: str
    on_full: str
    items: deque[Entity] = field(default_factory=deque)
    area: float = 0.0
    area2: float = 0.0
    max_length: int = 0
    wait_sum: float = 0.0
    wait_count: int = 0
    wait_max: float = 0.0
    balk_count: int = 0

    @property
    def length(self) -> int:
        return len(self.items)


@dataclass(slots=True)
class ServerState:
    """单个服务台。

    F8/F9 需要“最长时间 + 服务台序号”，因此每个服务台独立记录。
    """

    index: int
    status: str = "IDLE"          # IDLE / BUSY / BLOCKED
    entity_id: int | None = None
    start_time: float = 0.0
    idle_since: float = 0.0
    busy_since: float | None = None
    max_idle: float = 0.0
    max_idle_server: int = 0
    max_busy: float = 0.0
    max_busy_server: int = 0
    busy_total: float = 0.0


@dataclass(slots=True)
class ActivityState:
    """服务活动。"""

    label: str
    servers: list[ServerState]
    waiting: deque[int] = field(default_factory=deque)
    area: float = 0.0
    area2: float = 0.0
    blocked_area: float = 0.0
    max_active: int = 0
    completed: int = 0
    blocked_count: int = 0

    @property
    def capacity(self) -> int:
        return len(self.servers)

    @property
    def active(self) -> int:
        return sum(1 for server in self.servers
                   if server.status == "BUSY")

    @property
    def blocked(self) -> int:
        return sum(1 for server in self.servers
                   if server.status == "BLOCKED")

    def idle_server(self) -> ServerState | None:
        for server in self.servers:
            if server.status == "IDLE":
                return server
        return None


@dataclass(slots=True)
class AwaitState:
    """AWAIT 节点的等待文件统计。"""

    label: str
    resource: str
    current_length: int = 0
    max_length: int = 0
    area: float = 0.0
    area2: float = 0.0
    waiting: set[int] = field(default_factory=set)
    wait_count: int = 0
    wait_sum: float = 0.0
    wait_max: float = 0.0
    wait_enter: dict[int, float] = field(default_factory=dict)


@dataclass(slots=True)
class SelectState:
    """SELECT 节点运行态。

    ASM 模式下，只有所有 queues 都有实体时才允许组装；没有空闲
    服务台时不从队列取实体，避免“取出来又放不回去”。
    """

    label: str
    queues: list[str]
    servers: list[str]
    queue_rule: str
    server_rule: str
    save_rule: str = "FIRST"
    cursor: int = 0


@dataclass(slots=True)
class ResourceState:
    """RESOURCE 运行态。

    POOL 模式使用 held_by 记录持有者；RESTOCK 模式只维护 available。
    """

    name: str
    capacity: int
    available: int
    mode: str = "POOL"
    held_by: dict[int, int] = field(default_factory=dict)
    waiters: list[int] = field(default_factory=list)
    area: float = 0.0
    area2: float = 0.0
    max_held: int = 0
    wait_count: int = 0
    wait_sum: float = 0.0
    wait_max: float = 0.0
    wait_enter: dict[int, float] = field(default_factory=dict)


@dataclass(slots=True)
class GateState:
    """GATE 运行态；GATE 没有容量，只有 OPEN/CLOSED。"""

    name: str
    state: str = "CLOSED"
    waiters: list[int] = field(default_factory=list)
    wait_count: int = 0
    wait_sum: float = 0.0
    wait_max: float = 0.0
    wait_enter: dict[int, float] = field(default_factory=dict)


@dataclass(slots=True)
class ResourceStat:
    name: str
    capacity: int
    available: int
    average_held: float
    maximum_held: int
    current_held: int
    average_utilization: float
    std_utilization: float
    maximum_utilization: float
    current_utilization: float
    wait_count: int
    average_wait: float = 0.0
    max_wait: float = 0.0


@dataclass(slots=True)
class AwaitStat:
    label: str
    resource: str
    average_length: float
    std_length: float
    max_length: int
    current_length: int
    wait_count: int
    average_wait: float
    max_wait: float


@dataclass(slots=True)
class GateStat:
    name: str
    state: str
    wait_count: int
    average_wait: float = 0.0
    max_wait: float = 0.0


@dataclass(slots=True)
class QueueStat:
    label: str
    average_length: float
    std_length: float
    max_length: int
    current_length: int
    balk_count: int
    average_wait: float = 0.0
    maximum_wait: float = 0.0


@dataclass(slots=True)
class ServiceStat:
    activity: str
    capacity: int
    average_utilization: float
    std_utilization: float
    maximum_utilization: int
    current_utilization: int
    average_blockage: float
    maximum_idle: float
    maximum_idle_server: int
    maximum_busy: float
    maximum_busy_server: int
    completed: int


@dataclass(slots=True)
class RunResult:
    """一次运行的最终结果。

    字段保持简单，report() 只在报告层格式化。
    """

    project: str
    now: float
    observations: list[Observation]
    queues: list[QueueStat]
    services: list[ServiceStat]
    resources: list[ResourceStat] = field(default_factory=list)
    awaits: list[AwaitStat] = field(default_factory=list)
    gates: list[GateStat] = field(default_factory=list)
    continuous: list[dict] = field(default_factory=list)
    continuous_final: dict[str, float] = field(default_factory=dict)
    global_values: dict[str, float] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    debug_path: str | None = None
    seed: int | None = None
    start: float = 0.0
    end: float | None = None
    clear_time: float | None = None
    rng_mode: str = "substreams"
    retain_samples: bool = True
    engine_version: str = "0.1.0"
    model_hash: str = ""
    initial: dict[str, float] = field(default_factory=dict)
    constants: dict[str, float] = field(default_factory=dict)
    entities: dict[str, int] = field(default_factory=dict)
    entity_data: dict[str, list[dict[str, float]]] = field(
        default_factory=dict)
    continuous_options: dict = field(default_factory=dict)
    max_events: int | None = None
    max_same_time_events: int | None = None

    def manifest(self) -> dict:
        """返回足以复现这次运行的配置摘要。"""
        return {
            "project": self.project,
            "engine_version": self.engine_version,
            "model_hash": self.model_hash,
            "seed": self.seed,
            "start": self.start,
            "end": self.end,
            "clear_time": self.clear_time,
            "rng_mode": self.rng_mode,
            "retain_samples": self.retain_samples,
            "finished_at": self.now,
            "initial": dict(sorted(self.initial.items())),
            "constants": dict(sorted(self.constants.items())),
            "entities": dict(sorted(self.entities.items())),
            "entity_data": {
                key: value for key, value in sorted(self.entity_data.items())
            },
            "continuous": dict(sorted(self.continuous_options.items())),
            "max_events": self.max_events,
            "max_same_time_events": self.max_same_time_events,
            "observations": {
                item.label: item.count for item in self.observations
            },
        }

    def write_manifest(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    def summary(self) -> str:
        lines = [f"Helix: {self.project}", f"t = {self.now:.4f}"]
        for observation in self.observations:
            lines.append(
                f"{observation.label}: n={observation.count} "
                f"mean={observation.mean:.4f}")
        return "\n".join(lines)

    def _metric(self, name: str) -> float:
        """读取命名空间形式的自动统计指标。

        推荐使用带命名空间的完整名称，避免把自动指标误认为模型符号：

        - ``SYSTEM.TIME`` / ``SYSTEM.TIME.MEAN``
        - ``QUEUE.Q1.WAIT`` / ``QUEUE.Q1.LENGTH``
        - ``ACTIVITY.INSPECT.UTIL`` / ``ACTIVITY.INSPECT.BLOCK``
        - ``RESOURCE.R.UTIL`` / ``RESOURCE.R.WAIT``
        - ``GATE.LIGHT1.WAIT`` / ``GATE.LIGHT1.MAX_WAIT``
        - ``VAR.TEMP`` / ``VAR.TEMP.MEAN``

        为兼容旧脚本，也接受 ``Q1.WAIT``、``A1.UTIL`` 这类简写。
        """
        text = name.strip()
        upper = text.upper()

        observation = next(
            (item for item in self.observations
             if item.label == "TIME IN SYSTEM"), None)
        if upper.startswith("SYSTEM.TIME"):
            if observation is None:
                raise ValueError("模型没有产生 SYSTEM.TIME 观测")
            suffix = upper[len("SYSTEM.TIME"):].strip(".")
            if suffix in ("", "MEAN"):
                return observation.mean
            if suffix == "COUNT":
                return float(observation.count)
            if suffix == "STD":
                return observation.std
            if suffix == "MIN":
                return observation.minimum
            if suffix == "MAX":
                return observation.maximum
            raise ValueError(f"未知 SYSTEM.TIME 指标: {name}")

        # 单 GATE 的旧式简写；多 GATE 时必须写 GATE.<name>.WAIT。
        if upper in ("GATE.WAIT", "GATE.MAX_WAIT"):
            if len(self.gates) != 1:
                raise ValueError(
                    "GATE.WAIT 只适用于单个 GATE；"
                    "请使用 GATE.<name>.WAIT")
            metric = upper.split(".", 1)[1]
            return self._gate_metric(self.gates[0].name, metric)

        parts = text.split(".")
        if len(parts) == 2 and parts[0].upper() == "VAR":
            return self._var_metric(parts[1], "", text)
        if len(parts) >= 3:
            namespace = parts[0].upper()
            owner = parts[1]
            metric = parts[2].upper()
            if namespace == "QUEUE":
                return self._queue_metric(owner, metric)
            if namespace == "ACTIVITY":
                return self._activity_metric(owner, metric)
            if namespace == "RESOURCE":
                return self._resource_metric(owner, metric)
            if namespace == "GATE":
                return self._gate_metric(owner, metric)
            if namespace == "VAR" and len(parts) >= 3:
                return self._var_metric(parts[1], parts[2], name)

        # 兼容旧的两段式简写，例如 Q1.WAIT / A1.UTIL。
        if len(parts) == 2:
            owner, metric = parts
            metric = metric.upper()
            for getter in (self._queue_metric, self._activity_metric,
                           self._resource_metric):
                value = getter(owner, metric)
                if value != math.nan:
                    return value

        # 连续变量直接名：TEMP / TEMP.MEAN。
        if text in self.variables or any(
                label == text for label in self.variables.values()):
            variable = text
            if variable not in self.variables:
                variable = next(
                    symbol for symbol, label in self.variables.items()
                    if label == text)
            return self._var_metric(variable, "", text)

        raise ValueError(f"未知 track 指标: {name}")

    def _queue_metric(self, owner: str, metric: str) -> float:
        for queue in self.queues:
            if queue.label == owner:
                return {
                    "WAIT": queue.average_wait,
                    "MAX_WAIT": queue.maximum_wait,
                    "LENGTH": queue.average_length,
                    "STD_LENGTH": queue.std_length,
                    "MAX_LENGTH": float(queue.max_length),
                    "CURRENT": float(queue.current_length),
                    "BALK": float(queue.balk_count),
                }.get(metric, math.nan)
        return math.nan

    def _activity_metric(self, owner: str, metric: str) -> float:
        for service in self.services:
            if service.activity == owner:
                return {
                    "UTIL": service.average_utilization,
                    "STD_UTIL": service.std_utilization,
                    "MAX_UTIL": float(service.maximum_utilization),
                    "BLOCK": service.average_blockage,
                    "MAX_IDLE": service.maximum_idle,
                    "MAX_IDLE_SERVER": float(service.maximum_idle_server),
                    "MAX_BUSY": service.maximum_busy,
                    "MAX_BUSY_SERVER": float(service.maximum_busy_server),
                    "COMPLETED": float(service.completed),
                }.get(metric, math.nan)
        return math.nan

    def _resource_metric(self, owner: str, metric: str) -> float:
        for resource in self.resources:
            if resource.name == owner:
                return {
                    "UTIL": resource.average_held,
                    "AVG_UTIL": resource.average_utilization,
                    "UTILIZATION": resource.average_utilization,
                    "STD_UTIL": resource.std_utilization,
                    "MAX_UTIL": resource.maximum_utilization,
                    "CURRENT_UTIL": resource.current_utilization,
                    "MAX_HELD": float(resource.maximum_held),
                    "CURRENT": float(resource.current_held),
                    "AVAILABLE": float(resource.available),
                    "WAIT": float(resource.wait_count),
                }.get(metric, math.nan)
        return math.nan

    def _gate_metric(self, owner: str, metric: str) -> float:
        for gate in self.gates:
            if gate.name == owner:
                return {
                    "WAIT": gate.average_wait,
                    "MAX_WAIT": gate.max_wait,
                    "WAIT_COUNT": float(gate.wait_count),
                    "COUNT": float(gate.wait_count),
                }.get(metric, math.nan)
        return math.nan

    def _var_metric(self, variable: str, suffix: str,
                    original: str) -> float:
        if variable not in self.variables:
            for symbol, label in self.variables.items():
                if label == variable:
                    variable = symbol
                    break
        if not self.continuous:
            raise ValueError(f"变量没有连续采样: {original}")
        values = [
            float(sample["values"].get(variable, 0.0))
            for sample in self.continuous
        ]
        if not values:
            raise ValueError(f"变量没有连续采样: {original}")
        suffix = suffix.upper()
        if suffix == "MEAN":
            return sum(values) / len(values)
        if suffix == "MIN":
            return min(values)
        if suffix == "MAX":
            return max(values)
        if not suffix:
            return values[-1]
        raise ValueError(f"未知连续变量指标: {original}")

    def report(self, path: str, *, project: str | None = None,
               analyst: str | None = None, date: str | None = None,
               run_number: int = 1, total_runs: int = 1,
               track: list[str] | dict[str, str] | None = None,
               plot: list[str] | None = None) -> str:
        """写出 Markdown 报告，并按需生成 SVG。

        track:
          - None：输出全部自动统计；
          - list：按名称选择指标；
          - dict：报告标签 -> 指标名。

        plot:
          - None：连续变量存在时画全部；
          - []：不画；
          - list：指定变量。
        """
        project = project or self.project
        analyst = analyst or "Helix USER"
        date = date or datetime.now().strftime("%m/%d/%Y")

        lines = [
            "# Helix SUMMARY REPORT",
            "",
            f"**PROJECT**  {project}",
            f"**ANALYST**  {analyst}",
            f"**DATE**  {date}",
            f"**RUN**  {run_number} OF {total_runs}",
            f"**CURRENT TIME**  {self.now:.4f}",
        ]
        if self.seed is not None:
            lines += [
                f"**MODEL HASH**  {self.model_hash[:16]}",
                f"**SEED**  {self.seed}",
                f"**RNG MODE**  {self.rng_mode}",
                f"**END**  {self.end if self.end is not None else '-'}",
                f"**CLEAR TIME**  "
                f"{self.clear_time if self.clear_time is not None else '-'}",
            ]
        lines += [
            "",
        ]

        if track is None:
            # 默认报告使用表格式，列名保持完整，便于和 SLAM Summary Report 对照。
            if self.observations:
                lines += [
                    "## OBSERVATIONS",
                    "",
                    "| LABEL | MEAN | STD. DEV. | COEF. VAR. | "
                    "MIN | MAX | N |",
                    "|---|---:|---:|---:|---:|---:|---:|",
                ]
                for observation in self.observations:
                    cv = (observation.std / observation.mean
                          if observation.mean else 0.0)
                    lines.append(
                        f"| {observation.label} | {observation.mean:.4f} | "
                        f"{observation.std:.4f} | {cv:.4f} | "
                        f"{observation.minimum:.4f} | "
                        f"{observation.maximum:.4f} | "
                        f"{observation.count} |")
                lines.append("")

            if self.queues:
                lines += [
                    "## QUEUE STATISTICS",
                    "",
                    "| QUEUE | TYPE | AVG LENGTH | STD. LENGTH | "
                    "MAX LENGTH | CURRENT | BALK | AVG WAIT |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|",
                ]
                for queue in self.queues:
                    lines.append(
                        f"| {queue.label} | QUEUE | "
                        f"{queue.average_length:.4f} | "
                        f"{queue.std_length:.4f} | "
                        f"{queue.max_length} | {queue.current_length} | "
                        f"{queue.balk_count} | "
                        f"{queue.average_wait:.4f} |")
                lines.append("")

            if self.awaits:
                lines += [
                    "## WAIT FILE STATISTICS",
                    "",
                    "| WAIT FILE | RESOURCE | AVG LENGTH | STD. LENGTH | "
                    "MAX LENGTH | CURRENT | WAIT COUNT | AVG WAIT |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|",
                ]
                for await_stat in self.awaits:
                    lines.append(
                        f"| {await_stat.label} | {await_stat.resource} | "
                        f"{await_stat.average_length:.4f} | "
                        f"{await_stat.std_length:.4f} | "
                        f"{await_stat.max_length} | "
                        f"{await_stat.current_length} | "
                        f"{await_stat.wait_count} | "
                        f"{await_stat.average_wait:.4f} |")
                lines.append("")

            if self.services:
                lines += [
                    "## SERVICE ACTIVITY STATISTICS",
                    "",
                    "| ACTIVITY | SERVERS | AVG SVC UTIL. | "
                    "STD SVC UTIL. | MAX SVC UTIL. | CUR SVC UTIL. | "
                    "AVG BLOCK. | MAX IDLE TIME | MAX BUSY PERIOD | "
                    "COMPLETED |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
                for service in self.services:
                    lines.append(
                        f"| {service.activity} | {service.capacity} | "
                        f"{service.average_utilization:.4f} | "
                        f"{service.std_utilization:.4f} | "
                        f"{service.maximum_utilization} | "
                        f"{service.current_utilization} | "
                        f"{service.average_blockage:.4f} | "
                        f"{service.maximum_idle:.4f}/"
                        f"S{service.maximum_idle_server} | "
                        f"{service.maximum_busy:.4f}/"
                        f"S{service.maximum_busy_server} | "
                        f"{service.completed} |")
                lines.append("")

            if self.resources:
                lines += [
                    "## RESOURCE STATISTICS",
                    "",
                    "| RESOURCE | CAPACITY | AVAILABLE | AVG OCCUPANCY | "
                    "STD OCCUPANCY | MAX OCCUPANCY | CUR OCCUPANCY | "
                    "AVG HELD | MAX HELD | CURRENT | WAIT COUNT |",
                    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
                for resource in self.resources:
                    lines.append(
                        f"| {resource.name} | {resource.capacity} | "
                        f"{resource.available} | "
                        f"{resource.average_utilization:.4f} | "
                        f"{resource.std_utilization:.4f} | "
                        f"{resource.maximum_utilization:.4f} | "
                        f"{resource.current_utilization:.4f} | "
                        f"{resource.average_held:.4f} | "
                        f"{resource.maximum_held} | "
                        f"{resource.current_held} | "
                        f"{resource.wait_count} |")
                lines.append("")

            if self.gates:
                lines += [
                    "## GATE STATISTICS",
                    "",
                    "| GATE | STATE | WAIT COUNT | AVG WAIT | MAX WAIT |",
                    "|---|---|---:|---:|---:|",
                ]
                for gate in self.gates:
                    lines.append(
                        f"| {gate.name} | {gate.state} | "
                        f"{gate.wait_count} | {gate.average_wait:.4f} | "
                        f"{gate.max_wait:.4f} |")
                lines.append("")

            lines += [
                "## ABBREVIATIONS",
                "",
                "| ABBREVIATION | MEANING |",
                "|---|---|",
                "| MEAN | MEAN VALUE |",
                "| STD. DEV. | STANDARD DEVIATION |",
                "| COEF. VAR. | COEFFICIENT OF VARIATION |",
                "| N | NUMBER OF OBSERVATIONS |",
                "| TYPE | ASSOCIATED NODE TYPE |",
                "| AVG LENGTH | AVERAGE LENGTH |",
                "| STD. LENGTH | STANDARD DEVIATION OF LENGTH |",
                "| MAX LENGTH | MAXIMUM LENGTH |",
                "| CURRENT | CURRENT LENGTH / CURRENT HELD |",
                "| BALK | BALK COUNT |",
                "| AVG WAIT | AVERAGE WAIT |",
                "| MAX WAIT | MAXIMUM WAIT |",
                "| SERVERS | SERVER CAPACITY |",
                "| AVG SVC UTIL. | AVERAGE SERVICE UTILIZATION |",
                "| STD SVC UTIL. | STD. DEV. OF SERVICE UTILIZATION |",
                "| MAX SVC UTIL. | MAXIMUM SERVICE UTILIZATION |",
                "| CUR SVC UTIL. | CURRENT SERVICE UTILIZATION |",
                "| AVG BLOCK. | AVERAGE BLOCKAGE |",
                "| MAX IDLE TIME | MAXIMUM IDLE TIME / SERVER |",
                "| MAX BUSY PERIOD | MAXIMUM CONTINUOUS BUSY PERIOD / SERVER |",
                "| COMPLETED | TRANS. COUNT |",
                "| AVG OCCUPANCY | AVERAGE HELD / CAPACITY |",
                "| STD OCCUPANCY | STD. DEV. OF HELD / CAPACITY |",
                "| MAX OCCUPANCY | MAXIMUM HELD / CAPACITY |",
                "| CUR OCCUPANCY | CURRENT HELD / CAPACITY |",
                "| AVG HELD | AVERAGE HELD |",
                "| MAX HELD | MAXIMUM HELD |",
                "| AVAILABLE | REMAINING CAPACITY |",
                "",
            ]
        else:
            if isinstance(track, dict):
                entries = list(track.items())
            else:
                entries = [(name, name) for name in track]
            if entries:
                lines += ["## TRACKED METRICS", "",
                          "| TRACKED METRIC | VALUE |", "|---|---:|"]
                for label, metric in entries:
                    lines.append(
                        f"| {label} | {self._metric(metric):.4f} |")
                lines.append("")

        # plot=None 表示“有连续变量就画全部”，空列表表示不画。
        if plot is None:
            series = list(self.variables)
        else:
            series = []
            for name in plot:
                if name in self.variables:
                    series.append(name)
                else:
                    for symbol, label in self.variables.items():
                        if label == name:
                            series.append(symbol)
                            break
        if series and self.continuous:
            svg_path = Path(path).with_suffix(".svg")
            written = _write_continuous_svg(
                svg_path, self.continuous, series, self.variables)
            if written is not None:
                lines += ["", f"![Continuous variables]({svg_path.name})"]

        lines = _align_markdown_tables(lines)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return path
