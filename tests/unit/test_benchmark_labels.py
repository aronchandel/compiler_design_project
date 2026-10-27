from __future__ import annotations

import json
from pathlib import Path
import pytest

from cpp2py.source import SourceFile
from cpp2py.diagnostics import DiagnosticSink
from cpp2py.frontend.lexer import tokenize
from cpp2py.frontend.tokens import TokenKind

def _get_benchmarks_dir() -> Path:
    curr = Path(__file__).resolve().parent
    while curr != curr.parent:
        if (curr / "pyproject.toml").exists():
            return curr / "benchmarks"
        curr = curr.parent
    return Path("benchmarks")

def test_benchmark_program_count() -> None:
    bdir = _get_benchmarks_dir()
    progs_dir = bdir / "programs"
    assert progs_dir.exists(), f"Directory not found: {progs_dir}"
    progs = list(progs_dir.glob("*.cpp"))
    assert len(progs) >= 20, f"Expected >= 20 programs, found {len(progs)}"

def test_label_file_exists_and_is_valid_json() -> None:
    bdir = _get_benchmarks_dir()
    labels_file = bdir / "labels.json"
    assert labels_file.exists(), f"File not found: {labels_file}"
    data = json.loads(labels_file.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0

def test_label_validation_every_op_has_exactly_one_label() -> None:
    bdir = _get_benchmarks_dir()
    progs_dir = bdir / "programs"
    labels_file = bdir / "labels.json"

    labels = json.loads(labels_file.read_text(encoding="utf-8"))

    label_map: dict[tuple[str, int, int], dict] = {}
    label_keys_seen: set[tuple[str, int, int]] = set()

    for idx, lbl in enumerate(labels):
        key = (lbl["file"], lbl["line"], lbl["col"])
        assert key not in label_keys_seen, f"Duplicate label entry in labels.json: {key}"
        label_keys_seen.add(key)
        label_map[key] = lbl

        assert lbl["label"] in ("needs_helper", "native_ok"), f"Invalid label {lbl['label']!r} at {key}"
        assert lbl["op"] in ("/", "%"), f"Invalid op {lbl['op']!r} at {key}"
        assert isinstance(lbl["reason"], str) and len(lbl["reason"].strip()) > 0, f"Empty reason at {key}"
        assert isinstance(lbl["assumed_ranges"], dict), f"assumed_ranges must be a dict at {key}"

    found_ops: set[tuple[str, int, int]] = set()

    for cpp_path in sorted(progs_dir.glob("*.cpp")):
        filename = cpp_path.name
        src = cpp_path.read_text(encoding="utf-8")
        sf = SourceFile(filename, src)
        sink = DiagnosticSink()
        tokens = tokenize(sf, sink)
        assert not sink.has_errors(), f"Lexer error in {filename}: {[d.message for d in sink.all()]}"

        for tok in tokens:
            if tok.kind in (TokenKind.SLASH, TokenKind.PERCENT):
                key = (filename, tok.span.start.line, tok.span.start.col)
                assert key not in found_ops, f"Duplicate operator token at {key}"
                found_ops.add(key)
                assert key in label_map, f"Orphan operator without label in labels.json: {key} (op: {tok.text})"

    orphan_labels = label_keys_seen - found_ops
    assert not orphan_labels, f"Orphan labels in labels.json not found in any .cpp file: {orphan_labels}"

    assert len(found_ops) == len(labels), f"Found {len(found_ops)} ops but {len(labels)} labels"
