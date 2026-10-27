from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from cpp2py.source import SourceSpan
from cpp2py.semantics.types import Type, IntType, VoidType, BoolType

class SymbolKind(Enum):
    VARIABLE = auto()
    PARAMETER = auto()
    FUNCTION = auto()
    BUILTIN_IO = auto()
    CONSTANT = auto()

@dataclass(frozen=True, slots=True)
class Symbol:
    symbol_id: int
    name: str
    type: Type | None
    kind: SymbolKind
    decl_span: SourceSpan | None

@dataclass(frozen=True, slots=True)
class FunctionSymbol:
    name: str
    return_type: Type
    params: tuple[Symbol, ...]
    decl_span: SourceSpan

@dataclass
class SemanticInfo:
    symbols_by_node: dict[int, Symbol] = field(default_factory=dict)
    type_by_node: dict[int, Type] = field(default_factory=dict)
    functions: dict[str, FunctionSymbol] = field(default_factory=dict)
    addressed_symbols: set[int] = field(default_factory=set)
    constants: dict[str, int] = field(default_factory=dict)
