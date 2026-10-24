"""Unit tests for Phase 3 IR builder and IR canonical shapes.

Includes AC3.4 golden IR test matching ARCH §D.4.
"""

import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.ir.printer import format_module, format_instruction
from cpp2py.ir.model import Opcode, IRType


def build_module_from_cpp(code: str):
    source = SourceFile("test.cpp", code)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    ast = parse(tokens, sink)
    assert not sink.has_errors(), f"Parse errors: {sink.diagnostics}"
    config = CompilerConfig()
    info = analyze(ast, config, sink)
    assert not sink.has_errors(), f"Semantic errors: {sink.diagnostics}"
    module = build_ir(ast, info, config)
    return module


def test_ac3_4_golden_while_ir():
    """AC3.4 Golden IR for while loop equals ARCH §D.4 second illustration."""
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int i = 0;
        while (i < 3) {
            cout << i << endl;
            i += 1;
        }
        return 0;
    }
    """
    module = build_module_from_cpp(code)
    func = module.functions[0]
    # Filter to the instructions before return 0
    instructions = func.body[:-1]  # Exclude return 0

    expected_ops = [
        (Opcode.DECLARE, "declare i : i32"),
        (Opcode.ASSIGN, "i = assign 0"),
        (Opcode.LABEL, "loop_head_r0:"),
        (Opcode.CMP, "t0 = cmp lt i, 3"),
        (Opcode.BRANCH, "branch t0, loop_body_r0, loop_end_r0"),
        (Opcode.LABEL, "loop_body_r0:"),
        (Opcode.PRINT, "print i, endl"),
        (Opcode.ADD, "t1 = add i, 1"),
        (Opcode.ASSIGN, "i = assign t1"),
        (Opcode.JUMP, "jump loop_head_r0"),
        (Opcode.LABEL, "loop_end_r0:"),
    ]

    assert len(instructions) == len(expected_ops)
    for instr, (expected_opcode, expected_text_prefix) in zip(instructions, expected_ops):
        assert instr.opcode == expected_opcode
        formatted = format_instruction(instr).strip()
        # Remove op_id and span comment to compare semantic representation
        # Format is: op_<n>  <content>  ; <comment>
        parts = formatted.split(maxsplit=1)[1]  # drop op_<n>
        content = parts.split(";")[0].strip()
        assert content == expected_text_prefix or content.startswith(expected_text_prefix)


def test_if_then_ir_canonical_shape():
    code = """
    int main() {
        int x = 5;
        if (x > 0) {
            x = 10;
        }
        return x;
    }
    """
    module = build_module_from_cpp(code)
    func = module.functions[0]
    opcodes = [instr.opcode for instr in func.body]
    assert Opcode.CMP in opcodes
    assert Opcode.BRANCH in opcodes
    assert Opcode.LABEL in opcodes
    # Verify labels for if_then_r0 and if_end_r0
    labels = [instr.label_name for instr in func.body if instr.opcode == Opcode.LABEL]
    assert "if_then_r0" in labels
    assert "if_end_r0" in labels


def test_if_then_else_ir_canonical_shape():
    code = """
    int main() {
        int x = 5;
        if (x > 0) {
            x = 10;
        } else {
            x = 20;
        }
        return x;
    }
    """
    module = build_module_from_cpp(code)
    func = module.functions[0]
    labels = [instr.label_name for instr in func.body if instr.opcode == Opcode.LABEL]
    assert "if_then_r0" in labels
    assert "if_else_r0" in labels
    assert "if_end_r0" in labels


def test_for_loop_ir_canonical_shape():
    code = """
    int main() {
        int sum = 0;
        for (int i = 0; i < 5; ++i) {
            sum += i;
        }
        return sum;
    }
    """
    module = build_module_from_cpp(code)
    func = module.functions[0]
    labels = [instr.label_name for instr in func.body if instr.opcode == Opcode.LABEL]
    assert "loop_head_r0" in labels
    assert "loop_body_r0" in labels
    assert "loop_end_r0" in labels
    # Verify jump loop_head_r0 is present
    jumps = [instr for instr in func.body if instr.opcode == Opcode.JUMP]
    assert any(j.operands[0].name == "loop_head_r0" for j in jumps)


def test_nested_loops_region_ids():
    code = """
    int main() {
        for (int i = 0; i < 2; ++i) {
            for (int j = 0; j < 3; ++j) {
                int z = i + j;
            }
        }
        return 0;
    }
    """
    module = build_module_from_cpp(code)
    func = module.functions[0]
    labels = [instr.label_name for instr in func.body if instr.opcode == Opcode.LABEL]
    assert "loop_head_r0" in labels
    assert "loop_head_r1" in labels


def test_function_call_ir():
    code = """
    int add(int a, int b) {
        return a + b;
    }
    int main() {
        int x = add(1, 2);
        return x;
    }
    """
    module = build_module_from_cpp(code)
    assert len(module.functions) == 2
    main_func = module.functions[1]
    calls = [instr for instr in main_func.body if instr.opcode == Opcode.CALL]
    assert len(calls) == 1
    assert calls[0].func_name == "add"
    assert len(calls[0].operands) == 2


def test_ir_shadowing_variable_renaming():
    code = """
    int main() {
        int x = 1;
        {
            int x = 2;
            int y = x;
        }
        return x;
    }
    """
    module = build_module_from_cpp(code)
    func = module.functions[0]
    declares = [instr for instr in func.body if instr.opcode == Opcode.DECLARE]
    var_names = [d.dst.ir_name for d in declares]
    assert "x" in var_names
    assert "x_1" in var_names
