from __future__ import annotations

from typing import Any

from cpp2py.ir.model import Opcode
from cpp2py.localisation.ir_interpreter import TraceEntry

def find_first_differing_line(actual: str, expected: str) -> tuple[int, str, str]:
    actual_lines = actual.replace("\r\n", "\n").splitlines(keepends=True)
    expected_lines = expected.replace("\r\n", "\n").splitlines(keepends=True)

    max_len = max(len(actual_lines), len(expected_lines))
    for i in range(max_len):
        act = actual_lines[i] if i < len(actual_lines) else ""
        exp = expected_lines[i] if i < len(expected_lines) else ""
        if act != exp:
            return (i + 1, act, exp)

    return (max_len, "", "")

def find_output_trace_index(trace: list[TraceEntry], target_line: int) -> int:
    current_line = 1
    last_print_idx = -1

    for idx, entry in enumerate(trace):
        if entry.opcode == Opcode.PRINT:
            last_print_idx = idx
            chunk = entry.output_chunk or ""
            new_lines = chunk.count("\n")
            start_line = current_line
            end_line = current_line + new_lines - (1 if chunk.endswith("\n") else 0)
            if start_line <= target_line <= max(start_line, end_line):
                return idx
            current_line += new_lines

    if last_print_idx >= 0:
        return last_print_idx
    return len(trace) - 1 if trace else -1

def compute_backward_slice(
    trace: list[TraceEntry],
    target_trace_idx: int,
) -> dict[str, int]:
    if target_trace_idx < 0 or target_trace_idx >= len(trace):
        return {}

    target_entry = trace[target_trace_idx]
    slice_distances: dict[str, int] = {target_entry.op_id: 0}

    needed_distances: dict[str, int] = {}

    for op_name in target_entry.operand_names:
        if op_name and not op_name.lstrip("-").isdigit():
            needed_distances[op_name] = 0

    for i in range(target_trace_idx - 1, -1, -1):
        entry = trace[i]
        curr_op_id = entry.op_id

        if entry.dst and entry.dst in needed_distances:
            d = needed_distances[entry.dst]
            if curr_op_id not in slice_distances or d + 1 < slice_distances[curr_op_id]:
                slice_distances[curr_op_id] = d + 1

            new_dist = d + 1

            del needed_distances[entry.dst]

            for op_name in entry.operand_names:
                if op_name and not op_name.lstrip("-").isdigit():
                    if op_name not in needed_distances or new_dist < needed_distances[op_name]:
                        needed_distances[op_name] = new_dist

    return slice_distances
