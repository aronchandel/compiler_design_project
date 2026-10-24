"""Recursive-descent parser for the cpp2py compiler (Phase 1)."""

from __future__ import annotations

from cpp2py.source import SourceSpan
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.tokens import (
    Token, TokenKind, UNSUPPORTED_KEYWORDS, UNSUPPORTED_TYPE_KEYWORDS,
    UNSUPPORTED_OPERATORS,
)
from cpp2py.frontend import ast_nodes as ast


def parse(tokens: list[Token], sink: DiagnosticSink) -> ast.Program | None:
    """Parse a token list into a Program AST, or None on unrecoverable error."""
    parser = _Parser(tokens, sink)
    return parser.parse_program()


class _Parser:
    def __init__(self, tokens: list[Token], sink: DiagnosticSink) -> None:
        self._tokens = tokens
        self._sink = sink
        self._pos = 0
        self._had_error = False  # any error during parsing

    # ---------- helpers ----------

    def _cur(self) -> Token:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return self._tokens[-1]  # EOF

    def _peek(self, offset: int = 0) -> Token:
        idx = self._pos + offset
        if idx < len(self._tokens):
            return self._tokens[idx]
        return self._tokens[-1]

    def _at(self, kind: TokenKind) -> bool:
        return self._cur().kind == kind

    def _at_any(self, *kinds: TokenKind) -> bool:
        return self._cur().kind in kinds

    def _advance(self) -> Token:
        tok = self._cur()
        if self._pos < len(self._tokens) - 1:
            self._pos += 1
        return tok

    def _expect(self, kind: TokenKind, context: str = "") -> Token | None:
        if self._at(kind):
            return self._advance()
        tok = self._cur()
        if tok.kind in UNSUPPORTED_OPERATORS or tok.kind in UNSUPPORTED_KEYWORDS:
            self._error("E4001", f"unsupported construct '{tok.text}' (not supported in this version)", tok.span)
        elif tok.kind in UNSUPPORTED_TYPE_KEYWORDS:
            self._error("E4002", f"unsupported type '{tok.text}'", tok.span)
        elif kind == TokenKind.SEMI:
            self._error("E2002", f"missing ';'", tok.span)
        else:
            msg = f"expected '{_tok_name(kind)}'"
            if context:
                msg += f" {context}"
            msg += f", got '{tok.text or _tok_name(tok.kind)}'"
            self._error("E2001", msg, tok.span)
        return None

    def _error(self, code: str, msg: str, span: SourceSpan) -> None:
        self._had_error = True
        self._sink.error(code, msg, span)

    def _recover(self) -> None:
        """Skip tokens until synchronization point (';', '}', or statement start)."""
        _SYNC_TOKENS = (
            TokenKind.INT, TokenKind.VOID, TokenKind.RETURN,
            TokenKind.IF, TokenKind.WHILE, TokenKind.FOR,
            TokenKind.RBRACE, TokenKind.EOF
        )
        if self._at(TokenKind.SEMI):
            self._advance()
            return
        if self._at_any(*_SYNC_TOKENS):
            return

        while not self._at(TokenKind.EOF):
            if self._at(TokenKind.SEMI):
                self._advance()
                return
            if self._at_any(*_SYNC_TOKENS):
                return
            self._advance()

    # ---------- program ----------

    def parse_program(self) -> ast.Program | None:
        start_span = self._cur().span

        # Parse #include <iostream> lines
        while self._at(TokenKind.INCLUDE_IOSTREAM):
            self._advance()

        # Parse optional "using namespace std;"
        uses_std = False
        if self._at(TokenKind.USING):
            uses_std = True
            self._advance()
            self._expect(TokenKind.NAMESPACE, "after 'using'")
            if self._at(TokenKind.IDENT) and self._cur().text == 'std':
                self._advance()
            else:
                self._error("E2001", "expected 'std' after 'using namespace'", self._cur().span)
            self._expect(TokenKind.SEMI)

        # Parse function definition(s)
        functions: list[ast.FunctionDef] = []

        while not self._at(TokenKind.EOF):
            if self._at_any(TokenKind.INT, TokenKind.VOID):
                func = self._parse_function_def()
                if func is not None:
                    functions.append(func)
            elif self._cur().kind in UNSUPPORTED_TYPE_KEYWORDS:
                self._error("E4002", f"unsupported type '{self._cur().text}'", self._cur().span)
                self._advance()
                self._recover()
            elif self._cur().kind in UNSUPPORTED_KEYWORDS:
                self._error("E4001", f"unsupported construct '{self._cur().text}' (not supported in this version)", self._cur().span)
                self._advance()
                self._recover()
            else:
                self._error("E2001", f"unexpected token '{self._cur().text or _tok_name(self._cur().kind)}'", self._cur().span)
                self._advance()
                self._recover()

        if not functions and not self._had_error:
            self._error("E2001", "expected 'int main()' function definition", self._cur().span)

        # Check that main was defined
        has_main = any(f.name == 'main' for f in functions)
        if not has_main and not self._had_error:
            self._error("E2001", "no 'main' function defined", self._cur().span)

        if self._had_error:
            return None

        end_span = self._cur().span
        prog_span = self._make_span(start_span, end_span)
        return ast.Program(tuple(functions), uses_std, prog_span)

    def _parse_function_def(self) -> ast.FunctionDef | None:
        start = self._cur().span

        # Return type: 'int' or 'void'
        if self._at(TokenKind.INT):
            ret_type_tok = self._advance()
            ret_type = ast.TypeSpec('int', ret_type_tok.span)
        elif self._at(TokenKind.VOID):
            ret_type_tok = self._advance()
            ret_type = ast.TypeSpec('void', ret_type_tok.span)
        else:
            self._error("E2001", f"expected function return type, got '{self._cur().text}'", self._cur().span)
            self._recover()
            return None

        # Function name
        if not self._at(TokenKind.IDENT):
            self._error("E2001", f"expected function name, got '{self._cur().text}'", self._cur().span)
            self._recover()
            return None

        name_tok = self._advance()
        name = name_tok.text

        # Parameters
        if not self._expect(TokenKind.LPAREN, "after function name"):
            self._recover()
            return None

        params: list[ast.Param] = []
        if not self._at(TokenKind.RPAREN):
            while True:
                if self._at(TokenKind.INT):
                    p_type_tok = self._advance()
                    p_type = ast.TypeSpec('int', p_type_tok.span)
                    if not self._at(TokenKind.IDENT):
                        self._error("E2001", f"expected parameter name, got '{self._cur().text}'", self._cur().span)
                        self._recover()
                        return None
                    p_name_tok = self._advance()
                    p_span = self._make_span(p_type_tok.span, p_name_tok.span)
                    params.append(ast.Param(p_type, p_name_tok.text, p_span))
                elif self._cur().kind in UNSUPPORTED_TYPE_KEYWORDS or self._at(TokenKind.VOID):
                    type_text = self._cur().text
                    self._error("E4002", f"unsupported type '{type_text}'", self._cur().span)
                    self._recover()
                    return None
                else:
                    self._error("E2001", f"expected parameter declaration, got '{self._cur().text}'", self._cur().span)
                    self._recover()
                    return None

                if self._at(TokenKind.COMMA):
                    self._advance()
                else:
                    break

        if not self._expect(TokenKind.RPAREN):
            self._recover()
            return None

        # Check main requirements
        if name == 'main':
            if len(params) > 0:
                self._error("E4001", "unsupported construct 'main with parameters' (not supported in this version)", start)
            if ret_type.name != 'int':
                self._error("E4001", "unsupported construct 'void main' (main must return int)", start)

        # Body block
        body = self._parse_block()
        if body is None:
            return None

        end = self._cur().span
        func_span = self._make_span(start, end)
        return ast.FunctionDef(name, ret_type, tuple(params), body, func_span)

    def _parse_block(self) -> ast.Block | None:
        start = self._cur().span
        if not self._expect(TokenKind.LBRACE, "to open block"):
            return None

        statements: list[ast.Stmt] = []
        while not self._at(TokenKind.RBRACE) and not self._at(TokenKind.EOF):
            stmt = self._parse_statement()
            if stmt is not None:
                statements.append(stmt)

        end = self._cur().span
        if not self._expect(TokenKind.RBRACE, "to close block"):
            self._error("E2003", "unbalanced braces", start)
            return None

        block_span = self._make_span(start, self._peek(-1).span if self._pos > 0 else end)
        return ast.Block(tuple(statements), block_span)

    def _peek_relative(self, offset: int) -> Token:
        idx = self._pos + offset
        if 0 <= idx < len(self._tokens):
            return self._tokens[idx]
        return self._tokens[-1]

    # ---------- statements ----------

    def _parse_statement(self) -> ast.Stmt | None:
        tok = self._cur()

        # Check for unsupported keywords
        if tok.kind in UNSUPPORTED_KEYWORDS:
            self._error("E4001",
                        f"unsupported construct '{tok.text}' (not supported in this version)",
                        tok.span)
            self._advance()
            self._recover()
            return None

        # Check for unsupported type keywords used as declarations
        if tok.kind in UNSUPPORTED_TYPE_KEYWORDS:
            self._error("E4002", f"unsupported type '{tok.text}'", tok.span)
            self._advance()
            self._recover()
            return None

        # Check for unsupported operators at statement start
        if tok.kind in UNSUPPORTED_OPERATORS:
            op_text = tok.text
            self._error("E4001",
                        f"unsupported construct '{op_text}' (not supported in this version)",
                        tok.span)
            self._advance()
            self._recover()
            return None

        # Nested block
        if tok.kind == TokenKind.LBRACE:
            return self._parse_block()

        # If statement
        if tok.kind == TokenKind.IF:
            return self._parse_if_stmt()

        # While statement
        if tok.kind == TokenKind.WHILE:
            return self._parse_while_stmt()

        # For statement
        if tok.kind == TokenKind.FOR:
            return self._parse_for_stmt()

        # Prefix ++ or -- statement
        if tok.kind in (TokenKind.PLUS_PLUS, TokenKind.MINUS_MINUS):
            return self._parse_prefix_incdec_stmt()

        # Declaration: 'int ...'
        if tok.kind == TokenKind.INT:
            return self._parse_decl_stmt()

        # Return statement
        if tok.kind == TokenKind.RETURN:
            return self._parse_return_stmt()

        # Identifier: could be assignment, postfix inc/dec, call, cin, cout, or std::cin/std::cout
        if tok.kind == TokenKind.IDENT:
            # Check for std::cin or std::cout
            if tok.text == 'std' and self._peek(1).kind == TokenKind.SCOPE:
                return self._parse_qualified_io()

            if tok.text == 'cin':
                return self._parse_input_stmt(qualified=False)
            if tok.text == 'cout':
                return self._parse_output_stmt(qualified=False)

            next_tok = self._peek(1)
            if next_tok.kind in (TokenKind.PLUS_PLUS, TokenKind.MINUS_MINUS):
                return self._parse_postfix_incdec_stmt()

            if next_tok.kind in (TokenKind.ASSIGN, TokenKind.PLUS_EQ, TokenKind.MINUS_EQ,
                                 TokenKind.STAR_EQ, TokenKind.SLASH_EQ, TokenKind.PERCENT_EQ):
                return self._parse_assign_stmt()

            if next_tok.kind == TokenKind.LPAREN:
                return self._parse_call_stmt()

        # Unexpected token
        self._error("E2001", f"unexpected token '{tok.text or _tok_name(tok.kind)}'", tok.span)
        self._advance()
        self._recover()
        return None

    def _parse_stmt_or_block(self) -> ast.Stmt | None:
        if self._at(TokenKind.LBRACE):
            return self._parse_block()
        stmt = self._parse_statement()
        if stmt is None:
            return None
        return ast.Block((stmt,), stmt.span)

    def _parse_if_stmt(self) -> ast.IfStmt | None:
        start = self._cur().span
        self._advance()  # skip 'if'
        if not self._expect(TokenKind.LPAREN, "after 'if'"):
            self._recover()
            return None
        cond = self._parse_condition()
        if cond is None:
            self._recover()
            return None
        if not self._expect(TokenKind.RPAREN, "after if condition"):
            self._recover()
            return None
        then_body = self._parse_stmt_or_block()
        if then_body is None:
            return None

        else_body: ast.Stmt | None = None
        if self._at(TokenKind.ELSE):
            self._advance()  # skip 'else'
            else_body = self._parse_stmt_or_block()
            if else_body is None:
                return None

        end = else_body.span if else_body else then_body.span
        return ast.IfStmt(cond, then_body, else_body, span=self._make_span(start, end))

    def _parse_while_stmt(self) -> ast.WhileStmt | None:
        start = self._cur().span
        self._advance()  # skip 'while'
        if not self._expect(TokenKind.LPAREN, "after 'while'"):
            self._recover()
            return None
        cond = self._parse_condition()
        if cond is None:
            self._recover()
            return None
        if not self._expect(TokenKind.RPAREN, "after while condition"):
            self._recover()
            return None
        body = self._parse_stmt_or_block()
        if body is None:
            return None
        end = body.span
        return ast.WhileStmt(cond, body, span=self._make_span(start, end))

    def _parse_for_stmt(self) -> ast.ForStmt | None:
        start = self._cur().span
        self._advance()  # skip 'for'
        if not self._expect(TokenKind.LPAREN, "after 'for'"):
            self._recover()
            return None

        # 1. for_init
        init: ast.DeclStmt | ast.AssignStmt | ast.IncDecStmt | None = None
        if self._at(TokenKind.INT):
            init = self._parse_decl_stmt()
        elif self._at(TokenKind.SEMI):
            self._advance()  # empty init
        elif self._at(TokenKind.IDENT):
            next_tok = self._peek(1)
            if next_tok.kind in (TokenKind.PLUS_PLUS, TokenKind.MINUS_MINUS):
                init = self._parse_postfix_incdec_without_semi()
                self._expect(TokenKind.SEMI)
            elif next_tok.kind in (TokenKind.ASSIGN, TokenKind.PLUS_EQ, TokenKind.MINUS_EQ,
                                   TokenKind.STAR_EQ, TokenKind.SLASH_EQ, TokenKind.PERCENT_EQ):
                init = self._parse_assign_without_semi()
                self._expect(TokenKind.SEMI)
            else:
                self._error("E2001", "invalid for-loop init statement", self._cur().span)
                self._recover()
                return None
        elif self._at_any(TokenKind.PLUS_PLUS, TokenKind.MINUS_MINUS):
            init = self._parse_prefix_incdec_without_semi()
            self._expect(TokenKind.SEMI)
        else:
            self._error("E2001", "expected for-loop initialization", self._cur().span)
            self._recover()
            return None

        # 2. condition (mandatory)
        if self._at(TokenKind.SEMI):
            self._error("E2001", "for statement requires a condition", self._cur().span)
            self._recover()
            return None

        cond = self._parse_condition()
        if cond is None:
            self._recover()
            return None
        if not self._expect(TokenKind.SEMI, "after for-loop condition"):
            self._recover()
            return None

        # 3. for_update
        update: ast.AssignStmt | ast.IncDecStmt | None = None
        if not self._at(TokenKind.RPAREN):
            if self._at(TokenKind.IDENT):
                next_tok = self._peek(1)
                if next_tok.kind in (TokenKind.PLUS_PLUS, TokenKind.MINUS_MINUS):
                    update = self._parse_postfix_incdec_without_semi()
                elif next_tok.kind in (TokenKind.ASSIGN, TokenKind.PLUS_EQ, TokenKind.MINUS_EQ,
                                       TokenKind.STAR_EQ, TokenKind.SLASH_EQ, TokenKind.PERCENT_EQ):
                    update = self._parse_assign_without_semi()
                else:
                    self._error("E2001", "invalid for-loop update clause", self._cur().span)
                    self._recover()
                    return None
            elif self._at_any(TokenKind.PLUS_PLUS, TokenKind.MINUS_MINUS):
                update = self._parse_prefix_incdec_without_semi()
            else:
                self._error("E2001", "invalid for-loop update clause", self._cur().span)
                self._recover()
                return None

        if not self._expect(TokenKind.RPAREN, "after for-loop header"):
            self._recover()
            return None

        body = self._parse_stmt_or_block()
        if body is None:
            return None
        end = body.span
        return ast.ForStmt(init, cond, update, body, span=self._make_span(start, end))

    def _parse_prefix_incdec_stmt(self) -> ast.IncDecStmt | None:
        stmt = self._parse_prefix_incdec_without_semi()
        if stmt is None:
            self._recover()
            return None
        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None
        return ast.IncDecStmt(stmt.target, stmt.op, is_prefix=True, span=self._make_span(stmt.span, end))

    def _parse_prefix_incdec_without_semi(self) -> ast.IncDecStmt | None:
        start = self._cur().span
        op_tok = self._advance()
        if not self._at(TokenKind.IDENT):
            self._error("E2001", f"expected variable name, got '{self._cur().text}'", self._cur().span)
            return None
        name_tok = self._advance()
        target = ast.NameExpr(name_tok.text, name_tok.span)
        return ast.IncDecStmt(target, op_tok.text, is_prefix=True, span=self._make_span(start, name_tok.span))

    def _parse_postfix_incdec_stmt(self) -> ast.IncDecStmt | None:
        stmt = self._parse_postfix_incdec_without_semi()
        if stmt is None:
            self._recover()
            return None
        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None
        return ast.IncDecStmt(stmt.target, stmt.op, is_prefix=False, span=self._make_span(stmt.span, end))

    def _parse_postfix_incdec_without_semi(self) -> ast.IncDecStmt | None:
        start = self._cur().span
        name_tok = self._advance()
        target = ast.NameExpr(name_tok.text, name_tok.span)
        op_tok = self._advance()
        return ast.IncDecStmt(target, op_tok.text, is_prefix=False, span=self._make_span(start, op_tok.span))

    def _parse_call_stmt(self) -> ast.CallStmt | None:
        call = self._parse_call_expr()
        if call is None:
            self._recover()
            return None
        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None
        return ast.CallStmt(call, span=self._make_span(call.span, end))

    def _parse_assign_without_semi(self) -> ast.AssignStmt | None:
        start = self._cur().span
        name_tok = self._advance()
        target = ast.NameExpr(name_tok.text, name_tok.span)
        op_tok = self._advance()
        val = self._parse_expr()
        if val is None:
            return None
        end = val.span
        return ast.AssignStmt(target, op_tok.text, val, span=self._make_span(start, end))

    def _parse_condition(self) -> ast.Condition | None:
        start = self._cur().span
        if self._cur().kind in UNSUPPORTED_OPERATORS:
            self._error("E4001", f"unsupported construct '{self._cur().text}' (not supported in this version)", self._cur().span)
            self._advance()
            return None
        left = self._parse_additive()
        if left is None:
            return None
        if self._cur().kind in UNSUPPORTED_OPERATORS:
            self._error("E4001", f"unsupported construct '{self._cur().text}' (not supported in this version)", self._cur().span)
            self._advance()
            return None
        relops = (
            TokenKind.LT, TokenKind.LT_EQ, TokenKind.GT, TokenKind.GT_EQ,
            TokenKind.EQ_EQ, TokenKind.BANG_EQ
        )
        if not self._at_any(*relops):
            self._error("E2001", f"expected comparison operator in condition, got '{self._cur().text}'", self._cur().span)
            return None
        op_tok = self._advance()
        right = self._parse_additive()
        if right is None:
            return None
        if self._cur().kind in UNSUPPORTED_OPERATORS:
            self._error("E4001", f"unsupported construct '{self._cur().text}' (not supported in this version)", self._cur().span)
            self._advance()
            return None
        end = right.span
        return ast.Condition(op_tok.text, left, right, span=self._make_span(start, end))

    def _parse_decl_stmt(self) -> ast.DeclStmt | None:
        start = self._cur().span
        type_tok = self._advance()  # 'int'
        type_spec = ast.TypeSpec('int', type_tok.span)

        declarators: list[ast.Declarator] = []

        while True:
            if not self._at(TokenKind.IDENT):
                self._error("E2001", f"expected variable name, got '{self._cur().text}'", self._cur().span)
                self._recover()
                return None

            name_tok = self._advance()
            decl_start = name_tok.span

            init_expr: ast.Expr | None = None
            if self._at(TokenKind.ASSIGN):
                self._advance()  # skip =
                init_expr = self._parse_expr()
                if init_expr is None:
                    self._recover()
                    return None

            decl_end = self._peek_relative(-1).span if init_expr else name_tok.span
            decl_span = self._make_span(decl_start, decl_end)
            declarators.append(ast.Declarator(name_tok.text, init_expr, decl_span))

            if self._at(TokenKind.COMMA):
                self._advance()
            else:
                break

        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None

        stmt_span = self._make_span(start, end)
        return ast.DeclStmt(type_spec, tuple(declarators), stmt_span)

    def _parse_assign_stmt(self) -> ast.AssignStmt | None:
        start = self._cur().span
        name_tok = self._advance()
        target = ast.NameExpr(name_tok.text, name_tok.span)

        assign_ops = (
            TokenKind.ASSIGN, TokenKind.PLUS_EQ, TokenKind.MINUS_EQ,
            TokenKind.STAR_EQ, TokenKind.SLASH_EQ, TokenKind.PERCENT_EQ
        )
        if not self._at_any(*assign_ops):
            self._error("E2001", "expected assignment operator", self._cur().span)
            self._recover()
            return None

        op_tok = self._advance()
        value = self._parse_expr()
        if value is None:
            self._recover()
            return None

        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None

        stmt_span = self._make_span(start, end)
        return ast.AssignStmt(target, op_tok.text, value, stmt_span)

    def _parse_call_expr(self) -> ast.CallExpr | None:
        start = self._cur().span
        name_tok = self._advance()
        callee = name_tok.text

        if not self._expect(TokenKind.LPAREN, "in function call"):
            return None

        args: list[ast.Expr] = []
        if not self._at(TokenKind.RPAREN):
            while True:
                arg = self._parse_expr()
                if arg is None:
                    return None
                args.append(arg)
                if self._at(TokenKind.COMMA):
                    self._advance()
                else:
                    break

        if not self._expect(TokenKind.RPAREN, "to close function call arguments"):
            return None

        end = self._peek(-1).span
        return ast.CallExpr(callee, tuple(args), span=self._make_span(start, end))

    def _parse_return_stmt(self) -> ast.ReturnStmt | None:
        start = self._cur().span
        self._advance()  # skip 'return'

        value: ast.Expr | None = None
        if not self._at(TokenKind.SEMI):
            value = self._parse_expr()
            if value is None:
                self._recover()
                return None

        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None

        return ast.ReturnStmt(value, self._make_span(start, end))

    def _parse_qualified_io(self) -> ast.Stmt | None:
        """Parse std::cin or std::cout statement."""
        self._advance()  # 'std'
        self._advance()  # '::'

        tok = self._cur()
        if tok.kind == TokenKind.IDENT and tok.text == 'cin':
            return self._parse_input_stmt(qualified=True)
        elif tok.kind == TokenKind.IDENT and tok.text == 'cout':
            return self._parse_output_stmt(qualified=True)
        else:
            self._error("E2001", f"expected 'cin' or 'cout' after 'std::', got '{tok.text}'", tok.span)
            self._recover()
            return None

    def _parse_input_stmt(self, qualified: bool) -> ast.InputStmt | None:
        start = self._tokens[self._pos - (2 if qualified else 0)].span
        self._advance()  # skip 'cin'

        # Check for wrong operator
        if self._at(TokenKind.LSHIFT):
            self._error("E3009", "invalid use of '<<' with cin (use '>>')", self._cur().span)
            self._recover()
            return None

        targets: list[ast.NameExpr] = []
        while self._at(TokenKind.RSHIFT):
            self._advance()  # skip >>
            if not self._at(TokenKind.IDENT):
                self._error("E2001", f"expected variable name after '>>'", self._cur().span)
                self._recover()
                return None
            name_tok = self._advance()
            targets.append(ast.NameExpr(name_tok.text, name_tok.span))

        if not targets:
            self._error("E2001", "expected '>>' after 'cin'", self._cur().span)
            self._recover()
            return None

        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None

        return ast.InputStmt(tuple(targets), self._make_span(start, end), qualified=qualified)

    def _parse_output_stmt(self, qualified: bool) -> ast.OutputStmt | None:
        start = self._tokens[self._pos - (2 if qualified else 0)].span
        self._advance()  # skip 'cout'

        # Check for wrong operator
        if self._at(TokenKind.RSHIFT):
            self._error("E3009", "invalid use of '>>' with cout (use '<<')", self._cur().span)
            self._recover()
            return None

        items: list[ast.OutputItem] = []
        while self._at(TokenKind.LSHIFT):
            self._advance()  # skip <<
            item = self._parse_output_item()
            if item is None:
                self._recover()
                return None
            items.append(item)

        if not items:
            self._error("E2001", "expected '<<' after 'cout'", self._cur().span)
            self._recover()
            return None

        end = self._cur().span
        if not self._expect(TokenKind.SEMI):
            self._recover()
            return None

        return ast.OutputStmt(tuple(items), self._make_span(start, end), qualified=qualified)

    def _parse_output_item(self) -> ast.OutputItem | None:
        """Parse a single item in a cout << chain."""
        tok = self._cur()

        # String literal
        if tok.kind == TokenKind.STRING_LITERAL:
            self._advance()
            # Unescape the value
            raw = tok.text
            value = _unescape_string(raw[1:-1])
            return ast.StringLiteral(value, raw, tok.span)

        # endl (with optional std:: prefix)
        if tok.kind == TokenKind.IDENT and tok.text == 'endl':
            self._advance()
            return ast.EndlMarker(tok.span, qualified=False)

        if tok.kind == TokenKind.IDENT and tok.text == 'std':
            if self._peek(1).kind == TokenKind.SCOPE:
                next_after = self._peek(2)
                if next_after.kind == TokenKind.IDENT and next_after.text == 'endl':
                    self._advance()  # std
                    self._advance()  # ::
                    endl_tok = self._advance()  # endl
                    return ast.EndlMarker(self._make_span(tok.span, endl_tok.span), qualified=True)

        # Expression
        return self._parse_expr()

    # ---------- expressions ----------

    def _parse_expr(self) -> ast.Expr | None:
        left = self._parse_additive()
        if left is None:
            return None
        relops = (
            TokenKind.LT, TokenKind.LT_EQ, TokenKind.GT, TokenKind.GT_EQ,
            TokenKind.EQ_EQ, TokenKind.BANG_EQ
        )
        if self._at_any(*relops):
            op_tok = self._advance()
            right = self._parse_additive()
            if right is None:
                return None
            span = self._make_span(left.span, right.span)
            return ast.BinaryExpr(op_tok.text, left, right, span)
        return left

    def _parse_additive(self) -> ast.Expr | None:
        left = self._parse_multiplicative()
        if left is None:
            return None

        while self._at_any(TokenKind.PLUS, TokenKind.MINUS):
            op_tok = self._advance()
            right = self._parse_multiplicative()
            if right is None:
                return None
            span = self._make_span(left.span, right.span)
            left = ast.BinaryExpr(op_tok.text, left, right, span)

        return left

    def _parse_multiplicative(self) -> ast.Expr | None:
        left = self._parse_unary()
        if left is None:
            return None

        while self._at_any(TokenKind.STAR, TokenKind.SLASH, TokenKind.PERCENT):
            op_tok = self._advance()
            right = self._parse_unary()
            if right is None:
                return None
            span = self._make_span(left.span, right.span)
            left = ast.BinaryExpr(op_tok.text, left, right, span)

        return left

    def _parse_unary(self) -> ast.Expr | None:
        if self._at_any(TokenKind.PLUS, TokenKind.MINUS):
            op_tok = self._advance()
            operand = self._parse_unary()
            if operand is None:
                return None
            span = self._make_span(op_tok.span, operand.span)
            return ast.UnaryExpr(op_tok.text, operand, span)

        # Check for unsupported prefix operators
        if self._at(TokenKind.BANG):
            self._error("E4001", "unsupported construct '!' (not supported in this version)", self._cur().span)
            return None
        if self._at(TokenKind.PLUS_PLUS) or self._at(TokenKind.MINUS_MINUS):
            self._error("E4001",
                        f"unsupported construct '{self._cur().text}' (not supported in this version)",
                        self._cur().span)
            return None

        return self._parse_primary()

    def _parse_primary(self) -> ast.Expr | None:
        tok = self._cur()

        if tok.kind == TokenKind.INT_LITERAL:
            self._advance()
            return ast.IntLiteral(int(tok.text), tok.span)

        if tok.kind == TokenKind.IDENT:
            if self._peek(1).kind == TokenKind.LPAREN:
                return self._parse_call_expr()
            self._advance()
            return ast.NameExpr(tok.text, tok.span)

        if tok.kind == TokenKind.LPAREN:
            start = tok.span
            self._advance()  # skip (
            expr = self._parse_expr()
            if expr is None:
                return None

            if not self._at(TokenKind.RPAREN):
                self._error("E2003", "unbalanced parentheses: expected ')'", self._cur().span)
                return None
            end_tok = self._advance()  # skip )
            # Widen the span to include the parentheses
            expr = _with_span(expr, self._make_span(start, end_tok.span))
            return expr

        # Check for unsupported operators in expression position
        if tok.kind in UNSUPPORTED_OPERATORS:
            self._error("E4001",
                        f"unsupported construct '{tok.text}' (not supported in this version)",
                        tok.span)
            return None

        self._error("E2001", f"expected expression, got '{tok.text or _tok_name(tok.kind)}'", tok.span)
        return None

    # ---------- span helpers ----------

    def _make_span(self, start: SourceSpan, end: SourceSpan) -> SourceSpan:
        return SourceSpan(file=start.file, start=start.start, end=end.end)


