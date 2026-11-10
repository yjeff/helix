"""把旧 SLAM 语句转换为 HELIX 1。

这不是完整的 SLAM II 编译器：它复用 slam_v2 的旧解析器，
支持常见声明、连续方程和基础网络节点；无法表达的老语句会
以注释/warning 形式报告，而不是静默改错。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


_SKIP_KINDS = {"GOON", "COLCT", "EVENT", "ACCUM"}


def _load_parser(slam_root: str | Path | None):
    """导入 slam_v2 的旧 SLAM parser。"""
    root = Path(slam_root) if slam_root else (
        Path(__file__).resolve().parents[3] / "slam_v2")
    if not (root / "SLAM" / "parser.py").exists():
        raise FileNotFoundError(
            f"找不到旧 SLAM parser: {root}；请用 --slam-root 指定")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from SLAM.parser import parse_model  # noqa: PLC0415
    return parse_model


class SlamToHelix:
    """旧 Model IR -> HELIX 1 源码。"""

    def __init__(self, model, source_name: str = "<slam>") -> None:
        self.model = model
        self.source_name = source_name
        self.warnings: list[str] = []
        self.names: dict[str, str] = {}
        self.ss_index: dict[str, str] = {}
        self.xx_index: dict[str, str] = {}
        self.attrs: set[str] = set()
        self.extra_vars: dict[str, str] = {}
        for key, short, _label in model.variables:
            self.names[key.upper()] = short
            match = re.fullmatch(r"(SS|XX)\((\d+)\)", key, re.I)
            if match:
                target = (self.ss_index if match.group(1).upper() == "SS"
                          else self.xx_index)
                target[match.group(2)] = short
        self._collect_attrs()

    # ------------------------------------------------------------------
    # 名称与表达式
    # ------------------------------------------------------------------
    def _collect_attrs(self) -> None:
        for node in self.model.nodes.values():
            for assignment in node.fields.get("assignments", []):
                for token in re.findall(r"\b(?:ATRIB|C)\(\d+\)", assignment,
                                        re.I):
                    self._attr_name(token)
            for equation in self.model.equations:
                for token in re.findall(
                        r"\b(?:ATRIB|C)\(\d+\)", equation.expr, re.I):
                    self._attr_name(token)

    def _attr_name(self, token: str) -> str:
        match = re.fullmatch(r"(ATRIB|C)\((\d+)\)", token, re.I)
        assert match is not None
        prefix, index = match.group(1).upper(), match.group(2)
        name = f"{prefix}_{index}"
        self.attrs.add(name)
        self.extra_vars[name] = "ENTITY"
        return name

    def _name_for_key(self, key: str) -> str | None:
        key = key.upper()
        if key in self.names:
            return self.names[key]
        match = re.fullmatch(r"(DD|SS|XX)\((\d+)\)", key)
        if match:
            prefix, index = match.group(1), match.group(2)
            names = (self.ss_index if prefix in ("DD", "SS")
                     else self.xx_index)
            if index in names:
                return names[index]
            generated = f"{prefix}_{index}"
            self.names[key] = generated
            self.extra_vars[generated] = "GLOBAL"
            self.warnings.append(
                f"{key} 没有 VAR 声明，生成变量 {generated}")
            return generated
        return None

    def _expr(self, text: str) -> str:
        def replace(match: re.Match) -> str:
            prefix = match.group(1).upper()
            index = match.group(2)
            token = f"{prefix}({index})"
            if prefix == "ATRIB":
                return self._attr_name(token)
            if prefix == "C":
                return self._attr_name(token)
            name = self._name_for_key(token)
            return name if name else match.group(0)

        result = re.sub(r"\b(SS|XX|ATRIB|C)\((\d+)\)", replace,
                        text, flags=re.I)
        # 旧模型用 T 表示时间；若 T 本身是变量名则不替换。
        if "T" not in self.names.values():
            result = re.sub(r"\bT\b", "TNOW", result)
        if re.search(r"\b(?:SSL|XXL)\([^)]*\)", result, re.I):
            self.warnings.append(f"暂不支持 SSL/XXL 表达式: {text}")
        return result

    # ------------------------------------------------------------------
    # 主转换
    # ------------------------------------------------------------------
    def convert(self) -> str:
        lines: list[str] = [
            "HELIX 1",
            "",
            f"PROJECT \"CONVERTED {Path(self.source_name).name}\"",
            "",
        ]
        lines += self._variables()
        lines += self._continuous()
        lines += self._resources()
        lines += self._equations()
        lines += self._network()
        if self.warnings:
            lines += ["", "; conversion warnings:"] + [
                f";   {warning}" for warning in self.warnings]
        return "\n".join(lines) + "\n"

    def _variables(self) -> list[str]:
        result: list[str] = []
        for _key, short, label in self.model.variables:
            result.append(f"VAR {short} GLOBAL AS \"{label}\"")
        for name, scope in self.extra_vars.items():
            if name not in {short for _k, short, _l in self.model.variables}:
                result.append(f"VAR {name} {scope}")
        return result + ([""] if result else [])

    def _continuous(self) -> list[str]:
        spec = getattr(self.model, "continuous", None)
        if spec is None:
            return []
        return [
            "CONTINUOUS "
            f"METHOD={getattr(spec, 'method', 'RK4')}, "
            f"MIN_STEP={spec.tmin}, "
            f"SAVE_STEP={spec.dtsav}, "
            f"MAX_STEP={spec.dtmax}",
            "",
        ]

    def _resources(self) -> list[str]:
        result: list[str] = []
        for resource in self.model.resources.values():
            result.append(
                f"RESOURCE {resource.label}(capacity={resource.capacity})")
        for gate in self.model.gates.values():
            state = "OPEN" if gate.is_open else "CLOSED"
            result.append(f"GATE {gate.label}({state})")
        return result + ([""] if result else [])

    def _equations(self) -> list[str]:
        result: list[str] = []
        for equation in self.model.equations:
            key = f"{equation.kind}({equation.index})"
            name = self._name_for_key(key)
            if name is None:
                self.warnings.append(f"方程变量无法映射: {key}")
                continue
            result.append(
                f"  {equation.kind}({name}) = {self._expr(equation.expr)}")
        if result:
            result = ["EQUATION"] + result + ["END", ""]
        return result

    def _resolve(self, label: str | None) -> str | None:
        """跳过无 Helix 对应物的旧节点。"""
        seen: set[str] = set()
        while label and label in self.model.nodes:
            if label in seen:
                return None
            seen.add(label)
            node = self.model.nodes[label]
            if node.kind not in _SKIP_KINDS:
                return label
            label = node.next_label
        return label

    def _network(self) -> list[str]:
        result: list[str] = ["NETWORK"]
        for label in self.model.order:
            node = self.model.nodes[label]
            if node.kind in _SKIP_KINDS:
                if node.kind == "COLCT":
                    result.append(
                        f"  ; skipped COLCT {label}: {node.fields.get('id')}")
                elif node.kind == "EVENT":
                    result.append(
                        f"  ; skipped EVENT {label}: code={node.fields.get('code')}")
                elif node.kind == "ACCUM":
                    result.append(f"  ; skipped ACCUM {label}")
                continue
            statement = self._node_statement(node)
            if statement is None:
                continue
            target = self._resolve(node.next_label)
            if target:
                statement += f" -> {target}"
            result.append(f"  {label}: {statement}")
        result.append("END")
        return result

    def _node_statement(self, node) -> str | None:
        kind = node.kind
        fields = node.fields
        if kind == "CREATE":
            args: list[str] = []
            interval = str(fields.get("interval") or "")
            if interval:
                args.append(f"interval={interval}")
            first = fields.get("first")
            if first not in (None, 0, 0.0):
                args.append(f"first={first}")
            maximum = fields.get("max")
            if maximum is not None:
                args.append(f"count={maximum}")
            elif not interval:
                args.append("count=1")
                self.warnings.append(
                    f"{node.label}: 无 interval 的 CREATE 按单实体处理")
            return f"CREATE({', '.join(args)})"

        if kind == "QUEUE":
            args = []
            capacity = fields.get("capacity")
            if capacity not in (None, 0):
                args.append(f"capacity={capacity}")
            balk = fields.get("balk")
            if balk:
                args.append(f"on_full=BALK({self._resolve(balk) or balk})")
            elif fields.get("block"):
                args.append("on_full=BLOCK")
            return f"QUEUE({', '.join(args)})" if args else "QUEUE()"

        if kind == "ACTIVITY":
            duration = str(fields.get("duration") or "")
            rel = fields.get("rel_target")
            if rel:
                return f"ACTIVITY(until={rel})"
            if not duration or duration.upper().startswith("STOPA("):
                self.warnings.append(
                    f"{node.label}: 无 duration 的 ACTIVITY 转为 duration=0")
                duration = "0"
            if fields.get("cond"):
                self.warnings.append(
                    f"{node.label}: 忽略 ACTIVITY 条件 {fields['cond']}")
            servers = fields.get("servers", 1)
            args = [f"duration={self._expr(duration)}"]
            if servers != 1:
                args.append(f"servers={servers}")
            return f"ACTIVITY({', '.join(args)})"

        if kind in ("AWAIT", "FREE"):
            resource = fields.get("resource", "")
            units = fields.get("units", "1")
            args = [f"resource={resource}"]
            if str(units) != "1":
                args.append(f"units={units}")
            return f"{kind}({', '.join(args)})"

        if kind == "ASSIGN":
            assignments = []
            for item in fields.get("assignments", []):
                if "=" not in item:
                    self.warnings.append(f"{node.label}: 无法解析赋值 {item}")
                    continue
                lhs, rhs = item.split("=", 1)
                lhs = self._expr(lhs.strip())
                rhs = self._expr(rhs.strip())
                assignments.append(f"{lhs}={rhs}")
            return f"ASSIGN({', '.join(assignments)})"

        if kind == "TERMINATE":
            return "EXIT()"

        if kind == "DETECT":
            xvar = self._expr(str(fields.get("xvar", "")))
            direction = str(fields.get("xdir", "XN")).upper()
            operator = ">" if direction == "XP" else "<"
            edge = "RISING" if direction == "XP" else "FALLING"
            value = fields.get("value", 0)
            tol = fields.get("tol", 0.01)
            return (f"DETECT(when={xvar} {operator} {value}, "
                    f"edge={edge}, tol={tol})")

        if kind == "PREEMPT":
            self.warnings.append(
                f"{node.label}: PREEMPT 只转换资源，不保证旧优先级语义")
            resource = fields.get("resource", "")
            return f"PREEMPT(resource={resource})"

        if kind == "SELECT":
            self.warnings.append(f"{node.label}: SELECT 暂不支持，已跳过")
            return None

        self.warnings.append(f"{node.label}: 未支持语句 {kind}，已跳过")
        return None


def convert_text(text: str, *, source_name: str = "<string>",
                 slam_root: str | Path | None = None) -> tuple[str, list[str]]:
    """转换旧 SLAM 源码，返回 (Helix 源码, warnings)。"""
    parse_model = _load_parser(slam_root)
    model = parse_model(text, source_name=source_name)
    converter = SlamToHelix(model, source_name=source_name)
    return converter.convert(), converter.warnings


def convert_file(path: str | Path, *, slam_root: str | Path | None = None
                 ) -> tuple[str, list[str]]:
    path = Path(path)
    return convert_text(
        path.read_text(encoding="utf-8"),
        source_name=str(path), slam_root=slam_root)
