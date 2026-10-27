"""Immutable AST node dataclasses for the cpp2py compiler (Phase 1, extended for Arrays, Pointers, and <climits>)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from cpp2py.source import SourceSpan


# ---------- base ----------

_next_node_id = 0


def _alloc_node_id() -> int:
    global _next_node_id
    nid = _next_node_id
    _next_node_id += 1
    return nid


def reset_node_ids() -> None:
    """Reset the node ID counter (useful for deterministic tests)."""
    global _next_node_id
    _next_node_id = 0


# ---------- types ----------

@dataclass(frozen=True, slots=True)
class TypeSpec:
    name: str  # "int", "void", "long long"
    span: SourceSpan
    node_id: int

    def __init__(self, name: str, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


# ---------- expressions ----------

@dataclass(frozen=True, slots=True)
class IntLiteral:
    value: int
    span: SourceSpan
    node_id: int

    def __init__(self, value: int, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'value', value)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class NullptrLiteral:
    span: SourceSpan
    node_id: int

    def __init__(self, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class StringLiteral:
    value: str   # already unescaped
    raw: str     # the original text including quotes
    span: SourceSpan
    node_id: int

    def __init__(self, value: str, raw: str, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'value', value)
        object.__setattr__(self, 'raw', raw)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class EndlMarker:
    span: SourceSpan
    qualified: bool = False
    node_id: int = 0

    def __init__(self, span: SourceSpan, qualified: bool = False, node_id: int | None = None):
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'qualified', qualified)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class NameExpr:
    name: str
    span: SourceSpan
    node_id: int

    def __init__(self, name: str, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class UnaryExpr:
    op: str  # "-" or "+"
    operand: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, op: str, operand: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'operand', operand)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class AddressOfExpr:
    operand: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, operand: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'operand', operand)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class DerefExpr:
    operand: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, operand: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'operand', operand)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class IndexExpr:
    array: Expr
    index: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, array: Expr, index: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'array', array)
        object.__setattr__(self, 'index', index)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class InitializerList:
    elements: tuple[Expr, ...]
    span: SourceSpan
    node_id: int

    def __init__(self, elements: tuple[Expr, ...], span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'elements', elements)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class BinaryExpr:
    op: str  # "+" "-" "*" "/" "%"
    left: Expr
    right: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, op: str, left: Expr, right: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'left', left)
        object.__setattr__(self, 'right', right)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class Param:
    type_spec: TypeSpec
    name: str
    span: SourceSpan
    node_id: int
    is_pointer: bool = False
    is_array: bool = False
    array_size: Expr | None = None

    def __init__(self, type_spec: TypeSpec, name: str, span: SourceSpan, node_id: int | None = None,
                 is_pointer: bool = False, is_array: bool = False, array_size: Expr | None = None):
        object.__setattr__(self, 'type_spec', type_spec)
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())
        object.__setattr__(self, 'is_pointer', is_pointer)
        object.__setattr__(self, 'is_array', is_array)
        object.__setattr__(self, 'array_size', array_size)


@dataclass(frozen=True, slots=True)
class CallExpr:
    callee: str
    args: tuple[Expr, ...]
    span: SourceSpan
    node_id: int

    def __init__(self, callee: str, args: tuple[Expr, ...], span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'callee', callee)
        object.__setattr__(self, 'args', args)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class Condition:
    op: str  # "<" "<=" ">" ">=" "==" "!="
    left: Expr
    right: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, op: str, left: Expr, right: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'left', left)
        object.__setattr__(self, 'right', right)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


Expr = Union[
    IntLiteral, NullptrLiteral, NameExpr, UnaryExpr, BinaryExpr, CallExpr,
    IndexExpr, DerefExpr, AddressOfExpr
]
OutputItem = Union[Expr, StringLiteral, EndlMarker]


# ---------- statements ----------

@dataclass(frozen=True, slots=True)
class Declarator:
    name: str
    init: Expr | InitializerList | None
    span: SourceSpan
    node_id: int
    is_pointer: bool = False
    array_size: Expr | None = None

    def __init__(self, name: str, init: Expr | InitializerList | None, span: SourceSpan,
                 node_id: int | None = None, is_pointer: bool = False, array_size: Expr | None = None):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'init', init)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())
        object.__setattr__(self, 'is_pointer', is_pointer)
        object.__setattr__(self, 'array_size', array_size)


@dataclass(frozen=True, slots=True)
class DeclStmt:
    type_spec: TypeSpec
    declarators: tuple[Declarator, ...]
    span: SourceSpan
    node_id: int

    def __init__(self, type_spec: TypeSpec, declarators: tuple[Declarator, ...], span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'type_spec', type_spec)
        object.__setattr__(self, 'declarators', declarators)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class AssignStmt:
    target: NameExpr | IndexExpr | DerefExpr
    op: str  # "="
    value: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, target: NameExpr | IndexExpr | DerefExpr, op: str, value: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'target', target)
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'value', value)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class InputStmt:
    targets: tuple[NameExpr | IndexExpr | DerefExpr, ...]
    span: SourceSpan
    qualified: bool = False
    node_id: int = 0

    def __init__(self, targets: tuple[NameExpr | IndexExpr | DerefExpr, ...], span: SourceSpan, qualified: bool = False, node_id: int | None = None):
        object.__setattr__(self, 'targets', targets)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'qualified', qualified)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class OutputStmt:
    items: tuple[OutputItem, ...]
    span: SourceSpan
    qualified: bool = False
    node_id: int = 0

    def __init__(self, items: tuple[OutputItem, ...], span: SourceSpan, qualified: bool = False, node_id: int | None = None):
        object.__setattr__(self, 'items', items)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'qualified', qualified)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class ReturnStmt:
    value: Expr | None
    span: SourceSpan
    node_id: int

    def __init__(self, value: Expr | None, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'value', value)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class IncDecStmt:
    target: NameExpr | IndexExpr | DerefExpr
    op: str  # "++" or "--"
    is_prefix: bool
    span: SourceSpan
    node_id: int

    def __init__(self, target: NameExpr | IndexExpr | DerefExpr, op: str, is_prefix: bool = False,
                 span: SourceSpan | None = None, node_id: int | None = None):
        object.__setattr__(self, 'target', target)
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'is_prefix', is_prefix)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class CallStmt:
    call: CallExpr
    span: SourceSpan
    node_id: int

    def __init__(self, call: CallExpr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'call', call)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


# Forward declaration for Block as a statement
@dataclass(frozen=True, slots=True)
class Block:
    statements: tuple[Stmt, ...]
    span: SourceSpan
    node_id: int

    def __init__(self, statements: tuple[Stmt, ...], span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'statements', statements)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class IfStmt:
    cond: Condition
    then_body: Stmt
    else_body: Stmt | None
    span: SourceSpan
    node_id: int

    def __init__(self, cond: Condition, then_body: Stmt, else_body: Stmt | None,
                 span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'cond', cond)
        object.__setattr__(self, 'then_body', then_body)
        object.__setattr__(self, 'else_body', else_body)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class WhileStmt:
    cond: Condition
    body: Stmt
    span: SourceSpan
    node_id: int

    def __init__(self, cond: Condition, body: Stmt, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'cond', cond)
        object.__setattr__(self, 'body', body)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class ForStmt:
    init: DeclStmt | AssignStmt | IncDecStmt | None
    cond: Condition
    update: AssignStmt | IncDecStmt | None
    body: Stmt
    span: SourceSpan
    node_id: int

    def __init__(self, init: DeclStmt | AssignStmt | IncDecStmt | None,
                 cond: Condition,
                 update: AssignStmt | IncDecStmt | None,
                 body: Stmt, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'init', init)
        object.__setattr__(self, 'cond', cond)
        object.__setattr__(self, 'update', update)
        object.__setattr__(self, 'body', body)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


Stmt = Union[
    DeclStmt, AssignStmt, IncDecStmt, InputStmt, OutputStmt,
    IfStmt, WhileStmt, ForStmt, ReturnStmt, CallStmt, Block,
]


# ---------- top-level ----------

@dataclass(frozen=True, slots=True)
class FunctionDef:
    name: str
    return_type: TypeSpec
    params: tuple[Param, ...]
    body: Block
    span: SourceSpan
    node_id: int

    def __init__(self, name: str, return_type: TypeSpec, params: tuple[Param, ...],
                 body: Block, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'return_type', return_type)
        object.__setattr__(self, 'params', params)
        object.__setattr__(self, 'body', body)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class Program:
    functions: tuple[FunctionDef, ...]
    uses_std: bool
    span: SourceSpan
    node_id: int
    includes_climits: bool = False

    def __init__(self, functions: tuple[FunctionDef, ...], uses_std: bool,
                 span: SourceSpan, node_id: int | None = None,
                 includes_climits: bool = False):
        object.__setattr__(self, 'functions', functions)
        object.__setattr__(self, 'uses_std', uses_std)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())
        object.__setattr__(self, 'includes_climits', includes_climits)

    @property
    def main(self) -> FunctionDef | None:
        for f in self.functions:
            if f.name == 'main':
                return f
        return self.functions[0] if self.functions else None
