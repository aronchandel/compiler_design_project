"""Semantic analyzer for the cpp2py compiler (Phase 3)."""

from __future__ import annotations

from cpp2py.config import CompilerConfig
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend import ast_nodes as ast
from cpp2py.semantics.types import IntType, VoidType, BoolType
from cpp2py.semantics.symbols import Symbol, SymbolKind, FunctionSymbol, SemanticInfo


# Names that cannot be declared as variables
RESERVED_NAMES = frozenset({'cin', 'cout', 'endl', 'std', 'main'})


def analyze(program: ast.Program | None, config: CompilerConfig,
            sink: DiagnosticSink) -> SemanticInfo | None:
    """Run semantic analysis on the AST. Returns SemanticInfo or None on error."""
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
        self._assigned: set[int] = set()  # set of symbol_ids definitely assigned
        self._next_symbol_id = 0
        self._uses_std = program.uses_std

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
        return None

    def run(self) -> SemanticInfo | None:
        for func in self._program.functions:
            self._analyze_function(func)

        if self._sink.has_errors():
            return None
        return self._info

    def _analyze_function(self, func: ast.FunctionDef) -> None:
        # Check duplicate function name
        if func.name in self._functions:
            self._sink.error("E3002", f"duplicate function name '{func.name}'", func.span)
            return

        # Determine return type
        int_bits = self._config.target.int_bits
        ll_bits = self._config.target.long_long_bits
        ret_type: IntType | VoidType
        if func.return_type.name == "int":
            ret_type = IntType(int_bits)
        elif func.return_type.name == "long long":
            ret_type = IntType(ll_bits)
        else:
            ret_type = VoidType()

        # Check parameter names uniqueness and register params
        param_symbols: list[Symbol] = []
        seen_param_names: set[str] = set()
        for p in func.params:
            if p.name in seen_param_names or p.name in RESERVED_NAMES:
                self._sink.error("E3002", f"duplicate parameter name '{p.name}'", p.span)
                continue
            seen_param_names.add(p.name)
            p_bits = ll_bits if p.type_spec.name == "long long" else int_bits
            sym = Symbol(self._alloc_symbol_id(), p.name, IntType(p_bits),
                         SymbolKind.PARAMETER, p.span)
            param_symbols.append(sym)
            self._info.symbols_by_node[p.node_id] = sym

        func_sym = FunctionSymbol(func.name, ret_type, tuple(param_symbols), func.span)
        self._functions[func.name] = func_sym
        self._info.functions[func.name] = func_sym
        self._current_function = func_sym

        # Setup scope for function body
        self._scopes = [{}]
        for p_sym in param_symbols:
            self._scopes[0][p_sym.name] = p_sym

        # Function parameters are definitely assigned from start
        self._assigned = {p_sym.symbol_id for p_sym in param_symbols}

        # Analyze body
        self._analyze_block(func.body, push_scope=False)

        # Check missing return on non-void functions (main is exempt)
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

    def _analyze_decl(self, stmt: ast.DeclStmt) -> None:
        int_bits = self._config.target.int_bits
        ll_bits = self._config.target.long_long_bits
        var_bits = ll_bits if stmt.type_spec.name == "long long" else int_bits
        for decl in stmt.declarators:
            name = decl.name

            # Check reserved names
            if name in RESERVED_NAMES:
                self._sink.error("E3002", f"cannot declare '{name}' as a variable", decl.span)
                continue

            # Check redeclaration in current scope
            current_scope = self._scopes[-1]
            if name in current_scope:
                self._sink.error("E3002", f"redeclaration of '{name}'", decl.span)
                continue

            sym = Symbol(self._alloc_symbol_id(), name, IntType(var_bits),
                         SymbolKind.VARIABLE, decl.span)
            current_scope[name] = sym
            self._info.symbols_by_node[decl.node_id] = sym

            if decl.init is not None:
                init_type = self._analyze_expr(decl.init)
                if isinstance(init_type, VoidType):
                    self._sink.error("E3004", f"cannot initialize variable '{name}' with void expression", decl.span)
                self._assigned.add(sym.symbol_id)

    def _analyze_assign(self, stmt: ast.AssignStmt) -> None:
        name = stmt.target.name
        sym = self._lookup_var(name)

        if sym is None:
            self._sink.error("E3001", f"undeclared identifier '{name}'", stmt.target.span)
            return

        if sym.kind not in (SymbolKind.VARIABLE, SymbolKind.PARAMETER):
            self._sink.error("E3005", f"'{name}' is not an assignable variable", stmt.target.span)
            return

        self._info.symbols_by_node[stmt.target.node_id] = sym

        # For compound assignment (+=, -=, etc.), target must ALREADY be assigned
        if stmt.op != '=':
            if sym.symbol_id not in self._assigned:
                self._sink.error("E3003", f"variable '{name}' may be used before being assigned", stmt.target.span)

        val_type = self._analyze_expr(stmt.value)
        if isinstance(val_type, VoidType):
            self._sink.error("E3004", f"cannot assign void expression to '{name}'", stmt.span)

        self._assigned.add(sym.symbol_id)

    def _analyze_incdec(self, stmt: ast.IncDecStmt) -> None:
        name = stmt.target.name
        sym = self._lookup_var(name)

        if sym is None:
            self._sink.error("E3001", f"undeclared identifier '{name}'", stmt.target.span)
            return

        if sym.kind not in (SymbolKind.VARIABLE, SymbolKind.PARAMETER):
            self._sink.error("E3005", f"'{name}' is not an assignable variable", stmt.target.span)
            return

        self._info.symbols_by_node[stmt.target.node_id] = sym

        if sym.symbol_id not in self._assigned:
            self._sink.error("E3003", f"variable '{name}' may be used before being assigned", stmt.target.span)

        self._assigned.add(sym.symbol_id)

    def _analyze_if(self, stmt: ast.IfStmt) -> None:
        self._analyze_condition(stmt.cond)

        # Definite assignment over branches
        saved_assigned = set(self._assigned)

        self._analyze_stmt(stmt.then_body)
        then_assigned = set(self._assigned)

        if stmt.else_body is not None:
            self._assigned = set(saved_assigned)
            self._analyze_stmt(stmt.else_body)
            else_assigned = set(self._assigned)

            # Intersection: definitely assigned only if assigned on BOTH branches
            self._assigned = then_assigned & else_assigned
        else:
            # If no else branch, then assignments in then_body cannot be assumed
            self._assigned = saved_assigned

    def _analyze_while(self, stmt: ast.WhileStmt) -> None:
        self._analyze_condition(stmt.cond)

        saved_assigned = set(self._assigned)
        self._analyze_stmt(stmt.body)

        # Assignments inside while loop body do not count after the loop
        self._assigned = saved_assigned

    def _analyze_for(self, stmt: ast.ForStmt) -> None:
        # for_init counts for definite assignment and scoping
        self._enter_scope()

        if stmt.init is not None:
            self._analyze_stmt(stmt.init)

        self._analyze_condition(stmt.cond)

        # Body and update run conditionally
        saved_assigned = set(self._assigned)

        self._analyze_stmt(stmt.body)
        if stmt.update is not None:
            self._analyze_stmt(stmt.update)

        # Assignments in body/update do NOT count after loop, but init DOES
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

    def _analyze_call_expr(self, expr: ast.CallExpr, as_statement: bool = False) -> IntType | VoidType:
        callee = expr.callee
        if callee not in self._functions:
            self._sink.error("E3001", f"undeclared identifier '{callee}'", expr.span)
            return IntType(self._config.target.int_bits)

        fn = self._functions[callee]

        # Check argument count
        if len(expr.args) != len(fn.params):
            self._sink.error("E3006",
                             f"wrong argument count for '{callee}': expected {len(fn.params)}, got {len(expr.args)}",
                             expr.span)

        for arg in expr.args:
            arg_type = self._analyze_expr(arg)
            if isinstance(arg_type, VoidType):
                self._sink.error("E3004", f"cannot pass void expression as argument to '{callee}'", arg.span)

        if not as_statement and isinstance(fn.return_type, VoidType):
            self._sink.error("E3004", f"void function '{callee}' result cannot be used as a value", expr.span)

        self._info.type_by_node[expr.node_id] = fn.return_type
        return fn.return_type

    def _analyze_expr(self, expr: ast.Expr) -> IntType | VoidType | BoolType:
        if isinstance(expr, ast.IntLiteral):
            if expr.value <= self._config.target.int_max:
                t = IntType(self._config.target.int_bits)
            else:
                t = IntType(self._config.target.long_long_bits)
            self._info.type_by_node[expr.node_id] = t
            return t

        elif isinstance(expr, ast.NameExpr):
            name = expr.name

            # Check for I/O identifiers used without std:: or using
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

            # Check definite assignment
            if sym.kind in (SymbolKind.VARIABLE, SymbolKind.PARAMETER):
                if sym.symbol_id not in self._assigned:
                    self._sink.error("E3003",
                                     f"variable '{name}' may be used before being assigned",
                                     expr.span)

            t = sym.type or IntType(self._config.target.int_bits)
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
            # Check relational operator used as value -> E3008
            if expr.op in ('<', '<=', '>', '>=', '==', '!='):
                self._sink.error("E3008",
                                 f"relational expression '{expr.op}' used as a value",
                                 expr.span)

            left_t = self._analyze_expr(expr.left)
            right_t = self._analyze_expr(expr.right)
            if isinstance(left_t, VoidType) or isinstance(right_t, VoidType):
                self._sink.error("E3004", f"operator '{expr.op}' cannot be applied to void operands", expr.span)

            # Usual arithmetic promotions: if either is long long, result is long long
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
