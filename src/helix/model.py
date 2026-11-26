"""Helix 模型 IR 与编译器。

Compiler 的职责：
1. AST -> NodeSpec/EdgeSpec
2. 生成匿名节点标签
3. 把“顺序默认”展开成显式边
4. 校验标签、边和分支目标

运行期只读取 Model，不修改它。
"""
from __future__ import annotations

import hashlib
import json
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from .ast import (
    AttrDecl,
    ContinuousDecl,
    DetectDecl,
    EdgeDecl,
    GateDecl,
    IfBlock,
    NodeDecl,
    ParallelBlock,
    Program,
    ResourceDecl,
    SevntDecl,
    SplitBlock,
    VarDecl,
)
from .errors import HelixCompileError
from .parser import _split_top_level, parse


SUPPORTED_NODE_KINDS = frozenset({
    "CREATE",
    "QUEUE",
    "ACTIVITY",
    "ASSIGN",
    "EVENT",
    "OBSERVE",
    "SCAN",
    "IF",
    "PARALLEL",
    "SPLIT",
    "FORK",
    "JOIN",
    "MERGE",
    "SELECT",
    "AWAIT",
    "FREE",
    "ALTER",
    "PREEMPT",
    "OPEN",
    "CLOSE",
    "TERMINATE",
    "DETECT",
})


@dataclass(slots=True)
class VarSpec:
    name: str
    label: str
    low: float | None = None
    high: float | None = None
    default: float = 0.0
    scope: str = ""
    size: int = 0


@dataclass(slots=True)
class ResourceSpec:
    name: str
    capacity: int = 1
    mode: str = "POOL"


@dataclass(slots=True)
class AttrSpec:
    name: str


@dataclass(slots=True)
class GateSpec:
    name: str
    state: str = "CLOSED"


@dataclass(slots=True)
class DetectSpec:
    name: str
    when: str
    edge: str = "RISING"
    tol: float = 0.01


@dataclass(slots=True)
class SevntSpec:
    code: int
    when: str
    name: str = ""
    action: str = ""


@dataclass(slots=True)
class EdgeSpec:
    source: str
    target: str
    kind: str = "DEFAULT"


@dataclass(slots=True)
class NodeSpec:
    """单个网络节点。

    ``args`` 保留原始字符串，运行期再按节点类型解释。
    ``branches`` 只用于 IF：[(condition, target), ...]。
    """

    label: str
    kind: str
    args: dict[str, str] = field(default_factory=dict)
    outgoing: list[str] = field(default_factory=list)
    branches: list[tuple[str, str]] = field(default_factory=list)
    line: int = 0
    paths: list[tuple[str | None, str]] = field(default_factory=list)
    _frozen: bool = field(default=False, repr=False)

    def __setattr__(self, name: str, value) -> None:
        if getattr(self, "_frozen", False) and name != "_frozen":
            raise AttributeError(
                f"NodeSpec {self.label!r} 已冻结，不能修改 {name}")
        object.__setattr__(self, name, value)


