"""AST to IR lowering for Phase 1 / Phase 2 / Phase 3 language constructs (extended for Arrays, Pointers, <climits>).

Lowers declarations, assignments, compound assignments, inc/dec, I/O, control-flow
(if/else, while, for), functions, calls, and returns to flat three-address IR.
Reuses existing IR representations per ARCH §D.3.4 (calls for memory/pointer primitives).
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
from cpp2py.semantics.types import PointerType, ArrayType, VoidType, IntType

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
            if isinstance(sym.type, (PointerType, ArrayType)):
                return IRType.PTR
            if sym.symbol_id in self._info.addressed_symbols:
                return IRType.PTR
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

    def _decay_array(self, expr: ast.Expr, operand: Operand) -> Operand:
        """Decay an array operand into a pointer (_Ptr(arr, 0))."""
        if isinstance(expr, ast.NameExpr):
            sym = self._info.symbols_by_node.get(expr.node_id)
            if sym is not None and isinstance(sym.type, ArrayType):
                temp = TempRef(self._allocator.next_temp_id(), IRType.PTR)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=temp,
                    operands=(operand,),
                    func_name="_addr_of",
                    span=expr.span,
                ))
                return temp
        return operand

    def build(self) -> IRModule:
        functions: list[IRFunction] = []

        for func in self._program.functions:
            ir_func = self._build_function(func)
            functions.append(ir_func)

        source_name = self._program.span.file if self._program.span else ""
        return IRModule(functions=functions, source_name=source_name)

    def _get_ir_name(self, sym: Symbol | None) -> str:
        if sym is None:
            return "var"
        if sym.symbol_id in self._symbol_ir_names:
            return self._symbol_ir_names[sym.symbol_id]

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

    def _register_active_symbol(self, sym: Symbol) -> str:
        ir_name = self._get_ir_name(sym)
        if self._active_scope_symbols:
            self._active_scope_symbols[-1].add(sym.symbol_id)
        return ir_name

    def _enter_scope(self) -> None:
        self._active_scope_symbols.append(set())

    def _exit_scope(self) -> None:
        self._active_scope_symbols.pop()

    def _build_function(self, func: ast.FunctionDef) -> IRFunction:
        self._instructions = []
        self._regions = {}
        self._name_counters = {}
        self._active_scope_symbols = []

        params: list[VarRef] = []
        param_scope: set[int] = set()

        fn_sym = self._info.functions.get(func.name)
        if fn_sym is not None:
            for p_sym in fn_sym.params:
                p_type = self._sym_ir_type(p_sym)
                ir_name = p_sym.name
                self._symbol_ir_names[p_sym.symbol_id] = ir_name
                param_scope.add(p_sym.symbol_id)
                params.append(VarRef(symbol_id=p_sym.symbol_id, ir_name=ir_name, type=p_type))

        self._active_scope_symbols.append(param_scope)

        ret_type = IRType.VOID if isinstance(fn_sym.return_type if fn_sym else None, VoidType) else (
            IRType.I64 if (fn_sym and isinstance(fn_sym.return_type, IntType) and fn_sym.return_type.bits == 64) else IRType.I32
        )
        self._current_return_type = ret_type

        # Lower body
        for stmt in func.body.statements:
            self._lower_stmt(stmt)

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
                ret_instr = Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.RETURN,
                    operands=(Const(0, IRType.I32),),
                    span=closing_span,
                )
                self._instructions.append(ret_instr)
            elif ret_type == IRType.VOID:
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

                # 2. Array declaration
                if decl.array_size is not None:
                    size = sym.type.size if (sym and isinstance(sym.type, ArrayType)) else 1
                    init_ops: list[Operand] = []
                    if decl.init is not None and isinstance(decl.init, ast.InitializerList):
                        for elem in decl.init.elements:
                            init_ops.append(self._lower_expr(elem))
                    while len(init_ops) < size:
                        init_ops.append(Const(0, IRType.I32))
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=var_ref,
                        operands=tuple(init_ops),
                        func_name="_array_init",
                        span=stmt.span,
                    ))

                # 3. Addressed scalar variable (stored as 1-element list)
                elif sym is not None and sym.symbol_id in self._info.addressed_symbols:
                    init_val = self._lower_expr(decl.init) if decl.init is not None else Const(0, IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=var_ref,
                        operands=(init_val,),
                        func_name="_array_init",
                        span=stmt.span,
                    ))

                # 4. Normal scalar or pointer
                elif decl.init is not None:
                    init_val = self._lower_expr(decl.init)
                    if decl.is_pointer:
                        init_val = self._decay_array(decl.init, init_val)
                    init_val = self._emit_cast_if_needed(init_val, var_type, decl.span)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.ASSIGN,
                        dst=var_ref,
                        operands=(init_val,),
                        span=stmt.span,
                    ))

        elif isinstance(stmt, ast.AssignStmt):
            val_op = self._lower_expr(stmt.value)

            if isinstance(stmt.target, ast.NameExpr):
                sym = self._info.symbols_by_node.get(stmt.target.node_id)
                symbol_id = sym.symbol_id if sym is not None else 0
                ir_name = self._get_ir_name(sym) if sym is not None else stmt.target.name
                var_type = self._sym_ir_type(sym)
                var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

                if sym is not None and isinstance(sym.type, PointerType):
                    val_op = self._decay_array(stmt.value, val_op)

                if sym is not None and sym.symbol_id in self._info.addressed_symbols:
                    if stmt.op != '=':
                        op_map = {'+=': Opcode.ADD, '-=': Opcode.SUB, '*=': Opcode.MUL, '/=': Opcode.DIV, '%=': Opcode.MOD}
                        cur_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                        self._instructions.append(Instruction(
                            op_id=self._allocator.next_op_id(),
                            opcode=Opcode.CALL,
                            dst=cur_temp,
                            operands=(var_ref, Const(0, IRType.I32)),
                            func_name="_get_index",
                            span=stmt.span,
                        ))
                        res_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                        self._instructions.append(Instruction(
                            op_id=self._allocator.next_op_id(),
                            opcode=op_map[stmt.op],
                            dst=res_temp,
                            operands=(cur_temp, val_op),
                            span=stmt.span,
                        ))
                        val_op = res_temp
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=None,
                        operands=(var_ref, Const(0, IRType.I32), val_op),
                        func_name="_set_index",
                        span=stmt.span,
                    ))
                else:
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
                        op_map = {'+=': Opcode.ADD, '-=': Opcode.SUB, '*=': Opcode.MUL, '/=': Opcode.DIV, '%=': Opcode.MOD}
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

            elif isinstance(stmt.target, ast.IndexExpr):
                arr_op = self._lower_expr(stmt.target.array)
                idx_op = self._lower_expr(stmt.target.index)
                if stmt.op != '=':
                    op_map = {'+=': Opcode.ADD, '-=': Opcode.SUB, '*=': Opcode.MUL, '/=': Opcode.DIV, '%=': Opcode.MOD}
                    cur_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=cur_temp,
                        operands=(arr_op, idx_op),
                        func_name="_get_index",
                        span=stmt.span,
                    ))
                    res_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=op_map[stmt.op],
                        dst=res_temp,
                        operands=(cur_temp, val_op),
                        span=stmt.span,
                    ))
                    val_op = res_temp
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=None,
                    operands=(arr_op, idx_op, val_op),
                    func_name="_set_index",
                    span=stmt.span,
                ))

            elif isinstance(stmt.target, ast.DerefExpr):
                ptr_op = self._lower_expr(stmt.target.operand)
                if stmt.op != '=':
                    op_map = {'+=': Opcode.ADD, '-=': Opcode.SUB, '*=': Opcode.MUL, '/=': Opcode.DIV, '%=': Opcode.MOD}
                    cur_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=cur_temp,
                        operands=(ptr_op,),
                        func_name="_get_deref",
                        span=stmt.span,
                    ))
                    res_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=op_map[stmt.op],
                        dst=res_temp,
                        operands=(cur_temp, val_op),
                        span=stmt.span,
                    ))
                    val_op = res_temp
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=None,
                    operands=(ptr_op, val_op),
                    func_name="_set_deref",
                    span=stmt.span,
                ))

        elif isinstance(stmt, ast.IncDecStmt):
            op_map = {'++': Opcode.ADD, '--': Opcode.SUB}
            opcode = op_map[stmt.op]

            if isinstance(stmt.target, ast.NameExpr):
                sym = self._info.symbols_by_node.get(stmt.target.node_id)
                symbol_id = sym.symbol_id if sym is not None else 0
                ir_name = self._get_ir_name(sym) if sym is not None else stmt.target.name
                var_type = self._sym_ir_type(sym)
                var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

                if sym is not None and sym.symbol_id in self._info.addressed_symbols:
                    cur_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=cur_temp,
                        operands=(var_ref, Const(0, IRType.I32)),
                        func_name="_get_index",
                        span=stmt.span,
                    ))
                    res_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=opcode,
                        dst=res_temp,
                        operands=(cur_temp, Const(1, IRType.I32)),
                        span=stmt.span,
                    ))
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=None,
                        operands=(var_ref, Const(0, IRType.I32), res_temp),
                        func_name="_set_index",
                        span=stmt.span,
                    ))
                else:
                    step_type = IRType.I32 if var_type == IRType.PTR else var_type
                    temp = TempRef(self._allocator.next_temp_id(), var_type)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=opcode,
                        dst=temp,
                        operands=(var_ref, Const(1, step_type)),
                        span=stmt.span,
                    ))
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.ASSIGN,
                        dst=var_ref,
                        operands=(temp,),
                        span=stmt.span,
                    ))

            elif isinstance(stmt.target, ast.IndexExpr):
                arr_op = self._lower_expr(stmt.target.array)
                idx_op = self._lower_expr(stmt.target.index)
                cur_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=cur_temp,
                    operands=(arr_op, idx_op),
                    func_name="_get_index",
                    span=stmt.span,
                ))
                res_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=opcode,
                    dst=res_temp,
                    operands=(cur_temp, Const(1, IRType.I32)),
                    span=stmt.span,
                ))
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=None,
                    operands=(arr_op, idx_op, res_temp),
                    func_name="_set_index",
                    span=stmt.span,
                ))

            elif isinstance(stmt.target, ast.DerefExpr):
                ptr_op = self._lower_expr(stmt.target.operand)
                cur_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=cur_temp,
                    operands=(ptr_op,),
                    func_name="_get_deref",
                    span=stmt.span,
                ))
                res_temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=opcode,
                    dst=res_temp,
                    operands=(cur_temp, Const(1, IRType.I32)),
                    span=stmt.span,
                ))
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=None,
                    operands=(ptr_op, res_temp),
                    func_name="_set_deref",
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

            loop_var_sym: int | None = None
            declared_in_init = False
            if stmt.init is not None and isinstance(stmt.init, ast.DeclStmt):
                if len(stmt.init.declarators) == 1:
                    d = stmt.init.declarators[0]
                    s = self._info.symbols_by_node.get(d.node_id)
                    if s is not None:
                        loop_var_sym = s.symbol_id
                        declared_in_init = True
            elif stmt.init is not None and isinstance(stmt.init, ast.AssignStmt):
                if isinstance(stmt.init.target, ast.NameExpr):
                    s = self._info.symbols_by_node.get(stmt.init.target.node_id)
                    if s is not None:
                        loop_var_sym = s.symbol_id

            self._regions[rid] = RegionInfo(
                region_id=rid,
                kind="for",
                span=stmt.span,
                loop_var=loop_var_sym,
                loop_var_declared_in_init=declared_in_init,
            )

            self._enter_scope()

            if stmt.init is not None:
                self._lower_stmt(stmt.init)

            l_head = f"loop_head_{rid}"
            l_body = f"loop_body_{rid}"
            l_end = f"loop_end_{rid}"

            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.LABEL,
                label_name=l_head,
                operands=(LabelRef(l_head),),
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
                if isinstance(target, ast.NameExpr):
                    sym = self._info.symbols_by_node.get(target.node_id)
                    symbol_id = sym.symbol_id if sym is not None else 0
                    ir_name = self._get_ir_name(sym) if sym is not None else target.name
                    var_type = self._sym_ir_type(sym)
                    var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

                    if sym is not None and sym.symbol_id in self._info.addressed_symbols:
                        temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                        self._instructions.append(Instruction(
                            op_id=self._allocator.next_op_id(),
                            opcode=Opcode.READ,
                            dst=temp,
                            operands=(temp,),
                            span=stmt.span,
                        ))
                        self._instructions.append(Instruction(
                            op_id=self._allocator.next_op_id(),
                            opcode=Opcode.CALL,
                            dst=None,
                            operands=(var_ref, Const(0, IRType.I32), temp),
                            func_name="_set_index",
                            span=stmt.span,
                        ))
                    else:
                        self._instructions.append(Instruction(
                            op_id=self._allocator.next_op_id(),
                            opcode=Opcode.READ,
                            dst=var_ref,
                            operands=(var_ref,),
                            span=stmt.span,
                        ))
                elif isinstance(target, ast.IndexExpr):
                    arr_op = self._lower_expr(target.array)
                    idx_op = self._lower_expr(target.index)
                    temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.READ,
                        dst=temp,
                        operands=(temp,),
                        span=stmt.span,
                    ))
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=None,
                        operands=(arr_op, idx_op, temp),
                        func_name="_set_index",
                        span=stmt.span,
                    ))
                elif isinstance(target, ast.DerefExpr):
                    ptr_op = self._lower_expr(target.operand)
                    temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.READ,
                        dst=temp,
                        operands=(temp,),
                        span=stmt.span,
                    ))
                    self._instructions.append(Instruction(
                        op_id=self._allocator.next_op_id(),
                        opcode=Opcode.CALL,
                        dst=None,
                        operands=(ptr_op, temp),
                        func_name="_set_deref",
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
        if left_type == IRType.PTR or right_type == IRType.PTR:
            common_type = IRType.PTR
        else:
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
                if param_type == IRType.PTR:
                    arg_val = self._decay_array(arg, arg_val)
                arg_val = self._emit_cast_if_needed(arg_val, param_type, arg.span)
            arg_ops.append(arg_val)

        node_t = self._info.type_by_node.get(expr.node_id)
        is_void = isinstance(node_t, VoidType) or (fn_sym is not None and isinstance(fn_sym.return_type, VoidType))

        if is_expr and not is_void:
            ret_type = IRType.I64 if (isinstance(node_t, IntType) and node_t.bits == 64) else (
                IRType.PTR if isinstance(node_t, PointerType) else IRType.I32
            )
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
            t = IRType.I64 if (expr.value > self._config.target.int_max or expr.value < self._config.target.int_min) else IRType.I32
            return Const(expr.value, t)

        elif isinstance(expr, ast.NullptrLiteral):
            return Const(0, IRType.PTR)

        elif isinstance(expr, ast.NameExpr):
            if expr.name in self._info.constants:
                val = self._info.constants[expr.name]
                t = IRType.I64 if (val > self._config.target.int_max or val < self._config.target.int_min) else IRType.I32
                return Const(val, t)

            sym = self._info.symbols_by_node.get(expr.node_id)
            symbol_id = sym.symbol_id if sym is not None else 0
            ir_name = self._get_ir_name(sym) if sym is not None else expr.name
            var_type = self._sym_ir_type(sym)

            if sym is not None and sym.symbol_id in self._info.addressed_symbols:
                var_ref = VarRef(symbol_id=symbol_id, ir_name=ir_name, type=IRType.PTR)
                temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=temp,
                    operands=(var_ref, Const(0, IRType.I32)),
                    func_name="_get_index",
                    span=expr.span,
                ))
                return temp

            return VarRef(symbol_id=symbol_id, ir_name=ir_name, type=var_type)

        elif isinstance(expr, ast.AddressOfExpr):
            if isinstance(expr.operand, ast.NameExpr):
                sym = self._info.symbols_by_node.get(expr.operand.node_id)
                var_ref = VarRef(sym.symbol_id if sym else 0, self._get_ir_name(sym) if sym else expr.operand.name, type=IRType.PTR)
                temp = TempRef(self._allocator.next_temp_id(), IRType.PTR)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=temp,
                    operands=(var_ref,),
                    func_name="_addr_of",
                    span=expr.span,
                ))
                return temp
            elif isinstance(expr.operand, ast.IndexExpr):
                arr_op = self._lower_expr(expr.operand.array)
                idx_op = self._lower_expr(expr.operand.index)
                temp = TempRef(self._allocator.next_temp_id(), IRType.PTR)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.CALL,
                    dst=temp,
                    operands=(arr_op, idx_op),
                    func_name="_addr_of",
                    span=expr.span,
                ))
                return temp
            elif isinstance(expr.operand, ast.DerefExpr):
                return self._lower_expr(expr.operand.operand)

        elif isinstance(expr, ast.DerefExpr):
            ptr_op = self._lower_expr(expr.operand)
            temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.CALL,
                dst=temp,
                operands=(ptr_op,),
                func_name="_get_deref",
                span=expr.span,
            ))
            return temp

        elif isinstance(expr, ast.IndexExpr):
            arr_op = self._lower_expr(expr.array)
            idx_op = self._lower_expr(expr.index)
            temp = TempRef(self._allocator.next_temp_id(), IRType.I32)
            self._instructions.append(Instruction(
                op_id=self._allocator.next_op_id(),
                opcode=Opcode.CALL,
                dst=temp,
                operands=(arr_op, idx_op),
                func_name="_get_index",
                span=expr.span,
            ))
            return temp

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
            if expr.op in ('+', '-'):
                left_val = self._decay_array(expr.left, left_val)
                right_val = self._decay_array(expr.right, right_val)
            left_type = getattr(left_val, "type", IRType.I32)
            right_type = getattr(right_val, "type", IRType.I32)

            if left_type == IRType.PTR or right_type == IRType.PTR:
                res_type = IRType.I32 if (left_type == IRType.PTR and right_type == IRType.PTR and expr.op == '-') else IRType.PTR
                temp = TempRef(self._allocator.next_temp_id(), res_type)
                self._instructions.append(Instruction(
                    op_id=self._allocator.next_op_id(),
                    opcode=Opcode.ADD if expr.op == '+' else Opcode.SUB,
                    dst=temp,
                    operands=(left_val, right_val),
                    span=expr.span,
                ))
                return temp

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
            return res if res is not None else Const(0, IRType.I32)

        return Const(0, IRType.I32)
