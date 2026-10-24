"""Compiler orchestration: ties together all stages."""

from __future__ import annotations

from dataclasses import dataclass

from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink, Diagnostic
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.frontend.ast_nodes import Program, reset_node_ids
from cpp2py.semantics.analyzer import analyze
from cpp2py.codegen.ast_to_python import generate


@dataclass
class CompilationResult:
    """Result of a compilation run."""
    success: bool
    python_source: str | None
    diagnostics: tuple[Diagnostic, ...]
    ast: Program | None


def compile_source(text: str, filename: str,
                   config: CompilerConfig | None = None) -> CompilationResult:
    """Compile C++ source text to Python.

    Returns a CompilationResult with the generated Python (or None on error).
    """
    if config is None:
        config = CompilerConfig()

    reset_node_ids()
    source = SourceFile(filename, text)
    sink = DiagnosticSink()

    # Stage 1: Lex
    tokens = tokenize(source, sink)
    if sink.has_errors():
        return CompilationResult(False, None, sink.all(), None)

    # Stage 2: Parse
    program = parse(tokens, sink)
    if program is None or sink.has_errors():
        return CompilationResult(False, None, sink.all(), program)

    # Stage 3: Semantic analysis
    info = analyze(program, config, sink)
    if info is None or sink.has_errors():
        return CompilationResult(False, None, sink.all(), program)

    # Stage 4: Code generation (AST -> Python, bootstrap path)
    python_source = generate(program, info, sink)
    if python_source is None or sink.has_errors():
        return CompilationResult(False, None, sink.all(), program)

    return CompilationResult(True, python_source, sink.all(), program)
