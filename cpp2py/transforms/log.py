from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cpp2py.source import SourceSpan, Pos
from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    Const,
    VarRef,
    TempRef,
    StrConst,
    LabelRef,
    Operand,
    IRType,
)
from cpp2py.ir.printer import _format_instruction_body

@dataclass(slots=True)
class TransformRecord:
    seq: int
    pass_name: str
    op_id: str
    kind: str
    before: str | None
    after: str | None
    span: SourceSpan | None = None
    reason: str = ""
    derived_from: list[str] = field(default_factory=list)
    line: int | None = None

    def __post_init__(self) -> None:
        if self.line is None and self.span is not None:
            self.line = self.span.start.line

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "seq": self.seq,
            "pass": self.pass_name,
            "pass_name": self.pass_name,
            "op_id": self.op_id,
            "kind": self.kind,
            "before": self.before,
            "after": self.after,
            "line": self.line,
            "reason": self.reason,
            "derived_from": list(self.derived_from),
        }
        if self.span is not None:
            res["span"] = {
                "file": self.span.file,
                "start": {"line": self.span.start.line, "col": self.span.start.col},
                "end": {"line": self.span.end.line, "col": self.span.end.col},
            }
        else:
            res["span"] = None
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransformRecord:
        span = None
        if data.get("span"):
            s_dict = data["span"]
            span = SourceSpan(
                file=s_dict["file"],
                start=Pos(s_dict["start"]["line"], s_dict["start"]["col"], 0),
                end=Pos(s_dict["end"]["line"], s_dict["end"]["col"], 0),
            )
        pass_name = data.get("pass_name") or data.get("pass", "")
        return cls(
            seq=data["seq"],
            pass_name=pass_name,
            op_id=data["op_id"],
            kind=data["kind"],
            before=data.get("before"),
            after=data.get("after"),
            span=span,
            reason=data.get("reason", ""),
            derived_from=data.get("derived_from", []),
            line=data.get("line"),
        )

class TransformLog:

    def __init__(self, records: list[TransformRecord] | None = None) -> None:
        self.records: list[TransformRecord] = list(records) if records else []
        self._seq = max((r.seq for r in self.records), default=0)

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def add_record(
        self,
        pass_name: str,
        op_id: str,
        kind: str,
        before: str | None,
        after: str | None,
        span: SourceSpan | None,
        reason: str,
        derived_from: list[str] | tuple[str, ...] = (),
    ) -> TransformRecord:
        rec = TransformRecord(
            seq=self.next_seq(),
            pass_name=pass_name,
            op_id=op_id,
            kind=kind,
            before=before,
            after=after,
            span=span,
            reason=reason,
            derived_from=list(derived_from),
        )
        self.records.append(rec)
        return rec

    def write_jsonl(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r.to_dict(), separators=(",", ":")) + "\n" for r in self.records]
        p.write_text("".join(lines), encoding="utf-8")

    @classmethod
    def read_jsonl(cls, path: str | Path) -> TransformLog:
        p = Path(path)
        lines = p.read_text(encoding="utf-8").splitlines()
        records: list[TransformRecord] = []
        for line in lines:
            if line.strip():
                records.append(TransformRecord.from_dict(json.loads(line)))
        return cls(records)

    def replay(self, initial_module: IRModule) -> IRModule:
        mod = copy.deepcopy(initial_module)

        for rec in self.records:

            func_found: IRFunction | None = None
            instr_idx: int = -1
            target_instr: Instruction | None = None

            for func in mod.functions:
                for idx, instr in enumerate(func.body):
                    if instr.op_id == rec.op_id:
                        func_found = func
                        instr_idx = idx
                        target_instr = instr
                        break
                if func_found is not None:
                    break

            if rec.kind == "DELETE":
                if func_found is not None and instr_idx != -1:
                    func_found.body.pop(instr_idx)

            elif rec.kind == "REPLACE":
                if func_found is not None and target_instr is not None and rec.after:
                    opcode, dst, operands = _parse_instruction_body(rec.after, target_instr)
                    target_instr.opcode = opcode
                    target_instr.dst = dst
                    target_instr.operands = operands
                    if rec.derived_from:
                        target_instr.origin = tuple(rec.derived_from)

            elif rec.kind == "INSERT":

                pass

        return mod

