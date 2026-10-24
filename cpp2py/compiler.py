"""Compiler orchestration: ties together all stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink, Diagnostic
from cpp2py.config import CompilerConfig
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.parser import parse
from cpp2py.frontend.ast_nodes import Program, reset_node_ids
from cpp2py.semantics.analyzer import analyze
from cpp2py.ir.model import IRModule
from cpp2py.ir.builder import build_ir
from cpp2py.ir.verifier import verify_module
from cpp2py.ir.snapshots import SnapshotStore
from cpp2py.codegen import ast_to_python
from cpp2py.codegen import python_gen


@dataclass
class CompilationResult:
    """Result of a compilation run."""
    success: bool
    python_source: str | None
    diagnostics: tuple[Diagnostic, ...]
    ast: Program | None
    ir: IRModule | None = None
    artifact_dir: Path | None = None


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

    # Backend selection:
    if config.backend == "direct":
        # Phase 1 bootstrap generator: direct AST -> Python
        python_source = ast_to_python.generate(program, info, sink)
        if python_source is None or sink.has_errors():
            return CompilationResult(False, None, sink.all(), program, ir=None)
        return CompilationResult(True, python_source, sink.all(), program, ir=None)

    # Phase 2 default pipeline: AST -> IR -> verify -> Python
    module = build_ir(program, info, config)

    # Verify IR
    verify_module(module, sink)
    if sink.has_errors():
        return CompilationResult(False, None, sink.all(), program, ir=module)

    # Generate Python from IR
    python_source = python_gen.generate(module, sink, config)
    if python_source is None or sink.has_errors():
        return CompilationResult(False, None, sink.all(), program, ir=module)

    # Save snapshots if requested
    if config.snapshot_dir is not None:
        store = SnapshotStore(config.snapshot_dir)
        store.save_phase2_snapshots(text, module, module, python_source, config, sink.all())

    return CompilationResult(
        True,
        python_source,
        sink.all(),
        program,
        ir=module,
        artifact_dir=Path(config.snapshot_dir) if config.snapshot_dir else None,
    )
