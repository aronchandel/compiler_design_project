"""Precedence-aware Python expression renderer for the cpp2py code generator."""

from __future__ import annotations

from cpp2py.frontend import ast_nodes as ast


# Operator precedence levels (higher = binds tighter)
_PREC: dict[str, int] = {
    '+': 1,
    '-': 1,
    '*': 2,
    '/': 2,
    '%': 2,
}

# Map C++ operators to Python operators
_OP_MAP: dict[str, str] = {
    '+': '+',
    '-': '-',
    '*': '*',
    '/': '//',
    '%': '%',
}


def render_expr(expr: ast.Expr, name_fn: callable) -> str:
    """Render an AST expression as a Python expression string.

    name_fn: callable that maps C++ variable names to Python names.
    Returns the Python expression string.
    """
    return _render(expr, name_fn, parent_prec=-1, is_right=False)


def _render(expr: ast.Expr, name_fn: callable, parent_prec: int, is_right: bool) -> str:
    if isinstance(expr, ast.IntLiteral):
        return str(expr.value)

    elif isinstance(expr, ast.NameExpr):
        return name_fn(expr.name)

    elif isinstance(expr, ast.UnaryExpr):
        if expr.op == '+':
            # Unary plus is dropped
            return _render(expr.operand, name_fn, parent_prec, is_right)

        # Unary minus
        operand_str = _render(expr.operand, name_fn, parent_prec=-1, is_right=False)

        # Parenthesize operand when it is not a literal or a name
        needs_parens = not isinstance(expr.operand, (ast.IntLiteral, ast.NameExpr))

        if needs_parens:
            result = f"-({operand_str})"
        else:
            # Avoid emitting "--x": if operand starts with '-', wrap it
            if operand_str.startswith('-'):
                result = f"-({operand_str})"
            else:
                result = f"-{operand_str}"

        return result

    elif isinstance(expr, ast.BinaryExpr):
        prec = _PREC[expr.op]
        py_op = _OP_MAP[expr.op]

        left_str = _render(expr.left, name_fn, parent_prec=prec, is_right=False)
        # Right operand: parenthesize when it has the same precedence (left-associativity)
        right_str = _render(expr.right, name_fn, parent_prec=prec, is_right=True)

        result = f"{left_str} {py_op} {right_str}"

        # Parenthesize the whole expression if needed by parent
        if is_right and prec <= parent_prec:
            result = f"({result})"
        elif not is_right and prec < parent_prec:
            result = f"({result})"

        return result

    return str(expr)