def _parse_operand(token: str, ref_instr: Instruction | None = None) -> Operand:
    token = token.strip()
    if token.endswith(","):
        token = token[:-1].strip()

    try:
        val = int(token)
        return Const(val, IRType.I32)
    except ValueError:
        pass

    if token.startswith('"') and token.endswith('"'):
        return StrConst(token[1:-1])

    if token.startswith("t") and token[1:].isdigit():
        return TempRef(token, IRType.I32)

    if (
        token.startswith("loop_head_")
        or token.startswith("loop_body_")
        or token.startswith("loop_end_")
        or token.startswith("if_then_")
        or token.startswith("if_else_")
        or token.startswith("if_end_")
    ):
        return LabelRef(token)

    symbol_id = 0
    var_type = IRType.I32
    if ref_instr is not None:
        if ref_instr.dst and isinstance(ref_instr.dst, VarRef) and ref_instr.dst.ir_name == token:
            symbol_id = ref_instr.dst.symbol_id
            var_type = ref_instr.dst.type
        else:
            for op in ref_instr.operands:
                if isinstance(op, VarRef) and op.ir_name == token:
                    symbol_id = op.symbol_id
                    var_type = op.type
                    break
    return VarRef(symbol_id=symbol_id, ir_name=token, type=var_type)

def _parse_instruction_body(
    text: str, ref_instr: Instruction | None = None
) -> tuple[Opcode, VarRef | TempRef | None, tuple[Operand, ...]]:
    text = text.strip()

    if " = " in text:
        dst_str, rest = text.split(" = ", 1)
        dst_str = dst_str.strip()
        if dst_str.startswith("t") and dst_str[1:].isdigit():
            dst: VarRef | TempRef | None = TempRef(dst_str, IRType.I32)
        else:
            sym_id = 0
            if ref_instr and ref_instr.dst and isinstance(ref_instr.dst, VarRef) and ref_instr.dst.ir_name == dst_str:
                sym_id = ref_instr.dst.symbol_id
            dst = VarRef(sym_id, dst_str, IRType.I32)

        parts = rest.split(None, 1)
        op_name = parts[0]
        args_str = parts[1] if len(parts) > 1 else ""

        if op_name == "assign":
            opcode = Opcode.ASSIGN
            operands = (_parse_operand(args_str, ref_instr),)
        elif op_name in ("add", "sub", "mul", "div", "mod"):
            opcode = Opcode(op_name)
            arg_tokens = [a.strip() for a in args_str.split(",")]
            operands = tuple(_parse_operand(a, ref_instr) for a in arg_tokens)
        elif op_name == "neg":
            opcode = Opcode.NEG
            operands = (_parse_operand(args_str, ref_instr),)
        elif op_name == "cmp":
            opcode = Opcode.CMP
            cmp_parts = args_str.split(None, 1)
            cmp_op = cmp_parts[0]
            arg_tokens = [a.strip() for a in cmp_parts[1].split(",")]
            operands = tuple(_parse_operand(a, ref_instr) for a in arg_tokens)
            if ref_instr:
                ref_instr.cmp_op = cmp_op
        else:
            opcode = Opcode(op_name)
            operands = tuple(_parse_operand(a, ref_instr) for a in args_str.split(",") if a.strip())
        return opcode, dst, operands

    parts = text.split(None, 1)
    op_name = parts[0]
    args_str = parts[1] if len(parts) > 1 else ""

    if op_name == "declare":

        var_name = args_str.split(":")[0].strip()
        return Opcode.DECLARE, None, (_parse_operand(var_name, ref_instr),)
    elif op_name == "print":
        arg_tokens = [a.strip() for a in args_str.split(",")]
        operands = tuple(_parse_operand(a, ref_instr) for a in arg_tokens if a != "endl")
        if ref_instr:
            ref_instr.newline = ("endl" in arg_tokens)
        return Opcode.PRINT, None, operands
    elif op_name == "read":
        return Opcode.READ, None, (_parse_operand(args_str, ref_instr),)
    elif op_name == "return":
        operands = (_parse_operand(args_str, ref_instr),) if args_str else ()
        return Opcode.RETURN, None, operands
    elif op_name == "jump":
        return Opcode.JUMP, None, (LabelRef(args_str),)
    elif op_name == "branch":
        arg_tokens = [a.strip() for a in args_str.split(",")]
        return Opcode.BRANCH, None, tuple(_parse_operand(a, ref_instr) for a in arg_tokens)

    return Opcode(op_name), None, ()
