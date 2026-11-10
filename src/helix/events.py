"""事件与实体定义。

Event 是 Kernel 和 DiscreteRuntime 之间唯一的数据协议。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 事件类型使用字符串，便于 DEBUG/JSON 直接输出。
CREATE = "CREATE"
ENQUEUE = "ENQUEUE"
START_ACTIVITY = "START_ACTIVITY"
END_ACTIVITY = "END_ACTIVITY"
UNBLOCK = "UNBLOCK"
TERMINATE = "TERMINATE"
ASSIGN = "ASSIGN"
AWAIT = "AWAIT"
FREE = "FREE"
OPEN = "OPEN"
CLOSE = "CLOSE"
PREEMPT = "PREEMPT"
SELECT = "SELECT"
JOIN = "JOIN"
MERGE = "MERGE"
DETECT = "DETECT"
SEVNT = "SEVNT"


@dataclass(slots=True)
class Event:
    """一个被调度的事件。

    ``data`` 是轻量的类型化 payload，避免为每种事件建立子类。
    """

    time: float
    seq: int
    kind: str
    entity_id: int | None = None
    node: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "DISCRETE"

    def __lt__(self, other: "Event") -> bool:  # 供 heap 使用
        return (self.time, self.seq) < (other.time, other.seq)


@dataclass(slots=True)
class Entity:
    """网络中的实体。"""

    id: int
    created_at: float
    priority: float = 0.0
    preempt_priority: float = 0.0
    attrs: dict[str, float] = field(default_factory=dict)
    current_node: str | None = None
    status: str = "ACTIVE"
    origin_id: int | None = None
    part: str | None = None
    balked: bool = False
    queue_enter: float = 0.0
    wait_seq: int = 0
    members: dict[str, int] = field(default_factory=dict)

    # 服务活动相关；PREEMPT 需要保存剩余时间并使旧 END 事件失效。
    activity_label: str | None = None
    activity_end: float | None = None
    activity_token: int = 0
    remaining_time: float | None = None
    resume_activity: str | None = None
    resume_units: int = 1
