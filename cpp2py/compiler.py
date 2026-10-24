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
from cpp2py.transforms.constant_fold import ConstantFoldPass
from cpp2py.transforms.dead_temps import DeadTempsPass
from cpp2py.transforms.manager import run_pipeline
from cpp2py.transforms.log import TransformLog
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
    transform_log: TransformLog | None = None


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

    # IR pipeline: AST -> IR -> verify -> Transform Pipeline -> Python
    module = build_ir(program, info, config)

    # Initial verify IR
    verify_module(module, sink)
    if sink.has_errors():
        return CompilationResult(False, None, sink.all(), program, ir=module)

    # Initialize snapshot store if requested
    store: SnapshotStore | None = None
    if config.snapshot_dir is not None:
        store = SnapshotStore(config.snapshot_dir)
        store.save_initial_ir(module)

    # Run transformation pipeline if folding enabled
    transform_log: TransformLog | None = None
    if config.fold_constants:
        passes = [ConstantFoldPass(), DeadTempsPass()]
        transform_log = run_pipeline(
            module=module,
            passes=passes,
            config=config,
            sink=sink,
            snapshot_store=store,
        )
        if sink.has_errors():
            return CompilationResult(False, None, sink.all(), program, ir=module, transform_log=transform_log)

    # If transform log path specified, write log
    if config.transform_log_path is not None:
        if transform_log is None:
            transform_log = TransformLog()
        transform_log.write_jsonl(config.transform_log_path)

    # Save final IR snapshot if requested
    if store is not None:
        store.save_final_ir(module)

    # Generate Python from IR
    python_source = python_gen.generate(module, sink, config)
    if python_source is None or sink.has_errors():
        return CompilationResult(False, None, sink.all(), program, ir=module, transform_log=transform_log)

    # Save output and manifest if requested
    if store is not None:
        store.save_output_and_manifest(text, python_source, config, sink.all())

    return CompilationResult(
        True,
        python_source,
        sink.all(),
        program,
        ir=module,
        artifact_dir=Path(config.snapshot_dir) if config.snapshot_dir else None,
        transform_log=transform_log,
    )
