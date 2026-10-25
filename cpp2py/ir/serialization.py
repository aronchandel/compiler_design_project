"""JSON serialization and deserialization for the cpp2py Intermediate Representation (IR).

Conforms to ARCH §D.3, §G.3, and Phase 7 AC7.2.
Round-trip invariant: format_module(module_from_json(module_to_json(module))) == format_module(module)
"""

from __future__ import annotations

from typing import Any

from cpp2py.ir.model import (
    Const,
    IRFunction,
    IRModule,
    IRType,
    Instruction,
    LabelRef,
    Opcode,
    Operand,
    RegionInfo,
    StrConst,
    TempRef,
    VarRef,
)
from cpp2py.source import Pos, SourceSpan


def operand_to_json(op: Operand | None) -> dict[str, Any] | None:
    """Serialize an IR Operand to a JSON-compatible dict."""
    if op is None:
        return None
    if isinstance(op, Const):
        return {"kind": "const", "value": op.value, "type": str(op.type)}
    elif isinstance(op, VarRef):
        return {"kind": "var", "name": op.ir_name, "symbol_id": op.symbol_id, "type": str(op.type)}
    elif isinstance(op, TempRef):
        return {"kind": "temp", "temp_id": op.temp_id, "type": str(op.type)}
    elif isinstance(op, StrConst):
        return {"kind": "str", "text": op.text}
    elif isinstance(op, LabelRef):
        return {"kind": "label", "name": op.name}
    return {"kind": "unknown", "text": str(op)}


def operand_from_json(data: dict[str, Any] | None) -> Operand | None:
    """Deserialize an IR Operand from a JSON dict."""
    if data is None:
        return None
    kind = data.get("kind")
    if kind == "const":
        type_str = data.get("type", "i32")
        return Const(value=int(data["value"]), type=IRType(type_str))
    elif kind == "var":
        type_str = data.get("type", "i32")
        name = data.get("name") or data.get("ir_name", "")
        symbol_id = int(data.get("symbol_id", 0))
        return VarRef(symbol_id=symbol_id, ir_name=name, type=IRType(type_str))
    elif kind == "temp":
        type_str = data.get("type", "i32")
        temp_id = data.get("temp_id", "")
        return TempRef(temp_id=temp_id, type=IRType(type_str))
    elif kind == "str":
        return StrConst(text=data.get("text", ""))
    elif kind == "label":
        return LabelRef(name=data.get("name", ""))
    return None


def span_to_json(span: SourceSpan | None) -> dict[str, Any] | None:
    """Serialize a SourceSpan to JSON."""
    if span is None:
        return None
    return {
        "file": span.file,
        "start": {"line": span.start.line, "col": span.start.col, "offset": span.start.offset},
        "end": {"line": span.end.line, "col": span.end.col, "offset": span.end.offset},
    }


def span_from_json(data: dict[str, Any] | None) -> SourceSpan | None:
    """Deserialize a SourceSpan from JSON."""
    if data is None:
        return None
    file = data.get("file", "")
    start_data = data.get("start", {})
    end_data = data.get("end", {})
    start = Pos(
        line=int(start_data.get("line", 1)),
        col=int(start_data.get("col", 1)),
        offset=int(start_data.get("offset", 0)),
    )
    end = Pos(
        line=int(end_data.get("line", 1)),
        col=int(end_data.get("col", 1)),
        offset=int(end_data.get("offset", 0)),
    )
    return SourceSpan(file=file, start=start, end=end)


def region_to_json(region: RegionInfo) -> dict[str, Any]:
    """Serialize a RegionInfo to JSON."""
    res: dict[str, Any] = {
        "region_id": str(region.region_id),
        "kind": region.kind,
        "loop_var_declared_in_init": region.loop_var_declared_in_init,
    }
    if region.loop_var is not None:
        res["loop_var"] = str(region.loop_var)
    if region.span is not None:
        res["span"] = span_to_json(region.span)
    return res


def region_from_json(data: dict[str, Any]) -> RegionInfo:
    """Deserialize a RegionInfo from JSON."""
    return RegionInfo(
        region_id=data.get("region_id", ""),
        kind=data.get("kind", ""),
        span=span_from_json(data.get("span")),
        loop_var=data.get("loop_var"),
        loop_var_declared_in_init=bool(data.get("loop_var_declared_in_init", False)),
    )


