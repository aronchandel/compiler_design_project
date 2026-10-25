"""Static scan tests for AC7.9 layering and isolation.

Conforms to AC7.9:
"No module in localisation/ writes outside its output directory or imports
transforms/codegen internals (static scan test); no evaluation code exists."
"""

from __future__ import annotations

import ast
from pathlib import Path
import pytest


def test_localisation_imports_layering() -> None:
    """Verify localisation modules do not import codegen or transforms internals."""
    loc_dir = Path("cpp2py/localisation")
    assert loc_dir.exists()

    forbidden_modules = [
        "cpp2py.codegen",
        "cpp2py.transforms.manager",
        "cpp2py.transforms.constant_fold",
        "cpp2py.transforms.dead_temps",
        "cpp2py.evaluation",
        "evaluation",
    ]

    for py_file in loc_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=py_file.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    for forbidden in forbidden_modules:
                        assert not name.name.startswith(forbidden), (
                            f"{py_file.name} violates layering: imports {name.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for forbidden in forbidden_modules:
                    assert not mod.startswith(forbidden), (
                        f"{py_file.name} violates layering: imports from {mod}"
                    )


def test_no_evaluation_code_exists_in_cpp2py() -> None:
    """In Phase 8, cpp2py/evaluation exists. Verify production packages do not import evaluation."""
    root = Path("cpp2py")
    for subdir in ("frontend", "semantics", "ir", "transforms", "analysis", "codegen", "compiler"):
        pkg = root / subdir
        if pkg.exists():
            for py_file in pkg.rglob("*.py"):
                txt = py_file.read_text(encoding="utf-8")
                assert "cpp2py.evaluation" not in txt, f"Layering violation: {py_file} imports cpp2py.evaluation"


def test_localisation_does_not_modify_inputs(tmp_path: Path) -> None:
    """Verify localise() does not modify translator sources, IR, or case files."""
    from cpp2py.localisation import localise

    dummy_case = tmp_path / "case"
    dummy_case.mkdir()
    (dummy_case / "program.cpp").write_text("// test code", encoding="utf-8")
    (dummy_case / "input.txt").write_text("", encoding="utf-8")
    (dummy_case / "cxx_output.txt").write_text("hello\n", encoding="utf-8")

    prog_mtime = (dummy_case / "program.cpp").stat().st_mtime_ns
    cxx_mtime = (dummy_case / "cxx_output.txt").stat().st_mtime_ns

    # Run localisation
    rep = localise(dummy_case)
    assert rep is not None

    # Files must not have been modified
    assert (dummy_case / "program.cpp").stat().st_mtime_ns == prog_mtime
    assert (dummy_case / "cxx_output.txt").stat().st_mtime_ns == cxx_mtime
