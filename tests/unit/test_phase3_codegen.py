"""Unit tests for Phase 3 Python code generation.

Covers:
- AC3.7: Hand-built IR with condition that cannot inline -> while True: fallback,
         and verification that stdout matches direct condition.
- AC3.8: Nested-scope shadowing variable renaming (e.g. x vs x_1) and execution equivalence.
- AC3.9: Recursion depth test (depth <= 20 works, near 1000 raises RecursionError / out of contract).
- elif folding
- Compound assignment peepholes (+=, -=, *=, while // and % stay x = x // e)
- pass for empty blocks
"""

import sys
import subprocess
from pathlib import Path
import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.builder import build_ir
from cpp2py.codegen.python_gen import generate
from cpp2py.ir.model import (
    IRModule,
    IRFunction,
    Instruction,
    Opcode,
    Const,
    VarRef,
    TempRef,
    LabelRef,
    IRType,
)


def compile_cpp_to_py(code: str) -> str:
    src = SourceFile("test.cpp", code)
    sink = DiagnosticSink()
    tokens = tokenize(src, sink)
    ast = parse(tokens, sink)
    assert not sink.has_errors()
    config = CompilerConfig()
    info = analyze(ast, config, sink)
    assert not sink.has_errors()
    mod = build_ir(ast, info, config)
    gen_sink = DiagnosticSink()
    return generate(mod, gen_sink, config)


def test_ac3_7_while_true_fallback_and_equivalence(tmp_path):
    """AC3.7: Hand-built IR where loop condition has a CALL -> emits while True: fallback.

    Asserts while True: with break is emitted, and output equals direct condition.
    """
    # 1. Direct condition program in C++
    direct_cpp = """
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
    direct_py = compile_cpp_to_py(direct_cpp)
    assert "while i < 3:" in direct_py
    assert "while True:" not in direct_py

    # 2. Hand-built IR with a call helper inside the condition: check_cond(i)
    # def check_cond(val): return val < 3
    helper_func = IRFunction(
        name="check_cond",
        params=(VarRef(symbol_id=1, ir_name="v", type=IRType.I32),),
        return_type=IRType.BOOL,
        body=[
            Instruction("op_0", Opcode.CMP, dst=TempRef("t0", IRType.BOOL), operands=(VarRef(1, "v"), Const(3)), cmp_op="lt"),
            Instruction("op_1", Opcode.RETURN, operands=(TempRef("t0", IRType.BOOL),)),
        ]
    )

    main_body = [
        Instruction("op_2", Opcode.DECLARE, dst=VarRef(2, "i")),
        Instruction("op_3", Opcode.ASSIGN, dst=VarRef(2, "i"), operands=(Const(0),)),
        Instruction("op_4", Opcode.LABEL, label_name="loop_head_r0", operands=(LabelRef("loop_head_r0"),)),
        Instruction("op_5", Opcode.CALL, dst=TempRef("t1", IRType.BOOL), operands=(VarRef(2, "i"),), func_name="check_cond"),
        Instruction("op_6", Opcode.BRANCH, operands=(TempRef("t1", IRType.BOOL), LabelRef("loop_body_r0"), LabelRef("loop_end_r0"))),
        Instruction("op_7", Opcode.LABEL, label_name="loop_body_r0", operands=(LabelRef("loop_body_r0"),)),
        Instruction("op_8", Opcode.PRINT, operands=(VarRef(2, "i"),), newline=True),
        Instruction("op_9", Opcode.ADD, dst=TempRef("t2", IRType.I32), operands=(VarRef(2, "i"), Const(1))),
        Instruction("op_10", Opcode.ASSIGN, dst=VarRef(2, "i"), operands=(TempRef("t2"),)),
        Instruction("op_11", Opcode.JUMP, label_name="loop_head_r0", operands=(LabelRef("loop_head_r0"),)),
        Instruction("op_12", Opcode.LABEL, label_name="loop_end_r0", operands=(LabelRef("loop_end_r0"),)),
        Instruction("op_13", Opcode.RETURN, operands=(Const(0),)),
    ]
    main_func = IRFunction(name="main", params=(), return_type=IRType.I32, body=main_body)
    mod = IRModule(functions=[helper_func, main_func], source_name="fallback.cpp")

    config = CompilerConfig()
    gen_sink = DiagnosticSink()
    fallback_py = generate(mod, gen_sink, config)

    # Assert fallback is emitted
    assert "while True:" in fallback_py
    assert "if not (t1):" in fallback_py or "if not (check_cond" in fallback_py
    assert "break" in fallback_py

    # Execute both and verify identical stdout
    direct_file = tmp_path / "direct.py"
    direct_file.write_text(direct_py, encoding="utf-8")
    fallback_file = tmp_path / "fallback.py"
    fallback_file.write_text(fallback_py, encoding="utf-8")

    out_direct = subprocess.run([sys.executable, str(direct_file)], capture_output=True, text=True, check=True).stdout
    out_fallback = subprocess.run([sys.executable, str(fallback_file)], capture_output=True, text=True, check=True).stdout

    assert out_direct == out_fallback
    assert out_direct == "0\n1\n2\n"


def test_ac3_8_shadowing_variable_renaming(tmp_path):
    """AC3.8: Nested-scope variable named like outer is renamed and output matches expected."""
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 10;
        cout << x << endl;
        {
            int x = 20;
            cout << x << endl;
            {
                int x = 30;
                cout << x << endl;
            }
            cout << x << endl;
        }
        cout << x << endl;
        return 0;
    }
    """
    py_code = compile_cpp_to_py(code)
    # Check that Python code uses renamed variables
    assert "x_1" in py_code
    assert "x_2" in py_code

    py_file = tmp_path / "shadow.py"
    py_file.write_text(py_code, encoding="utf-8")
    out = subprocess.run([sys.executable, str(py_file)], capture_output=True, text=True, check=True).stdout
    assert out == "10\n20\n30\n20\n10\n"


