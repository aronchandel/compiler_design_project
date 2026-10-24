"""Unit tests for compat policy and decision rules across all modes."""

import pytest

from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.ir.builder import build_ir
from cpp2py.ir.model import Opcode
from cpp2py.analysis.range_analysis import analyze_ranges
from cpp2py.compat.policy import build_plan
from cpp2py.compat.plan import CompatAction


def test_naive_mode_keeps_w6001():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int a = 10 / 2;
        int b = 10 % 3;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig(compat_mode=CompatMode.NAIVE)
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)
    plan = build_plan(mod, ranges, cfg, sink)

    assert plan.mode == CompatMode.NAIVE
    # All decisions must be NATIVE
    assert all(d.action == CompatAction.NATIVE for d in plan.decisions.values())
    # W6001 must be emitted for each / and %
    w6001 = [d for d in sink.diagnostics if d.code == "W6001"]
    assert len(w6001) == 2


def test_always_mode_inserts_helpers():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int a = 10 / 2;
        int b = 10 % 3;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig(compat_mode=CompatMode.ALWAYS)
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)
    plan = build_plan(mod, ranges, cfg, sink)

    assert plan.mode == CompatMode.ALWAYS
    div_dec = [d for d in plan.decisions.values() if d.helper == "_cpp_div"]
    mod_dec = [d for d in plan.decisions.values() if d.helper == "_cpp_mod"]
    assert len(div_dec) == 1
    assert len(mod_dec) == 1
    # No W6001 in always mode
    assert not any(d.code == "W6001" for d in sink.diagnostics)


def test_range_guided_selectivity():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int non_neg = 10;
        int div_safe = non_neg / 2;

        int unknown;
        cin >> unknown;
        int div_risky = unknown / 2;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)
    plan = build_plan(mod, ranges, cfg, sink)

    assert plan.mode == CompatMode.RANGE_GUIDED
    # First division is native, second division is helper
    helpers = [d for d in plan.decisions.values() if d.action == CompatAction.HELPER]
    natives = [d for d in plan.decisions.values() if d.action == CompatAction.NATIVE]
    assert len(helpers) == 1
    assert helpers[0].helper == "_cpp_div"


def test_overflow_policy_wrap():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int a = 2147483647;
        int b = a + 1;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    target = TargetModel(overflow_policy=OverflowPolicy.WRAP)
    cfg = CompilerConfig(target=target, compat_mode=CompatMode.RANGE_GUIDED)
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)
    plan = build_plan(mod, ranges, cfg, sink)

    wrap_dec = [d for d in plan.decisions.values() if d.helper == "_wrap_i32"]
    assert len(wrap_dec) == 1


def test_overflow_policy_trap():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int a = 2147483647;
        int b = a + 1;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    target = TargetModel(overflow_policy=OverflowPolicy.TRAP)
    cfg = CompilerConfig(target=target, compat_mode=CompatMode.RANGE_GUIDED)
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)
    plan = build_plan(mod, ranges, cfg, sink)

    trap_dec = [d for d in plan.decisions.values() if d.helper == "_check_i32"]
    assert len(trap_dec) == 1
