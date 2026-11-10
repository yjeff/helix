"""Helix 的抽象语法树（AST）。

AST 只表达“用户写了什么”，不负责语义检查。
Compiler 负责把 AST 编译成 Model IR。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class VarDecl:
    name: str
    label: str
    low: float | None = None
    high: float | None = None
    scope: str | None = None
    size: int = 0
    line: int = 0


@dataclass(slots=True)
class ContinuousDecl:
    method: str = "RK4"
    min_step: float = 0.0
    save_step: float = 0.0
    max_step: float = 0.0
    tol: float = 1e-4
    line: int = 0


@dataclass(slots=True)
class ResourceDecl:
    name: str
    capacity: int = 1
    line: int = 0
    mode: str = "POOL"


@dataclass(slots=True)
class AttrDecl:
    name: str
    line: int = 0


@dataclass(slots=True)
class GateDecl:
    name: str
    state: str = "CLOSED"
    line: int = 0


@dataclass(slots=True)
class DetectDecl:
    name: str
    when: str
    edge: str = "RISING"
    tol: float = 0.01
    line: int = 0


@dataclass(slots=True)
class SevntDecl:
    code: int
    when: str
    name: str = ""
    action: str = ""
    line: int = 0


@dataclass(slots=True)
class NodeDecl:
    label: str | None
    kind: str
    args: dict[str, str]
    line: int
    outgoing: str | None = None


@dataclass(slots=True)
class EdgeDecl:
    source: str
    target: str
    line: int


@dataclass(slots=True)
class WhenBranch:
    condition: str
    target: str
    line: int


@dataclass(slots=True)
class IfBlock:
    label: str | None
    branches: list[WhenBranch]
    else_target: str | None
    line: int


@dataclass(slots=True)
class ParallelBlock:
    label: str | None
    paths: list[str]
    line: int


@dataclass(slots=True)
class SplitBlock:
    label: str | None
    parts: list[str]
    paths: dict[str, str]
    line: int


NetworkItem = NodeDecl | EdgeDecl | IfBlock | ParallelBlock | SplitBlock


@dataclass(slots=True)
class Program:
    version: str
    project: str = "Helix PROJECT"
    declarations: list[object] = field(default_factory=list)
    equations: list[str] = field(default_factory=list)
    network: list[NetworkItem] = field(default_factory=list)
