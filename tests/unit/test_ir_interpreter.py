from __future__ import annotations

import pytest

from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, OverflowPolicy, TargetModel
from cpp2py.ir.model import (
    Const,
    IRFunction,
    IRModule,
    IRType,
    Instruction,
    LabelRef,
    Opcode,
    StrConst,
    TempRef,
    VarRef,
)
from cpp2py.localisation.ir_interpreter import (
    IRInterpreter,
    cpp_div,
    cpp_mod,
    interpret_module,
    wrap_int,
)

def test_arithmetic_basic():
    cpp_code = """
    int main() {
        int a = 10, b = 3;
        std::cout << a + b << " " << a - b << " " << a * b << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp")
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir)
    assert interp_res.success
    assert interp_res.stdout == "13 7 30\n"
    assert interp_res.exit_code == 0

def test_division_and_mod_signs():
    assert cpp_div(-7, 2) == -3
    assert cpp_div(7, -2) == -3
    assert cpp_div(-7, -2) == 3
    assert cpp_mod(-7, 2) == -1
    assert cpp_mod(7, -2) == 1
    assert cpp_mod(-7, -2) == -1

    cpp_code = """
    int main() {
        int a = -7, b = 2;
        int c = 7, d = -2;
        std::cout << a / b << " " << a % b << " "
                  << c / d << " " << c % d << " "
                  << a / d << " " << a % d << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp")
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir)
    assert interp_res.success
    assert interp_res.stdout == "-3 -1 -3 1 3 -1\n"

