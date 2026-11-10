"""Helix parser。

Parser 只把 Statement 转成 AST，不处理：
- 节点存在性
- 默认边生成
- 参数求值
- 语义校验

这些工作由 compiler 完成。
"""
from __future__ import annotations

import re

from .ast import (
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
    WhenBranch,
)
from .errors import HelixSyntaxError
from .lexer import Lexer
from .tokens import Statement


_IDENT = r"[A-Za-z_]\w*"
_NODE_RE = re.compile(
    rf"^(?:(?P<label>{_IDENT})\s*:\s*)?"
    rf"(?P<kind>{_IDENT})\s*(?:\((?P<args>.*)\))?$",
    re.S,
)
_EDGE_RE = re.compile(
    rf"^(?P<source>{_IDENT})\s*(?:->|(?i:GOTO))\s*(?P<target>{_IDENT})$")
_VAR_RE = re.compile(
    rf"^VAR\s+(?P<name>{_IDENT})"
    rf"(?:\[(?P<size>[1-9][0-9]*)\])?"
    rf"(?:\s+(?P<scope>(?i:ENTITY|GLOBAL)))?"
    rf"(?:\s+AS\s+(?P<label>\"[^\"]*\"|'[^']*'))?"
    rf"(?:\s+RANGE\s+(?P<low>[-+0-9.eE]+)\s*\.\.\s*"
    rf"(?P<high>[-+0-9.eE]+))?$",
    re.S | re.I,
)


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _split_top_level(text: str, delimiter: str = ",") -> list[str]:
    """按顶层分隔符切分，忽略括号/方括号/花括号内部。"""
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False

    for char in text:
        if quote:
            buffer.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            buffer.append(char)
        elif char in "([{":
            depth += 1
            buffer.append(char)
        elif char in ")]}":
            depth -= 1
            buffer.append(char)
        elif char == delimiter and depth == 0:
            parts.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
    if "".join(buffer).strip():
        parts.append("".join(buffer).strip())
    return parts


def _find_transition(text: str) -> tuple[int, int] | None:
    """返回顶层转移符的位置和长度。

    支持两种写法：
      -> TARGET
      GOTO TARGET
    """
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0:
            if text.startswith("->", index):
                return index, 2
            if text[index:index + 4].upper() == "GOTO":
                before = text[index - 1] if index else " "
                after = text[index + 4] if index + 4 < len(text) else " "
                if not (before.isalnum() or before == "_") and \
                        not (after.isalnum() or after == "_"):
                    return index, 4
        index += 1
    return None


def _find_top_arrow(text: str) -> int:
    """兼容旧调用：只返回转移符起始位置。"""
    found = _find_transition(text)
    return -1 if found is None else found[0]


def _split_transition(text: str) -> tuple[str, str] | None:
    found = _find_transition(text)
    if found is None:
        return None
    index, length = found
    return text[:index].strip(), text[index + length:].strip()


def _parse_kv_args(text: str, preserve_keys: bool = False) -> dict[str, str]:
    """解析 ``name=value`` 参数列表，value 保留原始表达式文本。

    preserve_keys=True 用于 ASSIGN：赋值目标可能是区分大小写的
    VAR 名称，不能统一转小写。
    """
    result: dict[str, str] = {}
    for item in _split_top_level(text):
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"参数格式应为 name=value: {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        key_pattern = (
            rf"{_IDENT}(?:\[[^\[\]]+\])?"
            if preserve_keys else _IDENT
        )
        if not re.fullmatch(key_pattern, key):
            raise ValueError(f"非法参数名: {key!r}")
        result[key if preserve_keys else key.lower()] = value.strip()
    return result


def _parse_list(text: str) -> list[str]:
    """解析 ``[A, B, C]`` 形式的标识符列表。"""
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError(f"列表格式错误: {text!r}")
    inner = text[1:-1].strip()
    if not inner:
        return []
    items = [item.strip() for item in _split_top_level(inner)]
    for item in items:
        if not re.fullmatch(_IDENT, item):
            raise ValueError(f"列表项必须是标识符: {item!r}")
    return items


def _split_block_label(text: str, keyword: str) -> tuple[str | None, str]:
    """拆出 ``LABEL: KEYWORD`` 中的标签，返回 (label, rest)。

    rest 保留关键字本身，便于调用方按完整头部语法解析。
    """
    if ":" in text:
        prefix, rest = text.split(":", 1)
        if re.fullmatch(_IDENT, prefix.strip()):
            return prefix.strip(), rest.strip()
    return None, text.strip()


