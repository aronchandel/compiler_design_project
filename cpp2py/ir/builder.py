"""AST to IR lowering for Phase 1 / Phase 2 language constructs.

Lowers declarations, assignments, I/O, expressions and returns to flat three-address IR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cpp2py.source import SourceSpan, Pos
from cpp2py.ir.model import (
    IdAllocator,
    IRType,
    Const,
    VarRef,
    TempRef,
    StrConst,
    Operand,
    Opcode,
    Instruction,
    IRFunction,
    IRModule,
)
from cpp2py.frontend import ast_nodes as ast

if TYPE_CHECKING:
    from cpp2py.semantics.symbols import SemanticInfo
    from cpp2py.config import CompilerConfig


def build_ir(program: ast.Program, info: SemanticInfo, config: CompilerConfig) -> IRModule:
    """Build an IRModule from the AST and semantic information."""
    builder = IRBuilder(program, info, config)
    return builder.build()


class IRBuilder:
    """Lowers an AST Program into an IRModule."""

    def __init__(self, program: ast.Program, info: SemanticInfo, config: CompilerConfig) -> None:
        self._program = program
        self._info = info
        self._config = config
        self._allocator = IdAllocator()
        self._instructions: list[Instruction] = []

    def build(self) -> IRModule:
        functions: list[IRFunction] = []

        for func in self._program.functions:
            ir_func = self._build_function(func)
            functions.append(ir_func)

        source_name = self._program.span.file if self._program.span else ""
        return IRModule(functions=functions, source_name=source_name)

    def _build_function(self, func: ast.FunctionDef) -> IRFunction:
        self._instructions = []

        # Lower body statements
        for stmt in func.body.statements:
            self._lower_stmt(stmt)

        # Check if function ends with return
        has_return = (len(self._instructions) > 0 and
                      self._instructions[-1].opcode == Opcode.RETURN)

        if not has_return:
            # Append implicit "return 0" for main
            # Span is the closing brace
            closing_pos = func.body.span.end
            closing_span = SourceSpan(
                file=func.body.span.file,
                start=closing_pos,
                end=closing_pos,
            )
            ret_instr = Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.RETURN,
                operands=(Const(0, IRType.I32),),
                span=closing_span,
            )
            self._instructions.append(ret_instr)

        ret_type = IRType.I32 if func.return_type.name == "int" else IRType.VOID
        return IRFunction(
            name=func.name,
            params=(),
            return_type=ret_type,
            body=list(self._instructions),
            regions={},
        )

    def _lower_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.DeclStmt):
            for decl in stmt.declarators:
                sym = self._info.symbols_by_node.get(decl.node_id)
                symbol_id = sym.symbol_id if sym is not None else 0
                var_ref = VarRef(symbol_id=symbol_id, ir_name=decl.name, type=IRType.I32)

                # 1. declare v : type
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.DECLARE,
                    dst=var_ref,
                    operands=(var_ref,),
                    span=stmt.span,
                ))

                # 2. If initializer present: evaluate and assign
                if decl.init is not None:
                    init_val = self._lower_expr(decl.init)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.ASSIGN,
                        dst=var_ref,
                        operands=(init_val,),
                        span=stmt.span,
                    ))

        elif isinstance(stmt, ast.AssignStmt):
            sym = self._info.symbols_by_node.get(stmt.target.node_id)
            symbol_id = sym.symbol_id if sym is not None else 0
            var_ref = VarRef(symbol_id=symbol_id, ir_name=stmt.target.name, type=IRType.I32)

            val_op = self._lower_expr(stmt.value)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.ASSIGN,
                dst=var_ref,
                operands=(val_op,),
                span=stmt.span,
            ))

        elif isinstance(stmt, ast.InputStmt):
            for target in stmt.targets:
                sym = self._info.symbols_by_node.get(target.node_id)
                symbol_id = sym.symbol_id if sym is not None else 0
                var_ref = VarRef(symbol_id=symbol_id, ir_name=target.name, type=IRType.I32)

                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.READ,
                    dst=var_ref,
                    operands=(var_ref,),
                    span=stmt.span,
                ))

        elif isinstance(stmt, ast.OutputStmt):
            items = stmt.items
            has_trailing_endl = (len(items) > 0 and isinstance(items[-1], ast.EndlMarker))
            items_to_lower = items[:-1] if has_trailing_endl else items

            operands: list[Operand] = []
            for item in items_to_lower:
                if isinstance(item, ast.EndlMarker):
                    # Non-final endl becomes StrConst("\n")
                    operands.append(StrConst("\n"))
                elif isinstance(item, ast.StringLiteral):
                    operands.append(StrConst(item.value))
                else:
                    val = self._lower_expr(item)
                    operands.append(val)

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.PRINT,
                operands=tuple(operands),
                span=stmt.span,
                newline=has_trailing_endl,
            ))

        elif isinstance(stmt, ast.ReturnStmt):
            if stmt.value is not None:
                val = self._lower_expr(stmt.value)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.RETURN,
                    operands=(val,),
                    span=stmt.span,
                ))
            else:
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.RETURN,
                    operands=(),
                    span=stmt.span,
                ))

    def _lower_expr(self, expr: ast.Expr) -> Operand:
        if isinstance(expr, ast.IntLiteral):
            return Const(expr.value, IRType.I32)

        elif isinstance(expr, ast.NameExpr):
            sym = self._info.symbols_by_node.get(expr.node_id)
            symbol_id = sym.symbol_id if sym is not None else 0
            return VarRef(symbol_id=symbol_id, ir_name=expr.name, type=IRType.I32)

        elif isinstance(expr, ast.UnaryExpr):
            if expr.op == '+':
                # Unary plus has no effect
                return self._lower_expr(expr.operand)

            operand_val = self._lower_expr(expr.operand)
            temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.NEG,
                dst=temp,
                operands=(operand_val,),
                span=expr.span,
            ))
            return temp

        elif isinstance(expr, ast.BinaryExpr):
            # Left operand evaluated before right
            left_val = self._lower_expr(expr.left)
            right_val = self._lower_expr(expr.right)

            op_map = {
                '+': Opcode.ADD,
                '-': Opcode.SUB,
                '*': Opcode.MUL,
                '/': Opcode.DIV,
                '%': Opcode.MOD,
            }
            opcode = op_map[expr.op]
            temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=opcode,
                dst=temp,
                operands=(left_val, right_val),
                span=expr.span,
            ))
            return temp

        raise NotImplementedError(f"Unsupported expression node: {type(expr)}")