def test_overflow_policy_wrap():
    cpp_code = """
    int main() {
        int x = 2147483647;
        x = x + 1;
        std::cout << x << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp", CompilerConfig(fold_constants=False))
    assert res.success and res.ir is not None

    interp_wrap = interpret_module(res.ir, overflow_policy=OverflowPolicy.WRAP)
    assert interp_wrap.success
    assert interp_wrap.stdout == "-2147483648\n"

def test_overflow_policy_trap():
    cpp_code = """
    int main() {
        int x = 2147483647;
        x = x + 1;
        std::cout << x << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp", CompilerConfig(fold_constants=False))
    assert res.success and res.ir is not None

    interp_trap = interpret_module(res.ir, overflow_policy=OverflowPolicy.TRAP)
    assert not interp_trap.success
    assert "signed overflow in add" in interp_trap.error

def test_overflow_policy_assume_no_overflow():
    cpp_code = """
    int main() {
        int x = 2147483647;
        x = x + 1;
        std::cout << x << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp", CompilerConfig(fold_constants=False))
    assert res.success and res.ir is not None

    interp_ano = interpret_module(res.ir, overflow_policy=OverflowPolicy.ASSUME_NO_OVERFLOW)
    assert interp_ano.success
    assert len(interp_ano.ub_events) >= 1
    assert "signed overflow" in interp_ano.ub_events[0]

def test_int_min_division_overflow():
    cpp_code = """
    int main() {
        int a = -2147483647 - 1;
        int b = -1;
        std::cout << a / b << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp", CompilerConfig(fold_constants=False))
    assert res.success and res.ir is not None

    res_wrap = interpret_module(res.ir, overflow_policy=OverflowPolicy.WRAP)
    assert res_wrap.success
    assert res_wrap.stdout == "-2147483648\n"

    res_trap = interpret_module(res.ir, overflow_policy=OverflowPolicy.TRAP)
    assert not res_trap.success
    assert "signed overflow in division" in res_trap.error

    res_ano = interpret_module(res.ir, overflow_policy=OverflowPolicy.ASSUME_NO_OVERFLOW)
    assert res_ano.success
    assert any("INT_MIN / -1" in ev for ev in res_ano.ub_events)

def test_read_and_print_with_stdin():
    cpp_code = """
    int main() {
        int x, y;
        std::cin >> x >> y;
        std::cout << "sum = " << x + y << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp")
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir, stdin_text="15 27\n")
    assert interp_res.success
    assert interp_res.stdout == "sum = 42\n"

def test_control_flow_loop_and_branch():
    cpp_code = """
    int main() {
        int s = 0;
        for (int i = 1; i <= 5; ++i) {
            s += i;
        }
        std::cout << s << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp")
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir)
    assert interp_res.success
    assert interp_res.stdout == "15\n"

def test_recursion_factorial():
    cpp_code = """
    int fact(int n) {
        if (n <= 1) return 1;
        return n * fact(n - 1);
    }
    int main() {
        std::cout << fact(5) << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp")
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir)
    assert interp_res.success
    assert interp_res.stdout == "120\n"

def test_step_limit_termination():
    cpp_code = """
    int main() {
        int i = 0;
        while (i >= 0) {
            i = i + 1;
        }
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp", CompilerConfig(fold_constants=False))
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir, step_limit=500)
    assert not interp_res.success
    assert "Step limit" in interp_res.error

def test_trace_recording():
    cpp_code = """
    int main() {
        int a = 6;
        int b = 7;
        std::cout << a * b << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp", CompilerConfig(fold_constants=False))
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir, record_trace=True)
    assert interp_res.success
    assert len(interp_res.trace) > 0

    print_entries = [t for t in interp_res.trace if t.opcode == Opcode.PRINT]
    assert len(print_entries) == 1
    assert print_entries[0].output_chunk == "42\n"

def test_cast_narrowing():
    cpp_code = """
    int main() {
        long long big = 4294967296; // 2^32
        int x = big; // narrowed to 0
        std::cout << x << std::endl;
        return 0;
    }
    """
    res = compile_source(cpp_code, "test.cpp")
    assert res.success and res.ir is not None
    interp_res = interpret_module(res.ir)
    assert interp_res.success
    assert interp_res.stdout == "0\n"

@pytest.mark.parametrize(
    "a, b, exp_div, exp_mod",
    [
        (7, 3, 2, 1),
        (-7, 3, -2, -1),
        (7, -3, -2, 1),
        (-7, -3, 2, -1),
        (10, 2, 5, 0),
        (-10, 2, -5, 0),
        (10, -2, -5, 0),
        (-10, -2, 5, 0),
    ],
)
def test_div_mod_sign_combinations(a: int, b: int, exp_div: int, exp_mod: int) -> None:
    fn = IRFunction(
        name="main",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction("op_0", Opcode.DIV, TempRef("d", IRType.I32), (Const(a, IRType.I32), Const(b, IRType.I32))),
            Instruction("op_1", Opcode.MOD, TempRef("m", IRType.I32), (Const(a, IRType.I32), Const(b, IRType.I32))),
            Instruction("op_2", Opcode.PRINT, None, (TempRef("d", IRType.I32), StrConst(" "), TempRef("m", IRType.I32)), newline=True),
            Instruction("op_3", Opcode.RETURN, None, (Const(0, IRType.I32),)),
        ],
    )
    mod = IRModule([fn], source_name="signs.cpp")
    res = interpret_module(mod)
    assert res.success
    assert res.stdout == f"{exp_div} {exp_mod}\n"

@pytest.mark.parametrize(
    "policy, a, b, exp_val, should_trap, expect_ub",
    [
        (OverflowPolicy.WRAP, 2147483647, 1, -2147483648, False, False),
        (OverflowPolicy.WRAP, -2147483648, -1, 2147483647, False, False),
        (OverflowPolicy.TRAP, 2147483647, 1, None, True, True),
        (OverflowPolicy.ASSUME_NO_OVERFLOW, 2147483647, 1, 2147483648, False, True),
    ],
)
def test_add_sub_overflow_policy_semantics(
    policy: OverflowPolicy, a: int, b: int, exp_val: int | None, should_trap: bool, expect_ub: bool
) -> None:
    fn = IRFunction(
        name="main",
        params=(),
        return_type=IRType.I32,
        body=[
            Instruction("op_0", Opcode.ADD, TempRef("t0", IRType.I32), (Const(a, IRType.I32), Const(b, IRType.I32))),
            Instruction("op_1", Opcode.PRINT, None, (TempRef("t0", IRType.I32),), newline=True),
            Instruction("op_2", Opcode.RETURN, None, (Const(0, IRType.I32),)),
        ],
    )
    mod = IRModule([fn], source_name="policy.cpp")
    target = TargetModel(overflow_policy=policy)
    res = interpret_module(mod, target=target, overflow_policy=policy)

    if should_trap:
        assert not res.success
        assert "overflow" in res.error.lower()
    else:
        assert res.success
        assert res.stdout == f"{exp_val}\n"
        if expect_ub:
            assert len(res.ub_events) >= 1
