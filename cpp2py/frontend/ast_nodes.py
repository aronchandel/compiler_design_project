"""Immutable AST node dataclasses for the cpp2py compiler (Phase 1)."""

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
    name: str  # "int"
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


Expr = Union[IntLiteral, NameExpr, UnaryExpr, BinaryExpr]
OutputItem = Union[Expr, StringLiteral, EndlMarker]


# ---------- statements ----------

@dataclass(frozen=True, slots=True)
class Declarator:
    name: str
    init: Expr | None
    span: SourceSpan
    node_id: int

    def __init__(self, name: str, init: Expr | None, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'init', init)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


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
    target: NameExpr
    op: str  # "="
    value: Expr
    span: SourceSpan
    node_id: int

    def __init__(self, target: NameExpr, op: str, value: Expr, span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'target', target)
        object.__setattr__(self, 'op', op)
        object.__setattr__(self, 'value', value)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())


@dataclass(frozen=True, slots=True)
class InputStmt:
    targets: tuple[NameExpr, ...]
    span: SourceSpan
    qualified: bool = False
    node_id: int = 0

    def __init__(self, targets: tuple[NameExpr, ...], span: SourceSpan, qualified: bool = False, node_id: int | None = None):
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


Stmt = Union[DeclStmt, AssignStmt, InputStmt, OutputStmt, ReturnStmt]


# ---------- top-level ----------

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
class FunctionDef:
    name: str
    return_type: TypeSpec
    params: tuple[()]  # empty in Phase 1
    body: Block
    span: SourceSpan
    node_id: int

    def __init__(self, name: str, return_type: TypeSpec, params: tuple[()],
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

    def __init__(self, functions: tuple[FunctionDef, ...], uses_std: bool,
                 span: SourceSpan, node_id: int | None = None):
        object.__setattr__(self, 'functions', functions)
        object.__setattr__(self, 'uses_std', uses_std)
        object.__setattr__(self, 'span', span)
        object.__setattr__(self, 'node_id', node_id if node_id is not None else _alloc_node_id())

    @property
    def main(self) -> FunctionDef | None:
        for f in self.functions:
            if f.name == 'main':
                return f
        return self.functions[0] if self.functions else None
