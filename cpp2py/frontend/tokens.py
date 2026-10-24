"""Token kinds for the cpp2py lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from cpp2py.source import SourceSpan


class TokenKind(Enum):
    # Literals
    INT_LITERAL = auto()
    STRING_LITERAL = auto()

    # Identifiers and keywords
    IDENT = auto()

    # C++ keywords we recognise
    INT = auto()          # 'int'
    VOID = auto()         # 'void'
    RETURN = auto()       # 'return'
    USING = auto()        # 'using'
    NAMESPACE = auto()    # 'namespace'
    IF = auto()           # 'if'
    ELSE = auto()         # 'else'
    WHILE = auto()        # 'while'
    FOR = auto()          # 'for'

    # Unsupported keywords (detected to produce E4001)
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

    # Unsupported type keywords (detected to produce E4002)
    FLOAT = auto()
    DOUBLE = auto()
    CHAR = auto()
    BOOL = auto()
    LONG = auto()
    SHORT = auto()
    UNSIGNED = auto()
    SIGNED = auto()

    # Punctuation / operators
    PLUS = auto()         # +
    MINUS = auto()        # -
    STAR = auto()         # *
    SLASH = auto()        # /
    PERCENT = auto()      # %
    ASSIGN = auto()       # =
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    LBRACE = auto()       # {
    RBRACE = auto()       # }
    SEMI = auto()         # ;
    COMMA = auto()        # ,
    LSHIFT = auto()       # <<
    RSHIFT = auto()       # >>
    SCOPE = auto()        # ::
    HASH = auto()         # # (for preprocessor lines)

    # Unsupported operators (detected to produce E4001)
    PLUS_PLUS = auto()    # ++
    MINUS_MINUS = auto()  # --
    PLUS_EQ = auto()      # +=
    MINUS_EQ = auto()     # -=
    STAR_EQ = auto()      # *=
    SLASH_EQ = auto()     # /=
    PERCENT_EQ = auto()   # %=
    AMP_AMP = auto()      # &&
    PIPE_PIPE = auto()    # ||
    BANG = auto()          # !
    BANG_EQ = auto()      # !=
    LT = auto()           # <
    GT = auto()           # >
    LT_EQ = auto()        # <=
    GT_EQ = auto()        # >=
    EQ_EQ = auto()        # ==
    QUESTION = auto()     # ?
    COLON = auto()        # :

    # Special
    INCLUDE_IOSTREAM = auto()  # the whole '#include <iostream>' directive
    EOF = auto()


# Maps C++ keyword text -> TokenKind
KEYWORDS: dict[str, TokenKind] = {
    'int': TokenKind.INT,
    'return': TokenKind.RETURN,
    'using': TokenKind.USING,
    'namespace': TokenKind.NAMESPACE,
    # Unsupported keywords -> E4001
    'if': TokenKind.IF,
    'else': TokenKind.ELSE,
    'while': TokenKind.WHILE,
    'for': TokenKind.FOR,
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
    # Unsupported type keywords -> E4002
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

# Sets for quick membership testing
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
    """A single lexical token."""
    kind: TokenKind
    text: str
    span: SourceSpan
