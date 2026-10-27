from __future__ import annotations

import pytest
from cpp2py.compat.helpers import (
    _cpp_div_instrumented,
    _cpp_mod_instrumented,
    get_instrumentation_counts,
    get_instrumentation_prelude,
    helper_source,
    reset_instrumentation,
)
from cpp2py.testing.py_runner import run_python

def test_div_instrumentation_counts() -> None:
    reset_instrumentation()

    res1 = _cpp_div_instrumented(7, 2)
    assert res1 == 3
    counts = get_instrumentation_counts()
    assert counts["total"] == 1
    assert counts["div_total"] == 1
    assert counts["equals"] == 1
    assert counts["differs"] == 0

    res2 = _cpp_div_instrumented(-7, 2)
    assert res2 == -3
    counts = get_instrumentation_counts()
    assert counts["total"] == 2
    assert counts["div_total"] == 2
    assert counts["equals"] == 1
    assert counts["differs"] == 1
    assert counts["div_differs"] == 1

def test_mod_instrumentation_counts() -> None:
    reset_instrumentation()

    res1 = _cpp_mod_instrumented(7, 2)
    assert res1 == 1
    counts = get_instrumentation_counts()
    assert counts["total"] == 1
    assert counts["mod_total"] == 1
    assert counts["equals"] == 1
    assert counts["differs"] == 0

    res2 = _cpp_mod_instrumented(-7, 2)
    assert res2 == -1
    counts = get_instrumentation_counts()
    assert counts["total"] == 2
    assert counts["mod_total"] == 2
    assert counts["equals"] == 1
    assert counts["differs"] == 1
    assert counts["mod_differs"] == 1

def test_reset_instrumentation() -> None:
    reset_instrumentation()
    _cpp_div_instrumented(10, 3)
    assert get_instrumentation_counts()["total"] == 1
    reset_instrumentation()
    counts = get_instrumentation_counts()
    assert counts["total"] == 0
    assert counts["differs"] == 0
    assert counts["equals"] == 0

def test_instrumented_helper_sources() -> None:
    div_src = helper_source("_cpp_div", instrumented=True)
    mod_src = helper_source("_cpp_mod", instrumented=True)
    assert "_CPP2PY_INSTR_DIV_TOTAL" in div_src
    assert "_CPP2PY_INSTR_MOD_TOTAL" in mod_src

    prelude = get_instrumentation_prelude()
    assert "CPP2PY_INSTR_OUT" in prelude

    compile(div_src, "<test>", "exec")
    compile(mod_src, "<test>", "exec")
    compile(prelude, "<test>", "exec")

def test_instrumentation_on_tiny_program(tmp_path) -> None:
    instr_out = tmp_path / "counts.json"
    script = f"""import os, json
{get_instrumentation_prelude()}
{helper_source('_cpp_div', instrumented=True)}

# 1 execution equal: 10 / 2 = 5
q1 = _cpp_div(10, 2)
# 1 execution differs: -10 / 3 = -3 (native -4)
q2 = _cpp_div(-10, 3)
print(q1, q2)
"""
    env = {"CPP2PY_INSTR_OUT": str(instr_out)}
    old_env = None
    import os
    if "CPP2PY_INSTR_OUT" in os.environ:
        old_env = os.environ["CPP2PY_INSTR_OUT"]
    os.environ["CPP2PY_INSTR_OUT"] = str(instr_out)

    try:
        run_res = run_python(script)
        assert run_res.exit_code == 0
        assert "5 -3" in run_res.stdout
        assert instr_out.exists()
        import json
        data = json.loads(instr_out.read_text(encoding="utf-8"))
        assert data["total"] == 2
        assert data["differs"] == 1
        assert data["equals"] == 1
    finally:
        if old_env is not None:
            os.environ["CPP2PY_INSTR_OUT"] = old_env
        elif "CPP2PY_INSTR_OUT" in os.environ:
            del os.environ["CPP2PY_INSTR_OUT"]