@dataclass(slots=True)
class Model:
    project: str = "Helix PROJECT"
    version: str = "2"
    variables: dict[str, VarSpec] = field(default_factory=dict)
    attrs: dict[str, AttrSpec] = field(default_factory=dict)
    continuous: ContinuousDecl | None = None
    resources: dict[str, ResourceSpec] = field(default_factory=dict)
    gates: dict[str, GateSpec] = field(default_factory=dict)
    detects: list[DetectSpec] = field(default_factory=list)
    sevnts: list[SevntSpec] = field(default_factory=list)
    equations: list[str] = field(default_factory=list)
    nodes: dict[str, NodeSpec] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    edges: list[EdgeSpec] = field(default_factory=list)
    source_hash: str = ""
    _frozen: bool = field(default=False, repr=False)
    _fingerprint: str = field(default="", repr=False)

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------
    @classmethod
    def from_source(cls, source: str, *, debug_parse: bool = False,
                    debug_path: str | None = None,
                    source_name: str = "<string>") -> "Model":
        """解析并编译源码。

        ``debug_parse`` 目前只保留接口，后续由 debug 模块写入
        tokens.ndjson/parse.ndjson。
        """
        program = parse(source, source_name=source_name)
        model = compile_program(program, source_text=source)
        if debug_parse:
            from .debug import write_parse_artifacts

            write_parse_artifacts(
                source=source,
                source_name=source_name,
                program=program,
                model=model,
                directory=debug_path or "debug",
            )
        return model

    @classmethod
    def from_file(cls, path: str, *, debug_parse: bool = False,
                  debug_path: str | None = None) -> "Model":
        text = Path(path).read_text(encoding="utf-8")
        return cls.from_source(text, debug_parse=debug_parse,
                               debug_path=debug_path, source_name=str(path))

    def freeze(self) -> None:
        """冻结编译后的 Model IR。

        运行时只能读取 Model；ALTER 等动态值必须写入 RuntimeState。
        冻结后修改 ``nodes[...]``、``args``、outgoing/branches/paths
        会立即抛出 TypeError/AttributeError。
        """
        if self._frozen:
            return
        for node in self.nodes.values():
            if not isinstance(node.args, MappingProxyType):
                node.args = MappingProxyType(dict(node.args))
            if not isinstance(node.outgoing, tuple):
                node.outgoing = tuple(node.outgoing)
            if not isinstance(node.branches, tuple):
                node.branches = tuple(node.branches)
            if not isinstance(node.paths, tuple):
                node.paths = tuple(node.paths)
            node._frozen = True
        self.variables = MappingProxyType(dict(self.variables))
        self.attrs = MappingProxyType(dict(self.attrs))
        self.resources = MappingProxyType(dict(self.resources))
        self.gates = MappingProxyType(dict(self.gates))
        self.nodes = MappingProxyType(dict(self.nodes))
        self.detects = tuple(self.detects)
        self.sevnts = tuple(self.sevnts)
        self.equations = tuple(self.equations)
        self.order = tuple(self.order)
        self.edges = tuple(self.edges)
        self._frozen = True
        self._fingerprint = self.structure_fingerprint()

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def structure_fingerprint(self) -> str:
        """计算 Model IR 的结构指纹，用于发现运行期误写。"""
        payload = {
            "project": self.project,
            "version": self.version,
            "source_hash": self.source_hash,
            "variables": {
                name: [spec.scope, spec.size, spec.default, spec.label]
                for name, spec in self.variables.items()
            },
            "resources": {
                name: [spec.capacity, spec.mode]
                for name, spec in self.resources.items()
            },
            "gates": {
                name: spec.state for name, spec in self.gates.items()
            },
            "nodes": {
                label: {
                    "kind": node.kind,
                    "args": dict(node.args),
                    "outgoing": list(node.outgoing),
                    "branches": list(node.branches),
                    "paths": list(node.paths),
                }
                for label, node in self.nodes.items()
            },
            "order": list(self.order),
            "edges": [[edge.source, edge.target, edge.kind]
                      for edge in self.edges],
        }
        raw = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def check_integrity(self) -> None:
        """在每次运行前检查冻结后的 Model 是否被外部修改。"""
        if self._frozen and self._fingerprint:
            if self.structure_fingerprint() != self._fingerprint:
                warnings.warn(
                    "Model 在 freeze() 后被修改；运行结果可能不可复现。"
                    " 请把动态修改放入 Scenario/Runtime。",
                    RuntimeWarning,
                    stacklevel=3,
                )

    # ------------------------------------------------------------------
    # 场景
    # ------------------------------------------------------------------
    def initialize(self, *, initial: dict | None = None,
                   constants: dict | None = None,
                   entities: dict | None = None,
                   continuous: dict | None = None):
        """创建运行场景；不修改当前 Model。"""
        from .scenario import Scenario

        return Scenario(self, initial=initial or {},
                        constants=constants or {},
                        entities=entities or {},
                        continuous=continuous or {})

    def run(self, **kwargs):
        """便捷入口：等价于 initialize(...).run(...)。

        为了保持四步 API 清晰，推荐显式写 initialize。这里只是让
        简单脚本少写一行。
        """
        initial = kwargs.pop("initial", None)
        constants = kwargs.pop("constants", None)
        entities = kwargs.pop("entities", None)
        continuous = kwargs.pop("continuous", None)
        scenario = self.initialize(initial=initial, constants=constants,
                                   entities=entities,
                                   continuous=continuous)
        return scenario.run(**kwargs)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def node(self, label: str) -> NodeSpec:
        try:
            return self.nodes[label]
        except KeyError as exc:
            raise HelixCompileError(f"未定义节点: {label}") from exc

    def validate(self) -> None:
        """检查模型级不变量；错误信息面向用户。"""
        errors: list[str] = []
        for node in self.nodes.values():
            if node.kind not in SUPPORTED_NODE_KINDS:
                line = f"（第 {node.line} 行）" if node.line else ""
                errors.append(
                    f"{node.label}: 不支持的节点类型 {node.kind}{line}")
                continue
            for target in node.outgoing:
                if target not in self.nodes:
                    errors.append(
                        f"{node.label}: 后继节点不存在: {target}")
            for _condition, target in node.branches:
                if target not in self.nodes:
                    errors.append(
                        f"{node.label}: 分支目标不存在: {target}")
            for _part, target in node.paths:
                if target not in self.nodes:
                    errors.append(
                        f"{node.label}: 并行路径目标不存在: {target}")

            if node.kind == "CREATE":
                control = {"interval", "first", "count",
                           "priority", "until", "entity_class"}
                entity_class = node.args.get(
                    "entity_class", "CUSTOMER").strip().upper()
                if entity_class not in ("CUSTOMER", "INTERNAL"):
                    errors.append(
                        f"{node.label}: entity_class 必须是 "
                        "CUSTOMER 或 INTERNAL")
                by_lower = {
                    name.lower(): spec
                    for name, spec in self.variables.items()
                }
                attr_values: dict[str, list[str]] = {}
                renames: dict[str, str] = {}
                for key, raw_value in node.args.items():
                    if key.lower() in control:
                        continue
                    spec = self.variables.get(key)
                    if spec is None:
                        spec = by_lower.get(key.lower())
                    if spec is None:
                        errors.append(
                            f"{node.label}: CREATE 属性 {key} 未声明")
                        continue
                    if spec.scope != "ENTITY":
                        errors.append(
                            f"{node.label}: CREATE 属性 {key} 必须是 ENTITY")
                        continue
                    canonical = spec.name
                    if canonical != key:
                        renames[key] = canonical
                    text = raw_value.strip()
                    if not (text.startswith("[") and text.endswith("]")):
                        errors.append(
                            f"{node.label}: CREATE 属性 {canonical} 必须是列表")
                        continue
                    items = _split_top_level(text[1:-1])
                    if not items:
                        errors.append(
                            f"{node.label}: CREATE 属性 {canonical} 不能为空")
                        continue
                    attr_values[canonical] = items

                for old, new in renames.items():
                    node.args[new] = node.args.pop(old)

                if attr_values:
                    if "until" in node.args:
                        errors.append(
                            f"{node.label}: CREATE 属性列表不能与 until 同时使用")
                    lengths = {len(items) for items in attr_values.values()}
                    if len(lengths) != 1:
                        errors.append(
                            f"{node.label}: CREATE 属性列表长度必须一致")
                    if lengths:
                        length = next(iter(lengths))
                        if "count" in node.args:
                            try:
                                declared = int(float(node.args["count"]))
                            except ValueError:
                                declared = 0
                            if declared != length:
                                errors.append(
                                    f"{node.label}: CREATE 属性列表长度 "
                                    f"{length} 与 count={declared} 不一致")
                        else:
                            node.args["count"] = str(length)

                if "count" in node.args and "until" in node.args:
                    errors.append(
                        f"{node.label}: count 和 until 不能同时使用")
                if "count" in node.args:
                    try:
                        if int(float(node.args["count"])) < 1:
                            errors.append(
                                f"{node.label}: count 必须 >= 1")
                    except ValueError:
                        errors.append(
                            f"{node.label}: count 必须是数字")

            if node.kind == "QUEUE":
                raw_action = node.args.get("on_full", "ERROR").strip()
                action = raw_action.upper()
                if action.startswith("BALK(") and action.endswith(")"):
                    target = raw_action[5:-1].strip()
                    if target not in self.nodes:
                        errors.append(
                            f"{node.label}: BALK 目标不存在: {target}")
                elif action not in ("BLOCK", "ERROR"):
                    errors.append(
                        f"{node.label}: 未知 on_full={raw_action}")

            if node.kind == "ACTIVITY":
                try:
                    if int(float(node.args.get("servers", "1"))) < 1:
                        errors.append(
                            f"{node.label}: servers 必须 >= 1")
                except ValueError:
                    errors.append(
                        f"{node.label}: servers 必须是数字")

            if node.kind == "SELECT":
                try:
                    queues = _list_text(node.args.get("queues", ""))
                    servers = _list_text(node.args.get("servers", ""))
                except ValueError as exc:
                    errors.append(f"{node.label}: {exc}")
                else:
                    if not queues:
                        errors.append(
                            f"{node.label}: queues 不能为空")
                    if not servers:
                        errors.append(
                            f"{node.label}: servers 不能为空")
                    if node.args.get("queue_rule", "ASM").upper() != "ASM":
                        errors.append(
                            f"{node.label}: 暂只支持 queue_rule=ASM")
                    for queue_label in queues:
                        target = self.nodes.get(queue_label)
                        if target is None or target.kind != "QUEUE":
                            errors.append(
                                f"{node.label}: SELECT queue 不存在: "
                                f"{queue_label}")
                    for server_label in servers:
                        target = self.nodes.get(server_label)
                        if target is None or target.kind != "ACTIVITY":
                            errors.append(
                                f"{node.label}: SELECT server 不存在: "
                                f"{server_label}")
                    rule = node.args.get("server_rule", "LIT").upper()
                    if rule not in (
                            "POR", "CYC", "RAN", "LIT", "SIT", "LBT", "SBT"):
                        errors.append(
                            f"{node.label}: 未知 server_rule={rule}")

            if node.kind in ("AWAIT", "FREE"):
                resource = node.args.get("resource")
                gate = node.args.get("gate")
                if resource and resource not in self.resources:
                    errors.append(
                        f"{node.label}: 未定义 RESOURCE {resource}")
                if gate and gate not in self.gates:
                    errors.append(
                        f"{node.label}: 未定义 GATE {gate}")
                if not resource and not gate:
                    errors.append(
                        f"{node.label}: 需要 resource 或 gate")

            if node.kind == "PREEMPT":
                resource = node.args.get("resource")
                if resource not in self.resources:
                    errors.append(
                        f"{node.label}: 未定义 RESOURCE {resource}")
                elif self.resources[resource].capacity != 1:
                    errors.append(
                        f"{node.label}: PREEMPT 只支持容量为 1 的资源")
            if node.kind == "ALTER":
                selectors = [
                    key for key in ("resource", "create", "activity")
                    if node.args.get(key)
                ]
                if len(selectors) != 1:
                    errors.append(
                        f"{node.label}: ALTER 必须且只能指定 "
                        "resource/create/activity 之一")
                    continue
                selector = selectors[0]
                if selector == "resource":
                    resource = node.args.get("resource")
                    if resource not in self.resources:
                        errors.append(
                            f"{node.label}: 未定义 RESOURCE {resource}")
                    capacity = node.args.get("capacity")
                    if capacity is None:
                        errors.append(
                            f"{node.label}: ALTER resource 需要 capacity")
                    else:
                        try:
                            value = int(float(capacity))
                        except ValueError:
                            # 允许 CAPACITY(R)+N、ordernum 等运行时表达式。
                            pass
                        else:
                            if value < 0:
                                errors.append(
                                    f"{node.label}: capacity 必须 >= 0")
                elif selector == "create":
                    target = node.args.get("create")
                    if target not in self.nodes:
                        errors.append(
                            f"{node.label}: CREATE 节点不存在: {target}")
                    elif self.nodes[target].kind != "CREATE":
                        errors.append(
                            f"{node.label}: {target} 不是 CREATE 节点")
                    if "interval" not in node.args:
                        errors.append(
                            f"{node.label}: ALTER create 需要 interval")
                else:
                    target = node.args.get("activity")
                    if target not in self.nodes:
                        errors.append(
                            f"{node.label}: ACTIVITY 节点不存在: {target}")
                    elif self.nodes[target].kind != "ACTIVITY":
                        errors.append(
                            f"{node.label}: {target} 不是 ACTIVITY 节点")
                    elif self.nodes[target].args.get("until"):
                        errors.append(
                            f"{node.label}: until 型 ACTIVITY 没有 duration")
                    if "duration" not in node.args:
                        errors.append(
                            f"{node.label}: ALTER activity 需要 duration")
            if node.kind == "PREEMPT":
                target = node.args.get("preempted_to", "").strip()
                if target and target not in self.nodes:
                    errors.append(
                        f"{node.label}: preempted_to 节点不存在: {target}")
                remaining = node.args.get("remaining_at", "").strip()
                if remaining and remaining not in self.variables \
                        and remaining not in self.attrs:
                    errors.append(
                        f"{node.label}: remaining_at 未声明: {remaining}")

            if node.kind in ("OPEN", "CLOSE"):
                gate = node.args.get("gate")
                if gate not in self.gates:
                    errors.append(
                        f"{node.label}: 未定义 GATE {gate}")

            if node.kind == "FORK":
                try:
                    branches = _fork_branches(
                        node.args.get("branches", ""))
                except ValueError as exc:
                    errors.append(f"{node.label}: {exc}")
                else:
                    if not branches:
                        errors.append(
                            f"{node.label}: FORK branches 不能为空")
                    for _role, target in branches:
                        if target not in self.nodes:
                            errors.append(
                                f"{node.label}: FORK 目标不存在: {target}")

        # 统一事件命名空间：DETECT 标签、顶层 DETECT name、
        # SEVNT name 都必须是唯一事件名。
        event_names: set[str] = set()

        def register_event(name: str, where: str) -> None:
            if not name:
                return
            if name in event_names:
                errors.append(f"{where}: 事件名重复: {name}")
            event_names.add(name)

        for node in self.nodes.values():
            if node.kind == "DETECT":
                register_event(node.label, node.label)
        for spec in self.detects:
            register_event(spec.name, f"DETECT {spec.name}")
        for spec in self.sevnts:
            if spec.code != 1 and not spec.name:
                errors.append(
                    f"SEVNT code={spec.code}: 非系统停止事件需要 name")
            if spec.action and spec.action not in self.nodes:
                errors.append(
                    f"SEVNT {spec.code}: action 节点不存在: {spec.action}")
            register_event(spec.name, f"SEVNT {spec.code}")

        for node in self.nodes.values():
            if node.kind == "EVENT":
                name = node.args.get("name", "").strip()
                action = node.args.get("action", "").strip()
                if not name:
                    errors.append(f"{node.label}: EVENT 需要 name")
                if action and action not in self.nodes:
                    errors.append(
                        f"{node.label}: EVENT action 节点不存在: {action}")

        for node in self.nodes.values():
            if node.kind != "ACTIVITY":
                continue
            until = node.args.get("until", "").strip().strip("\"'")
            duration = node.args.get("duration", "").strip().upper()
            if duration.startswith(("REL(", "STOPA(")):
                errors.append(
                    f"{node.label}: REL/STOPA 已统一为 ACTIVITY(until=事件名)")
            if until and "[" not in until and until not in event_names:
                errors.append(
                    f"{node.label}: until 引用未知事件: {until}")

        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"边起点不存在: {edge.source}")
            if edge.target not in self.nodes:
                errors.append(f"边终点不存在: {edge.target}")
        if errors:
            raise HelixCompileError("；".join(errors))

    def structure_warnings(self) -> list[str]:
        """返回模型结构警告；不改变编译/运行行为。

        这些检查依赖静态图，无法看到 Python ``entities=`` 注入的初始
        实体，因此无 CREATE、不可达等只作为 warning。
        """
        warnings: list[str] = []
        creates = [node for node in self.nodes.values()
                   if node.kind == "CREATE"]
        terminals = [node for node in self.nodes.values()
                     if node.kind == "TERMINATE"]

        if not creates:
            warnings.append(
                "模型没有 CREATE 入口；如果通过 Python entities= 注入"
                "初始实体，可忽略此警告")
        if not terminals:
            warnings.append(
                "模型没有 EXIT()/TERMINATE() 终止节点；如果只靠 end "
                "停止，可忽略此警告")

        incoming: dict[str, set[str]] = {
            label: set() for label in self.nodes}
        outgoing: dict[str, list[str]] = {
            label: list(node.outgoing) for label, node in self.nodes.items()}

        def add_edge(source: str, target: str | None) -> None:
            if target and target in self.nodes:
                outgoing[source].append(target)
                incoming[target].add(source)

        for label, node in self.nodes.items():
            for target in node.outgoing:
                add_edge(label, target)
            for _condition, target in node.branches:
                add_edge(label, target)
            for _part, target in node.paths:
                add_edge(label, target)
            add_edge(label, node.args.get("preempted_to"))
            add_edge(label, node.args.get("action"))
            on_full = node.args.get("on_full", "").strip()
            match = re.fullmatch(r"(?i)BALK\(([A-Za-z_]\w*)\)", on_full)
            if match:
                add_edge(label, match.group(1))

        if creates:
            reachable: set[str] = set()
            stack = [node.label for node in creates]
            while stack:
                label = stack.pop()
                if label in reachable:
                    continue
                reachable.add(label)
                stack.extend(outgoing.get(label, []))
            unreachable = [
                label for label in self.order
                if label not in reachable and label not in {
                    node.label for node in creates}
            ]
            if unreachable:
                shown = ", ".join(unreachable[:10])
                if len(unreachable) > 10:
                    shown += ", ..."
                warnings.append(f"不可达节点: {shown}")

        isolated = [
            label for label in self.order
            if not incoming[label] and not outgoing[label]
        ]
        if isolated:
            shown = ", ".join(isolated[:10])
            if len(isolated) > 10:
                shown += ", ..."
            warnings.append(f"孤立节点: {shown}")
        return warnings


