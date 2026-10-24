"""AST to IR lowering for Phase 1 / Phase 2 / Phase 3 language constructs.

Lowers declarations, assignments, compound assignments, inc/dec, I/O, control-flow
(if/else, while, for), functions, calls, and returns to flat three-address IR.
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
    LabelRef,
    Operand,
    Opcode,
    Instruction,
    IRFunction,
    IRModule,
    RegionInfo,
)
from cpp2py.frontend import ast_nodes as ast

if TYPE_CHECKING:
    from cpp2py.semantics.symbols import SemanticInfo, Symbol
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
        self._regions: dict[str, RegionInfo] = {}
        self._symbol_ir_names: dict[int, str] = {}
        self._name_counters: dict[str, int] = {}
        self._active_scope_symbols: list[set[int]] = []
        self._current_return_type: IRType = IRType.I32

    def _sym_ir_type(self, sym: Symbol | None) -> IRType:
        if sym is not None and sym.type is not None:
            if hasattr(sym.type, "bits") and sym.type.bits == 64:
                return IRType.I64
        return IRType.I32

    def _emit_cast_if_needed(self, op: Operand, target_type: IRType, span: SourceSpan | None) -> Operand:
        op_type = getattr(op, "type", IRType.I32)
        if op_type == target_type:
            return op
        temp = TempRef(self._allocator.next_temp_id(), target_type)
        self._instructions.append(Instruction(
            op_id=self._allocator.next_op_id(),
            opcode=Opcode.CAST,
            dst=temp,
            operands=(op,),
            span=span,
        ))
        return temp

    def build(self) -> IRModule:
        functions: list[IRFunction] = []

        for func in self._program.functions:
            ir_func = self._build_function(func)
            functions.append(ir_func)

        source_name = self._program.span.file if self._program.span else ""
        return IRModule(functions=functions, source_name=source_name)

    def _get_ir_name(self, sym: Symbol) -> str:
        if sym.symbol_id in self._symbol_ir_names:
            return self._symbol_ir_names[sym.symbol_id]

        # Check if another symbol with the same name is currently active in enclosing scopes
        name = sym.name
        is_shadowing = any(
            self._symbol_ir_names.get(sid, "") == name or self._symbol_ir_names.get(sid, "").startswith(f"{name}_")
            for scope in self._active_scope_symbols
            for sid in scope
        )

        if is_shadowing:
            counter = self._name_counters.get(name, 0) + 1
            self._name_counters[name] = counter
            ir_name = f"{name}_{counter}"
        else:
            ir_name = name

        self._symbol_ir_names[sym.symbol_id] = ir_name
        return ir_name

    def _enter_scope(self) -> None:
        self._active_scope_symbols.append(set())

    def _exit_scope(self) -> None:
        self._active_scope_symbols.pop()

    def _register_active_symbol(self, sym: Symbol) -> str:
        ir_name = self._get_ir_name(sym)
        if self._active_scope_symbols:
            self._active_scope_symbols[-1].add(sym.symbol_id)
        return ir_name

    def _build_function(self, func: ast.FunctionDef) -> IRFunction:
        self._instructions = []
        self._regions = {}
        self._symbol_ir_names = {}
        self._name_counters = {}
        self._active_scope_symbols = []

        self._enter_scope()

        # Build parameters
        params: list[VarRef] = []
        for p in func.params:
            sym = self._info.symbols_by_node.get(p.node_id)
            if sym is not None:
                ir_name = self._register_active_symbol(sym)
                p_type = self._sym_ir_type(sym)
                params.append(VarRef(symbol_id=sym.symbol_id, ir_name=ir_name, type=p_type))

        if func.return_type.name == "int":
            ret_type = IRType.I32
        elif func.return_type.name == "long long":
            ret_type = IRType.I64
        else:
            ret_type = IRType.VOID
        self._current_return_type = ret_type

        # Lower body statements
        for stmt in func.body.statements:
            self._lower_stmt(stmt)

        self._exit_scope()

        # Check if function ends with return
        has_return = (len(self._instructions) > 0 and
                      self._instructions[-1].opcode == Opcode.RETURN)

        if not has_return:
            closing_pos = func.body.span.end
            closing_span = SourceSpan(
                file=func.body.span.file,
                start=closing_pos,
                end=closing_pos,
            )
            if func.name == "main":
                # Implicit return 0 for main
                ret_instr = Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.RETURN,
                    operands=(Const(0, IRType.I32),),
                    span=closing_span,
                )
                self._instructions.append(ret_instr)
            elif ret_type == IRType.VOID:
                # Implicit void return
                ret_instr = Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.RETURN,
                    operands=(),
                    span=closing_span,
                )
                self._instructions.append(ret_instr)

        return IRFunction(
            name=func.name,
            params=tuple(params),
            return_type=ret_type,
            body=list(self._instructions),
            regions=dict(self._regions),
        )

    def _lower_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.Block):
            self._enter_scope()
            for s in stmt.statements:
                self._lower_stmt(s)
            self._exit_scope()

        elif isinstance(stmt, ast.DeclStmt):
            for decl in stmt.declarators:
                sym = self._info.symbols_by_node.get(decl.node_id)
                symbol_id = sym.symbol_id if sym is not None else 0
                ir_name = self._register_active_symbol(sym) if sym is not None else decl.name
                var_type = self._sym_ir_type(sym)
                var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

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
                    init_val = self._emit_cast_if_needed(init_val, var_type, decl.span)
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
            ir_name = self._get_ir_name(sym) if sym is not None else stmt.target.name
            var_type = self._sym_ir_type(sym)
            var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

            val_op = self._lower_expr(stmt.value)

            if stmt.op == '=':
                val_op = self._emit_cast_if_needed(val_op, var_type, stmt.span)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.ASSIGN,
                    dst=var_ref,
                    operands=(val_op,),
                    span=stmt.span,
                ))
            else:
                op_map = {
                    '+=': Opcode.ADD,
                    '-=': Opcode.SUB,
                    '*=': Opcode.MUL,
                    '/=': Opcode.DIV,
                    '%=': Opcode.MOD,
                }
                opcode = op_map[stmt.op]
                rhs_type = getattr(val_op, "type", IRType.I32)
                common_type = IRType.I64 if (var_type == IRType.I64 or rhs_type == IRType.I64) else IRType.I32
                lhs_cast = self._emit_cast_if_needed(var_ref, common_type, stmt.span)
                rhs_cast = self._emit_cast_if_needed(val_op, common_type, stmt.span)
                temp = TempRef(self._allocator.next_temp_id(), common_type)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=opcode,
                    dst=temp,
                    operands=(lhs_cast, rhs_cast),
                    span=stmt.span,
                ))
                res = self._emit_cast_if_needed(temp, var_type, stmt.span)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.ASSIGN,
                    dst=var_ref,
                    operands=(res,),
                    span=stmt.span,
                ))

        elif isinstance(stmt, ast.IncDecStmt):
            sym = self._info.symbols_by_node.get(stmt.target.node_id)
            symbol_id = sym.symbol_id if sym is not None else 0
            ir_name = self._get_ir_name(sym) if sym is not None else stmt.target.name
            var_type = self._sym_ir_type(sym)
            var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

            opcode = Opcode.ADD if stmt.op == '++' else Opcode.SUB
            temp = TempRef(self._allocator.next_temp_id(), var_type)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=opcode,
                dst=temp,
                operands=(var_ref, Const(1, var_type)),
                span=stmt.span,
            ))
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.ASSIGN,
                dst=var_ref,
                operands=(temp,),
                span=stmt.span,
            ))

        elif isinstance(stmt, ast.IfStmt):
            rid = self._allocator.next_region_id()
            self._regions[rid] = RegionInfo(region_id=rid, kind="if", span=stmt.span)

            cond_op = self._lower_condition(stmt.cond)

            l_then = f"if_then_{rid}"
            l_else = f"if_else_{rid}"
            l_end = f"if_end_{rid}"

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.BRANCH,
                operands=(cond_op, LabelRef(l_then), LabelRef(l_else)),
                span=stmt.span,
            ))

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_then,
                operands=(LabelRef(l_then),),
            ))

            self._lower_stmt(stmt.then_body)

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.JUMP,
                label_name=l_end,
                operands=(LabelRef(l_end),),
            ))

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_else,
                operands=(LabelRef(l_else),),
            ))

            if stmt.else_body is not None:
                self._lower_stmt(stmt.else_body)

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_end,
                operands=(LabelRef(l_end),),
            ))

        elif isinstance(stmt, ast.WhileStmt):
            rid = self._allocator.next_region_id()
            self._regions[rid] = RegionInfo(region_id=rid, kind="while", span=stmt.span)

            l_head = f"loop_head_{rid}"
            l_body = f"loop_body_{rid}"
            l_end = f"loop_end_{rid}"

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_head,
                operands=(LabelRef(l_head),),
                role="loop_head",
                region_id=rid,
            ))

            cond_op = self._lower_condition(stmt.cond)

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.BRANCH,
                operands=(cond_op, LabelRef(l_body), LabelRef(l_end)),
                span=stmt.span,
            ))

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_body,
                operands=(LabelRef(l_body),),
            ))

            self._lower_stmt(stmt.body)

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.JUMP,
                label_name=l_head,
                operands=(LabelRef(l_head),),
            ))

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_end,
                operands=(LabelRef(l_end),),
            ))

        elif isinstance(stmt, ast.ForStmt):
            rid = self._allocator.next_region_id()

            loop_var = None
            loop_var_declared_in_init = False
            if isinstance(stmt.init, ast.DeclStmt) and stmt.init.declarators:
                sym = self._info.symbols_by_node.get(stmt.init.declarators[0].node_id)
                loop_var = sym.symbol_id if sym else None
                loop_var_declared_in_init = True
            elif isinstance(stmt.init, ast.AssignStmt):
                sym = self._info.symbols_by_node.get(stmt.init.target.node_id)
                loop_var = sym.symbol_id if sym else None
                loop_var_declared_in_init = False

            self._regions[rid] = RegionInfo(
                region_id=rid,
                kind="for",
                span=stmt.span,
                loop_var=loop_var,
                loop_var_declared_in_init=loop_var_declared_in_init,
            )

            self._enter_scope()

            # 1. Lower init
            if stmt.init is not None:
                self._lower_stmt(stmt.init)

            # 2. Canonical loop shape
            l_head = f"loop_head_{rid}"
            l_body = f"loop_body_{rid}"
            l_end = f"loop_end_{rid}"

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_head,
                operands=(LabelRef(l_head),),
                role="loop_head",
                region_id=rid,
            ))

            cond_op = self._lower_condition(stmt.cond)

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.BRANCH,
                operands=(cond_op, LabelRef(l_body), LabelRef(l_end)),
                span=stmt.span,
            ))

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_body,
                operands=(LabelRef(l_body),),
            ))

            self._lower_stmt(stmt.body)

            if stmt.update is not None:
                self._lower_stmt(stmt.update)

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.JUMP,
                label_name=l_head,
                operands=(LabelRef(l_head),),
            ))

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_end,
                operands=(LabelRef(l_end),),
            ))

            self._exit_scope()

        elif isinstance(stmt, ast.CallStmt):
            self._lower_call(stmt.call, is_expr=False)

        elif isinstance(stmt, ast.InputStmt):
            for target in stmt.targets:
                sym = self._info.symbols_by_node.get(target.node_id)
                symbol_id = sym.symbol_id if sym is not None else 0
                ir_name = self._get_ir_name(sym) if sym is not None else target.name
                var_type = self._sym_ir_type(sym)
                var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

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
                val = self._emit_cast_if_needed(val, self._current_return_type, stmt.span)
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

    def _lower_condition(self, cond: ast.Condition) -> TempRef:
        left_op = self._lower_expr(cond.left)
        right_op = self._lower_expr(cond.right)

        left_type = getattr(left_op, "type", IRType.I32)
        right_type = getattr(right_op, "type", IRType.I32)
        common_type = IRType.I64 if (left_type == IRType.I64 or right_type == IRType.I64) else IRType.I32
        left_op = self._emit_cast_if_needed(left_op, common_type, cond.left.span)
        right_op = self._emit_cast_if_needed(right_op, common_type, cond.right.span)

        cmp_map = {
            '<': 'lt',
            '<=': 'le',
            '>': 'gt',
            '>=': 'ge',
            '==': 'eq',
            '!=': 'ne',
        }
        cmp_op = cmp_map[cond.op]
        temp = TempRef(self._allocator.next_temp_id(), IRType.BOOL)
        self._instructions.append(Instruction(
            op_id=self._allocator.next_op_id(),
            opcode=Opcode.CMP,
            dst=temp,
            operands=(left_op, right_op),
            cmp_op=cmp_op,
            span=cond.span,
        ))
        return temp

    def _lower_call(self, expr: ast.CallExpr, is_expr: bool) -> Operand | None:
        fn_sym = self._info.functions.get(expr.callee)
        arg_ops: list[Operand] = []
        for i, arg in enumerate(expr.args):
            arg_val = self._lower_expr(arg)
            if fn_sym is not None and i < len(fn_sym.params):
                param_sym = fn_sym.params[i]
                param_type = self._sym_ir_type(param_sym)
                arg_val = self._emit_cast_if_needed(arg_val, param_type, arg.span)
            arg_ops.append(arg_val)

        from cpp2py.semantics.types import VoidType, IntType
        node_t = self._info.type_by_node.get(expr.node_id)
        is_void = isinstance(node_t, VoidType) or (fn_sym is not None and isinstance(fn_sym.return_type, VoidType))

        if is_expr and not is_void:
            ret_type = IRType.I64 if (isinstance(node_t, IntType) and node_t.bits == 64) else IRType.I32
            dst = TempRef(self._allocator.next_temp_id(), ret_type)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.CALL,
                dst=dst,
                operands=tuple(arg_ops),
                func_name=expr.callee,
                span=expr.span,
            ))
            return dst
        else:
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.CALL,
                dst=None,
                operands=tuple(arg_ops),
                func_name=expr.callee,
                span=expr.span,
            ))
            return None

    def _lower_expr(self, expr: ast.Expr) -> Operand:
        if isinstance(expr, ast.IntLiteral):
            t = IRType.I64 if expr.value > self._config.target.int_max else IRType.I32
            return Const(expr.value, t)

        elif isinstance(expr, ast.NameExpr):
            sym = self._info.symbols_by_node.get(expr.node_id)
            symbol_id = sym.symbol_id if sym is not None else 0
            ir_name = self._get_ir_name(sym) if sym is not None else expr.name
            var_type = self._sym_ir_type(sym)
            return VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

        elif isinstance(expr, ast.UnaryExpr):
            if expr.op == '+':
                return self._lower_expr(expr.operand)

            operand_val = self._lower_expr(expr.operand)
            op_type = getattr(operand_val, "type", IRType.I32)
            temp = TempRef(self._allocator.next_temp_id(), op_type)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.NEG,
                dst=temp,
                operands=(operand_val,),
                span=expr.span,
            ))
            return temp

        elif isinstance(expr, ast.BinaryExpr):
            left_val = self._lower_expr(expr.left)
            right_val = self._lower_expr(expr.right)
            left_type = getattr(left_val, "type", IRType.I32)
            right_type = getattr(right_val, "type", IRType.I32)
            common_type = IRType.I64 if (left_type == IRType.I64 or right_type == IRType.I64) else IRType.I32
            left_val = self._emit_cast_if_needed(left_val, common_type, expr.left.span)
            right_val = self._emit_cast_if_needed(right_val, common_type, expr.right.span)

            op_map = {
                '+': Opcode.ADD,
                '-': Opcode.SUB,
                '*': Opcode.MUL,
                '/': Opcode.DIV,
                '%': Opcode.MOD,
            }
            opcode = op_map.get(expr.op, Opcode.ADD)
            temp = TempRef(self._allocator.next_temp_id(), common_type)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=opcode,
                dst=temp,
                operands=(left_val, right_val),
                span=expr.span,
            ))
            return temp

        elif isinstance(expr, ast.CallExpr):
            res = self._lower_call(expr, is_expr=True)
            if res is not None:
                return res
            return Const(0, IRType.I32)

        raise NotImplementedError(f"Unsupported expression node: {type(expr)}")
