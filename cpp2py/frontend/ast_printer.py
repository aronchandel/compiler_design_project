"""AST pretty-printer for --dump-ast."""

from __future__ import annotations

from cpp2py.frontend import ast_nodes as ast


def dump(program: ast.Program) -> str:
    """Return a human-readable tree dump of the AST."""
    lines: list[str] = []
    _dump_program(program, lines, "")
    return '\n'.join(lines)


def _dump_program(prog: ast.Program, lines: list[str], prefix: str) -> None:
    lines.append(f"Program uses_std={prog.uses_std}")
    for i, func in enumerate(prog.functions):
        is_last = (i == len(prog.functions) - 1)
        connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
        child_prefix = prefix + ("   " if is_last else "\u2502  ")
        _dump_function(func, lines, prefix + connector, child_prefix)


def _dump_function(func: ast.FunctionDef, lines: list[str], prefix: str, child_prefix: str) -> None:
    lines.append(f"{prefix}FunctionDef {func.name} -> {func.return_type.name}")
    _dump_block(func.body, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")


def _dump_block(block: ast.Block, lines: list[str], prefix: str, child_prefix: str) -> None:
    lines.append(f"{prefix}Block")
    for i, stmt in enumerate(block.statements):
        is_last = (i == len(block.statements) - 1)
        connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
        next_prefix = child_prefix + ("   " if is_last else "\u2502  ")
        _dump_stmt(stmt, lines, child_prefix + connector, next_prefix)


def _dump_stmt(stmt: ast.Stmt, lines: list[str], prefix: str, child_prefix: str) -> None:
    if isinstance(stmt, ast.Block):
        _dump_block(stmt, lines, prefix, child_prefix)

    elif isinstance(stmt, ast.DeclStmt):
        lines.append(f"{prefix}DeclStmt {stmt.type_spec.name}")
        for i, decl in enumerate(stmt.declarators):
            is_last = (i == len(stmt.declarators) - 1)
            connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
            next_prefix = child_prefix + ("   " if is_last else "\u2502  ")
            if decl.init is not None:
                lines.append(f"{child_prefix}{connector}Declarator {decl.name}")
                _dump_expr(decl.init, lines, next_prefix + "\u2514\u2500 ", next_prefix + "   ")
            else:
                lines.append(f"{child_prefix}{connector}Declarator {decl.name}")

    elif isinstance(stmt, ast.AssignStmt):
        lines.append(f"{prefix}AssignStmt {stmt.op}")
        lines.append(f"{child_prefix}\u251c\u2500 NameExpr {stmt.target.name}")
        _dump_expr(stmt.value, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")

    elif isinstance(stmt, ast.IncDecStmt):
        kind = "Prefix" if stmt.is_prefix else "Postfix"
        lines.append(f"{prefix}IncDecStmt {stmt.op} {kind}")
        lines.append(f"{child_prefix}\u2514\u2500 NameExpr {stmt.target.name}")

    elif isinstance(stmt, ast.IfStmt):
        lines.append(f"{prefix}IfStmt")
        _dump_condition(stmt.cond, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
        if stmt.else_body is not None:
            _dump_stmt(stmt.then_body, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
            _dump_stmt(stmt.else_body, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")
        else:
            _dump_stmt(stmt.then_body, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")

    elif isinstance(stmt, ast.WhileStmt):
        lines.append(f"{prefix}WhileStmt")
        _dump_condition(stmt.cond, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
        _dump_stmt(stmt.body, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")

    elif isinstance(stmt, ast.ForStmt):
        lines.append(f"{prefix}ForStmt")
        if stmt.init is not None:
            _dump_stmt(stmt.init, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
        _dump_condition(stmt.cond, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
        if stmt.update is not None:
            _dump_stmt(stmt.update, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
        _dump_stmt(stmt.body, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")

    elif isinstance(stmt, ast.CallStmt):
        lines.append(f"{prefix}CallStmt")
        _dump_expr(stmt.call, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")

    elif isinstance(stmt, ast.InputStmt):
        lines.append(f"{prefix}InputStmt")
        for i, target in enumerate(stmt.targets):
            is_last = (i == len(stmt.targets) - 1)
            connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
            lines.append(f"{child_prefix}{connector}NameExpr {target.name}")

    elif isinstance(stmt, ast.OutputStmt):
        lines.append(f"{prefix}OutputStmt")
        for i, item in enumerate(stmt.items):
            is_last = (i == len(stmt.items) - 1)
            connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
            next_prefix = child_prefix + ("   " if is_last else "\u2502  ")
            if isinstance(item, ast.EndlMarker):
                lines.append(f"{child_prefix}{connector}EndlMarker")
            elif isinstance(item, ast.StringLiteral):
                lines.append(f"{child_prefix}{connector}StringLiteral {item.raw}")
            else:
                _dump_expr(item, lines, child_prefix + connector, next_prefix)

    elif isinstance(stmt, ast.ReturnStmt):
        if stmt.value is not None:
            lines.append(f"{prefix}ReturnStmt")
            _dump_expr(stmt.value, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")
        else:
            lines.append(f"{prefix}ReturnStmt")


def _dump_condition(cond: ast.Condition, lines: list[str], prefix: str, child_prefix: str) -> None:
    lines.append(f"{prefix}Condition {cond.op}")
    _dump_expr(cond.left, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
    _dump_expr(cond.right, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")


def _dump_expr(expr: ast.Expr, lines: list[str], prefix: str, child_prefix: str) -> None:
    if isinstance(expr, ast.IntLiteral):
        lines.append(f"{prefix}IntLiteral {expr.value}")

    elif isinstance(expr, ast.NameExpr):
        lines.append(f"{prefix}NameExpr {expr.name}")

    elif isinstance(expr, ast.UnaryExpr):
        lines.append(f"{prefix}UnaryExpr {expr.op}")
        _dump_expr(expr.operand, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")

    elif isinstance(expr, ast.BinaryExpr):
        lines.append(f"{prefix}BinaryExpr {expr.op}")
        _dump_expr(expr.left, lines, child_prefix + "\u251c\u2500 ", child_prefix + "\u2502  ")
        _dump_expr(expr.right, lines, child_prefix + "\u2514\u2500 ", child_prefix + "   ")

    elif isinstance(expr, ast.CallExpr):
        lines.append(f"{prefix}CallExpr {expr.callee}")
        for i, arg in enumerate(expr.args):
            is_last = (i == len(expr.args) - 1)
            connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
            next_prefix = child_prefix + ("   " if is_last else "\u2502  ")
            _dump_expr(arg, lines, child_prefix + connector, next_prefix)
