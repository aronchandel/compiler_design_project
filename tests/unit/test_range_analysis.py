"""Unit tests for intra-procedural interval range analysis."""

import pytest

from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.config import CompilerConfig, TargetModel
from cpp2py.ir.builder import build_ir
from cpp2py.analysis.intervals import Interval
from cpp2py.analysis.range_analysis import analyze_ranges
from cpp2py.analysis.risk import Risk
from cpp2py.ir.model import Opcode


def test_loop_counter_stays_non_negative():
    src = SourceFile("test.cpp", """
    int main() {
        int i = 0;
        while (i < 10) {
            int d = i / 2;
            i += 1;
        }
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)
    assert ranges.converged

    div_ops = [op for op in ranges.by_op.values() if op.opcode == Opcode.DIV]
    assert len(div_ops) == 1
    d_op = div_ops[0]
    # In range_guided, loop counter i is >= 0, divisor 2 is >= 1 -> NO risks
    assert d_op.operand_ranges[0].lo is not None and d_op.operand_ranges[0].lo >= 0
    assert d_op.operand_ranges[1].lo == 2 and d_op.operand_ranges[1].hi == 2
    assert Risk.DIV_TRUNC_DIFFERS not in d_op.risks


def test_read_without_assumed_range_needs_helper():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        int d = x / 2;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)

    div_ops = [op for op in ranges.by_op.values() if op.opcode == Opcode.DIV]
    assert len(div_ops) == 1
    d_op = div_ops[0]
    # x has full type range -> DIV_TRUNC_DIFFERS
    assert Risk.DIV_TRUNC_DIFFERS in d_op.risks


def test_read_with_assumed_range():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        int d = x / 2;
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig(assumed_ranges={"main.x": Interval(0, 1000)})
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)

    div_ops = [op for op in ranges.by_op.values() if op.opcode == Opcode.DIV]
    assert len(div_ops) == 1
    d_op = div_ops[0]
    assert Risk.DIV_TRUNC_DIFFERS not in d_op.risks
    assert ("main.x", Interval(0, 1000)) in ranges.assumptions


def test_branch_refinement_positive():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        if (x >= 0) {
            int d = x / 2;
        }
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)

    div_ops = [op for op in ranges.by_op.values() if op.opcode == Opcode.DIV]
    assert len(div_ops) == 1
    d_op = div_ops[0]
    # Inside x >= 0 branch, x range has lo >= 0 -> no risk
    assert d_op.operand_ranges[0].lo is not None and d_op.operand_ranges[0].lo >= 0
    assert Risk.DIV_TRUNC_DIFFERS not in d_op.risks


def test_widening_terminates():
    src = SourceFile("test.cpp", """
    #include <iostream>
    using namespace std;
    int main() {
        int n;
        cin >> n;
        int i = 0;
        while (i < n) {
            i += 1;
        }
        return 0;
    }
    """)
    sink = DiagnosticSink()
    cfg = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg, sink)
    assert not sink.has_errors()
    mod = build_ir(prog, info, cfg)
    ranges = analyze_ranges(mod, cfg)
    assert ranges.converged
    assert ranges.iterations < 20
