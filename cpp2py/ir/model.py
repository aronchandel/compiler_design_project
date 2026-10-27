from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Union

from cpp2py.source import SourceSpan

class IdAllocator:

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

    alloc_op_id = next_op_id
    alloc_temp_id = next_temp_id
    alloc_region_id = next_region_id

class IRType(Enum):
    I32 = "i32"
    I64 = "i64"
    BOOL = "bool"
    VOID = "void"
    STR = "str"
    PTR = "ptr"

    def __str__(self) -> str:
        return self.value

i32 = IRType.I32
i64 = IRType.I64
bool_type = IRType.BOOL
void_type = IRType.VOID
str_type = IRType.STR
ptr_type = IRType.PTR

@dataclass(frozen=True, slots=True)
class Const:
    value: int
    type: IRType = IRType.I32

    def __str__(self) -> str:
        return str(self.value)

@dataclass(frozen=True, slots=True)
class VarRef:
    symbol_id: int
    ir_name: str
    type: IRType = IRType.I32

    def __str__(self) -> str:
        return self.ir_name

@dataclass(frozen=True, slots=True)
class TempRef:
    temp_id: str
    type: IRType = IRType.I32

    def __str__(self) -> str:
        return self.temp_id

@dataclass(frozen=True, slots=True)
class StrConst:
    text: str
    type: IRType = IRType.STR

    def __str__(self) -> str:
        escaped = self.text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'

@dataclass(frozen=True, slots=True)
class LabelRef:
    name: str

    def __str__(self) -> str:
        return self.name

Operand = Union[Const, VarRef, TempRef, StrConst, LabelRef]

class Opcode(Enum):
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
    CAST = "cast"

    def __str__(self) -> str:
        return self.value

@dataclass(slots=True)
class Instruction:
    op_id: str
    opcode: Opcode
    dst: VarRef | TempRef | None = None
    operands: tuple[Operand, ...] = ()
    span: SourceSpan | None = None
    origin: tuple[int, ...] = ()
    label_name: str | None = None
    role: str | None = None
    region_id: str | None = None
    newline: bool = False
    cmp_op: str | None = None
    func_name: str | None = None

@dataclass(slots=True)
class RegionInfo:
    region_id: str
    kind: str
    span: SourceSpan | None = None
    loop_var: int | None = None
    loop_var_declared_in_init: bool = False

@dataclass(slots=True)
class IRFunction:
    name: str
    params: tuple[VarRef, ...]
    return_type: IRType
    body: list[Instruction] = field(default_factory=list)
    regions: dict[str, RegionInfo] = field(default_factory=dict)

@dataclass(slots=True)
class IRModule:
    functions: list[IRFunction]
    source_name: str = ""