# ---------- module-level helpers ----------

def _tok_name(kind: TokenKind) -> str:
    names = {
        TokenKind.SEMI: ';', TokenKind.LPAREN: '(', TokenKind.RPAREN: ')',
        TokenKind.LBRACE: '{', TokenKind.RBRACE: '}', TokenKind.ASSIGN: '=',
        TokenKind.EOF: 'end of file',
    }
    return names.get(kind, kind.name.lower())


def _unescape_string(s: str) -> str:
    """Unescape C++ string escape sequences."""
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            esc = s[i + 1]
            if esc == 'n':
                result.append('\n')
            elif esc == 't':
                result.append('\t')
            elif esc == '\\':
                result.append('\\')
            elif esc == '"':
                result.append('"')
            else:
                result.append('\\')
                result.append(esc)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _with_span(expr: ast.Expr, span: SourceSpan) -> ast.Expr:
    """Return a copy of an expression node with a new span."""
    if isinstance(expr, ast.IntLiteral):
        return ast.IntLiteral(expr.value, span, expr.node_id)
    elif isinstance(expr, ast.NameExpr):
        return ast.NameExpr(expr.name, span, expr.node_id)
    elif isinstance(expr, ast.UnaryExpr):
        return ast.UnaryExpr(expr.op, expr.operand, span, expr.node_id)
    elif isinstance(expr, ast.BinaryExpr):
        return ast.BinaryExpr(expr.op, expr.left, expr.right, span, expr.node_id)
    elif isinstance(expr, ast.CallExpr):
        return ast.CallExpr(expr.callee, expr.args, span, expr.node_id)
    return expr
