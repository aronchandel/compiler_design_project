from __future__ import annotations

import pytest

from cpp2py.ir.model import Opcode
from cpp2py.localisation.ir_interpreter import TraceEntry
from cpp2py.localisation.slicing import (
    compute_backward_slice,
    find_first_differing_line,
    find_output_trace_index,
)

def test_find_first_differing_line():
    act = "line 1\nline 2 differs\nline 3\n"
    exp = "line 1\nline 2 expected\nline 3\n"
    line_num, l_act, l_exp = find_first_differing_line(act, exp)
    assert line_num == 2
    assert "differs" in l_act
    assert "expected" in l_exp

    act_short = "line 1\n"
    exp_long = "line 1\nline 2\n"
    line_num2, _, _ = find_first_differing_line(act_short, exp_long)
    assert line_num2 == 2

def test_find_output_trace_index():
    trace = [
        TraceEntry(1, "op_0", Opcode.ASSIGN, "a", ("10",), [10], 10, None),
        TraceEntry(2, "op_1", Opcode.PRINT, None, ("a",), [10], "10\n", None, output_chunk="10\n"),
        TraceEntry(3, "op_2", Opcode.ASSIGN, "b", ("20",), [20], 20, None),
        TraceEntry(4, "op_3", Opcode.PRINT, None, ("b",), [20], "20\n", None, output_chunk="20\n"),
    ]

    assert find_output_trace_index(trace, 1) == 1

    assert find_output_trace_index(trace, 2) == 3

def test_backward_slice_hand_built():

    trace = [
        TraceEntry(1, "op_0", Opcode.ASSIGN, "a", ("5",), [5], 5, None),
        TraceEntry(2, "op_1", Opcode.ASSIGN, "b", ("7",), [7], 7, None),
        TraceEntry(3, "op_unrelated", Opcode.ASSIGN, "u", ("100",), [100], 100, None),
        TraceEntry(4, "op_mul", Opcode.MUL, "t0", ("a", "b"), [5, 7], 35, None),
        TraceEntry(5, "op_c", Opcode.ASSIGN, "c", ("t0",), [35], 35, None),
        TraceEntry(6, "op_print", Opcode.PRINT, None, ("c",), [35], "35\n", None, output_chunk="35\n"),
    ]

    slice_distances = compute_backward_slice(trace, target_trace_idx=5)

    assert "op_print" in slice_distances
    assert slice_distances["op_print"] == 0

    assert "op_c" in slice_distances
    assert slice_distances["op_c"] == 1

    assert "op_mul" in slice_distances
    assert slice_distances["op_mul"] == 2

    assert "op_0" in slice_distances
    assert slice_distances["op_0"] == 3

    assert "op_1" in slice_distances
    assert slice_distances["op_1"] == 3

    assert "op_unrelated" not in slice_distances
