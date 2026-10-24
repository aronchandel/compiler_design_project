"""Unit tests for CFG construction and RPO."""

from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.semantics.analyzer import analyze
from cpp2py.config import CompilerConfig
from cpp2py.ir.builder import build_ir
from cpp2py.analysis.cfg import CFG


def test_straight_line_cfg():
    src = SourceFile("test.cpp", "int main() { int a = 1; int b = 2; return a + b; }")
    sink = DiagnosticSink()
    cfg_conf = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg_conf, sink)
    mod = build_ir(prog, info, cfg_conf)
    cfg = CFG(mod.functions[0])
    assert cfg.entry is not None
    assert len(cfg.blocks) >= 1
    assert len(cfg.entry.successors) == 0  # ends in return


def test_while_loop_cfg():
    src = SourceFile("test.cpp", """
    int main() {
        int i = 0;
        while (i < 10) {
            i = i + 1;
        }
        return i;
    }
    """)
    sink = DiagnosticSink()
    cfg_conf = CompilerConfig()
    tokens = tokenize(src, sink)
    prog = parse(tokens, sink)
    info = analyze(prog, cfg_conf, sink)
    mod = build_ir(prog, info, cfg_conf)
    cfg = CFG(mod.functions[0])
    loop_heads = [b for b in cfg.blocks if b.is_loop_head]
    assert len(loop_heads) == 1
    rpo = cfg.reverse_post_order()
    assert len(rpo) >= 3
    assert rpo[0] == cfg.entry
