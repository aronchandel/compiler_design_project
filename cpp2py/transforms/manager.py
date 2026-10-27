from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Operand,
    IdAllocator,
)
from cpp2py.ir.printer import _format_instruction_body
from cpp2py.ir.verifier import verify_module
from cpp2py.transforms.log import TransformLog

if TYPE_CHECKING:
    from cpp2py.config import CompilerConfig
    from cpp2py.diagnostics import DiagnosticSink
    from cpp2py.ir.snapshots import SnapshotStore

class IRRewriter:

    def __init__(self, log: TransformLog, allocator: IdAllocator) -> None:
        self.log = log
        self.allocator = allocator
        self.current_pass: str = ""
        self.pass_changed: bool = False

    def replace(
        self,
        func: IRFunction,
        instr: Instruction,
        new_instr: Instruction,
        reason: str,
        derived_from: list[str] | tuple[str, ...] = (),
    ) -> None:
        new_instr.op_id = instr.op_id
        new_instr.span = instr.span
        if derived_from:
            new_instr.origin = tuple(derived_from)
        elif instr.origin:
            new_instr.origin = instr.origin

        before_text = _format_instruction_body(instr)
        after_text = _format_instruction_body(new_instr)

        self.log.add_record(
            pass_name=self.current_pass,
            op_id=instr.op_id,
            kind="REPLACE",
            before=before_text,
            after=after_text,
            span=instr.span,
            reason=reason,
            derived_from=derived_from,
        )

        idx = func.body.index(instr)
        func.body[idx] = new_instr
        self.pass_changed = True

    def substitute_operand(
        self,
        func: IRFunction,
        instr: Instruction,
        old_op: Operand,
        new_op: Operand,
        reason: str,
        derived_from: list[str] | tuple[str, ...] = (),
    ) -> None:
        before_text = _format_instruction_body(instr)

        new_operands: list[Operand] = []
        for op in instr.operands:
            if op == old_op:
                new_operands.append(new_op)
            else:
                new_operands.append(op)
        instr.operands = tuple(new_operands)

        if derived_from:
            instr.origin = tuple(derived_from)

        after_text = _format_instruction_body(instr)

        self.log.add_record(
            pass_name=self.current_pass,
            op_id=instr.op_id,
            kind="REPLACE",
            before=before_text,
            after=after_text,
            span=instr.span,
            reason=reason,
            derived_from=derived_from,
        )

        self.pass_changed = True

    def delete(self, func: IRFunction, instr: Instruction, reason: str) -> None:
        before_text = _format_instruction_body(instr)

        self.log.add_record(
            pass_name=self.current_pass,
            op_id=instr.op_id,
            kind="DELETE",
            before=before_text,
            after=None,
            span=instr.span,
            reason=reason,
            derived_from=[],
        )

        func.body.remove(instr)
        self.pass_changed = True

    def insert_before(
        self,
        func: IRFunction,
        anchor: Instruction,
        new_instr: Instruction,
        reason: str,
        derived_from: list[str] | tuple[str, ...] = (),
    ) -> None:
        new_instr.op_id = self.allocator.next_op_id()
        new_instr.span = anchor.span
        if derived_from:
            new_instr.origin = tuple(derived_from)

        after_text = _format_instruction_body(new_instr)

        self.log.add_record(
            pass_name=self.current_pass,
            op_id=new_instr.op_id,
            kind="INSERT",
            before=None,
            after=after_text,
            span=new_instr.span,
            reason=reason,
            derived_from=derived_from,
        )

        idx = func.body.index(anchor)
        func.body.insert(idx, new_instr)
        self.pass_changed = True

    def insert_after(
        self,
        func: IRFunction,
        anchor: Instruction,
        new_instr: Instruction,
        reason: str,
        derived_from: list[str] | tuple[str, ...] = (),
    ) -> None:
        new_instr.op_id = self.allocator.next_op_id()
        new_instr.span = anchor.span
        if derived_from:
            new_instr.origin = tuple(derived_from)

        after_text = _format_instruction_body(new_instr)

        self.log.add_record(
            pass_name=self.current_pass,
            op_id=new_instr.op_id,
            kind="INSERT",
            before=None,
            after=after_text,
            span=new_instr.span,
            reason=reason,
            derived_from=derived_from,
        )

        idx = func.body.index(anchor)
        func.body.insert(idx + 1, new_instr)
        self.pass_changed = True

@dataclass
class PassContext:
    config: CompilerConfig
    sink: DiagnosticSink

class IRPass(Protocol):
    name: str

    def run(self, func: IRFunction, rw: IRRewriter, ctx: PassContext) -> None:
        ...

def _create_allocator_for_module(module: IRModule) -> IdAllocator:
    alloc = IdAllocator()
    max_op = -1
    max_temp = -1
    max_region = -1

    for func in module.functions:
        for instr in func.body:
            if instr.op_id and instr.op_id.startswith("op_"):
                m = re.match(r"op_(\d+)", instr.op_id)
                if m:
                    max_op = max(max_op, int(m.group(1)))
            if instr.dst and hasattr(instr.dst, "temp_id"):
                m = re.match(r"t(\d+)", instr.dst.temp_id)
                if m:
                    max_temp = max(max_temp, int(m.group(1)))
            for op in instr.operands:
                if hasattr(op, "temp_id"):
                    m = re.match(r"t(\d+)", op.temp_id)
                    if m:
                        max_temp = max(max_temp, int(m.group(1)))
        for rid in func.regions:
            m = re.match(r"r?(\d+)", str(rid))
            if m:
                max_region = max(max_region, int(m.group(1)))

    alloc._op_counter = max_op + 1
    alloc._temp_counter = max_temp + 1
    alloc._region_counter = max_region + 1
    return alloc

def run_pipeline(
    module: IRModule,
    passes: list[IRPass],
    config: CompilerConfig,
    sink: DiagnosticSink,
    snapshot_store: Any = None,
    log: TransformLog | None = None,
    allocator: IdAllocator | None = None,
    max_iterations: int = 10,
) -> TransformLog:
    if log is None:
        log = TransformLog()
    if allocator is None:
        allocator = _create_allocator_for_module(module)

    rw = IRRewriter(log=log, allocator=allocator)
    ctx = PassContext(config=config, sink=sink)

    verify_module(module, sink)
    if sink.has_errors():
        return log

    for iteration in range(max_iterations):
        iter_changed = False
        for p in passes:
            rw.current_pass = p.name
            rw.pass_changed = False

            errs_before = sink.error_count()
            verify_module(module, sink)
            if sink.error_count() > errs_before:
                sink.error("E5001", f"IR verification failed before pass '{p.name}'")
                return log

            for func in module.functions:
                p.run(func, rw, ctx)

            errs_after = sink.error_count()
            verify_module(module, sink)
            if sink.error_count() > errs_after:
                sink.error("E5001", f"IR verification failed after pass '{p.name}'")
                return log

            if rw.pass_changed:
                iter_changed = True
                if snapshot_store is not None:
                    snapshot_store.save_pass_snapshot(p.name, module)

        if not iter_changed:
            break
    else:
        sink.warning("W6007", f"Transform pipeline did not reach fixed point after {max_iterations} iterations")

    return log
