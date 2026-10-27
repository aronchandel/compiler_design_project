import pytest
from cpp2py.source import Pos, SourceSpan, SourceFile
from cpp2py.diagnostics import Severity, Diagnostic, DiagnosticSink, render

def test_diagnostic_creation():
    span = SourceSpan("test.cpp", Pos(1, 1), Pos(1, 4))
    diag = Diagnostic(severity=Severity.ERROR, code="E1001", message="invalid character", span=span)
    assert diag.code == "E1001"
    assert diag.message == "invalid character"
    assert diag.severity == Severity.ERROR
    assert diag.span == span

def test_diagnostic_sink_recording():
    sink = DiagnosticSink()
    assert not sink.has_errors()
    assert len(sink.diagnostics) == 0

    span = SourceSpan("test.cpp", Pos(1, 1), Pos(1, 2))
    sink.error("E2001", "syntax error", span=span)
    assert sink.has_errors()
    assert len(sink.errors) == 1
    assert len(sink.warnings) == 0

    sink.warning("W6001", "division semantics difference", span=span)
    assert len(sink.warnings) == 1
    assert len(sink.diagnostics) == 2

def test_diagnostic_render_with_caret():
    source = SourceFile(filename="test.cpp", content="int x = @;\nreturn 0;\n")
    span = SourceSpan("test.cpp", Pos(1, 9), Pos(1, 10))
    diag = Diagnostic(severity=Severity.ERROR, code="E1001", message="invalid character '@'", span=span)
    rendered = render(diag, source)

    assert "test.cpp:1:9: error [E1001]: invalid character '@'" in rendered
    assert "int x = @;" in rendered
    assert "^" in rendered

def test_diagnostic_render_without_source():
    diag = Diagnostic(severity=Severity.ERROR, code="E9001", message="general failure")
    rendered = render(diag)
    assert "error [E9001]: general failure" in rendered
