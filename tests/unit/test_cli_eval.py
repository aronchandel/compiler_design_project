"""Unit tests for CLI evaluation integration, lazy import, and fault isolation (AC8.10)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import pytest


def test_cli_import_does_not_import_evaluation() -> None:
    """AC8.10: Verify that importing cpp2py.cli does not import cpp2py.evaluation."""
    # Run in a fresh subprocess to guarantee clean sys.modules
    cmd = [
        sys.executable,
        "-c",
        "import sys; import cpp2py.cli; assert 'cpp2py.evaluation' not in sys.modules, f'Leaked modules: {[m for m in sys.modules if \"evaluation\" in m]}'; print('OK')",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Import test failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    assert "OK" in res.stdout


def test_translate_does_not_activate_faults(tmp_path: Path) -> None:
    """AC8.10: Verify that running translate does not activate any evaluation fault patches."""
    cmd = [
        sys.executable,
        "-c",
        """import sys
from cpp2py.cli import main
import cpp2py.transforms.constant_fold as fold_mod

# Record original function pointer
orig_run = fold_mod.ConstantFoldPass.run

# Run a translation command
code = main(["translate", "examples/phase1/empty_main.cpp"])
assert code == 0

# Check that production function was NOT patched
assert fold_mod.ConstantFoldPass.run == orig_run
assert 'cpp2py.evaluation' not in sys.modules
print('OK')
""",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Isolation test failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    assert "OK" in res.stdout


def test_difftest_does_not_activate_faults() -> None:
    """AC8.10: Verify that running difftest CLI does not import cpp2py.evaluation."""
    cmd = [
        sys.executable,
        "-c",
        """import sys
from cpp2py.cli import main

# Run difftest help
try:
    main(["difftest", "--help"])
except SystemExit:
    pass

assert 'cpp2py.evaluation' not in sys.modules
print('OK')
""",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Difftest isolation test failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    assert "OK" in res.stdout


def test_eval_cli_help() -> None:
    """Verify that eval --help displays usage and options without crashing."""
    cmd = [sys.executable, "-m", "cpp2py", "eval", "--help"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "--suite" in res.stdout
    assert "--out" in res.stdout
    assert "localisation" in res.stdout
