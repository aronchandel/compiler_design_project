"""Unit tests for the Python execution runner."""

import pytest

from cpp2py.testing.py_runner import run_python


def test_run_python_simple():
    code = "print(42)"
    res = run_python(code)
    assert res.exit_code == 0
    assert res.stdout.strip() == "42"
    assert not res.timed_out
    assert not res.output_capped


def test_run_python_stdin():
    code = """
import sys
tokens = sys.stdin.read().split()
a = int(tokens[0])
b = int(tokens[1])
print(a + b)
"""
    res = run_python(code, stdin_text="15 27\n")
    assert res.exit_code == 0
    assert res.stdout.strip() == "42"


def test_run_python_exit_code():
    code = "import sys; sys.exit(7)"
    res = run_python(code)
    assert res.exit_code == 7


def test_run_python_output_cap():
    code = "print('X' * 5000)"
    res = run_python(code, output_cap=100)
    assert res.output_capped is True
    assert len(res.stdout) <= 100


def test_run_python_timeout():
    code = "import time; time.sleep(5)"
    res = run_python(code, timeout=0.5)
    assert res.timed_out is True
    assert res.exit_code == -1


def test_run_python_utf8():
    code = "print('café résumé — « »')"
    res = run_python(code)
    assert res.exit_code == 0
    assert "café résumé — « »" in res.stdout