def test_ac3_9_recursion_depth(tmp_path):
    """AC3.9: Recursion factorial works for <= 20; depth near 1000 is out of contract."""
    code = """
    #include <iostream>
    using namespace std;
    int fact(int n) {
        if (n <= 1) {
            return 1;
        }
        return n * fact(n - 1);
    }
    int main() {
        cout << fact(5) << endl;
        return 0;
    }
    """
    py_code = compile_cpp_to_py(code)
    py_file = tmp_path / "fact.py"
    py_file.write_text(py_code, encoding="utf-8")
    out = subprocess.run([sys.executable, str(py_file)], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "120"

    # Out of contract demonstration: calling depth 1000 causes RecursionError in Python
    deep_code = """
    #include <iostream>
    using namespace std;
    int deep(int n) {
        if (n <= 0) {
            return 0;
        }
        return deep(n - 1);
    }
    int main() {
        cout << deep(1050) << endl;
        return 0;
    }
    """
    deep_py = compile_cpp_to_py(deep_code)
    deep_file = tmp_path / "deep.py"
    deep_file.write_text(deep_py, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(deep_file)], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "RecursionError" in proc.stderr


def test_elif_folding():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 2;
        if (x == 1) {
            cout << 1 << endl;
        } else if (x == 2) {
            cout << 2 << endl;
        } else {
            cout << 3 << endl;
        }
        return 0;
    }
    """
    py_code = compile_cpp_to_py(code)
    assert "elif x == 2:" in py_code


def test_compound_assignment_peepholes():
    code = """
    int main() {
        int x = 10;
        x += 2;
        x -= 3;
        x *= 4;
        x = x / 2;
        x = x % 3;
        return x;
    }
    """
    py_code = compile_cpp_to_py(code)
    assert "x += 2" in py_code
    assert "x -= 3" in py_code
    assert "x *= 4" in py_code
    # div and mod must not use /= or %=
    assert "/=" not in py_code
    assert "%=" not in py_code
    assert "x = x // 2" in py_code
    assert "x = x % 3" in py_code


def test_empty_blocks_emit_pass():
    code = """
    int main() {
        int x = 0;
        while (x < 0) {
        }
        if (x > 0) {
        } else {
        }
        return 0;
    }
    """
    py_code = compile_cpp_to_py(code)
    assert "pass" in py_code
