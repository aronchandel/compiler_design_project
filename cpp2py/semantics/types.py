from __future__ import annotations

from dataclasses import dataclass
from typing import Union

@dataclass(frozen=True, slots=True)
class IntType:
    bits: int = 32

    def __str__(self) -> str:
        return "long long" if self.bits > 32 else "int"

@dataclass(frozen=True, slots=True)
class VoidType:
    def __str__(self) -> str:
        return "void"

@dataclass(frozen=True, slots=True)
class BoolType:
    def __str__(self) -> str:
        return "bool"

@dataclass(frozen=True, slots=True)
class ArrayType:
    element_type: Type
    size: int

    def __str__(self) -> str:
        return f"{self.element_type}[{self.size}]"

@dataclass(frozen=True, slots=True)
class PointerType:
    pointee_type: Type

    def __str__(self) -> str:
        return f"{self.pointee_type}*"

@dataclass(frozen=True, slots=True)
class NullptrType:
    def __str__(self) -> str:
        return "nullptr_t"

Type = Union[IntType, VoidType, BoolType, ArrayType, PointerType, NullptrType]