# ----------------------------------------------------------------------
# Compiler
# ----------------------------------------------------------------------
def compile_program(program: Program, *, source_text: str = "") -> Model:
    """把 AST 编译成 Model。

    顺序规则：
    - 普通节点没有箭头 → 连接下一条网络语句；
    - 有箭头 / EdgeDecl / IF 块 → 断开默认链；
    - TERMINATE 不产生默认后继。
    """
    model = Model(project=program.project,
                  source_hash=hashlib.sha256(
                      source_text.encode("utf-8")).hexdigest())

    for declaration in program.declarations:
        if isinstance(declaration, VarDecl):
            if declaration.name in model.variables:
                raise HelixCompileError(f"重复变量: {declaration.name}")
            model.variables[declaration.name] = VarSpec(
                declaration.name, declaration.label,
                declaration.low, declaration.high,
                scope=declaration.scope or "", size=declaration.size)
        elif isinstance(declaration, AttrDecl):
            if declaration.name in model.attrs:
                raise HelixCompileError(f"重复属性: {declaration.name}")
            model.attrs[declaration.name] = AttrSpec(declaration.name)
        elif isinstance(declaration, ContinuousDecl):
            if model.continuous is not None:
                raise HelixCompileError("CONTINUOUS 只能声明一次")
            model.continuous = declaration
        elif isinstance(declaration, ResourceDecl):
            if declaration.name in model.resources:
                raise HelixCompileError(f"重复资源: {declaration.name}")
            model.resources[declaration.name] = ResourceSpec(
                declaration.name, declaration.capacity, declaration.mode)
        elif isinstance(declaration, GateDecl):
            if declaration.name in model.gates:
                raise HelixCompileError(f"重复门: {declaration.name}")
            model.gates[declaration.name] = GateSpec(
                declaration.name, declaration.state)
        elif isinstance(declaration, DetectDecl):
            model.detects.append(DetectSpec(
                declaration.name, declaration.when,
                declaration.edge, declaration.tol))
        elif isinstance(declaration, SevntDecl):
            model.sevnts.append(SevntSpec(
                declaration.code, declaration.when,
                declaration.name, declaration.action))
        elif isinstance(declaration, NodeDecl):
            # 顶层不应出现节点；防御性报错。
            raise HelixCompileError(f"节点不能写在 NETWORK 外: {declaration.kind}")

    model.equations = list(program.equations)
    _compile_network(model, program.network)
    _resolve_variable_scopes(model)
    model.validate()
    model.freeze()
    return model


