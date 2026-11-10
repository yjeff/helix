"""连续方程/事件条件的安全表达式求值。

不用 Python ``eval``，而是把表达式解析成 AST，只允许：
- 数字
- 变量名
- 算术/比较/布尔运算
- 白名单数学函数

因此模型文本不能执行任意 Python 代码。
"""
from __future__ import annotations

import ast
import math
import re

from ..errors import HelixRuntimeError


_ALLOWED_FUNCTIONS = {
    "SIN": math.sin,
    "COS": math.cos,
    "TAN": math.tan,
    "ASIN": math.asin,
    "ACOS": math.acos,
    "ATAN": math.atan,
    "ATAN2": math.atan2,
    "SINH": math.sinh,
    "COSH": math.cosh,
    "TANH": math.tanh,
    "SQRT": math.sqrt,
    "EXP": math.exp,
    "LOG": math.log,
    "LOG10": math.log10,
    "ABS": abs,
    "MIN": min,
    "MAX": max,
    "MOD": math.fmod,
    "FLOOR": math.floor,
    "CEIL": math.ceil,
}


class Expression:
    """预编译的表达式。"""

    def __init__(self, source: str, *, label: str = "<expr>") -> None:
        self.source = source.strip()
        self.label = label
        # 模型层统一使用 AND/OR/NOT；Python AST 需要小写。
        normalized = re.sub(r"\bAND\b", "and", self.source, flags=re.I)
        normalized = re.sub(r"\bOR\b", "or", normalized, flags=re.I)
        normalized = re.sub(r"\bNOT\b", "not", normalized, flags=re.I)
        try:
            self.tree = ast.parse(normalized, mode="eval")
        except SyntaxError as exc:
            raise HelixRuntimeError(
                f"{label}: 表达式语法错误: {self.source!r}") from exc

    def evaluate(self, context: dict[str, float]) -> float:
        return float(self._eval(self.tree.body, context))

    def root_value(self, context: dict[str, float]) -> float:
        """返回比较条件对应的连续符号量。

        例如 ``TEMP < 5`` 返回 ``TEMP - 5``。根搜索需要连续量，
        不能直接用 0/1 的比较结果。
        """
        node = self.tree.body
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left = self._eval(node.left, context)
            right = self._eval(node.comparators[0], context)
            # 统一为 left - right；条件为真的符号由 op 决定。
            return left - right
        return self.evaluate(context)

    def _eval(self, node: ast.AST, context: dict[str, float]) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            name = node.id
            if name == "PI":
                return math.pi
            if name == "TNOW":
                return float(context.get("TNOW", 0.0))
            if name in context:
                return float(context[name])
            raise HelixRuntimeError(
                f"{self.label}: 未知变量 {name}")
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            index = int(self._eval(node.slice, context))
            key = f"{node.value.id}[{index}]"
            if key in context:
                return float(context[key])
            raise HelixRuntimeError(
                f"{self.label}: 未初始化数组元素 {key}")
        if isinstance(node, ast.BinOp):
            left = self._eval(node.left, context)
            right = self._eval(node.right, context)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left ** right
            if isinstance(node.op, ast.Mod):
                return left % right
            raise HelixRuntimeError(
                f"{self.label}: 不支持的运算符")
        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand, context)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.Not):
                return 0.0 if value else 1.0
            raise HelixRuntimeError(
                f"{self.label}: 不支持的一元运算符")
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, context)
                if isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                else:
                    raise HelixRuntimeError(
                        f"{self.label}: 不支持的比较运算")
                if not ok:
                    return 0.0
                left = right
            return 1.0
        if isinstance(node, ast.BoolOp):
            values = [self._eval(value, context) for value in node.values]
            if isinstance(node.op, ast.And):
                return 1.0 if all(values) else 0.0
            if isinstance(node.op, ast.Or):
                return 1.0 if any(values) else 0.0
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id.upper()
            if name == "SUM" and len(node.args) == 1 \
                    and isinstance(node.args[0], ast.Name):
                prefix = f"{node.args[0].id}["
                return float(sum(
                    value for key, value in context.items()
                    if key.startswith(prefix)))
            if name == "IF":
                if len(node.args) != 3:
                    raise HelixRuntimeError("IF 需要 3 个参数")
                condition = self._eval(node.args[0], context)
                return self._eval(
                    node.args[1] if condition else node.args[2], context)
            if name in ("AVAILABLE", "CAPACITY", "HELD"):
                if len(node.args) != 1:
                    raise HelixRuntimeError(f"{name} 需要 1 个资源名")
                argument = node.args[0]
                if isinstance(argument, ast.Name):
                    resource_name = argument.id
                elif (isinstance(argument, ast.Constant)
                      and isinstance(argument.value, str)):
                    resource_name = argument.value
                else:
                    raise HelixRuntimeError(
                        f"{name} 的参数必须是资源名")
                key = f"RESOURCE.{resource_name.upper()}.{name}"
                if key not in context:
                    raise HelixRuntimeError(
                        f"{self.label}: 未知资源 {resource_name}")
                return float(context[key])
            function = _ALLOWED_FUNCTIONS.get(name)
            if function is None:
                raise HelixRuntimeError(
                    f"{self.label}: 不允许的函数 {node.func.id}")
            args = [self._eval(arg, context) for arg in node.args]
            try:
                return float(function(*args))
            except (TypeError, ValueError, ZeroDivisionError) as exc:
                raise HelixRuntimeError(
                    f"{self.label}: 函数 {name} 计算失败") from exc
        raise HelixRuntimeError(
            f"{self.label}: 不支持的表达式元素 {type(node).__name__}")


def expression(source: str, *, label: str = "<expr>") -> Expression:
    return Expression(source, label=label)
