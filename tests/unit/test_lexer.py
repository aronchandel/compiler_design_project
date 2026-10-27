import pytest
from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.tokens import TokenKind
from cpp2py.frontend.lexer import tokenize

def lex(text: str):
    source = SourceFile("test.cpp", text)
    sink = DiagnosticSink()
    tokens = tokenize(source, sink)
    return tokens, sink

def test_lex_basic_tokens():
    text = "int main() { return 0; }"
    tokens, sink = lex(text)
    assert not sink.has_errors()
    kinds = [t.kind for t in tokens]
    assert kinds == [
        TokenKind.INT,
        TokenKind.IDENT,
        TokenKind.LPAREN,
        TokenKind.RPAREN,
        TokenKind.LBRACE,
        TokenKind.RETURN,
        TokenKind.INT_LITERAL,
        TokenKind.SEMI,
        TokenKind.RBRACE,
        TokenKind.EOF,
    ]

def test_lex_operators():
    text = "+ - * / % = :: << >> < >"
    tokens, sink = lex(text)
    assert not sink.has_errors()
    kinds = [t.kind for t in tokens[:-1]]
    assert kinds == [
        TokenKind.PLUS,
        TokenKind.MINUS,
        TokenKind.STAR,
        TokenKind.SLASH,
        TokenKind.PERCENT,
        TokenKind.ASSIGN,
        TokenKind.SCOPE,
        TokenKind.LSHIFT,
        TokenKind.RSHIFT,
        TokenKind.LT,
        TokenKind.GT,
    ]

def test_lex_shift_vs_comparison():
    tokens, sink = lex("<< < >> >")
    assert not sink.has_errors()
    kinds = [t.kind for t in tokens[:-1]]
    assert kinds == [TokenKind.LSHIFT, TokenKind.LT, TokenKind.RSHIFT, TokenKind.GT]

def test_lex_include_iostream():
    tokens, sink = lex("#include <iostream>\nint x;")
    assert not sink.has_errors()
    assert tokens[0].kind == TokenKind.INCLUDE_IOSTREAM
    assert tokens[1].kind == TokenKind.INT

def test_lex_unsupported_include():
    tokens, sink = lex("#include <vector>\n")
    assert sink.has_errors()
    assert any(e.code == "E4003" for e in sink.errors)

def test_lex_unsupported_directive():
    tokens, sink = lex("#define FOO 1\n")
    assert sink.has_errors()
    assert any(e.code == "E1005" for e in sink.errors)

def test_lex_line_comment():
    tokens, sink = lex("// line comment\nint x; // another")
    assert not sink.has_errors()
    kinds = [t.kind for t in tokens[:-1]]
    assert kinds == [TokenKind.INT, TokenKind.IDENT, TokenKind.SEMI]

def test_lex_block_comment():
    tokens, sink = lex("/* block comment */ int /* inside */ x;")
    assert not sink.has_errors()
    kinds = [t.kind for t in tokens[:-1]]
    assert kinds == [TokenKind.INT, TokenKind.IDENT, TokenKind.SEMI]

def test_lex_unterminated_block_comment():
    tokens, sink = lex("/* unterminated block comment")
    assert sink.has_errors()
    assert any(e.code == "E1003" for e in sink.errors)

def test_lex_string_literal_escapes():
    tokens, sink = lex(r'"hello\nworld\t\\\""')
    assert not sink.has_errors()
    assert tokens[0].kind == TokenKind.STRING_LITERAL
    assert tokens[0].text == r'"hello\nworld\t\\\""'

def test_lex_unterminated_string():
    tokens, sink = lex('"unterminated string\n')
    assert sink.has_errors()
    assert any(e.code == "E1002" for e in sink.errors)

def test_lex_invalid_character():
    tokens, sink = lex("@ $")
    assert sink.has_errors()
    assert any(e.code == "E1001" for e in sink.errors)

def test_lex_integer_literal_range():

    tokens, sink = lex("2147483647")
    assert not sink.has_errors()
    assert int(tokens[0].text) == 2147483647

    tokens, sink = lex("2147483648")
    assert not sink.has_errors()
    assert int(tokens[0].text) == 2147483648

    tokens, sink = lex("9223372036854775808")
    assert sink.has_errors()
    assert any(e.code == "E1004" for e in sink.errors)

def test_lex_crlf_input():
    tokens, sink = lex("int a = 1;\r\nint b = 2;\r\n")
    assert not sink.has_errors()

    assert tokens[0].span.start.line == 1
    assert tokens[5].span.start.line == 2

def test_lex_unsupported_keywords():
    text = "while for if else class struct"
    tokens, sink = lex(text)
    assert not sink.has_errors()
    kinds = [t.kind for t in tokens[:-1]]
    assert TokenKind.WHILE in kinds
    assert TokenKind.FOR in kinds
    assert TokenKind.IF in kinds
