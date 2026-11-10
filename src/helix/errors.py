"""Helix 错误类型。

设计原则：
- 编译错误尽量带文件、行号、列号和上下文；
- 运行错误只描述可执行的语义问题；
- 死锁单独成类，便于生成 deadlock.json。
"""
from __future__ import annotations


class HelixError(Exception):
    """所有 Helix 错误的基类。"""


class HelixSyntaxError(HelixError):
    """词法或语法错误。"""

    def __init__(self, message: str, *, line: int = 0, col: int = 0,
                 source: str = "<string>") -> None:
        self.message = message
        self.line = line
        self.col = col
        self.source = source
        super().__init__(self._format())

    def _format(self) -> str:
        where = f"{self.source}:{self.line}:{self.col}"
        return f"{where}: {self.message}"


class HelixCompileError(HelixError):
    """模型语义检查失败，例如未定义节点、重复标签。"""

    def __init__(self, message: str, *, node: str | None = None) -> None:
        self.message = message
        self.node = node
        prefix = f"[{node}] " if node else ""
        super().__init__(prefix + message)


class HelixRuntimeError(HelixError):
    """运行期错误，例如队列满且 on_full=ERROR。"""


class HelixDeadlockError(HelixRuntimeError):
    """FEL/CEL 为空但系统中仍有实体等待。"""

    def __init__(self, message: str, *, report: dict | None = None) -> None:
        self.report = report or {}
        super().__init__(message)
