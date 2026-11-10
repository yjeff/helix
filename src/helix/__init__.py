"""Helix 新实现。

推荐 API：

    model = helix.Model.from_file("model.helix")
    scenario = model.initialize(initial=..., entities=...)
    result = scenario.run(start=0, end=480, seed=1)
    result.report("report.md")
"""
from .errors import (
    HelixCompileError,
    HelixDeadlockError,
    HelixError,
    HelixRuntimeError,
    HelixSyntaxError,
)
from .model import Model, NodeSpec
from .parser import parse
from .scenario import Scenario
from .runtime.state import RunResult

__version__ = "0.1.0"

__all__ = [
    "Model",
    "NodeSpec",
    "Scenario",
    "RunResult",
    "parse",
    "HelixError",
    "HelixSyntaxError",
    "HelixCompileError",
    "HelixRuntimeError",
    "HelixDeadlockError",
    "__version__",
]
