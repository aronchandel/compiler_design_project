"""Unit tests for CompatPlan determinism and serialization."""

import json
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.config import CompilerConfig, CompatMode
from cpp2py.ir.builder import build_ir
from cpp2py.analysis.range_analysis import analyze_ranges
from cpp2py.compat.policy import build_plan


def test_plan_determinism():
    src_text = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        int d = x / 2;
        int m = x % 3;
        return 0;
    }
    """
    plans = []
    for _ in range(2):
        sink = DiagnosticSink()
        cfg = CompilerConfig(compat_mode=CompatMode.RANGE_GUIDED)
        tokens = tokenize(SourceFile("test.cpp", src_text), sink)
        prog = parse(tokens, sink)
        info = analyze(prog, cfg, sink)
        mod = build_ir(prog, info, cfg)
        ranges = analyze_ranges(mod, cfg)
        plan = build_plan(mod, ranges, cfg, sink)
        plans.append(json.dumps(plan.to_dict(), sort_keys=True, indent=2))

    assert plans[0] == plans[1]
