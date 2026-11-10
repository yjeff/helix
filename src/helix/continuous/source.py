"""连续系统 TimeSource。

它实现 Kernel 约定的三个方法：
- next_time(now, end)
- advance_to(t)
- events_at(t)

Kernel 不知道 DD/SS 或 RK4，只通过该接口推进。
"""
from __future__ import annotations

from ..events import DETECT, SEVNT, Event
from ..model import DetectSpec, Model, SevntSpec
from .equations import ContinuousModel, rk4_step, rkf45_step
from .expressions import Expression


class ContinuousSource:
    """连续状态、积分步长和 DETECT/SEVNT 的实现。"""

    def __init__(self, kernel) -> None:
        self.kernel = kernel
        self.model: Model = kernel.model
        self.continuous = ContinuousModel.from_model(self.model)
        self.constants = dict(kernel.scenario.constants)
        self.state: dict[str, float] = {}

        for name, spec in self.model.variables.items():
            if spec.scope != "GLOBAL":
                continue
            if spec.size:
                for index in range(1, spec.size + 1):
                    key = f"{name}[{index}]"
                    self.state[key] = float(
                        kernel.scenario.initial.get(key, spec.default))
            else:
                self.state[name] = float(
                    kernel.scenario.initial.get(name, spec.default))
        if self.continuous is not None:
            self.continuous.update_algebraic(
                kernel.start, self.state, self.constants)
        self.samples: list[dict] = [{
            "t": kernel.start,
            "values": dict(self.state),
        }]

        settings = self.model.continuous
        options = getattr(kernel, "continuous_options", {}) or {}

        def pick(name: str, default):
            return options[name] if name in options else default

        default_method = settings.method if settings else "RK4"
        default_tol = settings.tol if settings else 1e-4
        default_min = settings.min_step if settings else 0.001
        default_save = settings.save_step if settings else 0.1
        default_max = settings.max_step if settings else 0.1
        self.method = str(pick("method", default_method)).upper()
        self.tol = float(pick("tol", default_tol))
        self.min_step = float(pick("min_step", default_min))
        self.save_step = float(pick("save_step", default_save))
        self.max_step = float(pick("max_step", default_max))
        if self.min_step <= 0:
            self.min_step = 1e-6
        if self.max_step <= 0:
            self.max_step = max(self.min_step, 0.1)
        if self.save_step <= 0:
            self.save_step = self.max_step
        if self.method not in ("RK4", "RKF45"):
            raise ValueError(f"未知积分方法: {self.method}")

        # 自适应方法会动态调整 self.h；RK4 固定使用 max_step。
        self.h = self.max_step
        self.next_save = kernel.start + self.save_step
        self._pending_events: list[Event] = []

        # 网络中的 DETECT 节点：事件触发后不仅要记录，还要把
        # 一个信号实体送入它的后继网络。
        self.detect_nodes: list[DetectSpec] = []
        for node in self.model.nodes.values():
            if node.kind != "DETECT":
                continue
            self.detect_nodes.append(DetectSpec(
                name=node.label,
                when=node.args.get("when", ""),
                edge=node.args.get("edge", "RISING").upper(),
                tol=float(node.args.get("tol", "0.01")),
            ))

        # 每个 DETECT/SEVNT 维护上一次条件值，用边沿触发而不是
        # “当前为真就触发”。否则初始就为真的阈值会在第一步误触发。
        self._detect_expr: dict[str, Expression] = {}
        self._sevnt_expr: dict[int, Expression] = {}
        self._last_condition: dict[tuple[str, object], bool] = {}
        for spec in list(self.model.detects) + self.detect_nodes:
            self._last_condition[("D", spec.name)] = self._condition(
                spec, self._context())
        for spec in self.model.sevnts:
            self._last_condition[("S", spec.code)] = self._condition(
                spec, self._context())

    # ------------------------------------------------------------------
    # TimeSource 接口
    # ------------------------------------------------------------------
    def next_time(self, now: float, end: float | None) -> float | None:
        if self.continuous is None or not self.continuous.dd_order:
            return None
        candidates = [now + self.h]
        if self.save_step > 0:
            candidates.append(self.next_save)
        if end is not None:
            candidates.append(end)
        return min(candidates)

    def advance_to(self, target: float) -> float:
        """积分到 target 或更早的 DETECT 事件时刻。"""
        if self.continuous is None:
            return target
        if not self.continuous.dd_order:
            return target

        while self.kernel.now < target - 1e-12:
            step = min(self.h, target - self.kernel.now)
            if self.next_save > self.kernel.now + 1e-12:
                step = min(step, self.next_save - self.kernel.now)
            if step <= 1e-15:
                # 目标点与当前时刻重合；不能再缩步。
                break

            t0 = self.kernel.now
            before = dict(self.state)
            if self.method == "RKF45":
                candidate, error = rkf45_step(
                    self.continuous, t0, before, step,
                    self.constants, self.tol)
                if error > 1.0 and step > self.min_step:
                    # 误差超限：缩步重试，不推进 now。
                    self.h = max(self.min_step, step * 0.5)
                    continue
                after = candidate
                if error > 0:
                    factor = 0.9 * (1.0 / error) ** 0.2
                    factor = min(2.0, max(0.2, factor))
                else:
                    factor = 2.0
                self.h = min(self.max_step,
                             max(self.min_step, step * factor))
            else:
                after = dict(before)
                rk4_step(self.continuous, t0, after, step, self.constants)
                self.h = self.max_step

            # 步内根搜索：若 DETECT/SEVNT 条件在 (t0, t0+step) 内
            # 穿越，则用二分法找到事件时刻，避免只在步末触发。
            root = self._find_root(t0, before, step, after)
            if root is not None:
                root_step, root_state = root
                self.state = root_state
                self.kernel.now = t0 + root_step
                if self.continuous is not None:
                    self.continuous.update_algebraic(
                        self.kernel.now, self.state, self.constants)
                if self.next_save <= self.kernel.now + 1e-12:
                    self._record_sample(self.kernel.now)
                    self.next_save += self.save_step
                    while self.next_save <= self.kernel.now + 1e-12:
                        self.next_save += self.save_step
                self._check_events()
                return self.kernel.now

            self.state = after
            self.kernel.now += step
            if self.continuous is not None:
                self.continuous.update_algebraic(
                    self.kernel.now, self.state, self.constants)

            if self.next_save <= self.kernel.now + 1e-12:
                self._record_sample(self.kernel.now)
                self.next_save += self.save_step
                while self.next_save <= self.kernel.now + 1e-12:
                    self.next_save += self.save_step

            self._check_events()
            if self._pending_events:
                # 在检测到状态事件的时刻截断；Kernel 会先处理这些事件。
                return self.kernel.now

        return self.kernel.now

    def events_at(self, now: float) -> list[Event]:
        events = self._pending_events
        self._pending_events = []
        return events

    # ------------------------------------------------------------------
    # 采样与事件
    # ------------------------------------------------------------------
    def _record_sample(self, t: float) -> None:
        self.samples.append({
            "t": t,
            "values": dict(self.state),
        })

    def _context(self) -> dict[str, float]:
        context = dict(self.constants)
        context.update(self.state)
        context["TNOW"] = self.kernel.now
        return context

    def _trial_state(self, t0: float, base: dict[str, float],
                     step: float) -> dict[str, float]:
        """从 base 积分 step，用于根搜索的试探状态。"""
        trial = dict(base)
        if self.method == "RKF45":
            trial, _error = rkf45_step(
                self.continuous, t0, trial, step,
                self.constants, self.tol)
        else:
            rk4_step(self.continuous, t0, trial, step, self.constants)
        return trial

    def _find_root(self, t0: float, before: dict[str, float],
                   step: float, after: dict[str, float]):
        """寻找步内最早的 DETECT/SEVNT 根。

        返回 ``(step_from_t0, state_at_root)`` 或 None。
        """
        best_step: float | None = None
        best_state: dict[str, float] | None = None

        def values(state: dict[str, float], t: float) -> dict[str, float]:
            context = dict(self.constants)
            context.update(state)
            context["TNOW"] = t
            return context

        start_ctx = values(before, t0)
        end_ctx = values(after, t0 + step)

        specs = (list(self.model.detects) + self.detect_nodes
                 + list(self.model.sevnts))
        for spec in specs:
            expression = self._expr_for(spec)
            start_value = expression.root_value(start_ctx)
            end_value = expression.root_value(end_ctx)
            # 仅处理比较条件的符号穿越；非比较条件退回步末检查。
            if abs(end_value - start_value) < 1e-15:
                continue
            if not (start_value < 0.0 <= end_value
                    or end_value < 0.0 <= start_value):
                continue

            start_true = expression.evaluate(start_ctx) != 0.0
            end_true = expression.evaluate(end_ctx) != 0.0
            edge = getattr(spec, "edge", "RISING").upper()
            if edge == "RISING" and not (not start_true and end_true):
                continue
            if edge == "FALLING" and not (start_true and not end_true):
                continue
            if edge == "ANY" and start_true == end_true:
                continue
            lo, hi = 0.0, step
            for _ in range(60):
                mid = (lo + hi) / 2
                trial = self._trial_state(t0, before, mid)
                ctx = values(trial, t0 + mid)
                value = expression.root_value(ctx)
                if abs(value) < 1e-10 or hi - lo < 1e-9:
                    lo = hi = mid
                    break
                if (start_value < 0) == (value < 0):
                    lo = mid
                else:
                    hi = mid
            candidate_step = (lo + hi) / 2
            if best_step is None or candidate_step < best_step:
                best_step = candidate_step
                best_state = self._trial_state(t0, before, candidate_step)

        if best_step is None or best_state is None:
            return None
        return best_step, best_state

    def _expr_for(self, spec):
        if isinstance(spec, DetectSpec):
            expression = self._detect_expr.get(spec.name)
        else:
            expression = self._sevnt_expr.get(spec.code)
        if expression is None:
            expression = Expression(spec.when, label=str(
                getattr(spec, "name", getattr(spec, "code", "SEVNT"))))
            if isinstance(spec, DetectSpec):
                self._detect_expr[spec.name] = expression
            else:
                self._sevnt_expr[spec.code] = expression
        return expression

    def rearm_sevnt(self, code: int) -> None:
        """事件动作执行后重新武装 SEVNT，避免动作清空状态后
        仍因 last_condition=True 而错过下一次触发。"""
        self._last_condition[("S", code)] = False

    def _check_events(self) -> None:
        context = self._context()

        for spec in list(self.model.detects) + self.detect_nodes:
            key = ("D", spec.name)
            was = self._last_condition.get(key, False)
            now = self._condition(spec, context)
            edge = spec.edge.upper()
            trigger = (
                (edge == "RISING" and not was and now)
                or (edge == "FALLING" and was and not now)
                or (edge == "ANY" and was != now)
            )
            self._last_condition[key] = now
            if not trigger:
                continue
            self._pending_events.append(Event(
                time=self.kernel.now, seq=0, kind=DETECT,
                node=spec.name,
                data={"name": spec.name},
                source="CONTINUOUS"))

        for spec in self.model.sevnts:
            key = ("S", spec.code)
            was = self._last_condition.get(key, False)
            now = self._condition(spec, context)
            # SEVNT 没有 edge 参数，默认按上升沿触发。
            trigger = not was and now
            self._last_condition[key] = now
            if trigger:
                self._pending_events.append(Event(
                    time=self.kernel.now, seq=0, kind=SEVNT,
                    data={"code": spec.code, "name": spec.name,
                          "action": spec.action},
                    source="CONTINUOUS"))

    def _condition(self, spec: DetectSpec | SevntSpec,
                   context: dict[str, float]) -> bool:
        if isinstance(spec, DetectSpec):
            expression = self._detect_expr.get(spec.name)
        else:
            expression = self._sevnt_expr.get(spec.code)
        if expression is None:
            expression = Expression(spec.when, label=str(
                getattr(spec, "name", getattr(spec, "code", "SEVNT"))))
            if isinstance(spec, DetectSpec):
                self._detect_expr[spec.name] = expression
            else:
                self._sevnt_expr[spec.code] = expression
        return expression.evaluate(context) != 0.0