def _parse_continuous(text: str) -> ContinuousDecl:
    body = text[len("CONTINUOUS"):].strip()
    args = _parse_kv_args(body) if body else {}
    decl = ContinuousDecl()
    for key, value in args.items():
        if key == "method":
            decl.method = value.upper()
        elif key == "min_step":
            decl.min_step = float(value)
        elif key == "save_step":
            decl.save_step = float(value)
        elif key == "max_step":
            decl.max_step = float(value)
        elif key == "tol":
            decl.tol = float(value)
        else:
            raise ValueError(f"CONTINUOUS 未知字段: {key}")
    return decl


class Parser:
    """递归下降/语句驱动 parser。"""

    def __init__(self, source: str, *, source_name: str = "<string>") -> None:
        self.source = source
        self.source_name = source_name
        self.statements = Lexer(source, source_name=source_name).lex()
        self.index = 0
        self.program = Program(version="2")

    # ------------------------------------------------------------------
    # 基础游标
    # ------------------------------------------------------------------
    def _peek(self) -> Statement | None:
        if self.index >= len(self.statements):
            return None
        return self.statements[self.index]

    def _pop(self) -> Statement:
        statement = self.statements[self.index]
        self.index += 1
        return statement

    def _error(self, message: str, statement: Statement | None = None) -> None:
        line = statement.line if statement else 0
        raise HelixSyntaxError(message, line=line, col=1,
                              source=self.source_name)

    # ------------------------------------------------------------------
    # 顶层
    # ------------------------------------------------------------------
    def parse(self) -> Program:
        if not self.statements:
            self._error("空模型")
        first = self._pop()
        if first.text.upper() != "HELIX 1":
            self._error("模型必须以 'HELIX 1' 开始", first)

        while True:
            statement = self._peek()
            if statement is None:
                break
            parts = statement.text.split(None, 1)
            keyword = parts[0].upper() if parts else ""

            if keyword == "PROJECT":
                self._pop()
                self.program.project = _unquote(parts[1] if len(parts) > 1 else "")
            elif keyword == "VAR":
                self._pop()
                self.program.declarations.append(self._parse_var(statement))
            elif keyword == "ATTR":
                self._error(
                    "ATTR 已整合为 VAR NAME ENTITY", statement)
            elif keyword == "CONTINUOUS":
                self._pop()
                try:
                    self.program.declarations.append(
                        _parse_continuous(statement.text))
                except ValueError as exc:
                    self._error(str(exc), statement)
            elif keyword == "RESOURCE":
                self._pop()
                self.program.declarations.append(self._parse_resource(statement))
            elif keyword == "GATE":
                self._pop()
                self.program.declarations.append(self._parse_gate(statement))
            elif keyword == "DETECT":
                self._pop()
                self.program.declarations.append(self._parse_detect(statement))
            elif keyword == "SEVNT":
                self._pop()
                self.program.declarations.append(self._parse_sevnt(statement))
            elif keyword == "EQUATION":
                self._parse_equation()
            elif keyword == "NETWORK":
                self._parse_network()
            else:
                self._error(f"无法识别的顶层语句: {statement.text!r}",
                            statement)
        return self.program

    # ------------------------------------------------------------------
    # 顶层声明
    # ------------------------------------------------------------------
    def _parse_var(self, statement: Statement) -> VarDecl:
        match = _VAR_RE.match(statement.text)
        if not match:
            self._error(f"VAR 语法错误: {statement.text!r}", statement)
        name = match.group("name")
        label = _unquote(match.group("label")) if match.group("label") else name
        low = float(match.group("low")) if match.group("low") else None
        high = float(match.group("high")) if match.group("high") else None
        scope = match.group("scope").upper() if match.group("scope") else None
        size = int(match.group("size")) if match.group("size") else 0
        return VarDecl(name, label, low, high, scope, size, statement.line)

    def _parse_resource(self, statement: Statement) -> ResourceDecl:
        match = re.match(
            rf"^RESOURCE\s+(?P<name>{_IDENT})\s*(?:\((?P<args>.*)\))?$",
            statement.text, re.S | re.I)
        if not match:
            self._error(f"RESOURCE 语法错误: {statement.text!r}", statement)
        raw_args = (match.group("args") or "").strip()
        if raw_args and "=" not in raw_args:
            args = {"capacity": raw_args}
        else:
            args = _parse_kv_args(raw_args)
        mode = args.get("mode", "POOL").strip().upper()
        if mode not in ("POOL", "RESTOCK"):
            self._error(
                f"RESOURCE mode 必须是 POOL 或 RESTOCK: {mode}", statement)
        return ResourceDecl(
            match.group("name"), int(args.get("capacity", 1)),
            statement.line, mode)

    def _parse_gate(self, statement: Statement) -> GateDecl:
        match = re.match(
            rf"^GATE\s+(?P<name>{_IDENT})\s*(?:\((?P<args>.*)\))?$",
            statement.text, re.S | re.I)
        if not match:
            self._error(f"GATE 语法错误: {statement.text!r}", statement)
        raw_args = (match.group("args") or "").strip()
        if raw_args and "=" not in raw_args:
            args = {"state": raw_args}
        else:
            args = _parse_kv_args(raw_args)
        return GateDecl(
            match.group("name"), args.get("state", "CLOSED").upper(),
            statement.line)

    def _parse_detect(self, statement: Statement) -> DetectDecl:
        body = statement.text[len("DETECT"):].strip()
        args = _parse_kv_args(body)
        if "name" not in args or "when" not in args:
            self._error("DETECT 需要 name 和 when", statement)
        return DetectDecl(
            args["name"].strip("\"'"), args["when"],
            args.get("edge", "RISING").upper(),
            float(args.get("tol", 0.01)), statement.line)

    def _parse_sevnt(self, statement: Statement) -> SevntDecl:
        body = statement.text[len("SEVNT"):].strip()
        args = _parse_kv_args(body)
        if "code" not in args or "when" not in args:
            self._error("SEVNT 需要 code 和 when", statement)
        name = args.get("name", "").strip().strip("\"'")
        if name and not re.fullmatch(_IDENT, name):
            self._error("SEVNT name 必须是标识符", statement)
        action = args.get("action", "").strip()
        if action and not re.fullmatch(_IDENT, action):
            self._error("SEVNT action 必须是节点标签", statement)
        return SevntDecl(
            int(args["code"]), args["when"], name, action, statement.line)

    def _parse_equation(self) -> None:
        self._pop()  # EQUATION
        while True:
            statement = self._peek()
            if statement is None:
                self._error("EQUATION 缺少 END")
            if statement.text.upper() in ("END", "END EQUATION"):
                self._pop()
                return
            self.program.equations.append(self._pop().text)

    # ------------------------------------------------------------------
    # 网络
    # ------------------------------------------------------------------
    def _parse_network(self) -> None:
        start = self._pop()  # NETWORK
        while True:
            statement = self._peek()
            if statement is None:
                self._error("NETWORK 缺少 END", start)
            if statement.text.upper() in ("END", "END NETWORK"):
                self._pop()
                return

            upper = statement.text.upper()
            if upper == "PARALLEL" or re.match(
                    rf"^{_IDENT}\s*:\s*PARALLEL$", statement.text, re.I):
                self.program.network.append(self._parse_parallel())
            elif upper.startswith("SPLIT") or re.match(
                    rf"^{_IDENT}\s*:\s*SPLIT\b", statement.text, re.I):
                self.program.network.append(self._parse_split())
            elif upper.startswith("SCAN ") or re.match(
                    rf"^{_IDENT}\s*:\s*SCAN\b", statement.text, re.I):
                self.program.network.append(self._parse_scan())
            elif upper.startswith("IF ") or re.match(
                    rf"^{_IDENT}\s*:\s*IF\b", statement.text, re.I):
                self.program.network.append(self._parse_if())
            elif re.match(r"^(?:->|(?i:GOTO)\s+)", statement.text):
                # 上一行节点的显式跳转：
                #   ACTIVITY(...)
                #     -> Q1
                #     GOTO Q1
                split = _split_transition(statement.text)
                head = split[0] if split else ""
                target = split[1] if split else ""
                if head:
                    self._error("独立跳转行不能带节点内容", statement)
                if not re.fullmatch(_IDENT, target):
                    self._error("->/GOTO 后必须是节点标签", statement)
                previous = self.program.network[-1] if self.program.network else None
                if not isinstance(previous, NodeDecl):
                    self._error("->/GOTO 前面没有可连接的节点", statement)
                if previous.outgoing is not None:
                    self._error("节点只能有一个显式转移", statement)
                previous.outgoing = target
                self._pop()
            elif re.match(
                    rf"^{_IDENT}\s*(?:->|(?i:GOTO))\s*{_IDENT}$",
                    statement.text):
                self.program.network.append(self._parse_edge())
            else:
                self.program.network.append(self._parse_node())

    def _parse_edge(self) -> EdgeDecl:
        statement = self._pop()
        match = _EDGE_RE.match(statement.text)
        assert match is not None
        return EdgeDecl(match.group("source"), match.group("target"),
                        statement.line)

    def _parse_scan(self) -> NodeDecl:
        header = self._pop()
        label, text = _split_block_label(header.text, "SCAN")
        match = re.match(
            rf"^SCAN\s+(?P<var>{_IDENT})\s+IN\s+"
            r"(?P<start>[-+]?\d+)\s*\.\.\s*(?P<end>[-+]?\d+)$",
            text, re.I)
        if not match:
            self._error("SCAN 头部应为 SCAN i IN 1..n", header)
        args = {
            "var": match.group("var"),
            "start": match.group("start"),
            "end": match.group("end"),
        }
        while True:
            statement = self._peek()
            if statement is None:
                self._error("SCAN 缺少 END SCAN", header)
            upper = statement.text.upper()
            if upper == "END SCAN":
                self._pop()
                break
            if upper.startswith("WHERE "):
                args["where"] = statement.text[6:].strip()
            elif upper.startswith("DO "):
                previous = args.get("do", "")
                args["do"] = (previous + "\n" +
                              statement.text[3:].strip()).strip()
            elif upper == "STOP":
                args["stop"] = "FIRST"
            else:
                self._error("SCAN 内部只能是 WHERE/DO/STOP", statement)
            self._pop()
        return NodeDecl(label, "SCAN", args, header.line, None)

    def _parse_node(self) -> NodeDecl:
        statement = self._pop()
        # 先拆出 label: body，避免正则对复杂括号回溯。
        text = statement.text
        label: str | None = None
        colon = text.find(":")
        if colon != -1:
            possible = text[:colon].strip()
            if re.fullmatch(_IDENT, possible):
                label = possible
                text = text[colon + 1:].strip()

        # 支持节点和转移写在同一行：
        #   ACTIVITY(...) -> Q1
        #   ACTIVITY(...) GOTO Q1
        outgoing: str | None = None
        split = _split_transition(text)
        if split is not None:
            text, outgoing = split
            if not re.fullmatch(_IDENT, outgoing):
                self._error("->/GOTO 后必须是节点标签", statement)

        match = re.match(
            rf"^(?P<kind>{_IDENT})\s*(?:\((?P<args>.*)\))?$",
            text, re.S)
        if not match:
            self._error(f"网络语句无法解析: {statement.text!r}", statement)
        kind = match.group("kind").upper()
        # EXIT() 是 TERMINATE() 的短别名。
        if kind == "EXIT":
            kind = "TERMINATE"
        raw_args = (match.group("args") or "").strip()
        try:
            if raw_args and "=" not in raw_args:
                # 常用单参数简写：
                #   ACTIVITY(5)  -> duration=5
                #   AWAIT(DOCK)  -> resource=DOCK
                #   FREE(DOCK)   -> resource=DOCK
                if kind == "ACTIVITY":
                    args = {"duration": raw_args}
                elif kind in ("AWAIT", "FREE"):
                    args = {"resource": raw_args}
                elif kind == "QUEUE":
                    args = {"capacity": raw_args}
                elif kind == "CREATE":
                    args = {"interval": raw_args}
                elif kind == "OBSERVE":
                    parts = _split_top_level(raw_args)
                    if len(parts) != 2:
                        raise ValueError(
                            "OBSERVE 简写需要 name, value 两个参数")
                    args = {"name": parts[0], "value": parts[1]}
                else:
                    args = _parse_kv_args(
                        raw_args, preserve_keys=(kind == "ASSIGN"))
            else:
                args = _parse_kv_args(
                    raw_args,
                    preserve_keys=(kind == "ASSIGN"),
                )
        except ValueError as exc:
            self._error(str(exc), statement)
        return NodeDecl(label, kind, args, statement.line, outgoing)

    def _parse_if(self) -> IfBlock:
        header = self._pop()
        text = header.text
        label: str | None = None
        if ":" in text:
            prefix, rest = text.split(":", 1)
            if re.fullmatch(_IDENT, prefix.strip()):
                label = prefix.strip()
                text = rest.strip()
        if not text.upper().startswith("IF "):
            self._error(
                "IF 头部应为：IF condition -> target", header)
        first = text[3:].strip()
        split = _split_transition(first)
        if split is None:
            self._error("IF 缺少 ->/GOTO 目标", header)
        condition, target = split
        branches: list[WhenBranch] = [
            WhenBranch(condition, target, header.line)]

        else_target: str | None = None
        while True:
            statement = self._peek()
            if statement is None:
                self._error("IF 缺少 ELSE 分支", header)
            line = statement.text
            upper = line.upper()
            if upper.startswith("ELSE IF "):
                self._pop()
                split = _split_transition(line[8:].strip())
                if split is None:
                    self._error("ELSE IF 缺少 ->/GOTO 目标", statement)
                condition, target = split
                branches.append(WhenBranch(
                    condition, target, statement.line))
                continue
            if upper.startswith("ELSE"):
                self._pop()
                split = _split_transition(line[4:].strip())
                if split is None:
                    self._error("ELSE 缺少 ->/GOTO 目标", statement)
                head, target = split
                if head:
                    self._error("ELSE 不能带条件", statement)
                else_target = target
                break
            self._error("IF 中只能出现 ELSE IF 或 ELSE", statement)

        return IfBlock(label, branches, else_target, header.line)

    def _parse_parallel(self) -> ParallelBlock:
        header = self._pop()
        label, rest = _split_block_label(header.text, "PARALLEL")
        if rest.upper() != "PARALLEL":
            self._error(f"PARALLEL 头部语法错误: {header.text!r}", header)

        paths: list[str] = []
        while True:
            statement = self._peek()
            if statement is None:
                self._error("PARALLEL 缺少 END PARALLEL", header)
            if statement.text.upper() == "END PARALLEL":
                self._pop()
                break
            text = statement.text
            if not text.upper().startswith("PATH"):
                self._error(
                    f"PARALLEL 内只能是 PATH: {text!r}", statement)
            self._pop()
            body = text[4:].strip()
            split = _split_transition(body)
            if split is not None:
                head, body = split
                if head:
                    self._error("PATH 不能带额外内容", statement)
            if not re.fullmatch(_IDENT, body):
                self._error("PATH 目标必须是节点标签", statement)
            paths.append(body)

        return ParallelBlock(label, paths, header.line)

    def _parse_split(self) -> SplitBlock:
        header = self._pop()
        label, rest = _split_block_label(header.text, "SPLIT")
        match = re.fullmatch(r"SPLIT\s*\((.*)\)", rest, re.S | re.I)
        if not match:
            self._error(f"SPLIT 头部语法错误: {header.text!r}", header)
        try:
            args = _parse_kv_args(match.group(1))
            parts = _parse_list(args["parts"])
        except (KeyError, ValueError) as exc:
            self._error(f"SPLIT parts 错误: {exc}", header)

        paths: dict[str, str] = {}
        while True:
            statement = self._peek()
            if statement is None:
                self._error("SPLIT 缺少 END SPLIT", header)
            if statement.text.upper() == "END SPLIT":
                self._pop()
                break
            text = statement.text
            if not text.upper().startswith("PATH"):
                self._error(f"SPLIT 内只能是 PATH: {text!r}", statement)
            self._pop()
            body = text[4:].strip()
            match = re.fullmatch(
                rf"({_IDENT})\s*(?:->|(?i:GOTO))\s*({_IDENT})", body)
            if not match:
                self._error(
                    "SPLIT PATH 格式应为：PATH part -> target", statement)
            part, target = match.group(1), match.group(2)
            if part not in parts:
                self._error(f"SPLIT PATH 引用了未声明的 part: {part}",
                            statement)
            paths[part] = target

        missing = [part for part in parts if part not in paths]
        if missing:
            self._error(
                f"SPLIT 缺少 PATH: {', '.join(missing)}", header)
        return SplitBlock(label, parts, paths, header.line)


def parse(source: str, *, source_name: str = "<string>") -> Program:
    """便捷入口。"""
    # Windows 编辑器可能写入 UTF-8 BOM；它不是模型内容。
    source = source.lstrip("\ufeff")
    return Parser(source, source_name=source_name).parse()
