"""离散事件运行时。

本模块只实现“节点被事件触发后做什么”：
- CREATE
- QUEUE
- ACTIVITY
- IF
- TERMINATE

它不实现 FEL/CEL，也不直接推进时间；时间由 Kernel 管理。
"""
from __future__ import annotations

import math
import random
import re
from collections import deque

from ..errors import HelixRuntimeError
from ..events import (
    CREATE,
    DETECT,
    END_ACTIVITY,
    ENQUEUE,
    Entity,
    Event,
    SEVNT,
    TERMINATE,
)
from ..model import NodeSpec, _fork_branches
from ..parser import _parse_kv_args, _split_top_level
from ..continuous.expressions import Expression
from .state import (
    ActivityState,
    Observation,
    QueueStat,
    QueueState,
    ResourceStat,
    ResourceState,
    RunResult,
    SelectState,
    ServerState,
    ServiceStat,
    GateState,
    GateStat,
)


class DiscreteRuntime:
    """基础离散节点处理器。"""

    def __init__(self, kernel) -> None:
        self.kernel = kernel
        self.model = kernel.model
        self.scenario = kernel.scenario
        self.rng = random.Random(kernel.seed)

        self.entities: dict[int, Entity] = {}
        self.next_entity_id = 1
        self.wait_seq = 0
        self.queues: dict[str, QueueState] = {}
        self.activities: dict[str, ActivityState] = {}
        self.resources: dict[str, ResourceState] = {}
        self.gates: dict[str, GateState] = {}
        self.observations: dict[str, Observation] = {}
        self.variables: dict[str, float] = dict(self.scenario.initial)
        self.wait_events: dict[str, list[tuple[str, int]]] = {}
        self.stat_start = self.kernel.start

        self.create_counts: dict[str, int] = {}
        self.blocked_pending: dict[str, list[tuple[int, str]]] = {}
        self.join_groups: dict[str, list[int]] = {}
        self.selects: dict[str, SelectState] = {}

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        """建立运行态，并调度初始 CREATE 和初始实体。"""
        for node in self.model.nodes.values():
            if node.kind == "QUEUE":
                capacity = self._int_arg(node, "capacity", 0)
                order = node.args.get("order", "FIFO").upper()
                on_full = node.args.get("on_full", "ERROR").strip()
                self.queues[node.label] = QueueState(
                    node.label, capacity, order, on_full)
            elif node.kind == "ACTIVITY":
                servers = self._int_arg(node, "servers", 1)
                if servers < 1:
                    raise HelixRuntimeError(
                        f"{node.label}: servers 必须 >= 1")
                self.activities[node.label] = ActivityState(
                    node.label,
                    [ServerState(index=i,
                                 idle_since=self.kernel.now)
                     for i in range(1, servers + 1)],
                )
                self.blocked_pending[node.label] = []
            elif node.kind == "SELECT":
                queues = self._list_arg(node, "queues")
                servers = self._list_arg(node, "servers")
                self.selects[node.label] = SelectState(
                    label=node.label,
                    queues=queues,
                    servers=servers,
                    queue_rule=node.args.get("queue_rule", "ASM").upper(),
                    server_rule=node.args.get("server_rule", "LIT").upper(),
                    save_rule=node.args.get("save", "FIRST").upper(),
                )

        # 初始资源/门状态。
        for spec in self.model.resources.values():
            self.resources[spec.name] = ResourceState(
                name=spec.name,
                capacity=spec.capacity,
                available=spec.capacity,
                mode=spec.mode,
            )
        for spec in self.model.gates.values():
            self.gates[spec.name] = GateState(
                name=spec.name, state=spec.state)

        # 初始实体可按 QUEUE 标签入队，也可直接进入指定网络节点。
        for target_label, items in self.scenario.entities.items():
            for item in items:
                attrs = {
                    str(key): float(value)
                    for key, value in item.items()
                    if str(key).lower() != "priority"
                }
                priority = float(item.get("priority", 0.0))
                entity = self._new_entity(priority=priority, attrs=attrs)
                if target_label in self.queues:
                    self._enqueue(self.queues[target_label], entity)
                else:
                    self._route(entity, target_label)

        # CREATE 节点按 first 调度第一次创建。
        for node in self.model.nodes.values():
            if node.kind != "CREATE":
                continue
            self.create_counts[node.label] = 0
            first = self._float_arg(node, "first", 0.0)
            until = node.args.get("until")
            count = node.args.get("count")
            if until is not None and count is not None:
                raise HelixRuntimeError(
                    f"{node.label}: count 和 until 不能同时使用")
            first_time = max(self.kernel.now,
                             self.kernel.now + first)
            if until is not None and first_time > float(until) + 1e-12:
                continue
            self.kernel.schedule(Event(
                time=first_time,
                seq=0, kind=CREATE, node=node.label))

    # ------------------------------------------------------------------
    # 统计推进
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """返回动画/调试用的轻量运行状态快照。"""
        queue_members = {
            entity.id for queue in self.queues.values()
            for entity in queue.items
        }
        busy_members = {
            server.entity_id for activity in self.activities.values()
            for server in activity.servers
            if server.status == "BUSY" and server.entity_id is not None
        }
        waiting_members = {
            entity_id for activity in self.activities.values()
            for entity_id in activity.waiting
        }
        entities = []
        for entity in self.entities.values():
            if entity.status in ("TERMINATED", "BALKED"):
                continue
            status = entity.status
            if entity.id in busy_members:
                status = "BUSY"
            elif entity.id in queue_members:
                status = "QUEUED"
            elif entity.id in waiting_members:
                status = "WAITING"
            entities.append({
                "id": entity.id,
                "node": entity.current_node,
                "status": status,
                "priority": entity.priority,
                "attrs": dict(entity.attrs),
            })
        queues = [
            {
                "label": queue.label,
                "length": len(queue.items),
                "capacity": queue.capacity,
            }
            for queue in self.queues.values()
        ]
        activities = [
            {
                "label": activity.label,
                "active": activity.active,
                "blocked": activity.blocked,
                "waiting": len(activity.waiting),
                "servers": len(activity.servers),
                "max_active": activity.max_active,
                "completed": activity.completed,
            }
            for activity in self.activities.values()
        ]
        resources = [
            {
                "name": resource.name,
                "held": self._resource_used(resource),
                "available": resource.available,
                "capacity": resource.capacity,
                "waiting": len(resource.waiters),
            }
            for resource in self.resources.values()
        ]
        return {
            "entities": entities,
            "queues": queues,
            "activities": activities,
            "resources": resources,
        }

    def reset_statistics(self, now: float) -> None:
        """模拟旧版 MONTR,CLEAR：清空累计统计，保留当前状态。"""
        self.stat_start = now
        self.observations.clear()
        for queue in self.queues.values():
            queue.area = 0.0
            queue.area2 = 0.0
            queue.max_length = len(queue.items)
            queue.wait_sum = 0.0
            queue.wait_count = 0
            queue.wait_max = 0.0
            queue.balk_count = 0
        for activity in self.activities.values():
            activity.area = 0.0
            activity.area2 = 0.0
            activity.blocked_area = 0.0
            activity.max_active = activity.active
            activity.completed = 0
            for server in activity.servers:
                server.max_idle = 0.0
                server.max_busy = 0.0
                server.max_idle_server = 0
                server.max_busy_server = 0
                server.busy_total = 0.0
        for resource in self.resources.values():
            resource.area = 0.0
            resource.area2 = 0.0
            resource.max_held = self._resource_used(resource)
            resource.wait_count = 0
            resource.wait_sum = 0.0
            resource.wait_max = 0.0
            for entity_id in resource.waiters:
                resource.wait_enter[entity_id] = now
        for gate in self.gates.values():
            gate.wait_count = 0

    def advance(self, target: float, start: float | None = None) -> None:
        """推进队列/活动/服务台的时间加权统计。

        只由 Kernel 在时钟真正前进时调用；CEL 内不会重复累计。
        start 是统计区间起点，默认 kernel.now（纯离散模型）。
        连续模型必须先积分再调用，因此显式传入旧 now。
        """
        now = self.kernel.now if start is None else start
        dt = max(0.0, target - now)
        for queue in self.queues.values():
            length = len(queue.items)
            queue.area += length * dt
            queue.area2 += length * length * dt
        for activity in self.activities.values():
            active = activity.active
            blocked = activity.blocked
            activity.area += active * dt
            activity.area2 += active * active * dt
            activity.blocked_area += blocked * dt
            for server in activity.servers:
                self._update_server_interval(server, target)
        for resource in self.resources.values():
            held = self._resource_used(resource)
            resource.area += held * dt
            resource.area2 += held * held * dt
            resource.max_held = max(resource.max_held, held)

    @staticmethod
    def _update_server_interval(server: ServerState, now: float) -> None:
        """更新最大 idle/busy 段；不改变状态。

        busy 段是“连续忙碌期”，不是单次服务时长：
        - 服务结束但同一时刻立刻接上下一个实体时，busy_since 保持不变；
        - 真正出现空闲间隔后，才在 idle_since 处关闭 busy 段。
        """
        if server.status == "IDLE":
            idle_duration = max(0.0, now - server.idle_since)
            if idle_duration > server.max_idle:
                server.max_idle = idle_duration
                server.max_idle_server = server.index
            if (server.busy_since is not None
                    and now > server.idle_since + 1e-12):
                busy_duration = max(0.0, server.idle_since - server.busy_since)
                if busy_duration > server.max_busy:
                    server.max_busy = busy_duration
                    server.max_busy_server = server.index
                server.busy_since = None
        elif server.status == "BUSY":
            duration = max(0.0, now - server.busy_since)
            if duration > server.max_busy:
                server.max_busy = duration
                server.max_busy_server = server.index

    # ------------------------------------------------------------------
    # 事件分发
    # ------------------------------------------------------------------
    def fire_event(self, name: str) -> None:
        """按事件名释放 ACTIVITY(until=...)。"""
        self._fire_wait_events(name)

    def _resolve_event_name(self, raw: str, entity: Entity,
                            context: dict[str, float] | None = None) -> str:
        """解析事件名；NAME[expr] 会按当前实体/全局上下文求下标。"""
        name = raw.strip().strip("\"'")
        if name.endswith("]") and "[" in name:
            base, index_text = name[:-1].split("[", 1)
            if context is None:
                context = self._expression_context(entity)
            index = int(Expression(
                index_text, label=base).evaluate(context))
            return f"{base}[{index}]"
        return name

    def handle(self, event: Event) -> None:
        if event.kind == CREATE:
            self._on_create(event)
        elif event.kind == END_ACTIVITY:
            self._on_end_activity(event)
        elif event.kind == DETECT:
            self._on_detect(event)
        elif event.kind == SEVNT:
            name = str(event.data.get("name", "") or "").strip()
            if name:
                self._fire_wait_events(name)
            action = str(event.data.get("action", "") or "").strip()
            if action:
                signal = self._new_entity()
                signal.balked = True
                signal.status = "SEVNT_SIGNAL"
                self._route(signal, action)
        else:
            raise HelixRuntimeError(f"暂不支持事件: {event.kind}")

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------
    def _on_create(self, event: Event) -> None:
        node = self.model.node(event.node)
        control = {"interval", "first", "count", "priority", "until"}
        attr_specs: dict[str, list[str]] = {}
        for key, value in node.args.items():
            if key.lower() in control:
                continue
            text = value.strip()
            if text.startswith("[") and text.endswith("]"):
                attr_specs[key] = _split_top_level(text[1:-1])

        count = self.create_counts.get(node.label, 0)
        max_count = node.args.get("count")
        if max_count is not None and count >= int(max_count):
            return

        interval = node.args.get("interval")
        # 无 interval 时 count 表示一次批量创建的实体数；属性列表也走这里。
        if not interval and (attr_specs or max_count is not None):
            limit = int(max_count) if max_count is not None else len(
                next(iter(attr_specs.values())))
            while count < limit:
                count += 1
                priority = self._number(node.args.get("priority", "0"))
                entity = self._new_entity(priority=priority)
                if attr_specs:
                    self._apply_create_attrs(node, entity, count, attr_specs)
                self._route(entity, node.outgoing[0]
                            if node.outgoing else None)
            self.create_counts[node.label] = count
            return

        count += 1
        self.create_counts[node.label] = count
        priority = self._number(node.args.get("priority", "0"))
        entity = self._new_entity(priority=priority)
        if attr_specs:
            self._apply_create_attrs(node, entity, count, attr_specs)
        self._route(entity, node.outgoing[0] if node.outgoing else None)

        if not interval:
            return
        if max_count is not None and count >= int(max_count):
            return

        next_time = self.kernel.now + self._sample(interval)
        until = node.args.get("until")
        if until is not None and next_time > float(until) + 1e-12:
            return
        self.kernel.schedule(Event(
            time=next_time, seq=0, kind=CREATE, node=node.label))

    def _apply_create_attrs(self, node: NodeSpec, entity: Entity,
                            index: int,
                            specs: dict[str, list[str]]) -> None:
        """把 CREATE 属性列表的第 index 个值写入实体。"""
        context = self._expression_context(entity)
        for name, values in specs.items():
            if index < 1 or index > len(values):
                raise HelixRuntimeError(
                    f"{node.label}: CREATE 属性 {name} 列表长度不足")
            raw = values[index - 1].strip()
            if raw.upper().startswith(
                    ("UNFRM(", "RNORM(", "EXPON(", "EXP(", "ERLNG(")):
                value = self._sample(raw)
            else:
                value = Expression(
                    raw, label=f"{node.label}:{name}").evaluate(context)
            entity.attrs[name] = value
            context[name] = value

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------
    def _route(self, entity: Entity, target: str | None) -> None:
        if target is None:
            raise HelixRuntimeError(
                f"实体 {entity.id} 没有后继节点")
        node = self.model.node(target)
        entity.current_node = target

        if node.kind == "QUEUE":
            self._enqueue(self.queues[target], entity)
        elif node.kind == "ACTIVITY":
            self._start_activity(self.activities[target], entity)
        elif node.kind == "ASSIGN":
            self._assign(node, entity)
        elif node.kind == "EVENT":
            self._event(node, entity)
        elif node.kind == "OBSERVE":
            self._observe(node, entity)
        elif node.kind == "SCAN":
            self._scan(node, entity)
        elif node.kind == "IF":
            self._enter_if(node, entity)
        elif node.kind == "PARALLEL":
            self._enter_parallel(node, entity)
        elif node.kind == "SPLIT":
            self._enter_split(node, entity)
        elif node.kind == "FORK":
            self._enter_fork(node, entity)
        elif node.kind == "JOIN":
            self._enter_join(node, entity)
        elif node.kind == "MERGE":
            self._enter_merge(node, entity)
        elif node.kind == "SELECT":
            self._try_select(node.label)
        elif node.kind == "AWAIT":
            self._await(node, entity)
        elif node.kind == "FREE":
            self._free(node, entity)
        elif node.kind == "ALTER":
            self._alter(node, entity)
            self._route(entity, node.outgoing[0]
                        if node.outgoing else None)
        elif node.kind == "PREEMPT":
            self._preempt(node, entity)
        elif node.kind == "OPEN":
            self._open_gate(node)
        elif node.kind == "CLOSE":
            self._close_gate(node)
        elif node.kind == "TERMINATE":
            self._terminate(entity)
        else:
            raise HelixRuntimeError(
                f"{target}: 暂不支持节点类型 {node.kind}")

    def _terminate(self, entity: Entity) -> None:
        entity.status = "BALKED" if entity.balked else "TERMINATED"
        if not entity.balked:
            observation = self.observations.setdefault(
                "TIME IN SYSTEM", Observation("TIME IN SYSTEM"))
            observation.add(self.kernel.now - entity.created_at)

    # ------------------------------------------------------------------
    # QUEUE
    # ------------------------------------------------------------------
    def _enqueue(self, queue: QueueState, entity: Entity) -> None:
        """把实体放入队列，并决定“满队列”行为。

        这里的满队列处理只针对“新到达实体”：
        - BALK：实体离开网络；
        - BLOCK：活动已完成但下游无空间，进入 blocked；
        - ERROR：模型配置错误或容量不足。
        """
        if queue.capacity and len(queue.items) >= queue.capacity:
            raw_action = queue.on_full.strip()
            action = raw_action.upper()
            if action.startswith("BALK(") and action.endswith(")"):
                # BALK 实体不进入队列，也不记录系统时间。
                target = raw_action[5:-1].strip()
                entity.balked = True
                queue.balk_count += 1
                self._route(entity, target)
                return
            if action == "BLOCK":
                # 从 CREATE 直接到达满 BLOCK 队列时没有上游活动，
                # 无法表示“谁被阻塞”，因此视为模型错误。
                raise HelixRuntimeError(
                    f"{queue.label}: 没有上游活动可阻塞")
            raise HelixRuntimeError(
                f"{queue.label}: 队列已满，on_full={queue.on_full}")

        # queue_enter 用于 QUEUE.WAIT 观测；balk 实体不会走到这里。
        entity.queue_enter = self.kernel.now
        self._insert_queue(queue, entity)
        queue.max_length = max(queue.max_length, len(queue.items))

        # 入队后立即尝试启动后继活动；如果该队列没有后继活动，
        # 说明它只是缓冲节点，不能自动消费实体。
        self._try_service(queue.label)
        self._release_blocked()

    def _insert_queue(self, queue: QueueState, entity: Entity) -> None:
        """按 queue.order 插入实体。

        第一版支持 FIFO/LIFO/PRIORITY/HIGH/LOW；排序只在入队时进行，
        不从队列中途重新排序，避免实体位置在等待期间跳动。
        """
        order = queue.order.upper()
        if order == "FIFO":
            queue.items.append(entity)
            return
        if order == "LIFO":
            queue.items.appendleft(entity)
            return
        if order == "PRIORITY":
            key = lambda item: item.priority
        elif order == "LOW_PRIORITY":
            key = lambda item: -item.priority
        elif order.startswith("HIGH(") and order.endswith(")"):
            attr = order[5:-1].strip()
            key = lambda item: item.attrs.get(attr, 0.0)
        elif order.startswith("LOW(") and order.endswith(")"):
            attr = order[4:-1].strip()
            key = lambda item: -item.attrs.get(attr, 0.0)
        else:
            raise HelixRuntimeError(
                f"{queue.label}: 未知 order={queue.order}")

        items = list(queue.items)
        items.append(entity)
        items.sort(key=key, reverse=True)
        queue.items = deque(items)

    def _try_service(self, queue_label: str) -> None:
        """队列有实体且后继活动有空闲服务台时启动服务。

        注意：QUEUE 的 wait 统计只统计真正被服务台取走的实体；
        被 BALK 的实体 wait_count 不应增加。
        """
        queue = self.queues[queue_label]
        node = self.model.nodes[queue_label]
        if not node.outgoing:
            if queue.items:
                raise HelixRuntimeError(
                    f"{queue_label}: 没有后继 ACTIVITY")
            return
        target = self.model.node(node.outgoing[0])
        if target.kind == "SELECT":
            # SELECT 自己从 queues 取实体；QUEUE 不直接弹出。
            self._try_select(target.label)
            return
        if target.kind != "ACTIVITY":
            # 其他非 ACTIVITY 节点由各自运行时处理。
            if queue.items:
                self._route(queue.items.popleft(), target.label)
            return

        activity = self.activities[target.label]
        while queue.items:
            server = activity.idle_server()
            if server is None:
                break
            entity = queue.items.popleft()
            wait = self.kernel.now - entity.queue_enter
            queue.wait_sum += wait
            queue.wait_count += 1
            queue.wait_max = max(queue.wait_max, wait)
            self._start_activity(activity, entity, server=server)

    def _release_blocked(self) -> None:
        """下游队列出现空间后，完成被阻塞的活动。

        注意：被阻塞实体要去的是“完成活动的后继队列”，不是活动
        自己服务的输入队列。因此 pending 中必须保存 target。
        """
        for activity in self.activities.values():
            pending = self.blocked_pending[activity.label]
            if not pending:
                continue

            released = 0
            for entity_id, target in list(pending):
                queue = self.queues.get(target)
                if queue is None:
                    continue
                if queue.capacity and len(queue.items) >= queue.capacity:
                    continue
                server = next((s for s in activity.servers
                               if s.status == "BLOCKED"
                               and s.entity_id == entity_id), None)
                if server is None:
                    continue

                pending.remove((entity_id, target))
                entity = self.entities[entity_id]
                activity.completed += 1
                server.status = "IDLE"
                server.entity_id = None
                server.idle_since = self.kernel.now
                self._enqueue(queue, entity)
                released += 1

            if released:
                # 队列腾出空间后可能还能启动服务。
                self._try_service_activity(activity.label)

    def _queue_for_activity(self, activity_label: str) -> str | None:
        for label, queue in self.queues.items():
            node = self.model.nodes[label]
            if node.outgoing and node.outgoing[0] == activity_label:
                return label
        return None

    # ------------------------------------------------------------------
    # ACTIVITY
    # ------------------------------------------------------------------
    def _start_activity(self, activity: ActivityState, entity: Entity,
                        *, server: ServerState | None = None,
                        duration: float | None = None) -> None:
        if server is None:
            server = activity.idle_server()
        if server is None:
            # 没有队列直接进入 ACTIVITY 时，实体在活动前等待。
            activity.waiting.append(entity.id)
            return

        self._update_server_interval(server, self.kernel.now)
        server.status = "BUSY"
        server.entity_id = entity.id
        activity.max_active = max(activity.max_active, activity.active)
        server.start_time = self.kernel.now
        if server.busy_since is None:
            server.busy_since = self.kernel.now

        node = self.model.node(activity.label)
        duration_spec = node.args.get("duration", "0").strip()
        upper_duration = duration_spec.upper()
        if upper_duration.startswith("STOPA(") or upper_duration.startswith("REL("):
            raise HelixRuntimeError(
                f"{node.label}: REL/STOPA 已统一为 ACTIVITY(until=事件名)")
        until = node.args.get("until")
        if until:
            # 统一事件等待：DETECT 节点标签和 SEVNT.name 都走这里。
            waiting_for = self._resolve_event_name(until, entity)
            if waiting_for.upper().startswith("REL("):
                raise HelixRuntimeError(
                    f"{node.label}: 请写成 ACTIVITY(until={waiting_for[4:-1]})")
            entity.activity_token += 1
            entity.activity_label = activity.label
            entity.activity_end = None
            entity.remaining_time = None
            self.wait_events.setdefault(waiting_for, []).append(
                (activity.label, entity.id))
            return

        if duration is None:
            duration = self._sample(node.args.get("duration", "0"), entity)

        # 每次开始服务都生成新 token；PREEMPT 时 token++，旧 END
        # 事件到达后会被识别为过期事件而忽略。
        entity.activity_token += 1
        entity.activity_label = activity.label
        entity.activity_end = self.kernel.now + duration
        entity.remaining_time = None
        entity.resume_activity = None

        self.kernel.schedule(Event(
            time=self.kernel.now + duration,
            seq=0, kind=END_ACTIVITY,
            entity_id=entity.id, node=activity.label,
            data={"duration": duration, "token": entity.activity_token}))

    def _on_end_activity(self, event: Event) -> None:
        """服务完成：释放服务台，再决定路由/阻塞。

        这里故意先更新 busy 段，再把 server 置为 IDLE：
        - F9 的 max busy 只统计真正 BUSY 的时间；
        - 如果后继队列满，server 进入 BLOCKED，不把阻塞时间算成 BUSY；
        - 如果后继队列可接收，立刻尝试同一活动下一实体。
        """
        activity = self.activities[event.node]
        entity = self.entities[event.entity_id]
        token = event.data.get("token")
        if token is not None and token != entity.activity_token:
            # 该实体已被 PREEMPT，旧的 END 事件失效。
            return
        server = next((s for s in activity.servers
                       if s.entity_id == entity.id
                       and s.status == "BUSY"), None)
        if server is None:
            raise HelixRuntimeError(
                f"{activity.label}: 找不到实体 {entity.id} 的服务台")

        self._update_server_interval(server, self.kernel.now)
        server.busy_total += max(0.0, self.kernel.now - server.busy_since)
        node = self.model.node(activity.label)
        target = node.outgoing[0] if node.outgoing else None
        if target is None:
            raise HelixRuntimeError(f"{activity.label}: 没有后继节点")

        # 先结束 BUSY 段；下面若发现需要 BLOCK，再切到 BLOCKED。
        server.status = "IDLE"
        server.entity_id = None
        server.idle_since = self.kernel.now
        entity.activity_label = None
        entity.activity_end = None
        entity.remaining_time = None

        next_node = self.model.node(target)
        if next_node.kind == "QUEUE":
            queue = self.queues[target]
            full = bool(queue.capacity
                        and len(queue.items) >= queue.capacity)
            action = queue.on_full.upper()
            if full and action == "BLOCK":
                # BLOCKED 不是 BUSY；结束当前连续忙碌段。
                server.busy_since = None
                server.status = "BLOCKED"
                server.entity_id = entity.id
                self.blocked_pending[activity.label].append(
                    (entity.id, target))
                return
            if full and action.startswith("BALK("):
                activity.completed += 1
                entity.balked = True
                queue.balk_count += 1
                self._route(entity, action[5:-1].strip())
                self._try_service_activity(activity.label)
                self._release_waiting(activity)
                self._try_select_for_activity(activity.label)
                return

        activity.completed += 1
        self._route(entity, target)
        self._try_service_activity(activity.label)
        self._release_waiting(activity)
        self._try_select_for_activity(activity.label)
        self._release_blocked()

    def _release_waiting(self, activity: ActivityState) -> None:
        """直接进入 ACTIVITY、没有 QUEUE 缓冲的实体。"""
        while activity.waiting:
            server = activity.idle_server()
            if server is None:
                break
            entity = self.entities[activity.waiting.popleft()]
            self._start_activity(activity, entity, server=server)

    def _try_service_activity(self, activity_label: str) -> None:
        queue_label = self._queue_for_activity(activity_label)
        if queue_label:
            self._try_service(queue_label)

    # ------------------------------------------------------------------
    # DETECT / 事件等待
    # ------------------------------------------------------------------
    def _on_detect(self, event: Event) -> None:
        """DETECT 节点触发：先释放事件等待，再发出信号实体。"""
        node = self.model.node(event.node)
        self._fire_wait_events(node.label)
        signal = self._new_entity()
        signal.balked = True
        signal.status = "DETECT_SIGNAL"
        self._route(signal, node.outgoing[0] if node.outgoing else None)

    def _fire_wait_events(self, name: str) -> None:
        """结束所有等待指定事件名的活动。"""
        waiters = self.wait_events.pop(name, [])
        for activity_label, entity_id in waiters:
            entity = self.entities.get(entity_id)
            if entity is None:
                continue
            activity = self.activities.get(activity_label)
            if activity is None:
                continue
            self._on_end_activity(Event(
                time=self.kernel.now,
                seq=0,
                kind=END_ACTIVITY,
                entity_id=entity_id,
                node=activity_label,
                data={"token": entity.activity_token},
            ))

    # ------------------------------------------------------------------
    # ASSIGN
    # ------------------------------------------------------------------
    def _assign(self, node: NodeSpec, entity: Entity) -> None:
        """执行 ``ASSIGN(NAME=expr, ...)``。

        名称必须在 VAR 中声明：
        - scope=ENTITY 写入当前实体；
        - scope=GLOBAL 写入连续状态/离散共享变量。
        """
        if "set" in node.args:
            raise HelixRuntimeError(
                f"{node.label}: 旧语法 ASSIGN(set=...) 已移除，"
                "请写成 ASSIGN(NAME=expr, ...)")
        context = self._expression_context(entity)
        self._assign_args(node.args, entity, node.label, context)
        self._route(entity, node.outgoing[0] if node.outgoing else None)

    def _assign_args(self, args: dict[str, str], entity: Entity,
                     label: str,
                     context: dict[str, float] | None = None) -> None:
        if context is None:
            context = self._expression_context(entity)
        for name, expression in args.items():
            upper = expression.strip().upper()
            if upper.startswith(("UNFRM(", "RNORM(", "EXPON(",
                                 "EXP(", "ERLNG(")):
                value = self._sample(expression)
            else:
                value = Expression(
                    expression, label=f"{label}:{name}").evaluate(context)
            target = name
            if "[" in target and target.endswith("]"):
                base, index_text = target[:-1].split("[", 1)
                spec = self.model.variables.get(base)
                if spec is None or not spec.size:
                    raise HelixRuntimeError(
                        f"{label}: 未声明数组: {base}")
                index = int(Expression(
                    index_text, label=f"{label}:{base}").evaluate(
                        context))
                if index < 1 or index > spec.size:
                    raise HelixRuntimeError(
                        f"{label}: 数组下标越界: {target}")
                target = f"{base}[{index}]"
                spec = self.model.variables[base]
            else:
                spec = self.model.variables.get(target)
            if spec is None:
                raise HelixRuntimeError(
                    f"{label}: 未声明变量: {name}")
            if spec.scope == "GLOBAL":
                self.variables[target] = value
                if hasattr(self.kernel.continuous, "state") and \
                        target in self.kernel.continuous.state:
                    self.kernel.continuous.state[target] = value
            else:
                entity.attrs[target] = value
            context[target] = value

    # ------------------------------------------------------------------
    # OBSERVE
    # ------------------------------------------------------------------
    def _observe(self, node: NodeSpec, entity: Entity,
                 context: dict[str, float] | None = None,
                 route: bool = True) -> None:
        """记录一次显式观测；不改变实体状态。"""
        name = node.args.get("name", "").strip().strip("\"'")
        if not name:
            raise HelixRuntimeError(f"{node.label}: OBSERVE 需要 name")
        if context is None:
            context = self._expression_context(entity)
        value = Expression(
            node.args.get("value", "0"),
            label=f"{node.label}:{name}").evaluate(context)
        observation = self.observations.setdefault(name, Observation(name))
        observation.add(value)
        if route:
            self._route(entity, node.outgoing[0]
                        if node.outgoing else None)

    # ------------------------------------------------------------------
    # SCAN
    # ------------------------------------------------------------------
    def _scan(self, node: NodeSpec, entity: Entity) -> None:
        """按范围扫描数组，匹配时执行 ASSIGN/EVENT 动作。"""
        variable = node.args.get("var", "").strip()
        where = node.args.get("where", "").strip()
        do = node.args.get("do", "").strip()
        if not variable or not where or not do:
            raise HelixRuntimeError(
                f"{node.label}: SCAN 需要 var/where/do")
        actions = [line.strip() for line in do.splitlines() if line.strip()]
        context = self._expression_context(entity)
        start = int(float(node.args.get("start", "1")))
        end = int(float(node.args.get("end", "0")))
        stop_first = node.args.get("stop", "").upper() == "FIRST"
        condition = Expression(where, label=f"{node.label}:WHERE")
        for index in range(start, end + 1):
            context[variable] = float(index)
            if condition.evaluate(context) == 0.0:
                continue
            for action in actions:
                upper = action.upper()
                if upper.startswith("ASSIGN(") and action.endswith(")"):
                    args = _parse_kv_args(
                        action[7:-1], preserve_keys=True)
                    self._assign_args(
                        args, entity, f"{node.label}:DO", context)
                elif upper.startswith("EVENT(") and action.endswith(")"):
                    args = _parse_kv_args(action[6:-1])
                    raw_name = args.get("name", "").strip()
                    self.fire_event(self._resolve_event_name(
                        raw_name, entity, context))
                elif upper.startswith("OBSERVE(") and action.endswith(")"):
                    inner = action[8:-1]
                    if "=" in inner:
                        args = _parse_kv_args(inner)
                    else:
                        parts = _split_top_level(inner)
                        if len(parts) != 2:
                            raise HelixRuntimeError(
                                f"{node.label}: OBSERVE 简写需要 name, value")
                        args = {"name": parts[0], "value": parts[1]}
                    spec = NodeSpec(
                        f"{node.label}:OBS", "OBSERVE", args, 0, None)
                    self._observe(spec, entity, context, route=False)
                else:
                    raise HelixRuntimeError(
                        f"{node.label}: SCAN DO 只支持 ASSIGN/EVENT")
            if stop_first:
                break
        self._route(entity, node.outgoing[0] if node.outgoing else None)

    # ------------------------------------------------------------------
    # EVENT
    # ------------------------------------------------------------------
    def _event(self, node: NodeSpec, entity: Entity) -> None:
        """触发命名事件，并可把当前实体路由到动作节点。"""
        name = self._resolve_event_name(
            node.args.get("name", "").strip(), entity)
        if not name:
            raise HelixRuntimeError(f"{node.label}: EVENT 需要 name")
        self.fire_event(name)
        action = node.args.get("action", "").strip()
        target = action or (node.outgoing[0] if node.outgoing else None)
        self._route(entity, target)

    def _expression_context(self, entity: Entity) -> dict[str, float]:
        context = dict(self.scenario.constants)
        context.update(self.variables)
        if hasattr(self.kernel.continuous, "state"):
            context.update(self.kernel.continuous.state)
        context.update(entity.attrs)
        context["TNOW"] = self.kernel.now
        context["PRIORITY"] = entity.priority
        for resource in self.resources.values():
            name = resource.name.upper()
            held = self._resource_used(resource)
            context[f"RESOURCE.{name}.CAPACITY"] = float(resource.capacity)
            context[f"RESOURCE.{name}.HELD"] = float(held)
            context[f"RESOURCE.{name}.AVAILABLE"] = float(resource.available)
        return context

    # ------------------------------------------------------------------
    # RESOURCE / GATE
    # ------------------------------------------------------------------
    def _resource_used(self, resource: ResourceState) -> int:
        if resource.mode == "RESTOCK":
            return max(0, resource.capacity - resource.available)
        return sum(resource.held_by.values())

    def _await(self, node: NodeSpec, entity: Entity) -> None:
        """申请资源或等待 GATE。

        AWAIT 是原子申请：资源不足时整个实体等待，不做部分分配。
        等待顺序由 priority 决定，priority 相同按进入等待的 seq。
        """
        gate_name = node.args.get("gate")
        if gate_name:
            gate = self.gates.get(gate_name)
            if gate is None:
                raise HelixRuntimeError(
                    f"{node.label}: 未定义 GATE {gate_name}")
            if gate.state == "OPEN":
                self._route(entity, node.outgoing[0] if node.outgoing else None)
            else:
                entity.status = "WAITING_GATE"
                entity.wait_seq = self._next_wait_seq()
                gate.waiters.append(entity.id)
                gate.wait_count += 1
            return

        resource_name = node.args.get("resource")
        if not resource_name:
            raise HelixRuntimeError(f"{node.label}: AWAIT 缺少 resource/gate")
        resource = self.resources.get(resource_name)
        if resource is None:
            raise HelixRuntimeError(
                f"{node.label}: 未定义 RESOURCE {resource_name}")
        units = int(Expression(
            node.args.get("units", "1"),
            label=f"{node.label}:units").evaluate(
                self._expression_context(entity)))
        if units < 1:
            raise HelixRuntimeError(f"{node.label}: units 必须 >= 1")

        if resource.available >= units:
            if resource.mode == "RESTOCK":
                self._allocate_stock(resource, entity, units)
            else:
                self._allocate(resource, entity, units)
            self._route(entity, node.outgoing[0] if node.outgoing else None)
        else:
            entity.status = "WAITING_RESOURCE"
            entity.wait_seq = self._next_wait_seq()
            resource.waiters.append(entity.id)
            resource.wait_count += 1
            resource.wait_enter[entity.id] = self.kernel.now

    def _free(self, node: NodeSpec, entity: Entity) -> None:
        """释放资源；随后唤醒能获得资源的最高优先级等待者。"""
        resource_name = node.args.get("resource")
        resource = self.resources.get(resource_name)
        if resource is None:
            raise HelixRuntimeError(
                f"{node.label}: 未定义 RESOURCE {resource_name}")
        units = int(Expression(
            node.args.get("units", "1"),
            label=f"{node.label}:units").evaluate(
                self._expression_context(entity)))
        if resource.mode == "RESTOCK":
            release = min(units, resource.capacity - resource.available)
            if release > 0:
                resource.available += release
            self._route(entity, node.outgoing[0] if node.outgoing else None)
            self._wake_resource(resource)
            return
        held = resource.held_by.get(entity.id, 0)
        release = min(units, held)
        if release:
            resource.held_by[entity.id] = held - release
            if resource.held_by[entity.id] == 0:
                del resource.held_by[entity.id]
            resource.available += release
        self._route(entity, node.outgoing[0] if node.outgoing else None)
        self._wake_resource(resource)

    def _allocate(self, resource: ResourceState, entity: Entity,
                  units: int) -> None:
        entered = resource.wait_enter.pop(entity.id, None)
        if entered is not None:
            wait = max(0.0, self.kernel.now - entered)
            resource.wait_sum += wait
            resource.wait_max = max(resource.wait_max, wait)
        resource.available -= units
        resource.held_by[entity.id] = resource.held_by.get(entity.id, 0) + units

    def _allocate_stock(self, resource: ResourceState, entity: Entity,
                        units: int) -> None:
        entered = resource.wait_enter.pop(entity.id, None)
        if entered is not None:
            wait = max(0.0, self.kernel.now - entered)
            resource.wait_sum += wait
            resource.wait_max = max(resource.wait_max, wait)
        resource.available -= units

    def _wake_resource(self, resource: ResourceState) -> None:
        """按 priority 降序扫描等待者，唤醒第一个能完整满足的实体。"""
        if not resource.waiters:
            return
        ordered = sorted(
            (self.entities[eid] for eid in resource.waiters),
            key=lambda ent: (-ent.priority, ent.wait_seq))
        if resource.mode == "RESTOCK":
            for entity in ordered:
                node = self.model.node(entity.current_node)
                units = int(Expression(
                    node.args.get("units", "1"),
                    label=f"{node.label}:units").evaluate(
                        self._expression_context(entity)))
                if resource.available < units:
                    continue
                resource.waiters.remove(entity.id)
                self._allocate_stock(resource, entity, units)
                self._route(entity, node.outgoing[0] if node.outgoing else None)
                self._wake_resource(resource)
                return
            return
        for entity in ordered:
            if entity.status == "PREEMPTED" and entity.resume_activity:
                units = entity.resume_units
                activity = self.activities.get(entity.resume_activity)
                if activity is None or activity.idle_server() is None:
                    continue
                if resource.available < units:
                    continue
                resource.waiters.remove(entity.id)
                self._allocate(resource, entity, units)
                entity.status = "ACTIVE"
                self._start_activity(
                    activity, entity,
                    server=activity.idle_server(),
                    duration=entity.remaining_time or 0.0)
                self._wake_resource(resource)
                return

            wait_node = self.model.node(entity.current_node)
            units = int(Expression(
                wait_node.args.get("units", "1"),
                label=f"{wait_node.label}:units").evaluate(
                    self._expression_context(entity)))
            if resource.available < units:
                continue
            resource.waiters.remove(entity.id)
            self._allocate(resource, entity, units)
            node = self.model.node(entity.current_node)
            self._route(entity, node.outgoing[0] if node.outgoing else None)
            # 继续尝试下一个等待者，可能还有足够单位。
            self._wake_resource(resource)
            return

    def _alter(self, node: NodeSpec, entity: Entity) -> None:
        resource_name = node.args.get("resource")
        if resource_name:
            resource = self.resources.get(resource_name)
            if resource is None:
                raise HelixRuntimeError(
                    f"{node.label}: 未定义 RESOURCE {resource_name}")
            raw_capacity = node.args.get("capacity", "0")
            capacity = int(Expression(
                raw_capacity, label=f"{node.label}:capacity").evaluate(
                    self._expression_context(entity)))
            if capacity < 1:
                raise HelixRuntimeError(f"{node.label}: capacity 必须 >= 1")
            if resource.mode == "RESTOCK":
                delta = capacity - resource.capacity
                resource.capacity = capacity
                resource.available = max(
                    0, min(capacity, resource.available + delta))
            else:
                resource.capacity = capacity
                held = sum(resource.held_by.values())
                resource.available = max(0, capacity - held)
            self._wake_resource(resource)
            return

        create_name = node.args.get("create")
        if create_name:
            target = self.model.nodes.get(create_name)
            if target is None or target.kind != "CREATE":
                raise HelixRuntimeError(
                    f"{node.label}: CREATE 节点不存在: {create_name}")
            interval = node.args.get("interval")
            if not interval:
                raise HelixRuntimeError(
                    f"{node.label}: ALTER create 需要 interval")
            # 只修改后续抽样；已经排入 FEL 的 CREATE 事件保持不变。
            target.args["interval"] = interval
            return

        activity_name = node.args.get("activity")
        if activity_name:
            target = self.model.nodes.get(activity_name)
            if target is None or target.kind != "ACTIVITY":
                raise HelixRuntimeError(
                    f"{node.label}: ACTIVITY 节点不存在: {activity_name}")
            if target.args.get("until"):
                raise HelixRuntimeError(
                    f"{node.label}: until 型 ACTIVITY 没有 duration")
            duration = node.args.get("duration")
            if not duration:
                raise HelixRuntimeError(
                    f"{node.label}: ALTER activity 需要 duration")
            # 只影响后续启动；正在运行的活动保留自己的结束事件。
            target.args["duration"] = duration
            return

        raise HelixRuntimeError(
            f"{node.label}: ALTER 必须指定 resource/create/activity")

    def _preempt_priority(self, node: NodeSpec, entity: Entity) -> float:
        """解析 PREEMPT 的 HIGH(K)/LOW(K) 优先级表达式。"""
        raw = node.args.get("priority", "").strip()
        if not raw:
            return entity.priority
        match = re.match(
            r"(?i)^(HIGH|LOW)\s*\((.*)\)$", raw)
        if match is None:
            return Expression(raw, label=f"{node.label}:priority").evaluate(
                self._expression_context(entity))
        value = Expression(
            match.group(2), label=f"{node.label}:priority").evaluate(
                self._expression_context(entity))
        return value if match.group(1).upper() == "HIGH" else -value

    def _preempt(self, node: NodeSpec, entity: Entity) -> None:
        """抢占资源。

        规则：
        - 资源可用：直接获得；
        - 被低优先级实体占用：抢占持有者；
        - 没有更低优先级持有者：当前实体等待。

        被抢占实体如果正在 ACTIVITY：
        - 保存 remaining_time；
        - activity_token++ 使旧 END 事件失效；
        - 服务台立即变为 IDLE。
        若指定 preempted_to，则立即路由；否则进入资源等待，
        资源恢复后从剩余时间继续。
        """
        resource_name = node.args.get("resource")
        resource = self.resources.get(resource_name)
        if resource is None:
            raise HelixRuntimeError(
                f"{node.label}: 未定义 RESOURCE {resource_name}")
        units = int(self._number(node.args.get("units", "1")))
        if resource.mode == "RESTOCK":
            raise HelixRuntimeError(
                f"{node.label}: RESTOCK 资源不支持 PREEMPT")
        priority = self._preempt_priority(node, entity)
        entity.preempt_priority = priority
        remaining_at = node.args.get("remaining_at", "").strip()

        if resource.available >= units:
            self._allocate(resource, entity, units)
            entity.preempt_priority = priority
            self._route(entity, node.outgoing[0] if node.outgoing else None)
            return

        # 只有优先级更低的持有者才会被抢占；书中的额外限制：
        # 正在 QUEUE/AWAIT 或还持有其他资源的实体不能被抢占。
        def can_preempt(victim: Entity) -> bool:
            if victim.preempt_priority >= priority:
                return False
            node = self.model.nodes.get(victim.current_node or "")
            if node is not None and node.kind in ("QUEUE", "AWAIT"):
                return False
            for other in self.resources.values():
                if other is resource:
                    continue
                if other.held_by.get(victim.id, 0) > 0:
                    return False
            return True

        holders = [
            self.entities[entity_id]
            for entity_id in resource.held_by
            if entity_id in self.entities
            and can_preempt(self.entities[entity_id])
        ]
        if not holders:
            entity.status = "WAITING_RESOURCE"
            entity.wait_seq = self._next_wait_seq()
            resource.waiters.append(entity.id)
            resource.wait_count += 1
            resource.wait_enter[entity.id] = self.kernel.now
            return

        holders.sort(key=lambda item: (item.preempt_priority, item.wait_seq))
        needed = units
        for victim in holders:
            if needed <= 0:
                break
            held = resource.held_by.get(victim.id, 0)
            take = min(held, needed)
            if take <= 0:
                continue
            resource.held_by[victim.id] = held - take
            if resource.held_by[victim.id] == 0:
                del resource.held_by[victim.id]
            resource.available += take
            needed -= take

            self._detach_activity(victim)
            victim.status = "PREEMPTED"
            victim.resume_units = take
            if remaining_at and victim.remaining_time is not None:
                victim.attrs[remaining_at] = victim.remaining_time
            preempted_to = node.args.get("preempted_to")
            if preempted_to:
                victim.current_node = preempted_to
                victim.status = "ACTIVE"
                self._route(victim, preempted_to)
            else:
                victim.wait_seq = self._next_wait_seq()
                resource.waiters.append(victim.id)
                resource.wait_count += 1
                resource.wait_enter[victim.id] = self.kernel.now

        self._allocate(resource, entity, units)
        entity.preempt_priority = priority
        self._route(entity, node.outgoing[0] if node.outgoing else None)
        self._wake_resource(resource)

    def _detach_activity(self, entity: Entity) -> None:
        """把被抢占实体从当前 SERVICE 中摘下，但不算完成。"""
        if not entity.activity_label:
            return
        activity = self.activities.get(entity.activity_label)
        if activity is None:
            return
        server = next((s for s in activity.servers
                       if s.entity_id == entity.id
                       and s.status == "BUSY"), None)
        if server is None:
            return

        self._update_server_interval(server, self.kernel.now)
        server.busy_total += max(0.0, self.kernel.now - server.busy_since)
        remaining = max(0.0, (entity.activity_end or self.kernel.now)
                        - self.kernel.now)
        entity.remaining_time = remaining
        entity.resume_activity = activity.label
        entity.activity_token += 1
        entity.activity_end = None

        server.status = "IDLE"
        server.entity_id = None
        server.idle_since = self.kernel.now

    def _open_gate(self, node: NodeSpec) -> None:
        gate_name = node.args.get("gate")
        gate = self.gates.get(gate_name)
        if gate is None:
            raise HelixRuntimeError(f"{node.label}: 未定义 GATE {gate_name}")
        gate.state = "OPEN"
        ordered = sorted(
            (self.entities[eid] for eid in gate.waiters),
            key=lambda ent: (-ent.priority, ent.wait_seq))
        gate.waiters.clear()
        for entity in ordered:
            await_node = self.model.node(entity.current_node)
            self._route(entity,
                        await_node.outgoing[0] if await_node.outgoing else None)

    def _close_gate(self, node: NodeSpec) -> None:
        gate_name = node.args.get("gate")
        gate = self.gates.get(gate_name)
        if gate is None:
            raise HelixRuntimeError(f"{node.label}: 未定义 GATE {gate_name}")
        gate.state = "CLOSED"

    def _next_wait_seq(self) -> int:
        self.wait_seq += 1
        return self.wait_seq

    # ------------------------------------------------------------------
    # SELECT
    # ------------------------------------------------------------------
    def _try_select(self, select_label: str) -> None:
        """ASM 选择：所有队列都有实体且有服务台时组装一个实体。

        关键顺序：
        1. 先确认所有队列非空；
        2. 再确认有空闲服务台；
        3. 都满足后才从队列取实体。

        这样可以避免“取出了实体但服务台不可用”，把实体放回队列
        会破坏 FIFO/优先级顺序。
        """
        state = self.selects.get(select_label)
        if state is None:
            raise HelixRuntimeError(f"{select_label}: 未初始化 SELECT")
        if state.queue_rule != "ASM":
            raise HelixRuntimeError(
                f"{select_label}: 暂只支持 queue_rule=ASM")

        while True:
            if any(not self.queues[label].items for label in state.queues):
                return

            chosen = self._choose_select_server(state)
            if chosen is None:
                return
            activity, server = chosen

            members: list[Entity] = []
            for queue_label in state.queues:
                queue = self.queues[queue_label]
                entity = queue.items.popleft()
                wait = self.kernel.now - entity.queue_enter
                queue.wait_sum += wait
                queue.wait_count += 1
                queue.wait_max = max(queue.wait_max, wait)
                members.append(entity)

            assembled = self._merge_entities(members, state.save_rule)
            assembled.members = {
                queue_label: member.id
                for queue_label, member in zip(state.queues, members)
            }
            for member in members:
                member.status = "MERGED"
            assembled.current_node = select_label
            self._start_activity(activity, assembled, server=server)

    def _choose_select_server(self, state: SelectState):
        """按 server_rule 选一个空闲 (ActivityState, ServerState)。

        支持：
        - POR: 按 servers 列表顺序；
        - CYC: 从上次选择之后循环；
        - RAN: 随机；
        - LIT / SIT: 空闲最久 / 空闲最短；
        - LBT / SBT: 累计忙碌时间最大 / 最小。
        """
        candidates = []
        for server_label in state.servers:
            activity = self.activities.get(server_label)
            if activity is None:
                raise HelixRuntimeError(
                    f"{state.label}: SELECT 服务台不存在: {server_label}")
            for server in activity.servers:
                if server.status == "IDLE":
                    candidates.append((activity, server))
        if not candidates:
            return None

        rule = state.server_rule
        if rule == "POR":
            return candidates[0]
        if rule == "CYC":
            index = state.cursor % len(candidates)
            state.cursor = (index + 1) % len(candidates)
            return candidates[index]
        if rule == "RAN":
            return self.rng.choice(candidates)
        if rule == "LIT":
            return min(candidates,
                       key=lambda pair: (pair[1].idle_since, pair[1].index))
        if rule == "SIT":
            return max(candidates,
                       key=lambda pair: (pair[1].idle_since, -pair[1].index))
        if rule == "LBT":
            return max(candidates,
                       key=lambda pair: (pair[1].busy_total, -pair[1].index))
        if rule == "SBT":
            return min(candidates,
                       key=lambda pair: (pair[1].busy_total, pair[1].index))
        raise HelixRuntimeError(
            f"{state.label}: 暂不支持 server_rule={state.server_rule}")

    def _try_select_for_activity(self, activity_label: str) -> None:
        """某个服务台释放后，重新尝试所有包含它的 SELECT。"""
        for state in self.selects.values():
            if activity_label in state.servers:
                self._try_select(state.label)

    # ------------------------------------------------------------------
    # PARALLEL / SPLIT / JOIN / MERGE
    # ------------------------------------------------------------------
    def _enter_parallel(self, node: NodeSpec, entity: Entity) -> None:
        """复制实体，每条 PATH 独立推进。"""
        if not node.paths:
            raise HelixRuntimeError(f"{node.label}: PARALLEL 没有 PATH")
        for index, (_part, target) in enumerate(node.paths):
            child = entity if index == 0 else self._clone_entity(entity)
            if index > 0:
                child.origin_id = entity.id
            self._route(child, target)

    def _enter_split(self, node: NodeSpec, entity: Entity) -> None:
        """按 part 拆分组件；不是复制完整实体。"""
        if not node.paths:
            raise HelixRuntimeError(f"{node.label}: SPLIT 没有 PATH")
        for index, (part, target) in enumerate(node.paths):
            child = entity if index == 0 else self._clone_entity(entity)
            child.part = part
            if index > 0:
                child.origin_id = entity.id
            self._route(child, target)

    def _enter_fork(self, node: NodeSpec, entity: Entity) -> None:
        """把 SELECT ASM 保存的原始成员路由到各自分支。

        与 SPLIT 的区别：
        - SPLIT 创建新组件；
        - FORK 复用原始 LOAD/TRKS/LDER 实体，保持实体身份和队列驻留统计。
        """
        if not entity.members:
            raise HelixRuntimeError(
                f"{node.label}: FORK 没有可路由的 members")
        branches = _fork_branches(node.args.get("branches", ""))
        if not branches:
            raise HelixRuntimeError(
                f"{node.label}: FORK 没有 branches")
        for role, target in branches:
            member_id = entity.members.get(role)
            if member_id is None:
                raise HelixRuntimeError(
                    f"{node.label}: FORK 缺少成员 {role}")
            member = self.entities.get(member_id)
            if member is None:
                raise HelixRuntimeError(
                    f"{node.label}: FORK 成员不存在: {member_id}")
            self._route(member, target)
        entity.status = "MERGED"

    def _enter_join(self, node: NodeSpec, entity: Entity) -> None:
        """等待 count 个实体后按 merge 规则合并。"""
        try:
            count = int(float(node.args.get("count", "2")))
        except ValueError as exc:
            raise HelixRuntimeError(
                f"{node.label}: JOIN count 非法") from exc
        if count < 1:
            raise HelixRuntimeError(f"{node.label}: JOIN count 必须 >= 1")

        group = self.join_groups.setdefault(node.label, [])
        group.append(entity.id)
        if len(group) < count:
            entity.status = "WAITING_JOIN"
            return

        ids = group[:count]
        del group[:count]
        entities = [self.entities[entity_id] for entity_id in ids]
        for member in entities:
            member.status = "MERGED"
        merged = self._merge_entities(
            entities, node.args.get("merge", "FIRST").upper())
        target = node.outgoing[0] if node.outgoing else None
        if target is None:
            raise HelixRuntimeError(f"{node.label}: JOIN 没有后继")
        self._route(merged, target)

    def _enter_merge(self, node: NodeSpec, entity: Entity) -> None:
        """任一路到达即可继续，不合并属性。"""
        target = node.outgoing[0] if node.outgoing else None
        if target is None:
            raise HelixRuntimeError(f"{node.label}: MERGE 没有后继")
        self._route(entity, target)

    def _clone_entity(self, source: Entity) -> Entity:
        """复制实体，保留创建时间、优先级和属性。"""
        clone = self._new_entity(
            priority=source.priority,
            attrs=dict(source.attrs),
            origin_id=source.origin_id or source.id,
            part=source.part,
        )
        clone.created_at = source.created_at
        return clone

    def _merge_entities(self, entities: list[Entity],
                        rule: str) -> Entity:
        """按 FIRST/LAST/HIGH/LOW/SUM/MULT 合并属性。"""
        if not entities:
            raise HelixRuntimeError("JOIN 没有可合并实体")
        if rule == "FIRST":
            chosen = entities[0]
            attrs = dict(chosen.attrs)
        elif rule == "LAST":
            chosen = entities[-1]
            attrs = dict(chosen.attrs)
        elif rule.startswith("HIGH(") and rule.endswith(")"):
            key = rule[5:-1].strip()
            chosen = max(entities, key=lambda item: item.attrs.get(key, 0.0))
            attrs = dict(chosen.attrs)
        elif rule.startswith("LOW(") and rule.endswith(")"):
            key = rule[4:-1].strip()
            chosen = min(entities, key=lambda item: item.attrs.get(key, 0.0))
            attrs = dict(chosen.attrs)
        elif rule in ("SUM", "MULT"):
            attrs = {}
            keys = {key for item in entities for key in item.attrs}
            for key in keys:
                values = [item.attrs.get(key, 0.0) for item in entities]
                if rule == "SUM":
                    attrs[key] = sum(values)
                else:
                    product = 1.0
                    for value in values:
                        product *= value
                    attrs[key] = product
            chosen = entities[0]
        else:
            raise HelixRuntimeError(f"未知 merge 规则: {rule}")

        merged = self._new_entity(
            priority=max(item.priority for item in entities),
            attrs=attrs,
            origin_id=entities[0].id,
            part=None,
        )
        # JOIN 后的系统时间从组内最早创建时间算起。
        merged.created_at = min(item.created_at for item in entities)
        return merged

    # ------------------------------------------------------------------
    # IF
    # ------------------------------------------------------------------
    def _enter_if(self, node: NodeSpec, entity: Entity) -> None:
        draw = self.rng.random() if any(
            "RANDOM" in condition.upper()
            for condition, _ in node.branches) else None
        for condition, target in node.branches:
            if self._eval_condition(condition, draw, entity, node.label):
                self._route(entity, target)
                return
        # Compiler 已保证 ELSE 存在；这里作为防御。
        raise HelixRuntimeError(f"{node.label}: IF 没有命中分支")

    def _eval_condition(self, condition: str, draw: float | None,
                        entity: Entity, label: str) -> bool:
        text = condition.strip()
        match = re.fullmatch(
            r"RANDOM\(\)\s*(<=|<|>=|>)\s*([-+0-9.eE]+)",
            text, re.I)
        if match and draw is not None:
            operator, value = match.group(1), float(match.group(2))
            return {
                "<": draw < value,
                "<=": draw <= value,
                ">": draw > value,
                ">=": draw >= value,
            }[operator]
        upper = text.upper()
        if upper == "TRUE":
            return True
        if upper == "FALSE":
            return False
        if re.search(r"RANDOM\(\)", text, re.I):
            if draw is None:
                raise HelixRuntimeError(
                    f"{label}: RANDOM() 缺少抽样值")
            text = re.sub(r"RANDOM\(\)", f"({draw!r})", text, flags=re.I)
        # 属性/变量条件：支持 id = 1、id <> 2、tons > 20、A AND B 等。
        normalized = text.replace("<>", "!=")
        normalized = re.sub(r"(?<![<>=!])=(?!=)", "==", normalized)
        try:
            result = Expression(
                normalized, label=f"{label} IF").evaluate(
                    self._expression_context(entity))
        except HelixRuntimeError as exc:
            raise HelixRuntimeError(
                f"{label}: 暂不支持 IF 条件: {condition}") from exc
        return bool(result)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    def _new_entity(self, *, priority: float = 0.0,
                    attrs: dict[str, float] | None = None,
                    origin_id: int | None = None,
                    part: str | None = None) -> Entity:
        entity = Entity(
            id=self.next_entity_id,
            created_at=self.kernel.now,
            priority=priority,
            attrs=dict(attrs or {}),
            origin_id=origin_id,
            part=part,
        )
        self.next_entity_id += 1
        self.entities[entity.id] = entity
        return entity

    def _number(self, text: str) -> float:
        text = text.strip()
        if text in self.scenario.initial:
            return self.scenario.initial[text]
        if text in self.scenario.constants:
            return self.scenario.constants[text]
        return float(text)

    def _float_arg(self, node: NodeSpec, name: str, default: float) -> float:
        value = node.args.get(name)
        return default if value is None else self._number(value)

    def _int_arg(self, node: NodeSpec, name: str, default: int) -> int:
        value = node.args.get(name)
        return default if value is None else int(self._number(value))

    def _list_arg(self, node: NodeSpec, name: str) -> list[str]:
        """解析 ``[A, B]`` 参数；只允许节点标签。"""
        raw = node.args.get(name, "").strip()
        if not (raw.startswith("[") and raw.endswith("]")):
            raise HelixRuntimeError(
                f"{node.label}: {name} 必须是 [A, B] 列表")
        inner = raw[1:-1].strip()
        if not inner:
            return []
        items = [item.strip() for item in inner.split(",")]
        for item in items:
            if not re.fullmatch(r"[A-Za-z_]\w*", item):
                raise HelixRuntimeError(
                    f"{node.label}: {name} 含非法标签: {item!r}")
        return items

    def _sample(self, spec: str, entity: Entity | None = None) -> float:
        """抽样分布，或计算实体上下文中的时间表达式。"""
        text = str(spec).strip()
        upper = text.upper()
        if upper.startswith(("EXPON(", "EXP(")):
            mean = self._sample_arg(
                text[text.index("(") + 1:-1], entity, "EXPON mean")
            return self.rng.expovariate(1.0 / mean)
        if upper.startswith("ERLNG("):
            args = _split_top_level(text[6:-1])
            return self.rng.gammavariate(
                self._sample_arg(args[1], entity, "ERLNG stages"),
                self._sample_arg(args[0], entity, "ERLNG mean"))
        if upper.startswith("RNORM("):
            args = _split_top_level(text[6:-1])
            return self.rng.gauss(
                self._sample_arg(args[0], entity, "RNORM mean"),
                self._sample_arg(args[1], entity, "RNORM std"))
        if upper.startswith("UNFRM("):
            args = _split_top_level(text[6:-1])
            return self.rng.uniform(
                self._sample_arg(args[0], entity, "UNFRM low"),
                self._sample_arg(args[1], entity, "UNFRM high"))
        if entity is not None:
            return Expression(
                text, label="VALUE").evaluate(
                    self._expression_context(entity))
        return self._number(text)

    def _sample_arg(self, text: str, entity: Entity | None,
                    label: str) -> float:
        if entity is None:
            return self._number(text)
        return Expression(text.strip(), label=label).evaluate(
            self._expression_context(entity))

    # ------------------------------------------------------------------
    # 结果
    # ------------------------------------------------------------------
    def result(self, now: float) -> RunResult:
        """把运行态汇总成只读结果。

        时间加权指标用 area / (now - start) 计算；这里的 duration
        必须与 advance() 使用的区间一致，否则平均值会被 end 截断或
        多算一段。
        """
        duration = max(now - self.stat_start, 1e-12)

        queues: list[QueueStat] = []
        for queue in self.queues.values():
            mean = queue.area / duration
            variance = max(0.0, queue.area2 / duration - mean * mean)
            queues.append(QueueStat(
                label=queue.label,
                average_length=mean,
                std_length=math.sqrt(variance),
                max_length=queue.max_length,
                current_length=len(queue.items),
                balk_count=queue.balk_count,
                average_wait=(queue.wait_sum / queue.wait_count
                              if queue.wait_count else 0.0),
                maximum_wait=queue.wait_max,
            ))

        services: list[ServiceStat] = []
        for activity in self.activities.values():
            mean = activity.area / duration
            variance = max(0.0, activity.area2 / duration - mean * mean)
            max_idle = max(activity.servers, key=lambda s: s.max_idle)
            max_busy = max(activity.servers, key=lambda s: s.max_busy)
            services.append(ServiceStat(
                activity=activity.label,
                capacity=activity.capacity,
                average_utilization=mean,
                std_utilization=math.sqrt(variance),
                maximum_utilization=activity.max_active,
                current_utilization=activity.active,
                average_blockage=activity.blocked_area / duration,
                maximum_idle=max_idle.max_idle,
                maximum_idle_server=max_idle.max_idle_server or max_idle.index,
                maximum_busy=max_busy.max_busy,
                maximum_busy_server=max_busy.max_busy_server or max_busy.index,
                completed=activity.completed,
            ))

        resources: list[ResourceStat] = []
        for resource in self.resources.values():
            mean = resource.area / duration
            variance = max(0.0, resource.area2 / duration - mean * mean)
            current = self._resource_used(resource)
            capacity = max(1, resource.capacity)
            resources.append(ResourceStat(
                name=resource.name,
                capacity=resource.capacity,
                available=resource.available,
                average_held=mean,
                maximum_held=resource.max_held,
                current_held=current,
                average_utilization=mean / capacity,
                std_utilization=math.sqrt(variance) / capacity,
                maximum_utilization=resource.max_held / capacity,
                current_utilization=current / capacity,
                wait_count=resource.wait_count,
                average_wait=(resource.wait_sum / resource.wait_count
                              if resource.wait_count else 0.0),
                max_wait=resource.wait_max,
            ))
        gates = [
            GateStat(
                name=gate.name,
                state=gate.state,
                wait_count=gate.wait_count,
            )
            for gate in self.gates.values()
        ]

        return RunResult(
            project=self.model.project,
            now=now,
            observations=list(self.observations.values()),
            queues=queues,
            services=services,
            resources=resources,
            gates=gates,
        )
