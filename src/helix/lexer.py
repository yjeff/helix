"""Helix 词法扫描器。

与旧 SLAM 不同，Helix 不再使用分号结束语句：

- 换行结束一条语句；
- 分号后到行尾是注释；
- 括号未闭合时自动续行；
- 语句内 Token 由 :class:`Token` 描述。
"""
from __future__ import annotations

from .errors import HelixSyntaxError
from .tokens import (
    ARROW,
    COLON,
    COMMA,
    EOF,
    EQUAL,
    IDENT,
    LBRACE,
    LBRACKET,
    LPAREN,
    NUMBER,
    OP,
    RBRACE,
    RBRACKET,
    RPAREN,
    STRING,
    Statement,
    Token,
)


_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")", "]", "}"}
_TWO_CHAR_OPS = {"<=", ">=", "==", "!=", "->"}


def _strip_comment(line: str) -> str:
    """删除分号注释，但保留字符串中的分号。"""
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char == ";":
            return line[:index]
    return line


def _scan_depth(text: str) -> int:
    """计算括号净深度，忽略字符串。

    这样 ``BEGN: SELECT(`` 后面的多行参数会被拼成一条语句。
    """
    depth = 0
    quote: str | None = None
    escaped = False
    for char in text:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in _OPEN:
            depth += 1
        elif char in _CLOSE:
            depth -= 1
    return depth


def _tokenize(text: str, *, line: int, source: str) -> list[Token]:
    """把一条语句切成 Token。

    这里不做语法判断，只负责识别词法单元。
    """
    tokens: list[Token] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char.isspace():
            index += 1
            continue

        start = index

        # 字符串使用单引号或双引号，支持反斜杠转义。
        if char in "\"'":
            quote = char
            index += 1
            value_chars: list[str] = []
            escaped = False
            while index < length:
                current = text[index]
                if escaped:
                    value_chars.append(current)
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    index += 1
                    break
                else:
                    value_chars.append(current)
                index += 1
            else:
                raise HelixSyntaxError(
                    "字符串没有结束引号", line=line, col=start + 1,
                    source=source)
            tokens.append(Token(STRING, text[start:index],
                                "".join(value_chars), line, start + 1,
                                len(tokens)))
            continue

        # 标识符/关键字。
        if char.isalpha() or char == "_":
            index += 1
            while index < length and (
                    text[index].isalnum() or text[index] == "_"):
                index += 1
            word = text[start:index]
            tokens.append(Token(IDENT, word, word, line, start + 1,
                                len(tokens)))
            continue

        # 数字，支持小数与指数。
        if char.isdigit() or (
                char == "." and index + 1 < length
                and text[index + 1].isdigit()):
            index += 1
            has_dot = char == "."
            while index < length:
                current = text[index]
                if current.isdigit():
                    index += 1
                elif current == "." and not has_dot:
                    has_dot = True
                    index += 1
                elif current in "eE":
                    index += 1
                    if index < length and text[index] in "+-":
                        index += 1
                else:
                    break
            raw = text[start:index]
            try:
                value = float(raw) if any(
                    c in raw for c in ".eE") else int(raw)
            except ValueError as exc:  # pragma: no cover - 防御
                raise HelixSyntaxError(
                    f"非法数字: {raw}", line=line, col=start + 1,
                    source=source) from exc
            tokens.append(Token(NUMBER, raw, value, line, start + 1,
                                len(tokens)))
            continue

        # 双字符运算符必须先于单字符判断。
        two = text[index:index + 2]
        if two in _TWO_CHAR_OPS:
            index += 2
            kind = ARROW if two == "->" else OP
            tokens.append(Token(kind, two, two, line, start + 1,
                                len(tokens)))
            continue

        single = {
            ":": COLON,
            "=": EQUAL,
            ",": COMMA,
            "(": LPAREN,
            ")": RPAREN,
            "[": LBRACKET,
            "]": RBRACKET,
            "{": LBRACE,
            "}": RBRACE,
        }
        if char in single:
            index += 1
            tokens.append(Token(single[char], char, char, line,
                                start + 1, len(tokens)))
            continue

        if char in "+-*/^<>":
            index += 1
            tokens.append(Token(OP, char, char, line, start + 1,
                                len(tokens)))
            continue

        raise HelixSyntaxError(
            f"无法识别的字符: {char!r}", line=line, col=start + 1,
            source=source)

    tokens.append(Token(EOF, "", None, line, length + 1, len(tokens)))
    return tokens


class Lexer:
    """把源文件切分成逻辑语句和 Token。"""

    def __init__(self, source: str, *, source_name: str = "<string>") -> None:
        self.source = source
        self.source_name = source_name

    def lex(self) -> list[Statement]:
        statements: list[Statement] = []
        buffer: list[str] = []
        start_line = 0
        depth = 0

        for line_no, raw_line in enumerate(self.source.splitlines(), 1):
            line = _strip_comment(raw_line).rstrip()
            if not line.strip() and not buffer:
                continue

            if not buffer:
                start_line = line_no
            buffer.append(line)
            depth += _scan_depth(line)

            if depth < 0:
                raise HelixSyntaxError(
                    "括号不匹配", line=line_no, col=1,
                    source=self.source_name)

            if depth == 0:
                text = " ".join(part.strip() for part in buffer).strip()
                if text:
                    tokens = _tokenize(text, line=start_line,
                                       source=self.source_name)
                    statements.append(Statement(text, start_line, tokens))
                buffer = []

        if buffer:
            raise HelixSyntaxError(
                "文件结束时仍有未闭合的括号", line=start_line,
                col=1, source=self.source_name)
        return statements