_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


def _resolve_variable_scopes(model: Model) -> None:
    """按使用位置推断 VAR 作用域。

    规则：
    - 出现在 EQUATION/DETECT/SEVNT 条件中的名称 → GLOBAL
    - 显式 ENTITY/GLOBAL 优先
    - 其余 → ENTITY
    """
    global_usage: set[str] = set()
    for equation in model.equations:
        global_usage.update(_IDENT_RE.findall(equation))
    for spec in model.detects:
        global_usage.update(_IDENT_RE.findall(spec.when))
    for spec in model.sevnts:
        global_usage.update(_IDENT_RE.findall(spec.when))
    for node in model.nodes.values():
        if node.kind == "DETECT":
            global_usage.update(_IDENT_RE.findall(
                node.args.get("when", "")))

    errors: list[str] = []
    model.attrs.clear()
    for equation in model.equations:
        match = re.match(r"^\s*(?:DD|SS)\s*\(\s*([^)]*)\)", equation, re.I)
        if match and match.group(1).strip().isdigit():
            errors.append(
                f"EQUATION 不支持数字下标: {equation!r}；"
                "请使用变量名，例如 DD(TEMP)")
    for name, spec in model.variables.items():
        if not spec.scope:
            spec.scope = "GLOBAL" if name in global_usage else "ENTITY"
        if spec.scope == "ENTITY" and name in global_usage:
            errors.append(
                f"VAR {name}: 在 EQUATION/DETECT/SEVNT 中使用，"
                "作用域必须为 GLOBAL")
        if spec.scope == "ENTITY" and spec.size:
            errors.append(f"VAR {name}: 数组只支持 GLOBAL")
        if spec.scope == "ENTITY":
            model.attrs[name] = AttrSpec(name)
    if errors:
        raise HelixCompileError("；".join(errors))


