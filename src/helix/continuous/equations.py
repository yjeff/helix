"""DD/SS 方程编译与 RK4 积分。"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..errors import HelixRuntimeError
from ..model import Model
from .expressions import Expression, expression


_EQUATION_RE = re.compile(
    r"^(DD|SS)\s*\(\s*([A-Za-z_]\w*(?:\[[0-9]+\])?)\s*\)\s*=\s*(.+)$", re.I)


@dataclass
class ContinuousModel:
    """连续方程集合。

    - ``ss`` 是代数方程，按书写顺序求值；
    - ``dd`` 是微分方程，RK4 每个 RHS 调用都重新计算。
    """

    dd: dict[str, Expression] = field(default_factory=dict)
    ss: list[tuple[str, Expression]] = field(default_factory=list)
    dd_order: list[str] = field(default_factory=list)

    @classmethod
    def from_model(cls, model: Model) -> "ContinuousModel | None":
        if not model.equations:
            return None
        result = cls()
        for line in model.equations:
            match = _EQUATION_RE.match(line.strip())
            if not match:
                raise HelixRuntimeError(
                    f"无法解析 EQUATION: {line!r}")
            kind, name, body = match.groups()
            base = name.split("[", 1)[0]
            if base not in model.variables:
                raise HelixRuntimeError(
                    f"EQUATION 引用了未声明变量: {name}")
            spec = model.variables[base]
            if spec.scope != "GLOBAL":
                raise HelixRuntimeError(
                    f"EQUATION 变量必须是 GLOBAL: {name}")
            if spec.size and "[" not in name:
                raise HelixRuntimeError(
                    f"EQUATION 数组变量必须带下标: {name}")
            expr = expression(body, label=f"{kind}({name})")
            if kind.upper() == "DD":
                if name in result.dd:
                    raise HelixRuntimeError(
                        f"重复 DD 方程: {name}")
                result.dd[name] = expr
                result.dd_order.append(name)
            else:
                result.ss.append((name, expr))
        return result

    def derivatives(self, t: float, state: dict[str, float],
                    constants: dict[str, float]) -> list[float]:
        """计算当前状态下的 DD 向量。"""
        context = dict(constants)
        context.update(state)
        context["TNOW"] = t
        # 代数方程按书写顺序更新 context；后续方程能看到前面的结果。
        for name, expr in self.ss:
            context[name] = expr.evaluate(context)
        values: list[float] = []
        for name in self.dd_order:
            values.append(self.dd[name].evaluate(context))
        return values

    def update_algebraic(self, t: float, state: dict[str, float],
                         constants: dict[str, float]) -> None:
        """把 SS 代数变量写回状态，供采样/报告使用。"""
        context = dict(constants)
        context.update(state)
        context["TNOW"] = t
        for name, expr in self.ss:
            context[name] = expr.evaluate(context)
            state[name] = context[name]


def rkf45_step(continuous: ContinuousModel, t: float,
               state: dict[str, float], dt: float,
               constants: dict[str, float],
               tolerance: float = 1e-4) -> tuple[dict[str, float], float]:
    """RKF45（Fehlberg 4(5)）单步。

    返回 ``(新状态, 归一化误差)``；调用方根据误差决定接受/缩步。
    这里同时计算四阶和五阶解，用两者差值估计截断误差。
    """
    names = continuous.dd_order
    y0 = [state[name] for name in names]

    # 标准 Fehlberg 系数。
    k1 = continuous.derivatives(t, dict(state), constants)
    k2 = continuous.derivatives(
        t + dt / 4,
        {**state, **{n: state[n] + dt / 4 * k1[i]
                    for i, n in enumerate(names)}},
        constants)
    k3 = continuous.derivatives(
        t + 3 * dt / 8,
        {**state, **{n: state[n] + dt * (3 / 32 * k1[i] + 9 / 32 * k2[i])
                    for i, n in enumerate(names)}},
        constants)
    k4 = continuous.derivatives(
        t + 12 * dt / 13,
        {**state, **{n: state[n] + dt * (
            1932 / 2197 * k1[i] - 7200 / 2197 * k2[i]
            + 7296 / 2197 * k3[i]) for i, n in enumerate(names)}},
        constants)
    k5 = continuous.derivatives(
        t + dt,
        {**state, **{n: state[n] + dt * (
            439 / 216 * k1[i] - 8 * k2[i]
            + 3680 / 513 * k3[i] - 845 / 4104 * k4[i])
            for i, n in enumerate(names)}},
        constants)
    k6 = continuous.derivatives(
        t + dt / 2,
        {**state, **{n: state[n] + dt * (
            -8 / 27 * k1[i] + 2 * k2[i]
            - 3544 / 2565 * k3[i] + 1859 / 4104 * k4[i]
            - 11 / 40 * k5[i]) for i, n in enumerate(names)}},
        constants)

    new: dict[str, float] = dict(state)
    error = 0.0
    for i, name in enumerate(names):
        fourth = y0[i] + dt * (
            25 / 216 * k1[i] + 1408 / 2565 * k3[i]
            + 2197 / 4104 * k4[i] - 1 / 5 * k5[i])
        fifth = y0[i] + dt * (
            16 / 135 * k1[i] + 6656 / 12825 * k3[i]
            + 28561 / 56430 * k4[i] - 9 / 50 * k5[i]
            + 2 / 55 * k6[i])
        new[name] = fifth
        scale = tolerance + tolerance * max(abs(y0[i]), abs(fifth))
        error = max(error, abs(fifth - fourth) / max(scale, 1e-12))
    return new, error


def rk4_step(continuous: ContinuousModel, t: float,
             state: dict[str, float], dt: float,
             constants: dict[str, float]) -> None:
    """标准四阶 Runge-Kutta。

    state 原地更新；只对 dd_order 中的变量积分。
    """
    names = continuous.dd_order
    y0 = [state[name] for name in names]

    def add_scaled(values: list[float], scale: float) -> dict[str, float]:
        trial = dict(state)
        for name, value in zip(names, values):
            trial[name] = state[name] + scale * value
        return trial

    k1 = continuous.derivatives(t, dict(state), constants)
    k2 = continuous.derivatives(
        t + dt / 2, add_scaled(k1, dt / 2), constants)
    k3 = continuous.derivatives(
        t + dt / 2, add_scaled(k2, dt / 2), constants)
    k4 = continuous.derivatives(
        t + dt, add_scaled(k3, dt), constants)

    for index, name in enumerate(names):
        state[name] = y0[index] + dt / 6 * (
            k1[index] + 2 * k2[index] + 2 * k3[index] + k4[index])
