"""词法单元定义。

Helix 是“按行语句”语言：
- 一条语句通常占一行；
- 括号未闭合时允许续行；
- 分号后是注释。

Token 保存文本、行列和位置，既供 parser 使用，也供 debug 输出。
"""
from __future__ import annotations

from dataclasses import dataclass


# Token 类型使用字符串，便于 DEBUG 直接写出，避免 Enum 序列化成本。
IDENT = "IDENT"
NUMBER = "NUMBER"
STRING = "STRING"
COLON = "COLON"
ARROW = "ARROW"
EQUAL = "EQUAL"
COMMA = "COMMA"
LPAREN = "LPAREN"
RPAREN = "RPAREN"
LBRACKET = "LBRACKET"
RBRACKET = "RBRACKET"
LBRACE = "LBRACE"
RBRACE = "RBRACE"
OP = "OP"
EOF = "EOF"


@dataclass(slots=True)
class Token:
    """一个词法单元。

    Attributes:
        kind: Token 类型。
        text: 原始文本，例如 ``"Q1"``、``"->"``。
        value: 解析后的值；数字为 int/float，字符串去掉引号。
        line: 行号，从 1 开始。
        col: 列号，从 1 开始。
        index: 在所属语句内的序号。
    """

    kind: str
    text: str
    value: object
    line: int
    col: int
    index: int

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"Token({self.kind!r}, {self.text!r}, {self.line}:{self.col})"


@dataclass(slots=True)
class Statement:
    """一条完整的逻辑语句及其 Token。"""

    text: str
    line: int
    tokens: list[Token]
