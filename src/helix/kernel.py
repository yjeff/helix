"""FEL/CEL 事件内核。

Kernel 只认识 Event 和 TimeSource，不认识 QUEUE/ACTIVITY/RK4。
这样增加连续系统时，不需要重写调度核心。
"""
from __future__ import annotations

import heapq
from collections import deque

from .debug import DebugRecorder
from .errors import HelixDeadlockError, HelixRuntimeError
from .events import DETECT, Event, SEVNT
from .runtime.discrete import DiscreteRuntime
from .scenario import Scenario


class Kernel:
    """事件调度器。"""

    def __init__(self, *, scenario: Scenario, start: float, end: float | None,
                 seed: int, debug: bool = False,
                 debug_path: str | None = None,
                 clear_time: float | None = None,
                 continuous: dict | None = None) -> None:
        self.scenario = scenario
        self.model = scenario.model
        self.start = start
        self.end = end
        self.now = start
        self.seed = seed
        self.clear_time = clear_time
        self.cleared = clear_time is None
        self.continuous_options = dict(continuous or {})

        self.seq = 0
        self.batch = 0
        self.fel: list[Event] = []
        self.cel: deque[Event] = deque()
        self.stop_requested = False

        self.runtime = DiscreteRuntime(self)
        if self.model.equations:
            from .continuous.source import ContinuousSource

            self.continuous = ContinuousSource(self)
        else:
            self.continuous = _NullContinuousSource()
        self.debug: DebugRecorder | None = None
        if debug:
            self.debug = DebugRecorder(
                debug_path or "debug",
                model=self.model,
                run_info={
                    "format": "helix-debug",
                    "version": 1,
                    "project": self.model.project,
                    "seed": seed,
                    "start": start,
                    "end": end,
                    "continuous": self.continuous_options,
                    "model_hash": self.model.source_hash,
                    "initial": scenario.initial,
                    "constants": scenario.constants,
                    "entities": {
                        key: len(value)
                        for key, value in scenario.entities.items()
                    },
                },
            )

    # ------------------------------------------------------------------
    # 事件调度
    # ------------------------------------------------------------------
    def schedule(self, event: Event) -> None:
        """把事件放入 CEL 或 FEL。

        同一时刻的事件必须进入 CEL，且不能推进 now。
        """
        if event.time < self.now - 1e-12:
            raise HelixRuntimeError(
                f"事件时间倒退: {event.time} < {self.now}")

        self.seq += 1
        event.seq = self.seq

        if abs(event.time - self.now) <= 1e-12:
            event.time = self.now
            self.cel.append(event)
        else:
            heapq.heappush(self.fel, event)

    def _move_fel_to_cel(self) -> None:
        """把 FEL 中所有当前时刻事件按 seq 移入 CEL。"""
        while self.fel and abs(self.fel[0].time - self.now) <= 1e-12:
            self.cel.append(heapq.heappop(self.fel))

    # ------------------------------------------------------------------
    # 时间
    # ------------------------------------------------------------------
    def _next_time(self) -> float | None:
        candidates: list[float] = []
        if self.fel:
            candidates.append(self.fel[0].time)
        if self.end is not None:
            candidates.append(self.end)
        cont = self.continuous.next_time(self.now, self.end)
        if cont is not None:
            candidates.append(cont)
        return min(candidates) if candidates else None

    def advance_statistics(self, target: float) -> float:
        """把状态从 now 推进到 target。

        顺序：
        1. 连续系统先积分（可能提前返回 t'）；
        2. runtime 用 t' 更新队列/活动面积；
        3. 最后才改 now。

        注意 runtime.advance() 读取的是旧的 kernel.now，因此统计的
        dt 正好是 [now, target]；如果先改 now 再统计，平均值会少一段。
        """
        if target < self.now - 1e-12:
            raise HelixRuntimeError(
                f"时间倒退: {target} < {self.now}")

        if (not self.cleared and self.clear_time is not None
                and self.now < self.clear_time <= target + 1e-12):
            # 先推进到 clear_time，清空累计统计，再继续到原目标。
            start = self.now
            actual = self.continuous.advance_to(self.clear_time)
            self.runtime.advance(actual, start=start)
            self.now = actual
            self.runtime.reset_statistics(self.now)
            self.cleared = True
            if target > self.now + 1e-12:
                return self.advance_statistics(target)
            return self.now

        start = self.now
        actual = self.continuous.advance_to(target)
        if actual < self.now - 1e-12 or actual > target + 1e-12:
            raise HelixRuntimeError(
                f"连续系统返回非法时间: {actual}, 目标 {target}")
        self.runtime.advance(actual, start=start)
        self.now = actual
        return actual

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def _record_state(self, event: str | None = None) -> None:
        if self.debug is None:
            return
        state = self.runtime.snapshot()
        state["t"] = self.now
        self.debug.record_state(state, batch=self.batch, event=event)

    def run(self):
        """运行到 end 或事件耗尽。

        主循环刻意保持“薄”：
        - Kernel 只负责时间、FEL/CEL 和 dispatch；
        - DiscreteRuntime 决定某个事件如何改变网络状态；
        - ContinuousSource 决定连续系统推进到哪里。

        这样接入 RK4/DD/SS 时，不需要在这个循环里增加大量 if。
        """
        self.runtime.initialize()
        self._record_state("INIT")
        event_count = 0

        while True:
            if not self.cel:
                # CEL 为空才允许推进时钟。这个顺序非常关键：
                # 同一时刻的所有事件必须先处理完，统计面积只更新一次。
                if self.end is not None and self.now >= self.end - 1e-12:
                    self.advance_statistics(self.end)
                    break

                target = self._next_time()
                if target is None:
                    break

                if self.end is not None and target > self.end + 1e-12:
                    # 超过结束时刻的 FEL 事件不执行，但统计要推进到 end。
                    self.advance_statistics(self.end)
                    break

                if target <= self.now + 1e-12:
                    raise HelixRuntimeError(
                        f"时间没有推进: now={self.now}, target={target}")

                # advance_statistics 负责连续积分 + 时间加权统计。
                # 返回值可能早于 target（DETECT 在积分步内截断）。
                self.advance_statistics(target)
                self.batch += 1

                # 连续事件先入 CEL，再放入 FEL 同刻事件。
                # 这样 DETECT/SEVNT 看到的是“连续状态刚越过阈值”的
                # 状态，而不是已被离散事件修改过的状态。
                self.cel.extend(self.continuous.events_at(self.now))
                self._move_fel_to_cel()

                if not self.cel:
                    # 当前时刻只有连续采样/保存点，没有离散事件。
                    continue

            event = self.cel.popleft()
            event_count += 1
            if event_count > 1_000_000:
                raise HelixRuntimeError(
                    f"事件数超过上限，可能零时间循环: now={self.now}")
            if self.debug is not None:
                # 先记录再处理，保证动画看到的是“事件发生前”的图；
                # 事件 payload 中带有处理前的必要状态。
                self.debug.record(event, batch=self.batch)
            if event.kind == DETECT:
                # 网络中的 DETECT 节点会把信号实体送入后继；
                # 顶层 DETECT 声明只用于 DEBUG/外部观察。
                node = self.model.nodes.get(event.node)
                if node is not None and node.kind == "DETECT":
                    self.runtime.handle(event)
                else:
                    # 顶层 DETECT 声明没有网络后继，但仍可作为
                    # ACTIVITY(until=NAME) 的事件源。
                    self.runtime.fire_event(event.node)
                self._record_state(event.kind)
                continue
            if event.kind == SEVNT:
                code = int(event.data.get("code", 0))
                if code == 1:
                    self._record_state(event.kind)
                    self.stop_requested = True
                    break
                self.runtime.handle(event)
                if hasattr(self.continuous, "rearm_sevnt"):
                    self.continuous.rearm_sevnt(code)
                self._record_state(event.kind)
                continue
            self.runtime.handle(event)
            self._record_state(event.kind)

            if self.stop_requested:
                break

        # 结束统计由 runtime 汇总；DEBUG 关闭放在最后，避免异常时
        # 遗留未 flush 的文件。
        self._record_state("FINAL")
        result = self.runtime.result(self.now)
        result.global_values = dict(self.runtime.variables)
        result.variables = {
            name: spec.label for name, spec in self.model.variables.items()
            if spec.scope == "GLOBAL"
        }
        if hasattr(self.continuous, "samples"):
            result.continuous = list(self.continuous.samples)
            result.continuous_final = dict(
                getattr(self.continuous, "state", {}))
            if (result.continuous
                    and abs(result.continuous[-1]["t"] - self.now) < 1e-9):
                # 同一时刻的 end 事件可能改变变量；最后采样应反映最终状态。
                result.continuous[-1]["values"] = dict(
                    result.continuous_final)
        if self.debug is not None:
            result.debug_path = str(self.debug.directory)
            self.debug.close()
        return result


class _NullContinuousSource:
    """没有连续方程时的空实现。

    接口与真正的 ContinuousSource 完全一致，因此 Kernel 不需要
    分支判断“有没有连续系统”。
    """

    def next_time(self, now: float, end: float | None) -> float | None:
        return end

    def advance_to(self, target: float) -> float:
        return target

    def events_at(self, now: float) -> list[Event]:
        return []
