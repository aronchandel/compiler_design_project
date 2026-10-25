"""Dynamic backward def-use slicing over interpreter execution traces.

Conforms to ARCH §I.2.
"""

from __future__ import annotations

from typing import Any

from cpp2py.ir.model import Opcode
from cpp2py.localisation.ir_interpreter import TraceEntry


def find_first_differing_line(actual: str, expected: str) -> tuple[int, str, str]:
    """Find 1-based line index and contents of the first differing line.

    Returns (line_number, actual_line, expected_line).
    If one is a prefix of the other, returns the line index where one ends.
    """
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
    """Find the trace index of the PRINT operation that produced target_line (1-based)."""
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
    """Compute backward def-use slice from trace[target_trace_idx].

    Returns mapping of op_id -> minimum distance d from output (d >= 0).
    """
    if target_trace_idx < 0 or target_trace_idx >= len(trace):
        return {}

    target_entry = trace[target_trace_idx]
    slice_distances: dict[str, int] = {target_entry.op_id: 0}

    # Track dependencies: name -> distance of the user
    needed_distances: dict[str, int] = {}

    # Seed dependencies with operands of the target entry
    for op_name in target_entry.operand_names:
        if op_name and not op_name.lstrip("-").isdigit():
            needed_distances[op_name] = 0

    # Trace backwards from target_trace_idx - 1 down to 0
    for i in range(target_trace_idx - 1, -1, -1):
        entry = trace[i]
        curr_op_id = entry.op_id

        # Check if entry defines a variable or temp in needed_distances
        if entry.dst and entry.dst in needed_distances:
            d = needed_distances[entry.dst]
            if curr_op_id not in slice_distances or d + 1 < slice_distances[curr_op_id]:
                slice_distances[curr_op_id] = d + 1

            new_dist = d + 1
            # Current definition satisfies the demand for entry.dst
            del needed_distances[entry.dst]
            # Add its operands to needed_distances
            for op_name in entry.operand_names:
                if op_name and not op_name.lstrip("-").isdigit():
                    if op_name not in needed_distances or new_dist < needed_distances[op_name]:
                        needed_distances[op_name] = new_dist

    return slice_distances
