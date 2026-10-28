from __future__ import annotations

from cpp2py.config import CompilerConfig
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend import ast_nodes as ast
from cpp2py.semantics.types import Type, IntType, VoidType, BoolType, ArrayType, PointerType, NullptrType
from cpp2py.semantics.symbols import Symbol, SymbolKind, FunctionSymbol, SemanticInfo

RESERVED_NAMES = frozenset({'cin', 'cout', 'endl', 'std', 'main'})

def analyze(program: ast.Program | None, config: CompilerConfig,
            sink: DiagnosticSink) -> SemanticInfo | None:
    if program is None:
        return None
    analyzer = _Analyzer(program, config, sink)
    return analyzer.run()

class _Analyzer:
    def __init__(self, program: ast.Program, config: CompilerConfig,
                 sink: DiagnosticSink) -> None:
        self._program = program
        self._config = config
        self._sink = sink
        self._info = SemanticInfo()
        self._functions: dict[str, FunctionSymbol] = {}
        self._current_function: FunctionSymbol | None = None
        self._scopes: list[dict[str, Symbol]] = []
        self._assigned: set[int] = set()
        self._next_symbol_id = 0
        self._uses_std = program.uses_std
        self._climits_constants: dict[str, int] = (
            config.target.climits_macros() if program.includes_climits else {}
        )
        self._info.constants.update(self._climits_constants)

    def _alloc_symbol_id(self) -> int:
        sid = self._next_symbol_id
        self._next_symbol_id += 1
        return sid

    def _enter_scope(self) -> None:
        self._scopes.append({})

    def _exit_scope(self) -> None:
        self._scopes.pop()

    def _lookup_var(self, name: str) -> Symbol | None:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        if name in self._climits_constants:
            val = self._climits_constants[name]
            bits = 64 if (val < -(1 << 31) or val > (1 << 31) - 1) else 32
            return Symbol(
                self._alloc_symbol_id(),
                name,
                IntType(bits),
                SymbolKind.CONSTANT,
                None,
            )
        return None

    def run(self) -> SemanticInfo | None:
        for func in self._program.functions:
            self._analyze_function(func)

        if self._sink.has_errors():
            return None
        return self._info

    def _analyze_function(self, func: ast.FunctionDef) -> None:

        if func.name in self._functions:
            self._sink.error("E3002", f"duplicate function name '{func.name}'", func.span)
            return

        int_bits = self._config.target.int_bits
        ll_bits = self._config.target.long_long_bits
        ret_type: Type
        if func.return_type.name == "int":
            ret_type = IntType(int_bits)
        elif func.return_type.name == "long long":
            ret_type = IntType(ll_bits)
        else:
            ret_type = VoidType()

        param_symbols: list[Symbol] = []
        seen_param_names: set[str] = set()
        for p in func.params:
            if p.name in seen_param_names or p.name in RESERVED_NAMES:
                self._sink.error("E3002", f"duplicate parameter name '{p.name}'", p.span)
                continue
            seen_param_names.add(p.name)
            p_bits = ll_bits if p.type_spec.name == "long long" else int_bits
            base_type = IntType(p_bits)

            p_type: Type
            if p.is_pointer or p.is_array:

                p_type = PointerType(base_type)
            else:
                p_type = base_type

            sym = Symbol(self._alloc_symbol_id(), p.name, p_type,
                         SymbolKind.PARAMETER, p.span)
            param_symbols.append(sym)
            self._info.symbols_by_node[p.node_id] = sym

        func_sym = FunctionSymbol(func.name, ret_type, tuple(param_symbols), func.span)
        self._functions[func.name] = func_sym
        self._info.functions[func.name] = func_sym
        self._current_function = func_sym

        self._scopes = [{}]
        for p_sym in param_symbols:
            self._scopes[0][p_sym.name] = p_sym

        self._assigned = {p_sym.symbol_id for p_sym in param_symbols}

        self._analyze_block(func.body, push_scope=False)

        if func.name != "main" and isinstance(ret_type, IntType):
            if not self._returns_on_all_paths(func.body):
                self._sink.error("E3007", f"missing return on some path of function '{func.name}'", func.span)

    def _returns_on_all_paths(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.ReturnStmt):
            return True
        elif isinstance(stmt, ast.Block):
            for s in stmt.statements:
                if self._returns_on_all_paths(s):
                    return True
            return False
        elif isinstance(stmt, ast.IfStmt):
            if stmt.else_body is None:
                return False
            return self._returns_on_all_paths(stmt.then_body) and self._returns_on_all_paths(stmt.else_body)
        return False

    def _analyze_block(self, block: ast.Block, push_scope: bool = True) -> None:
        if push_scope:
            self._enter_scope()

        for stmt in block.statements:
            self._analyze_stmt(stmt)

        if push_scope:
            self._exit_scope()

    def _analyze_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.Block):
            self._analyze_block(stmt, push_scope=True)
        elif isinstance(stmt, ast.DeclStmt):
            self._analyze_decl(stmt)
        elif isinstance(stmt, ast.AssignStmt):
            self._analyze_assign(stmt)
        elif isinstance(stmt, ast.IncDecStmt):
            self._analyze_incdec(stmt)
        elif isinstance(stmt, ast.IfStmt):
            self._analyze_if(stmt)
        elif isinstance(stmt, ast.WhileStmt):
            self._analyze_while(stmt)
        elif isinstance(stmt, ast.ForStmt):
            self._analyze_for(stmt)
        elif isinstance(stmt, ast.CallStmt):
            self._analyze_call_stmt(stmt)
        elif isinstance(stmt, ast.InputStmt):
            self._analyze_input(stmt)
        elif isinstance(stmt, ast.OutputStmt):
            self._analyze_output(stmt)
        elif isinstance(stmt, ast.ReturnStmt):
            self._analyze_return(stmt)

    def _eval_const_expr(self, expr: ast.Expr) -> int | None:
        if isinstance(expr, ast.IntLiteral):
            return expr.value
        elif isinstance(expr, ast.NameExpr):
            if expr.name in self._info.constants:
                return self._info.constants[expr.name]
            return None
        elif isinstance(expr, ast.UnaryExpr):
            sub = self._eval_const_expr(expr.operand)
            if sub is not None:
                return -sub if expr.op == '-' else sub
            return None
        elif isinstance(expr, ast.BinaryExpr):
            left = self._eval_const_expr(expr.left)
            right = self._eval_const_expr(expr.right)
            if left is not None and right is not None:
                if expr.op == '+':
                    return left + right
                elif expr.op == '-':
                    return left - right
                elif expr.op == '*':
                    return left * right
                elif expr.op == '/' and right != 0:
                    return left // right
                elif expr.op == '%' and right != 0:
                    return left % right
            return None
        return None

    def _analyze_decl(self, stmt: ast.DeclStmt) -> None:
        int_bits = self._config.target.int_bits
        ll_bits = self._config.target.long_long_bits
        var_bits = ll_bits if stmt.type_spec.name == "long long" else int_bits
        base_type = IntType(var_bits)

        for decl in stmt.declarators:
            name = decl.name

            if name in RESERVED_NAMES:
                self._sink.error("E3002", f"cannot declare '{name}' as a variable", decl.span)
                continue

            current_scope = self._scopes[-1]
            if name in current_scope:
                self._sink.error("E3002", f"redeclaration of '{name}'", decl.span)
                continue

            if decl.is_pointer:
                ptr_type = PointerType(base_type)
                sym = Symbol(self._alloc_symbol_id(), name, ptr_type,
                             SymbolKind.VARIABLE, decl.span)
                current_scope[name] = sym
                self._info.symbols_by_node[decl.node_id] = sym

                if decl.init is not None:
                    init_type = self._analyze_expr(decl.init)
                    if isinstance(init_type, VoidType):
                        self._sink.error("E3004", f"cannot initialize pointer '{name}' with void expression", decl.span)
                    elif not isinstance(init_type, (PointerType, NullptrType, ArrayType)):
                        self._sink.error("E3004", f"cannot initialize pointer '{name}' with integer expression", decl.span)
                    self._assigned.add(sym.symbol_id)

            elif decl.array_size is not None:
                size_type = self._analyze_expr(decl.array_size)
                if not isinstance(size_type, IntType):
                    self._sink.error("E3004", f"array size must be an integer, got '{size_type}'", decl.array_size.span)
                    size = 1
                    arr_type = ArrayType(base_type, size)
                else:
                    const_size = self._eval_const_expr(decl.array_size)
                    if const_size is not None:
                        if const_size <= 0:
                            self._sink.error("E3003", "array size must be a positive constant integer", decl.array_size.span)
                            size = 1
                        else:
                            size = const_size
                        arr_type = ArrayType(base_type, size)
                    else:
                        size = None
                        arr_type = ArrayType(base_type, None)

                sym = Symbol(self._alloc_symbol_id(), name, arr_type,
                             SymbolKind.VARIABLE, decl.span)
                current_scope[name] = sym
                self._info.symbols_by_node[decl.node_id] = sym
                self._assigned.add(sym.symbol_id)

                if decl.init is not None:
                    if size is None:
                        self._sink.error("E3003", f"variable-sized array '{name}' cannot have an initializer", decl.init.span)
                    elif isinstance(decl.init, ast.InitializerList):
                        if len(decl.init.elements) > size:
                            self._sink.error("E3003", f"too many initializers for array '{name}' of size {size}", decl.init.span)
                        for elem in decl.init.elements:
                            elem_t = self._analyze_expr(elem)
                            if not isinstance(elem_t, IntType):
                                self._sink.error("E3004", f"array initializer must be integer, got '{elem_t}'", elem.span)
                    else:
                        self._sink.error("E3003", f"array '{name}' must be initialized with an initializer list", decl.init.span)

            else:
                sym = Symbol(self._alloc_symbol_id(), name, base_type,
                             SymbolKind.VARIABLE, decl.span)
                current_scope[name] = sym
                self._info.symbols_by_node[decl.node_id] = sym

                if decl.init is not None:
                    init_type = self._analyze_expr(decl.init)
                    if isinstance(init_type, VoidType):
                        self._sink.error("E3004", f"cannot initialize variable '{name}' with void expression", decl.span)
                    elif isinstance(init_type, (PointerType, NullptrType, ArrayType)):
                        self._sink.error("E3004", f"cannot initialize scalar variable '{name}' with pointer/array", decl.span)
                    self._assigned.add(sym.symbol_id)

    def _analyze_assign(self, stmt: ast.AssignStmt) -> None:
        target = stmt.target

        if isinstance(target, ast.NameExpr):
            name = target.name
            sym = self._lookup_var(name)

            if sym is None:
                self._sink.error("E3001", f"undeclared identifier '{name}'", target.span)
                return

            if sym.kind == SymbolKind.CONSTANT:
                self._sink.error("E3005", f"cannot assign to constant '{name}'", target.span)
                return

            if sym.kind not in (SymbolKind.VARIABLE, SymbolKind.PARAMETER):
                self._sink.error("E3005", f"'{name}' is not an assignable variable", target.span)
                return

            self._info.symbols_by_node[target.node_id] = sym

            if stmt.op != '=':
                if sym.symbol_id not in self._assigned:
                    self._sink.error("E3003", f"variable '{name}' may be used before being assigned", target.span)

            val_type = self._analyze_expr(stmt.value)
            if isinstance(val_type, VoidType):
                self._sink.error("E3004", f"cannot assign void expression to '{name}'", stmt.span)

            if isinstance(sym.type, PointerType):
                if not isinstance(val_type, (PointerType, NullptrType, ArrayType)):
                    self._sink.error("E3004", f"cannot assign integer to pointer '{name}'", stmt.span)
            elif isinstance(sym.type, ArrayType):
                self._sink.error("E3005", f"cannot assign to entire array '{name}'", stmt.span)
            elif isinstance(sym.type, IntType):
                if isinstance(val_type, (PointerType, NullptrType, ArrayType)):
                    self._sink.error("E3004", f"cannot assign pointer/array to integer '{name}'", stmt.span)

            self._assigned.add(sym.symbol_id)

        elif isinstance(target, ast.IndexExpr):
            elem_t = self._analyze_expr(target)
            val_type = self._analyze_expr(stmt.value)
            if isinstance(val_type, VoidType):
                self._sink.error("E3004", "cannot assign void expression to array element", stmt.span)
            elif isinstance(elem_t, IntType) and isinstance(val_type, (PointerType, NullptrType)):
                self._sink.error("E3004", "cannot assign pointer to integer array element", stmt.span)

        elif isinstance(target, ast.DerefExpr):
            pointee_t = self._analyze_expr(target)
            val_type = self._analyze_expr(stmt.value)
            if isinstance(val_type, VoidType):
                self._sink.error("E3004", "cannot assign void expression through pointer", stmt.span)
            elif isinstance(pointee_t, IntType) and isinstance(val_type, (PointerType, NullptrType)):
                self._sink.error("E3004", "cannot assign pointer through integer pointer", stmt.span)

    def _analyze_incdec(self, stmt: ast.IncDecStmt) -> None:
        target = stmt.target
        if isinstance(target, ast.NameExpr):
            name = target.name
            sym = self._lookup_var(name)

            if sym is None:
                self._sink.error("E3001", f"undeclared identifier '{name}'", target.span)
                return

            if sym.kind not in (SymbolKind.VARIABLE, SymbolKind.PARAMETER):
                self._sink.error("E3005", f"'{name}' is not an assignable variable", target.span)
                return

            self._info.symbols_by_node[target.node_id] = sym

            if sym.symbol_id not in self._assigned:
                self._sink.error("E3003", f"variable '{name}' may be used before being assigned", target.span)

            self._assigned.add(sym.symbol_id)
        else:
            self._analyze_expr(target)

    def _analyze_if(self, stmt: ast.IfStmt) -> None:
        self._analyze_condition(stmt.cond)

        saved_assigned = set(self._assigned)

        self._analyze_stmt(stmt.then_body)
        then_assigned = set(self._assigned)

        if stmt.else_body is not None:
            self._assigned = set(saved_assigned)
            self._analyze_stmt(stmt.else_body)
            else_assigned = set(self._assigned)
            self._assigned = then_assigned & else_assigned
        else:
            self._assigned = saved_assigned

    def _analyze_while(self, stmt: ast.WhileStmt) -> None:
        self._analyze_condition(stmt.cond)

        saved_assigned = set(self._assigned)
        self._analyze_stmt(stmt.body)
        self._assigned = saved_assigned

    def _analyze_for(self, stmt: ast.ForStmt) -> None:
        self._enter_scope()

        if stmt.init is not None:
            self._analyze_stmt(stmt.init)

        self._analyze_condition(stmt.cond)

        saved_assigned = set(self._assigned)

        self._analyze_stmt(stmt.body)
        if stmt.update is not None:
            self._analyze_stmt(stmt.update)

        self._assigned = saved_assigned
        self._exit_scope()

    def _analyze_call_stmt(self, stmt: ast.CallStmt) -> None:
        self._analyze_call_expr(stmt.call, as_statement=True)

    def _analyze_condition(self, cond: ast.Condition) -> None:
        left_type = self._analyze_expr(cond.left)
        right_type = self._analyze_expr(cond.right)

        if isinstance(left_type, VoidType) or isinstance(right_type, VoidType):
            self._sink.error("E3004", "void expression cannot be used in comparison", cond.span)

        self._info.type_by_node[cond.node_id] = BoolType()

    def _analyze_input(self, stmt: ast.InputStmt) -> None:
        if not stmt.qualified and not self._uses_std:
            self._sink.error("E3001",
                             "undeclared identifier 'cin' (use 'std::cin' or add 'using namespace std;')",
                             stmt.span)

        for target in stmt.targets:
            if isinstance(target, ast.NameExpr):
                name = target.name
                sym = self._lookup_var(name)

                if sym is None:
                    self._sink.error("E3001", f"undeclared identifier '{name}'", target.span)
                    continue

                if sym.kind not in (SymbolKind.VARIABLE, SymbolKind.PARAMETER):
                    self._sink.error("E3005", f"'{name}' is not a variable", target.span)
                    continue

                self._info.symbols_by_node[target.node_id] = sym
                self._assigned.add(sym.symbol_id)
            else:
                self._analyze_expr(target)

    def _analyze_output(self, stmt: ast.OutputStmt) -> None:
        if not stmt.qualified and not self._uses_std:
            self._sink.error("E3001",
                             "undeclared identifier 'cout' (use 'std::cout' or add 'using namespace std;')",
                             stmt.span)

        for item in stmt.items:
            if isinstance(item, ast.EndlMarker):
                if not item.qualified and not self._uses_std:
                    self._sink.error("E3001",
                                     "undeclared identifier 'endl' (use 'std::endl' or add 'using namespace std;')",
                                     item.span)
                continue
            if isinstance(item, ast.StringLiteral):
                continue
            item_type = self._analyze_expr(item)
            if isinstance(item_type, VoidType):
                self._sink.error("E3004", "cannot print void expression", item.span)

    def _analyze_return(self, stmt: ast.ReturnStmt) -> None:
        cur_fn = self._current_function
        if cur_fn is None:
            return

        if isinstance(cur_fn.return_type, VoidType):
            if stmt.value is not None:
                self._sink.error("E3004", f"return with a value in void function '{cur_fn.name}'", stmt.span)
        else:
            if stmt.value is None:
                self._sink.error("E3004", f"void return in non-void function '{cur_fn.name}'", stmt.span)
            else:
                val_type = self._analyze_expr(stmt.value)
                if isinstance(val_type, VoidType):
                    self._sink.error("E3004", f"cannot return void expression from function '{cur_fn.name}'", stmt.span)

    def _analyze_call_expr(self, expr: ast.CallExpr, as_statement: bool = False) -> Type:
        callee = expr.callee
        if callee not in self._functions:
            self._sink.error("E3001", f"undeclared identifier '{callee}'", expr.span)
            return IntType(self._config.target.int_bits)

        fn = self._functions[callee]

        if len(expr.args) != len(fn.params):
            self._sink.error("E3006",
                             f"wrong argument count for '{callee}': expected {len(fn.params)}, got {len(expr.args)}",
                             expr.span)

        for i, arg in enumerate(expr.args):
            arg_type = self._analyze_expr(arg)
            if isinstance(arg_type, VoidType):
                self._sink.error("E3004", f"cannot pass void expression as argument to '{callee}'", arg.span)

        if not as_statement and isinstance(fn.return_type, VoidType):
            self._sink.error("E3004", f"void function '{callee}' result cannot be used as a value", expr.span)

        self._info.type_by_node[expr.node_id] = fn.return_type
        return fn.return_type

    def _analyze_expr(self, expr: ast.Expr) -> Type:
        if isinstance(expr, ast.IntLiteral):
            if expr.value <= self._config.target.int_max and expr.value >= self._config.target.int_min:
                t = IntType(self._config.target.int_bits)
            else:
                t = IntType(self._config.target.long_long_bits)
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.NullptrLiteral):
            t = NullptrType()
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.NameExpr):
            name = expr.name

            if name in ('cin', 'cout', 'endl') and not self._uses_std:
                self._sink.error("E3001",
                                 f"undeclared identifier '{name}' (use 'std::{name}' or add 'using namespace std;')",
                                 expr.span)
                t = IntType(self._config.target.int_bits)
                self._info.type_by_node[expr.node_id] = t
                return t

            sym = self._lookup_var(name)
            if sym is None:
                self._sink.error("E3001", f"undeclared identifier '{name}'", expr.span)
                t = IntType(self._config.target.int_bits)
                self._info.type_by_node[expr.node_id] = t
                return t

            self._info.symbols_by_node[expr.node_id] = sym

            if sym.kind in (SymbolKind.VARIABLE, SymbolKind.PARAMETER):
                if sym.symbol_id not in self._assigned:
                    self._sink.error("E3003",
                                     f"variable '{name}' may be used before being assigned",
                                     expr.span)

            t = sym.type or IntType(self._config.target.int_bits)
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.AddressOfExpr):
            op = expr.operand
            if isinstance(op, ast.NameExpr):
                sym = self._lookup_var(op.name)
                if sym is not None:
                    self._info.symbols_by_node[op.node_id] = sym
                    self._info.addressed_symbols.add(sym.symbol_id)
                    elem_t = sym.type.element_type if isinstance(sym.type, ArrayType) else sym.type
                    t = PointerType(elem_t or IntType(32))
                else:
                    self._sink.error("E3001", f"undeclared identifier '{op.name}'", op.span)
                    t = PointerType(IntType(32))
            elif isinstance(op, ast.IndexExpr):
                elem_t = self._analyze_expr(op)
                t = PointerType(elem_t)
            elif isinstance(op, ast.DerefExpr):
                deref_t = self._analyze_expr(op)
                t = PointerType(deref_t)
            else:
                self._sink.error("E3003", "lvalue required as unary '&' operand", expr.span)
                t = PointerType(IntType(32))
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.DerefExpr):
            op_t = self._analyze_expr(expr.operand)
            if isinstance(op_t, PointerType):
                t = op_t.pointee_type
            elif isinstance(op_t, ArrayType):
                t = op_t.element_type
            else:
                self._sink.error("E3003", f"cannot dereference non-pointer type '{op_t}'", expr.span)
                t = IntType(self._config.target.int_bits)
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.IndexExpr):
            arr_t = self._analyze_expr(expr.array)
            idx_t = self._analyze_expr(expr.index)
            if not isinstance(idx_t, IntType):
                self._sink.error("E3004", f"array index must be an integer, got '{idx_t}'", expr.index.span)

            if isinstance(arr_t, ArrayType):
                t = arr_t.element_type
            elif isinstance(arr_t, PointerType):
                t = arr_t.pointee_type
            else:
                self._sink.error("E3003", f"subscripted value is neither array nor pointer (type is '{arr_t}')", expr.span)
                t = IntType(self._config.target.int_bits)
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.UnaryExpr):
            op_t = self._analyze_expr(expr.operand)
            if isinstance(op_t, VoidType):
                self._sink.error("E3004", f"operator '{expr.op}' cannot be applied to void operand", expr.span)
            t = op_t if isinstance(op_t, IntType) else IntType(self._config.target.int_bits)
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.BinaryExpr):
            if expr.op in ('<', '<=', '>', '>=', '==', '!='):
                self._sink.error("E3008",
                                 f"relational expression '{expr.op}' used as a value",
                                 expr.span)

            left_t = self._analyze_expr(expr.left)
            right_t = self._analyze_expr(expr.right)
            if isinstance(left_t, VoidType) or isinstance(right_t, VoidType):
                self._sink.error("E3004", f"operator '{expr.op}' cannot be applied to void operands", expr.span)

            if expr.op in ('+', '-'):
                if isinstance(left_t, (PointerType, ArrayType)) and isinstance(right_t, IntType):
                    elem = left_t.pointee_type if isinstance(left_t, PointerType) else left_t.element_type
                    t = PointerType(elem)
                    self._info.type_by_node[expr.node_id] = t
                    return t
                elif expr.op == '+' and isinstance(left_t, IntType) and isinstance(right_t, (PointerType, ArrayType)):
                    elem = right_t.pointee_type if isinstance(right_t, PointerType) else right_t.element_type
                    t = PointerType(elem)
                    self._info.type_by_node[expr.node_id] = t
                    return t
                elif expr.op == '-' and isinstance(left_t, (PointerType, ArrayType)) and isinstance(right_t, (PointerType, ArrayType)):
                    t = IntType(self._config.target.int_bits)
                    self._info.type_by_node[expr.node_id] = t
                    return t

            ll_bits = self._config.target.long_long_bits
            if (isinstance(left_t, IntType) and left_t.bits == ll_bits) or (isinstance(right_t, IntType) and right_t.bits == ll_bits):
                t = IntType(ll_bits)
            else:
                t = IntType(self._config.target.int_bits)
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.CallExpr):
            return self._analyze_call_expr(expr, as_statement=False)

        t = IntType(self._config.target.int_bits)
        self._info.type_by_node[expr.node_id] = t
        return t
