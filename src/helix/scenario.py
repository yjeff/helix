"""初始化后的运行场景。

Model 是只读模板；Scenario 保存一次运行所需的初值、常量和
初始实体。多次 run 都从同一份 Scenario 状态重新开始。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import HelixCompileError
from .model import Model


@dataclass(slots=True)
class Scenario:
    model: Model
    initial: dict[str, float] = field(default_factory=dict)
    constants: dict[str, float] = field(default_factory=dict)
    entities: dict[str, list[dict]] = field(default_factory=dict)
    continuous: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.initial = self._normalize_initial(self.initial)
        self.constants = {
            str(key): float(value) for key, value in self.constants.items()
        }
        self.entities = self._normalize_entities(self.entities)
        self.continuous = self._normalize_continuous(self.continuous)

    def _normalize_continuous(self, continuous: dict) -> dict:
        options = dict(continuous or {})
        allowed = {"method", "min_step", "save_step", "max_step", "tol"}
        unknown = set(options) - allowed
        if unknown:
            raise HelixCompileError(
                f"未知 continuous 参数: {', '.join(sorted(unknown))}")
        return options

    # ------------------------------------------------------------------
    # 名称解析
    # ------------------------------------------------------------------
    def _normalize_initial(self, initial: dict) -> dict[str, float]:
        """把标签/符号统一成变量名。

        Helix 用户层优先使用 VAR 的标签；内部以变量名保存。
        """
        by_label = {spec.label: name for name, spec in
                    self.model.variables.items()
                    if spec.scope == "GLOBAL"}
        result: dict[str, float] = {}
        for name, spec in self.model.variables.items():
            if spec.scope != "GLOBAL":
                continue
            if spec.size:
                for index in range(1, spec.size + 1):
                    result[f"{name}[{index}]"] = spec.default
            else:
                result[name] = spec.default
        for key, value in initial.items():
            key = str(key)
            name = key if key in self.model.variables and \
                self.model.variables[key].scope == "GLOBAL" \
                else by_label.get(key)
            if name is None:
                available = ", ".join(sorted(
                    name for name, spec in self.model.variables.items()
                    if spec.scope == "GLOBAL"))
                raise HelixCompileError(
                    f"未知初始变量: {key}；可用变量: {available}")
            spec = self.model.variables[name]
            if spec.size:
                if isinstance(value, dict):
                    items = value.items()
                elif isinstance(value, (list, tuple)):
                    items = enumerate(value, start=1)
                else:
                    raise HelixCompileError(
                        f"数组初值必须是 list/dict: {key}")
                for index, item in items:
                    index = int(index)
                    if index < 1 or index > spec.size:
                        raise HelixCompileError(
                            f"数组初值下标越界: {key}[{index}]")
                    result[f"{name}[{index}]"] = float(item)
            else:
                result[name] = float(value)
        return result

    def _normalize_entities(self, entities: dict) -> dict[str, list[dict]]:
        node_labels = {node.label for node in self.model.nodes.values()}
        result: dict[str, list[dict]] = {}
        for key, items in entities.items():
            label = str(key)
            if label not in node_labels:
                raise HelixCompileError(
                    f"entities 引用了不存在的节点: {label}")
            result[label] = [dict(item) for item in items]
        return result

    # ------------------------------------------------------------------
    # 运行
    # ------------------------------------------------------------------
    def run(self, *, start: float = 0.0, end: float | None = None,
            seed: int = 0, debug: bool = False,
            debug_path: str | None = None, clear_time: float | None = None):
        """运行场景并返回 RunResult。

        start/end/seed 属于运行控制；continuous 已在 initialize 中固定。
        clear_time 模拟旧版 MONTR,CLEAR：到达该时刻后清空统计累计值。
        """
        from .kernel import Kernel

        return Kernel(
            scenario=self,
            start=float(start),
            end=None if end is None else float(end),
            seed=int(seed),
            debug=debug,
            debug_path=debug_path,
            clear_time=None if clear_time is None else float(clear_time),
            continuous=self.continuous,
        ).run()