def _list_text(text: str) -> list[str]:
    """解析 SELECT 的 ``[A, B]`` 参数，供编译器校验。"""
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError(f"列表格式错误: {text!r}")
    inner = text[1:-1].strip()
    if not inner:
        return []
    items = [item.strip() for item in inner.split(",")]
    for item in items:
        if not item.replace("_", "").isalnum():
            raise ValueError(f"非法列表项: {item!r}")
    return items


def _fork_branches(text: str) -> list[tuple[str, str]]:
    """解析 ``[LDER -> LOADER_REST, TRKS -> HAUL]``。

    FORK 的 role 使用 SELECT 的 queue 标签，这样装配成员与分支
    之间的关系是显式的。
    """
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError(f"FORK branches 列表格式错误: {text!r}")
    inner = text[1:-1].strip()
    if not inner:
        return []
    branches: list[tuple[str, str]] = []
    for item in inner.split(","):
        match = re.fullmatch(
            r"\s*([A-Za-z_]\w*)\s*(?:->|(?i:GOTO))\s*([A-Za-z_]\w*)\s*",
            item)
        if not match:
            raise ValueError(f"FORK 分支格式错误: {item!r}")
        branch_role, target = match.group(1), match.group(2)
        branches.append((branch_role, target))
    return branches


