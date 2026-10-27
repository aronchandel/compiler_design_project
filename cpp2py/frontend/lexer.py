from __future__ import annotations

from cpp2py.source import SourceFile, SourceSpan
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.tokens import Token, TokenKind, KEYWORDS
from cpp2py.config import TargetModel

def tokenize(source: SourceFile, sink: DiagnosticSink, target: TargetModel | None = None) -> list[Token]:
    lexer = _Lexer(source, sink, target or TargetModel())
    return lexer.run()

class _Lexer:
    def __init__(self, source: SourceFile, sink: DiagnosticSink, target: TargetModel) -> None:
        self._source = source
        self._sink = sink
        self._target = target
        self._text = source.text
        self._pos = 0
        self._tokens: list[Token] = []

    def run(self) -> list[Token]:
        while self._pos < len(self._text):
            self._skip_whitespace()
            if self._pos >= len(self._text):
                break

            ch = self._text[self._pos]

            if ch == '/' and self._pos + 1 < len(self._text):
                next_ch = self._text[self._pos + 1]
                if next_ch == '/':
                    self._skip_line_comment()
                    continue
                elif next_ch == '*':
                    self._skip_block_comment()
                    continue

            if ch == '#':
                self._lex_preprocessor()
                continue

            if ch == '"':
                self._lex_string()
                continue

            if ch.isdigit():
                self._lex_number()
                continue

            if ch.isalpha() or ch == '_':
                self._lex_identifier()
                continue

            if self._try_multi_char_op():
                continue

            if self._try_single_char_op(ch):
                continue

            start = self._pos
            self._pos += 1
            span = self._source.span(start, self._pos)
            self._sink.error("E1001", f"invalid character '{ch}'", span)

        eof_off = len(self._text)
        eof_span = self._source.span(eof_off, eof_off)
        self._tokens.append(Token(TokenKind.EOF, '', eof_span))
        return self._tokens

    def _skip_whitespace(self) -> None:
        while self._pos < len(self._text) and self._text[self._pos] in ' \t\n\r':
            self._pos += 1

    def _skip_line_comment(self) -> None:

        self._pos += 2
        while self._pos < len(self._text) and self._text[self._pos] != '\n':
            self._pos += 1

    def _skip_block_comment(self) -> None:
        start = self._pos
        self._pos += 2
        while self._pos + 1 < len(self._text):
            if self._text[self._pos] == '*' and self._text[self._pos + 1] == '/':
                self._pos += 2
                return
            self._pos += 1

        if self._pos < len(self._text):
            self._pos += 1
        span = self._source.span(start, self._pos)
        self._sink.error("E1003", "unterminated block comment", span)

    def _lex_preprocessor(self) -> None:
        start = self._pos
        self._pos += 1

        while self._pos < len(self._text) and self._text[self._pos] in ' \t':
            self._pos += 1

        word_start = self._pos
        while self._pos < len(self._text) and (self._text[self._pos].isalpha() or self._text[self._pos] == '_'):
            self._pos += 1
        directive = self._text[word_start:self._pos]

        if directive == 'include':

            while self._pos < len(self._text) and self._text[self._pos] in ' \t':
                self._pos += 1

            if self._pos < len(self._text) and self._text[self._pos] == '<':
                angle_start = self._pos
                self._pos += 1
                while self._pos < len(self._text) and self._text[self._pos] != '>' and self._text[self._pos] != '\n':
                    self._pos += 1
                if self._pos < len(self._text) and self._text[self._pos] == '>':
                    self._pos += 1
                    header = self._text[angle_start:self._pos]
                    if header == '<iostream>':
                        span = self._source.span(start, self._pos)
                        self._tokens.append(Token(TokenKind.INCLUDE_IOSTREAM, '#include <iostream>', span))
                        return
                    elif header == '<climits>':
                        span = self._source.span(start, self._pos)
                        self._tokens.append(Token(TokenKind.INCLUDE_CLIMITS, '#include <climits>', span))
                        return
                    else:
                        span = self._source.span(start, self._pos)
                        header_name = header[1:-1]
                        self._sink.error("E4003", f"unsupported header '<{header_name}>'", span)
                        return

            if self._pos < len(self._text) and self._text[self._pos] == '"':
                self._pos += 1
                while self._pos < len(self._text) and self._text[self._pos] != '"' and self._text[self._pos] != '\n':
                    self._pos += 1
                if self._pos < len(self._text) and self._text[self._pos] == '"':
                    self._pos += 1
                span = self._source.span(start, self._pos)
                self._sink.error("E4003", "unsupported header", span)
                return

            while self._pos < len(self._text) and self._text[self._pos] != '\n':
                self._pos += 1
            span = self._source.span(start, self._pos)
            self._sink.error("E4003", "unsupported header", span)
            return
        else:

            while self._pos < len(self._text) and self._text[self._pos] != '\n':
                self._pos += 1
            span = self._source.span(start, self._pos)
            self._sink.error("E1005", f"unsupported preprocessor directive '#{directive}'", span)

    def _lex_string(self) -> None:
        start = self._pos
        self._pos += 1
        value_chars: list[str] = []

        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch == '\n' or ch == '\r':

                span = self._source.span(start, self._pos)
                self._sink.error("E1002", "unterminated string literal", span)
                return
            if ch == '"':
                self._pos += 1
                text = self._text[start:self._pos]
                span = self._source.span(start, self._pos)
                self._tokens.append(Token(TokenKind.STRING_LITERAL, text, span))
                return
            if ch == '\\':
                self._pos += 1
                if self._pos >= len(self._text):
                    span = self._source.span(start, self._pos)
                    self._sink.error("E1002", "unterminated string literal", span)
                    return
                esc = self._text[self._pos]
                if esc == 'n':
                    value_chars.append('\n')
                elif esc == 't':
                    value_chars.append('\t')
                elif esc == '\\':
                    value_chars.append('\\')
                elif esc == '"':
                    value_chars.append('"')
                else:
                    value_chars.append('\\')
                    value_chars.append(esc)
                self._pos += 1
            else:
                value_chars.append(ch)
                self._pos += 1

        span = self._source.span(start, self._pos)
        self._sink.error("E1002", "unterminated string literal", span)

    def _lex_number(self) -> None:
        start = self._pos
        while self._pos < len(self._text) and self._text[self._pos].isdigit():
            self._pos += 1

        text = self._text[start:self._pos]
        span = self._source.span(start, self._pos)

        value = int(text)
        if value > self._target.long_long_max:
            self._sink.error("E1004", f"integer literal {text} does not fit in long long", span)
            return

        self._tokens.append(Token(TokenKind.INT_LITERAL, text, span))

    def _lex_identifier(self) -> None:
        start = self._pos
        while self._pos < len(self._text) and (self._text[self._pos].isalnum() or self._text[self._pos] == '_'):
            self._pos += 1

        text = self._text[start:self._pos]
        span = self._source.span(start, self._pos)

        kind = KEYWORDS.get(text, TokenKind.IDENT)
        self._tokens.append(Token(kind, text, span))

    def _try_multi_char_op(self) -> bool:
        if self._pos + 1 >= len(self._text):
            return False

        two = self._text[self._pos:self._pos + 2]
        start = self._pos

        mapping: dict[str, TokenKind] = {
            '<<': TokenKind.LSHIFT,
            '>>': TokenKind.RSHIFT,
            '::': TokenKind.SCOPE,
            '++': TokenKind.PLUS_PLUS,
            '--': TokenKind.MINUS_MINUS,
            '+=': TokenKind.PLUS_EQ,
            '-=': TokenKind.MINUS_EQ,
            '*=': TokenKind.STAR_EQ,
            '/=': TokenKind.SLASH_EQ,
            '%=': TokenKind.PERCENT_EQ,
            '&&': TokenKind.AMP_AMP,
            '||': TokenKind.PIPE_PIPE,
            '!=': TokenKind.BANG_EQ,
            '<=': TokenKind.LT_EQ,
            '>=': TokenKind.GT_EQ,
            '==': TokenKind.EQ_EQ,
        }

        kind = mapping.get(two)
        if kind is not None:
            self._pos += 2
            span = self._source.span(start, self._pos)
            self._tokens.append(Token(kind, two, span))
            return True

        return False

    def _try_single_char_op(self, ch: str) -> bool:
        mapping: dict[str, TokenKind] = {
            '+': TokenKind.PLUS,
            '-': TokenKind.MINUS,
            '*': TokenKind.STAR,
            '/': TokenKind.SLASH,
            '%': TokenKind.PERCENT,
            '=': TokenKind.ASSIGN,
            '(': TokenKind.LPAREN,
            ')': TokenKind.RPAREN,
            '{': TokenKind.LBRACE,
            '}': TokenKind.RBRACE,
            '[': TokenKind.LBRACKET,
            ']': TokenKind.RBRACKET,
            ';': TokenKind.SEMI,
            ',': TokenKind.COMMA,
            '&': TokenKind.AMP,
            '<': TokenKind.LT,
            '>': TokenKind.GT,
            '!': TokenKind.BANG,
            '?': TokenKind.QUESTION,
            ':': TokenKind.COLON,
        }

        kind = mapping.get(ch)
        if kind is not None:
            start = self._pos
            self._pos += 1
            span = self._source.span(start, self._pos)
            self._tokens.append(Token(kind, ch, span))
            return True

        return False