def instruction_to_json(instr: Instruction) -> dict[str, Any]:
    """Serialize an Instruction to JSON."""
    res: dict[str, Any] = {
        "op_id": instr.op_id,
        "opcode": instr.opcode.value,
        "dst": str(instr.dst) if instr.dst is not None else None,
        "operands": [operand_to_json(op) for op in instr.operands],
    }
    if instr.dst is not None:
        res["dst_operand"] = operand_to_json(instr.dst)
    if instr.span is not None:
        res["span"] = span_to_json(instr.span)
    if instr.origin:
        res["origin"] = list(instr.origin)
    if instr.label_name is not None:
        res["label_name"] = instr.label_name
    if instr.role is not None:
        res["role"] = instr.role
    if instr.region_id is not None:
        res["region_id"] = str(instr.region_id)
    if instr.newline:
        res["newline"] = instr.newline
    if instr.cmp_op is not None:
        res["cmp_op"] = instr.cmp_op
    if instr.func_name is not None:
        res["func_name"] = instr.func_name
    return res


def instruction_from_json(data: dict[str, Any]) -> Instruction:
    """Deserialize an Instruction from JSON."""
    op_id = data["op_id"]
    opcode = Opcode(data["opcode"])

    dst: VarRef | TempRef | None = None
    if "dst_operand" in data and data["dst_operand"] is not None:
        op = operand_from_json(data["dst_operand"])
        if isinstance(op, (VarRef, TempRef)):
            dst = op
    elif "dst" in data and data["dst"] is not None:
        dst_val = data["dst"]
        if isinstance(dst_val, dict):
            op = operand_from_json(dst_val)
            if isinstance(op, (VarRef, TempRef)):
                dst = op
        elif isinstance(dst_val, str):
            if dst_val.startswith("t") and dst_val[1:].isdigit():
                dst = TempRef(temp_id=dst_val, type=IRType.I32)
            else:
                dst = VarRef(symbol_id=0, ir_name=dst_val, type=IRType.I32)

    raw_operands = data.get("operands", [])
    operands = tuple(operand_from_json(o) for o in raw_operands if o is not None)

    span = span_from_json(data.get("span"))
    origin = tuple(data.get("origin", []))
    label_name = data.get("label_name")
    role = data.get("role")
    region_id = data.get("region_id")
    newline = bool(data.get("newline", False))
    cmp_op = data.get("cmp_op")
    func_name = data.get("func_name")

    return Instruction(
        op_id=op_id,
        opcode=opcode,
        dst=dst,
        operands=operands,  # type: ignore
        span=span,
        origin=origin,
        label_name=label_name,
        role=role,
        region_id=region_id,
        newline=newline,
        cmp_op=cmp_op,
        func_name=func_name,
    )


def function_to_json(func: IRFunction) -> dict[str, Any]:
    """Serialize an IRFunction to JSON."""
    return {
        "name": func.name,
        "return_type": str(func.return_type),
        "params": [str(p) for p in func.params],
        "param_refs": [operand_to_json(p) for p in func.params],
        "body": [instruction_to_json(i) for i in func.body],
        "regions": {str(k): region_to_json(r) for k, r in func.regions.items()},
    }


def function_from_json(data: dict[str, Any]) -> IRFunction:
    """Deserialize an IRFunction from JSON."""
    name = data["name"]
    return_type = IRType(data.get("return_type", "void"))

    params: list[VarRef] = []
    if "param_refs" in data and data["param_refs"]:
        for p_data in data["param_refs"]:
            p = operand_from_json(p_data)
            if isinstance(p, VarRef):
                params.append(p)
    elif "params" in data:
        for idx, p in enumerate(data["params"]):
            if isinstance(p, dict):
                op = operand_from_json(p)
                if isinstance(op, VarRef):
                    params.append(op)
            else:
                params.append(VarRef(symbol_id=idx, ir_name=str(p), type=IRType.I32))

    body = [instruction_from_json(i) for i in data.get("body", [])]

    regions: dict[str | int, RegionInfo] = {}
    if "regions" in data:
        for k, r_data in data["regions"].items():
            regions[k] = region_from_json(r_data)

    return IRFunction(
        name=name,
        params=tuple(params),
        return_type=return_type,
        body=body,
        regions=regions,
    )


def module_to_json(module: IRModule) -> dict[str, Any]:
    """Serialize an IRModule to a JSON dict."""
    return {
        "source_name": module.source_name,
        "functions": [function_to_json(f) for f in module.functions],
    }


def module_from_json(data: dict[str, Any]) -> IRModule:
    """Deserialize an IRModule from a JSON dict."""
    source_name = data.get("source_name", "")
    functions = [function_from_json(f) for f in data.get("functions", [])]
    return IRModule(functions=functions, source_name=source_name)