def _unique_label(model: Model, stem: str) -> str:
    """生成稳定且唯一的匿名节点标签。"""
    index = 1
    while f"{stem}_{index}" in model.nodes:
        index += 1
    return f"{stem}_{index}"


def _compile_network(model: Model, items: list[object]) -> None:
    """编译 NETWORK，展开默认顺序边。

    这是 Helix 与旧 SLAM 最大的结构差异：
    - 普通节点默认连向下一条语句；
    - 有显式 -> 的节点不再自动连下一条；
    - IF/PARALLEL/SPLIT 的目标是“分支根”，不能被顺序链误连；
    - TERMINATE 不产生默认后继。

    先收集 branch_roots 再遍历，原因是我们必须先知道后面的节点
    是否会被前面的分支引用，否则会把 A、B 两个并行分支错误地连成
    A -> B。
    """
    previous: str | None = None
    pending_edges: list[EdgeSpec] = []

    # 分支目标不是顺序链的一部分；例如 IF 的 DONE/Q2、
    # PARALLEL 的两个 PATH、SPLIT 的多个 part。
    branch_roots: set[str] = set()
    for item in items:
        if isinstance(item, IfBlock):
            branch_roots.update(branch.target for branch in item.branches)
            if item.else_target:
                branch_roots.add(item.else_target)
        elif isinstance(item, ParallelBlock):
            branch_roots.update(item.paths)
        elif isinstance(item, SplitBlock):
            branch_roots.update(item.paths.values())
        elif isinstance(item, NodeDecl) and item.kind == "SELECT":
            try:
                branch_roots.update(
                    _list_text(item.args.get("queues", "")))
                branch_roots.update(
                    _list_text(item.args.get("servers", "")))
            except ValueError:
                # 具体错误由 validate() 给出；这里只负责建边。
                pass
        elif isinstance(item, NodeDecl) and item.kind == "FORK":
            try:
                branch_roots.update(
                    target for _role, target in
                    _fork_branches(item.args.get("branches", "")))
            except ValueError:
                pass

    for item in items:
        if isinstance(item, NodeDecl):
            label = item.label or _unique_label(model, item.kind)
            if label in model.nodes:
                raise HelixCompileError(f"重复节点: {label}")
            node = NodeSpec(label, item.kind, dict(item.args),
                            [], [], item.line)
            model.nodes[label] = node
            model.order.append(label)

            # 顺序默认：前一个节点没有显式箭头，且不是“分支根 →
            # 分支根”的转换时，才连接。分支根仍然可以由 CREATE 或
            # 其他普通节点进入，例如 CREATE -> LOAD。
            if (previous is not None
                    and not (label in branch_roots
                             and previous in branch_roots)):
                model.edges.append(EdgeSpec(previous, label, "DEFAULT"))
                model.nodes[previous].outgoing.append(label)

            if item.outgoing:
                pending_edges.append(
                    EdgeSpec(label, item.outgoing, "EXPLICIT"))
                previous = None
            elif node.kind in ("TERMINATE", "SELECT"):
                # SELECT 的服务台由 servers 列表定义，不能由下一行
                # 顺序默认成唯一后继。
                previous = None
            else:
                previous = label

        elif isinstance(item, IfBlock):
            label = item.label or _unique_label(model, "IF")
            if label in model.nodes:
                raise HelixCompileError(f"重复节点: {label}")
            branches = [(branch.condition, branch.target)
                        for branch in item.branches]
            if item.else_target is None:
                raise HelixCompileError(
                    f"{label}: IF 缺少 ELSE", node=label)
            # ELSE 用 TRUE 条件表示，保证 runtime 的分支循环统一。
            branches.append(("TRUE", item.else_target))
            node = NodeSpec(label, "IF", {}, [], branches, item.line)
            model.nodes[label] = node
            model.order.append(label)

            if previous is not None:
                model.edges.append(EdgeSpec(previous, label, "DEFAULT"))
                model.nodes[previous].outgoing.append(label)

            # IF 的分支由 branches 表达，不参与默认顺序链。
            previous = None

        elif isinstance(item, EdgeDecl):
            pending_edges.append(EdgeSpec(
                item.source, item.target, "EXPLICIT"))
            previous = None

        elif isinstance(item, ParallelBlock):
            label = item.label or _unique_label(model, "PARALLEL")
            if label in model.nodes:
                raise HelixCompileError(f"重复节点: {label}")
            paths = [(None, target) for target in item.paths]
            node = NodeSpec(label, "PARALLEL", {}, [], [], item.line, paths)
            model.nodes[label] = node
            model.order.append(label)
            if previous is not None:
                model.edges.append(EdgeSpec(previous, label, "DEFAULT"))
                model.nodes[previous].outgoing.append(label)
            previous = None

        elif isinstance(item, SplitBlock):
            label = item.label or _unique_label(model, "SPLIT")
            if label in model.nodes:
                raise HelixCompileError(f"重复节点: {label}")
            paths = [(part, item.paths[part]) for part in item.parts]
            node = NodeSpec(label, "SPLIT", {}, [], [], item.line, paths)
            model.nodes[label] = node
            model.order.append(label)
            if previous is not None:
                model.edges.append(EdgeSpec(previous, label, "DEFAULT"))
                model.nodes[previous].outgoing.append(label)
            previous = None

        else:  # pragma: no cover - AST 类型防御
            raise HelixCompileError(f"未知网络项: {item!r}")

    # 所有节点都在 model.nodes 后，再挂显式边，允许前向引用。
    for edge in pending_edges:
        if edge.source not in model.nodes:
            raise HelixCompileError(f"边起点不存在: {edge.source}")
        if edge.target not in model.nodes:
            raise HelixCompileError(f"边终点不存在: {edge.target}")
        if edge.target not in model.nodes[edge.source].outgoing:
            model.nodes[edge.source].outgoing.append(edge.target)
        model.edges.append(edge)
