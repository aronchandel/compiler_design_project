import pytest
from cpp2py.source import Pos, SourceSpan, SourceFile

def test_pos_and_span_creation():
    p1 = Pos(line=1, col=5)
    p2 = Pos(line=1, col=10)
    span = SourceSpan(start=p1, end=p2)
    assert span.start.line == 1
    assert span.start.col == 5
    assert span.end.line == 1
    assert span.end.col == 10

def test_source_file_line_text():
    content = "int a = 1;\nint b = 2;\n"
    sf = SourceFile(filename="test.cpp", content=content)
    assert sf.line_text(1) == "int a = 1;"
    assert sf.line_text(2) == "int b = 2;"
    assert sf.line_text(3) == ""
    assert sf.line_text(0) == ""

def test_source_file_crlf_normalization():
    content = "line1\r\nline2\r\nline3"
    sf = SourceFile(filename="crlf.cpp", content=content)
    assert sf.line_text(1) == "line1"
    assert sf.line_text(2) == "line2"
    assert sf.line_text(3) == "line3"

def test_source_file_pos_at():
    content = "abc\ndef"
    sf = SourceFile(filename="test.cpp", content=content)
    p = sf.pos_at(line=2, col=3)
    assert p.line == 2
    assert p.col == 3
