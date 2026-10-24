"""Data model for the cpp2py Intermediate Representation (IR).

Strict layering rule: this module must NOT import anything from frontend or semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Union

from cpp2py.source import SourceSpan


class IdAllocator:
    """Module-wide monotonic ID allocator for operations, temporaries and regions."""

    def __init__(self) -> None:
        self._op_counter: int = 0
        self._temp_counter: int = 0
        self._region_counter: int = 0

    def next_op_id(self) -> str:
        res = f"op_{self._op_counter}"
        self._op_counter += 1
        return res

    def next_temp_id(self) -> str:
        res = f"t{self._temp_counter}"
        self._temp_counter += 1
        return res

    def next_region_id(self) -> str:
        res = f"r{self._region_counter}"
        self._region_counter += 1
        return res

    # Convenient aliases
    alloc_op_id = next_op_id
    alloc_temp_id = next_temp_id
    alloc_region_id = next_region_id


class IRType(Enum):
    I32 = "i32"
    I64 = "i64"
    BOOL = "bool"
    VOID = "void"
    STR = "str"

    def __str__(self) -> str:
        return self.value


# Short type aliases for convenience
i32 = IRType.I32
i64 = IRType.I64
bool_type = IRType.BOOL
void_type = IRType.VOID
str_type = IRType.STR


@dataclass(frozen=True, slots=True)
class Const:
    """Integer constant operand."""
    value: int
    type: IRType = IRType.I32

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class VarRef:
    """Variable reference operand."""
    symbol_id: int
    ir_name: str
    type: IRType = IRType.I32

    def __str__(self) -> str:
        return self.ir_name


@dataclass(frozen=True, slots=True)
class TempRef:
    """Single-assignment temporary operand."""
    temp_id: str
    type: IRType = IRType.I32

    def __str__(self) -> str:
        return self.temp_id


@dataclass(frozen=True, slots=True)
class StrConst:
    """String constant operand (used only inside print)."""
    text: str
    type: IRType = IRType.STR

    def __str__(self) -> str:
        escaped = self.text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'


@dataclass(frozen=True, slots=True)
class LabelRef:
    """Label reference operand."""
    name: str

    def __str__(self) -> str:
        return self.name


Operand = Union[Const, VarRef, TempRef, StrConst, LabelRef]


class Opcode(Enum):
    """All opcodes defined in ARCH §D.3.4 except cast (which is P5)."""
    DECLARE = "declare"
    ASSIGN = "assign"
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    MOD = "mod"
    NEG = "neg"
    READ = "read"
    PRINT = "print"
    LABEL = "label"
    JUMP = "jump"
    BRANCH = "branch"
    CMP = "cmp"
    CALL = "call"
    RETURN = "return"

    def __str__(self) -> str:
        return self.value


@dataclass(slots=True)
class Instruction:
    """Single IR instruction."""
    op_id: str
    opcode: Opcode
    dst: VarRef | TempRef | None = None
    operands: tuple[Operand, ...] = ()
    span: SourceSpan | None = None
    origin: tuple[str, ...] = ()

    # Specific metadata for control-flow, print, cmp, call
    label_name: str | None = None
    role: str | None = None
    region_id: str | None = None
    newline: bool = False
    cmp_op: str | None = None
    func_name: str | None = None


@dataclass(slots=True)
class RegionInfo:
    """Metadata describing a control-flow region."""
    region_id: str | int
    kind: str  # "if", "while", "for"
    span: SourceSpan | None = None
    loop_var: str | int | None = None
    loop_var_declared_in_init: bool = False


@dataclass(slots=True)
class IRFunction:
    """IR representation of a function."""
    name: str
    params: tuple[VarRef, ...]
    return_type: IRType
    body: list[Instruction] = field(default_factory=list)
    regions: dict[str | int, RegionInfo] = field(default_factory=dict)


@dataclass(slots=True)
class IRModule:
    """Top-level IR container for a compilation unit."""
    functions: list[IRFunction]
    source_name: str = ""
