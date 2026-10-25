"""Enforce the layering rules of ARCHITECTURE.md §C.1.

Base -> frontend -> semantics -> ir -> transforms -> analysis -> compat -> codegen -> compiler -> cli
A module may import only from layers to its left/above in this chain.
"""

import ast
from pathlib import Path
import pytest


def get_imports(py_file: Path) -> set[str]:
    """Parse a Python source file and return all imported module paths."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
    return imported


def test_layering_rules():
    repo_root = Path(__file__).resolve().parent.parent.parent
    pkg_dir = repo_root / "cpp2py"
    assert pkg_dir.exists()

    # Rule 1: frontend must never import semantics, ir, codegen, compiler, cli
    frontend_files = list((pkg_dir / "frontend").glob("*.py"))
    for f in frontend_files:
        imports = get_imports(f)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.semantics", "cpp2py.ir", "cpp2py.codegen", "cpp2py.compiler", "cpp2py.cli"
            ]), f"Layering violation in {f.name}: imports {imp}"

    # Rule 2: semantics must never import ir, codegen, compiler, cli
    semantics_files = list((pkg_dir / "semantics").glob("*.py"))
    for f in semantics_files:
        imports = get_imports(f)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.ir", "cpp2py.codegen", "cpp2py.compiler", "cpp2py.cli"
            ]), f"Layering violation in {f.name}: imports {imp}"

    # Rule 3: ir.model must NOT import frontend or semantics
    ir_model_file = pkg_dir / "ir" / "model.py"
    if ir_model_file.exists():
        imports = get_imports(ir_model_file)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.frontend", "cpp2py.semantics", "cpp2py.codegen", "cpp2py.compiler"
            ]), f"Layering violation in ir/model.py: imports {imp}"

    # Rule 4: codegen must never import compiler, cli
    codegen_files = list((pkg_dir / "codegen").glob("*.py"))
    for f in codegen_files:
        imports = get_imports(f)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.compiler", "cpp2py.cli"
            ]), f"Layering violation in {f.name}: imports {imp}"

    # Rule 5: transforms must never import codegen, compiler, cli
    transforms_files = list((pkg_dir / "transforms").glob("*.py"))
    for f in transforms_files:
        imports = get_imports(f)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.codegen", "cpp2py.compiler", "cpp2py.cli"
            ]), f"Layering violation in {f.name}: imports {imp}"

    # Rule 6: analysis must never import codegen, compiler, cli
    analysis_files = list((pkg_dir / "analysis").glob("*.py"))
    for f in analysis_files:
        imports = get_imports(f)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.codegen", "cpp2py.compiler", "cpp2py.cli"
            ]), f"Layering violation in {f.name}: imports {imp}"

    # Rule 7: compat must never import compiler, cli
    compat_files = list((pkg_dir / "compat").glob("*.py"))
    for f in compat_files:
        imports = get_imports(f)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.compiler", "cpp2py.cli"
            ]), f"Layering violation in {f.name}: imports {imp}"

    # Rule 8: No forbidden later-phase directories
    forbidden_dirs = ["evaluation"]
    for d in forbidden_dirs:
        assert not (pkg_dir / d).exists(), f"Forbidden later-phase directory exists: cpp2py/{d}"

    # Rule 9: testing imports only public compiler API and base
    testing_files = list((pkg_dir / "testing").rglob("*.py"))
    for f in testing_files:
        imports = get_imports(f)
        for imp in imports:
            assert not any(imp.startswith(prefix) for prefix in [
                "cpp2py.frontend", "cpp2py.semantics", "cpp2py.ir",
                "cpp2py.transforms", "cpp2py.analysis", "cpp2py.compat",
                "cpp2py.codegen", "cpp2py.cli"
            ]), f"Layering violation in testing file {f.name}: imports {imp}"
