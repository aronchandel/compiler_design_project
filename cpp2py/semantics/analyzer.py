"""Semantic analyzer for the cpp2py compiler (Phase 1)."""

from __future__ import annotations

from cpp2py.config import CompilerConfig
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend import ast_nodes as ast
from cpp2py.semantics.types import IntType
from cpp2py.semantics.symbols import Symbol, SymbolKind, SemanticInfo


# Names that cannot be declared as variables
RESERVED_NAMES = frozenset({'cin', 'cout', 'endl', 'std', 'main'})


def analyze(program: ast.Program, config: CompilerConfig,
            sink: DiagnosticSink) -> SemanticInfo | None:
    """Run semantic analysis on the AST. Returns SemanticInfo or None on error."""
    analyzer = _Analyzer(program, config, sink)
    return analyzer.run()


class _Analyzer:
    def __init__(self, program: ast.Program, config: CompilerConfig,
                 sink: DiagnosticSink) -> None:
        self._program = program
        self._config = config
        self._sink = sink
        self._info = SemanticInfo()
        self._scope: dict[str, Symbol] = {}  # name -> Symbol
        self._assigned: set[str] = set()  # names definitely assigned
        self._next_symbol_id = 0
        self._uses_std = program.uses_std

    def _alloc_symbol_id(self) -> int:
        sid = self._next_symbol_id
        self._next_symbol_id += 1
        return sid

    def run(self) -> SemanticInfo | None:
        for func in self._program.functions:
            self._analyze_function(func)

        if self._sink.has_errors():
            return None
        return self._info

    def _analyze_function(self, func: ast.FunctionDef) -> None:
        # Validate return statement placement
        stmts = func.body.statements
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, ast.ReturnStmt):
                if i != len(stmts) - 1:
                    self._sink.error("E4001",
                                     "unsupported construct 'return' (not supported in this version)",
                                     stmt.span)
                elif stmt.value is not None:
                    if not (isinstance(stmt.value, ast.IntLiteral) and stmt.value.value == 0):
                        self._sink.error("E4001",
                                         "unsupported construct 'return <value>' (not supported in this version)",
                                         stmt.span)

        # Analyze statements
        for stmt in stmts:
            self._analyze_stmt(stmt)

    def _analyze_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.DeclStmt):
            self._analyze_decl(stmt)
        elif isinstance(stmt, ast.AssignStmt):
            self._analyze_assign(stmt)
        elif isinstance(stmt, ast.InputStmt):
            self._analyze_input(stmt)
        elif isinstance(stmt, ast.OutputStmt):
            self._analyze_output(stmt)
        elif isinstance(stmt, ast.ReturnStmt):
            self._analyze_return(stmt)

    def _analyze_decl(self, stmt: ast.DeclStmt) -> None:
        for decl in stmt.declarators:
            name = decl.name

            # Check reserved names
            if name in RESERVED_NAMES:
                self._sink.error("E3002",
                                 f"cannot declare '{name}' as a variable",
                                 decl.span)
                continue

            # Check redeclaration
            if name in self._scope:
                self._sink.error("E3002",
                                 f"redeclaration of '{name}'",
                                 decl.span)
                continue

            # Create symbol
            sym = Symbol(self._alloc_symbol_id(), name, IntType(self._config.target.int_bits),
                         SymbolKind.VARIABLE, decl.span)
            self._scope[name] = sym
            self._info.symbols_by_node[decl.node_id] = sym

            if decl.init is not None:
                self._analyze_expr(decl.init)
                self._assigned.add(name)

    def _analyze_assign(self, stmt: ast.AssignStmt) -> None:
        name = stmt.target.name

        # Check target is a declared variable
        if name not in self._scope:
            self._sink.error("E3001", f"undeclared identifier '{name}'", stmt.target.span)
            return

        sym = self._scope[name]
        if sym.kind != SymbolKind.VARIABLE:
            self._sink.error("E3005", f"'{name}' is not a variable", stmt.target.span)
            return

        self._info.symbols_by_node[stmt.target.node_id] = sym

        # Analyze the value expression
        self._analyze_expr(stmt.value)
        self._assigned.add(name)

    def _analyze_input(self, stmt: ast.InputStmt) -> None:
        if not stmt.qualified and not self._uses_std:
            self._sink.error("E3001",
                             "undeclared identifier 'cin' (use 'std::cin' or add 'using namespace std;')",
                             stmt.span)

        for target in stmt.targets:
            name = target.name

            if name not in self._scope:
                self._sink.error("E3001", f"undeclared identifier '{name}'", target.span)
                continue

            sym = self._scope[name]
            if sym.kind != SymbolKind.VARIABLE:
                self._sink.error("E3005", f"'{name}' is not a variable", target.span)
                continue

            self._info.symbols_by_node[target.node_id] = sym
            self._assigned.add(name)

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
            self._analyze_expr(item)

    def _analyze_return(self, stmt: ast.ReturnStmt) -> None:
        if stmt.value is not None:
            self._analyze_expr(stmt.value)

    def _analyze_expr(self, expr: ast.Expr) -> None:
        if isinstance(expr, ast.IntLiteral):
            self._info.type_by_node[expr.node_id] = IntType(self._config.target.int_bits)

        elif isinstance(expr, ast.NameExpr):
            name = expr.name

            # Check for I/O identifiers used without std:: or using
            if name in ('cin', 'cout', 'endl') and not self._uses_std:
                if name not in self._scope:
                    self._sink.error("E3001",
                                     f"undeclared identifier '{name}' (use 'std::{name}' or add 'using namespace std;')",
                                     expr.span)
                    return

            if name not in self._scope:
                self._sink.error("E3001", f"undeclared identifier '{name}'", expr.span)
                return

            sym = self._scope[name]
            self._info.symbols_by_node[expr.node_id] = sym

            # Check definite assignment
            if sym.kind == SymbolKind.VARIABLE and name not in self._assigned:
                self._sink.error("E3003",
                                 f"variable '{name}' may be used before being assigned",
                                 expr.span)

            self._info.type_by_node[expr.node_id] = IntType(self._config.target.int_bits)

        elif isinstance(expr, ast.UnaryExpr):
            self._analyze_expr(expr.operand)
            self._info.type_by_node[expr.node_id] = IntType(self._config.target.int_bits)

        elif isinstance(expr, ast.BinaryExpr):
            self._analyze_expr(expr.left)
            self._analyze_expr(expr.right)
            self._info.type_by_node[expr.node_id] = IntType(self._config.target.int_bits)
