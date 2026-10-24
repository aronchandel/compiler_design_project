"""CLI entry point for the cpp2py compiler."""

from __future__ import annotations

import argparse
import os
import sys

import cpp2py
from cpp2py.source import SourceFile
from cpp2py.diagnostics import Severity, render
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.analysis.intervals import Interval
from cpp2py.compiler import compile_source
from cpp2py.frontend.ast_printer import dump
from cpp2py.ir.printer import format_module


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point. Returns exit status."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog='cpp2py', description='C++ to Python translator')
    parser.add_argument('--version', action='version', version=f'cpp2py {cpp2py.__version__}')

    subparsers = parser.add_subparsers(dest='command')

    # translate subcommand
    translate_parser = subparsers.add_parser('translate', help='Translate C++ to Python')
    translate_parser.add_argument('input', help='Input C++ file')
    translate_parser.add_argument('-o', '--output', help='Output Python file')
    translate_parser.add_argument('--dump-ast', action='store_true', help='Dump AST instead of generating Python')
    translate_parser.add_argument('--dump-ir', action='store_true', help='Dump IR instead of generating Python')
    translate_parser.add_argument('--snapshots', metavar='DIR', help='Directory to save compilation snapshots')
    translate_parser.add_argument('--no-fold', action='store_false', dest='fold_constants', default=True, help='Disable constant folding and transform passes')
    translate_parser.add_argument('--transform-log', metavar='FILE', dest='transform_log', default=None, help='File to write transformation log (JSON Lines)')
    translate_parser.add_argument('--idiomatic-loops', action='store_true', dest='idiomatic_loops', default=False, help='Emit idiomatic Python for loops when qualifying')
    translate_parser.add_argument('--compat', choices=['naive', 'always', 'range_guided'], default='range_guided', help='Compatibility helper mode (default: range_guided)')
    translate_parser.add_argument('--overflow', choices=['assume_no_overflow', 'wrap', 'trap'], default='assume_no_overflow', help='Signed integer overflow policy (default: assume_no_overflow)')
    translate_parser.add_argument('--assume-range', action='append', dest='assume_ranges', default=[], metavar='FUNC.VAR=LO:HI', help='Assume range for variable in function')
    translate_parser.add_argument('--ranges-out', metavar='FILE', dest='ranges_out', default=None, help='File to write ranges JSON')
    translate_parser.add_argument('--compat-plan', metavar='FILE', dest='compat_plan', default=None, help='File to write compatibility plan JSON')

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == 'translate':
        return _cmd_translate(args)

    return 1


def _cmd_translate(args: argparse.Namespace) -> int:
    """Handle the translate subcommand."""
    input_path = args.input

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        print(f"error: file not found: {input_path}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: cannot read {input_path}: {e}", file=sys.stderr)
        return 1

    assumed_ranges: dict[str, Interval] = {}
    for entry in (args.assume_ranges or []):
        try:
            var_part, range_part = entry.split('=', 1)
            lo_str, hi_str = range_part.split(':', 1)
            lo = int(lo_str) if lo_str else None
            hi = int(hi_str) if hi_str else None
            assumed_ranges[var_part.strip()] = Interval(lo, hi)
        except ValueError:
            print(f"error: invalid --assume-range format '{entry}', expected FUNC.VAR=LO:HI", file=sys.stderr)
            return 1

    source = SourceFile(input_path, text)
    target = TargetModel(overflow_policy=OverflowPolicy(args.overflow))
    config = CompilerConfig(
        target=target,
        compat_mode=CompatMode(args.compat),
        assumed_ranges=assumed_ranges,
        snapshot_dir=args.snapshots,
        fold_constants=args.fold_constants,
        idiomatic_loops=args.idiomatic_loops,
        transform_log_path=args.transform_log,
        ranges_out=args.ranges_out,
        compat_plan_out=args.compat_plan,
    )

    if args.dump_ast:
        return _do_dump_ast(text, source, config)

    if args.dump_ir:
        return _do_dump_ir(text, source, config)

    return _do_translate(text, source, config, args.output)


def _do_dump_ast(text: str, source: SourceFile, config: CompilerConfig) -> int:
    """Dump the AST and exit."""
    from cpp2py.diagnostics import DiagnosticSink
    from cpp2py.frontend.lexer import tokenize
    from cpp2py.frontend.parser import parse
    from cpp2py.frontend.ast_nodes import reset_node_ids

    reset_node_ids()
    sink = DiagnosticSink()
    tokens = tokenize(source, sink, config.target)

    if sink.has_errors():
        _print_diagnostics(sink.all(), source)
        return 2

    program = parse(tokens, sink)

    if sink.has_errors() or program is None:
        _print_diagnostics(sink.all(), source)
        return 2

    print(dump(program))
    return 0


def _do_dump_ir(text: str, source: SourceFile, config: CompilerConfig) -> int:
    """Dump the IR and exit."""
    from cpp2py.diagnostics import DiagnosticSink
    from cpp2py.frontend.lexer import tokenize
    from cpp2py.frontend.parser import parse
    from cpp2py.frontend.ast_nodes import reset_node_ids
    from cpp2py.semantics.analyzer import analyze
    from cpp2py.ir.builder import build_ir
    from cpp2py.ir.verifier import verify_module

    reset_node_ids()
    sink = DiagnosticSink()
    tokens = tokenize(source, sink, config.target)

    if sink.has_errors():
        _print_diagnostics(sink.all(), source)
        return 2

    program = parse(tokens, sink)
    if sink.has_errors() or program is None:
        _print_diagnostics(sink.all(), source)
        return 2

    info = analyze(program, config, sink)
    if sink.has_errors() or info is None:
        _print_diagnostics(sink.all(), source)
        return 2

    module = build_ir(program, info, config)
    verify_module(module, sink)
    if sink.has_errors():
        _print_diagnostics(sink.all(), source)
        return 2

    if config.fold_constants:
        from cpp2py.transforms.constant_fold import ConstantFoldPass
        from cpp2py.transforms.dead_temps import DeadTempsPass
        from cpp2py.transforms.manager import run_pipeline

        passes = [ConstantFoldPass(), DeadTempsPass()]
        run_pipeline(module, passes, config, sink)
        if sink.has_errors():
            _print_diagnostics(sink.all(), source)
            return 2

    sys.stdout.write(format_module(module))
    return 0


def _do_translate(text: str, source: SourceFile, config: CompilerConfig,
                  output_path: str | None) -> int:
    """Translate and output."""
    result = compile_source(text, source.name, config)

    # Print diagnostics to stderr
    _print_diagnostics(result.diagnostics, source)

    if not result.success:
        # Do NOT write output file
        return 2

    if result.python_source is None:
        return 3

    if output_path:
        # Create output directory if needed
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result.python_source)
        except OSError as e:
            print(f"error: cannot write {output_path}: {e}", file=sys.stderr)
            return 1
    else:
        sys.stdout.write(result.python_source)

    return 0


def _print_diagnostics(diagnostics: tuple, source: SourceFile) -> None:
    """Print all diagnostics to stderr."""
    for diag in diagnostics:
        print(render(diag, source), file=sys.stderr)
