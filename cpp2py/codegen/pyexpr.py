from __future__ import annotations

from cpp2py.frontend import ast_nodes as ast

_PREC: dict[str, int] = {
    '<': 0,
    '<=': 0,
    '>': 0,
    '>=': 0,
    '==': 0,
    '!=': 0,
    '+': 1,
    '-': 1,
    '*': 2,
    '/': 2,
    '%': 2,
}

_OP_MAP: dict[str, str] = {
    '<': '<',
    '<=': '<=',
    '>': '>',
    '>=': '>=',
    '==': '==',
    '!=': '!=',
    '+': '+',
    '-': '-',
    '*': '*',
    '/': '//',
    '%': '%',
}

def render_expr(expr: ast.Expr, name_fn: callable) -> str:
    return _render(expr, name_fn, parent_prec=-1, is_right=False)

def _render(expr: ast.Expr, name_fn: callable, parent_prec: int, is_right: bool) -> str:
    if isinstance(expr, ast.IntLiteral):
        return str(expr.value)

    elif isinstance(expr, ast.NullptrLiteral):
        return "_Ptr(None, 0)"

    elif isinstance(expr, ast.NameExpr):
        return name_fn(expr.name)

    elif isinstance(expr, ast.IndexExpr):
        arr_str = _render(expr.array, name_fn, parent_prec=3, is_right=False)
        idx_str = _render(expr.index, name_fn, parent_prec=-1, is_right=False)
        return f"{arr_str}[{idx_str}]"

    elif isinstance(expr, ast.DerefExpr):
        ptr_str = _render(expr.operand, name_fn, parent_prec=3, is_right=False)
        return f"{ptr_str}[0]"

    elif isinstance(expr, ast.AddressOfExpr):
        if isinstance(expr.operand, ast.NameExpr):
            var_name = name_fn(expr.operand.name)
            return f"_Ptr({var_name}, 0)"
        elif isinstance(expr.operand, ast.IndexExpr):
            arr_str = _render(expr.operand.array, name_fn, parent_prec=3, is_right=False)
            idx_str = _render(expr.operand.index, name_fn, parent_prec=-1, is_right=False)
            return f"_Ptr({arr_str}, {idx_str})"
        elif isinstance(expr.operand, ast.DerefExpr):

            return _render(expr.operand.operand, name_fn, parent_prec, is_right)
        else:
            inner_str = _render(expr.operand, name_fn, parent_prec=-1, is_right=False)
            return f"_Ptr({inner_str}, 0)"

    elif isinstance(expr, ast.UnaryExpr):
        if expr.op == '+':

            return _render(expr.operand, name_fn, parent_prec, is_right)

        operand_str = _render(expr.operand, name_fn, parent_prec=-1, is_right=False)

        needs_parens = not isinstance(expr.operand, (ast.IntLiteral, ast.NameExpr, ast.IndexExpr, ast.DerefExpr))

        if needs_parens:
            result = f"-({operand_str})"
        else:

            if operand_str.startswith('-'):
                result = f"-({operand_str})"
            else:
                result = f"-{operand_str}"

        return result

    elif isinstance(expr, ast.BinaryExpr):
        prec = _PREC.get(expr.op, 1)
        py_op = _OP_MAP.get(expr.op, expr.op)

        left_str = _render(expr.left, name_fn, parent_prec=prec, is_right=False)

        right_str = _render(expr.right, name_fn, parent_prec=prec, is_right=True)

        result = f"{left_str} {py_op} {right_str}"

        if is_right and prec <= parent_prec:
            result = f"({result})"
        elif not is_right and prec < parent_prec:
            result = f"({result})"

        return result

    elif isinstance(expr, ast.CallExpr):
        callee_str = name_fn(expr.callee)
        args_str = ", ".join(_render(a, name_fn, parent_prec=-1, is_right=False) for a in expr.args)
        return f"{callee_str}({args_str})"

    elif isinstance(expr, ast.Condition):
        left_str = _render(expr.left, name_fn, parent_prec=0, is_right=False)
        right_str = _render(expr.right, name_fn, parent_prec=0, is_right=True)
        return f"{left_str} {expr.op} {right_str}"

    return str(expr)
