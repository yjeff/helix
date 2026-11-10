"""结构化 DEBUG 输出。

设计约束：
- DEBUG 不改变随机数、事件顺序或统计结果；
- 事件逐行写入，避免长仿真占用大量内存；
- tokens/parser 的 DEBUG 由编译阶段单独处理。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .events import Event
from .lexer import Lexer


def write_parse_artifacts(*, source: str, source_name: str,
                          program, model, directory: str | Path) -> None:
    """写出编译期 DEBUG：tokens / parse / ast。

    这些记录只用于语言开发和错误定位，不参与运行。
    """
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)

    statements = Lexer(source, source_name=source_name).lex()
    with (root / "tokens.ndjson").open("w", encoding="utf-8") as handle:
        for statement in statements:
            for token in statement.tokens:
                if token.kind == "EOF":
                    continue
                handle.write(json.dumps({
                    "i": token.index,
                    "type": token.kind,
                    "value": token.value,
                    "line": token.line,
                    "col": token.col,
                }, ensure_ascii=False) + "\n")

    records: list[dict] = [{"seq": 1, "action": "program",
                            "value": "HELIX 1"}]
    sequence = 2
    for declaration in program.declarations:
        record = {"seq": sequence, "action": "declaration",
                  "kind": type(declaration).__name__}
        if hasattr(declaration, "name"):
            record["name"] = declaration.name
        records.append(record)
        sequence += 1
    for item in program.network:
        record = {"seq": sequence, "action": type(item).__name__}
        if hasattr(item, "label"):
            record["label"] = item.label
        if hasattr(item, "kind"):
            record["kind"] = item.kind
        if hasattr(item, "source"):
            record["source"] = item.source
            record["target"] = item.target
        records.append(record)
        sequence += 1

    with (root / "parse.ndjson").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    ast_data = {
        "project": program.project,
        "equations": program.equations,
        "declarations": [
            type(declaration).__name__
            for declaration in program.declarations
        ],
        "network": [
            {
                "type": type(item).__name__,
                "label": getattr(item, "label", None),
                "kind": getattr(item, "kind", None),
            }
            for item in program.network
        ],
    }
    (root / "ast.json").write_text(
        json.dumps(ast_data, ensure_ascii=False, indent=2),
        encoding="utf-8")


class DebugRecorder:
    """把运行元数据、模型快照和事件写成磁盘文件。"""

    def __init__(self, directory: str | Path, *, model, run_info: dict) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._events = (self.directory / "events.ndjson").open(
            "w", encoding="utf-8")
        self._states = (self.directory / "states.ndjson").open(
            "w", encoding="utf-8")
        self._write_json("run.json", run_info)
        self._write_json("model.json", self._model_dict(model))

    @staticmethod
    def _model_dict(model) -> dict:
        """只导出动画/调试需要的图结构，不导出 Python 对象。"""
        return {
            "project": model.project,
            "nodes": [
                {
                    "label": node.label,
                    "kind": node.kind,
                    "args": node.args,
                    "outgoing": node.outgoing,
                    "branches": node.branches,
                }
                for node in model.nodes.values()
            ],
            "edges": [
                {"source": edge.source, "target": edge.target,
                 "kind": edge.kind}
                for edge in model.edges
            ],
        }

    def _write_json(self, name: str, data: Any) -> None:
        path = self.directory / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def record(self, event: Event, *, batch: int) -> None:
        """记录一个已经处理或即将处理的事件。"""
        payload = {
            "t": event.time,
            "seq": event.seq,
            "batch": batch,
            "type": event.kind,
            "entity": event.entity_id,
            "node": event.node,
            "source": event.source,
        }
        payload.update(event.data)
        self._events.write(
            json.dumps(payload, ensure_ascii=False) + "\n")

    def record_state(self, state: dict, *, batch: int,
                     event: str | None = None) -> None:
        """记录事件处理后的状态快照，供动画播放器使用。"""
        payload = {
            "batch": batch,
            "t": state.get("t"),
            "event": event,
        }
        payload.update(state)
        self._states.write(
            json.dumps(payload, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self._events.close()
        self._states.close()

    def __enter__(self) -> "DebugRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
