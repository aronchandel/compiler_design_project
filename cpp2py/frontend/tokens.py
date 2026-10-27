from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from cpp2py.source import SourceSpan

class TokenKind(Enum):

    INT_LITERAL = auto()
    STRING_LITERAL = auto()

    IDENT = auto()

    INT = auto()
    VOID = auto()
    RETURN = auto()
    USING = auto()
    NAMESPACE = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    NULLPTR = auto()

    DO = auto()
    SWITCH = auto()
    BREAK = auto()
    CONTINUE = auto()
    GOTO = auto()
    CLASS = auto()
    STRUCT = auto()
    NEW = auto()
    DELETE = auto()
    TEMPLATE = auto()
    CONST = auto()
    STATIC = auto()
    AUTO = auto()

    FLOAT = auto()
    DOUBLE = auto()
    CHAR = auto()
    BOOL = auto()
    LONG = auto()
    SHORT = auto()
    UNSIGNED = auto()
    SIGNED = auto()

    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    ASSIGN = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    SEMI = auto()
    COMMA = auto()
    AMP = auto()
    LSHIFT = auto()
    RSHIFT = auto()
    SCOPE = auto()
    HASH = auto()

    PLUS_PLUS = auto()
    MINUS_MINUS = auto()
    PLUS_EQ = auto()
    MINUS_EQ = auto()
    STAR_EQ = auto()
    SLASH_EQ = auto()
    PERCENT_EQ = auto()
    AMP_AMP = auto()
    PIPE_PIPE = auto()
    BANG = auto()
    BANG_EQ = auto()
    LT = auto()
    GT = auto()
    LT_EQ = auto()
    GT_EQ = auto()
    EQ_EQ = auto()
    QUESTION = auto()
    COLON = auto()

    INCLUDE_IOSTREAM = auto()
    INCLUDE_CLIMITS = auto()
    EOF = auto()

KEYWORDS: dict[str, TokenKind] = {
    'int': TokenKind.INT,
    'return': TokenKind.RETURN,
    'using': TokenKind.USING,
    'namespace': TokenKind.NAMESPACE,
    'if': TokenKind.IF,
    'else': TokenKind.ELSE,
    'while': TokenKind.WHILE,
    'for': TokenKind.FOR,
    'nullptr': TokenKind.NULLPTR,

    'do': TokenKind.DO,
    'switch': TokenKind.SWITCH,
    'break': TokenKind.BREAK,
    'continue': TokenKind.CONTINUE,
    'goto': TokenKind.GOTO,
    'class': TokenKind.CLASS,
    'struct': TokenKind.STRUCT,
    'new': TokenKind.NEW,
    'delete': TokenKind.DELETE,
    'template': TokenKind.TEMPLATE,
    'const': TokenKind.CONST,
    'static': TokenKind.STATIC,
    'auto': TokenKind.AUTO,

    'float': TokenKind.FLOAT,
    'double': TokenKind.DOUBLE,
    'char': TokenKind.CHAR,
    'bool': TokenKind.BOOL,
    'long': TokenKind.LONG,
    'short': TokenKind.SHORT,
    'unsigned': TokenKind.UNSIGNED,
    'signed': TokenKind.SIGNED,
    'void': TokenKind.VOID,
}

UNSUPPORTED_KEYWORDS: frozenset[TokenKind] = frozenset({
    TokenKind.DO, TokenKind.SWITCH, TokenKind.BREAK, TokenKind.CONTINUE,
    TokenKind.GOTO, TokenKind.CLASS, TokenKind.STRUCT, TokenKind.NEW,
    TokenKind.DELETE, TokenKind.TEMPLATE, TokenKind.CONST, TokenKind.STATIC,
    TokenKind.AUTO,
})

UNSUPPORTED_TYPE_KEYWORDS: frozenset[TokenKind] = frozenset({
    TokenKind.FLOAT, TokenKind.DOUBLE, TokenKind.CHAR, TokenKind.BOOL,
    TokenKind.SHORT, TokenKind.UNSIGNED, TokenKind.SIGNED,
})

UNSUPPORTED_OPERATORS: frozenset[TokenKind] = frozenset({
    TokenKind.AMP_AMP, TokenKind.PIPE_PIPE, TokenKind.BANG,
    TokenKind.QUESTION, TokenKind.COLON,
})

@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    span: SourceSpan
