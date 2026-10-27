import pytest

from cpp2py.testing.comparator import (
    DiffResult,
    Outcome,
    compare_results,
    compute_agreement_rate,
    normalize_newlines,
)
from cpp2py.testing.cxx_runner import ExecutionResult

def test_normalize_newlines():
    assert normalize_newlines("hello\r\nworld\r\n") == "hello\nworld\n"
    assert normalize_newlines("line1\nline2\r\nline3") == "line1\nline2\nline3"

    assert normalize_newlines("hello   \r\n") == "hello   \n"

def test_outcome_pass():
    cxx = ExecutionResult(stdout="42\n", stderr="", exit_code=0)
    py = ExecutionResult(stdout="42\r\n", stderr="", exit_code=0)
    res = compare_results("t1", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.PASS
    assert not res.is_mismatch()

def test_outcome_mismatch_stdout():
    cxx = ExecutionResult(stdout="-3\n", stderr="", exit_code=0)
    py = ExecutionResult(stdout="-4\n", stderr="", exit_code=0)
    res = compare_results("t2", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.MISMATCH_STDOUT
    assert res.is_mismatch()

def test_outcome_trailing_whitespace_mismatch():
    cxx = ExecutionResult(stdout="42\n", stderr="", exit_code=0)
    py = ExecutionResult(stdout="42 \n", stderr="", exit_code=0)
    res = compare_results("t3", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.MISMATCH_STDOUT
    assert res.is_mismatch()

def test_outcome_mismatch_exit():
    cxx = ExecutionResult(stdout="done\n", stderr="", exit_code=0)
    py = ExecutionResult(stdout="done\n", stderr="", exit_code=1)
    res = compare_results("t4", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.MISMATCH_EXIT
    assert res.is_mismatch()

def test_outcome_mismatch_one_sided_failure():
    cxx = ExecutionResult(stdout="", stderr="SIGSEGV", exit_code=-11)
    py = ExecutionResult(stdout="ok\n", stderr="", exit_code=0)
    res = compare_results("t5", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.MISMATCH_ONE_SIDED_FAILURE
    assert res.is_mismatch()

def test_outcome_both_failed_agree_trap():
    cxx = ExecutionResult(stdout="", stderr="SIGILL", exit_code=-4)
    py = ExecutionResult(stdout="", stderr="OverflowError", exit_code=1)
    res = compare_results("t6", cxx_result=cxx, py_result=py, overflow_policy="trap")
    assert res.outcome == Outcome.BOTH_FAILED_AGREE
    assert not res.is_mismatch()

def test_outcome_ub_excluded_sanitizer():
    cxx = ExecutionResult(stdout="0\n", stderr="", exit_code=0)
    py = ExecutionResult(stdout="0\n", stderr="", exit_code=0)
    ubsan = ExecutionResult(
        stdout="",
        stderr="runtime error: signed integer overflow: 2147483647 + 1 cannot be represented",
        exit_code=1,
    )
    res = compare_results("t7", cxx_result=cxx, py_result=py, ubsan_result=ubsan)
    assert res.outcome == Outcome.UB_EXCLUDED
    assert not res.is_mismatch()

def test_outcome_ub_excluded_div_zero():
    cxx = ExecutionResult(stdout="", stderr="SIGFPE", exit_code=-8)
    py = ExecutionResult(stdout="", stderr="ZeroDivisionError: division by zero", exit_code=1)
    res = compare_results("t8", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.UB_EXCLUDED
    assert not res.is_mismatch()

def test_outcome_translate_rejected():
    res = compare_results("t9", translate_success=False, translate_diagnostics=["E4001: unsupported construct"])
    assert res.outcome == Outcome.TRANSLATE_REJECTED
    assert not res.is_mismatch()

def test_outcome_cpp_compile_error():
    res = compare_results("t10", cxx_compile_success=False, cxx_compile_error="g++ syntax error")
    assert res.outcome == Outcome.CPP_COMPILE_ERROR
    assert not res.is_mismatch()

def test_outcome_timeout_cpp():
    cxx = ExecutionResult(stdout="", stderr="", exit_code=-1, timed_out=True)
    py = ExecutionResult(stdout="ok\n", stderr="", exit_code=0, timed_out=False)
    res = compare_results("t11", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.TIMEOUT_CPP
    assert res.is_mismatch()

def test_outcome_timeout_py():
    cxx = ExecutionResult(stdout="ok\n", stderr="", exit_code=0, timed_out=False)
    py = ExecutionResult(stdout="", stderr="", exit_code=-1, timed_out=True)
    res = compare_results("t12", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.TIMEOUT_PY
    assert res.is_mismatch()

def test_outcome_both_timed_out():
    cxx = ExecutionResult(stdout="", stderr="", exit_code=-1, timed_out=True)
    py = ExecutionResult(stdout="", stderr="", exit_code=-1, timed_out=True)
    res = compare_results("t13", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.BOTH_FAILED_AGREE
    assert not res.is_mismatch()

def test_outcome_skipped():
    res = compare_results("t14", skipped=True, skip_reason="g++ not found")
    assert res.outcome == Outcome.SKIPPED
    assert not res.is_mismatch()

def test_compute_agreement_rate():
    counts = {
        Outcome.PASS: 90,
        Outcome.MISMATCH_STDOUT: 5,
        Outcome.MISMATCH_EXIT: 3,
        Outcome.MISMATCH_ONE_SIDED_FAILURE: 2,
        Outcome.TIMEOUT_CPP: 0,
        Outcome.TIMEOUT_PY: 0,
        Outcome.UB_EXCLUDED: 10,
        Outcome.TRANSLATE_REJECTED: 4,
        Outcome.CPP_COMPILE_ERROR: 2,
        Outcome.BOTH_FAILED_AGREE: 1,
        Outcome.SKIPPED: 20,
    }

    rate, num, denom = compute_agreement_rate(counts)
    assert num == 90
    assert denom == 100
    assert rate == 0.90

def test_compute_agreement_rate_empty():
    counts = {Outcome.UB_EXCLUDED: 5, Outcome.SKIPPED: 10}
    rate, num, denom = compute_agreement_rate(counts)
    assert num == 0
    assert denom == 0
    assert rate is None

def test_outcome_ub_hardware_integer_overflow():

    cxx = ExecutionResult(stdout="", stderr="", exit_code=3221225621)
    py = ExecutionResult(stdout="0\n", stderr="", exit_code=0)
    res = compare_results("t15", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.UB_EXCLUDED
    assert not res.is_mismatch()
    assert "3221225621" in res.reason

def test_outcome_ub_hardware_divide_by_zero():

    cxx = ExecutionResult(stdout="", stderr="", exit_code=3221225620)
    py = ExecutionResult(stdout="0\n", stderr="", exit_code=0)
    res = compare_results("t16", cxx_result=cxx, py_result=py)
    assert res.outcome == Outcome.UB_EXCLUDED
    assert not res.is_mismatch()

def test_outcome_ub_sigfpe():

    cxx1 = ExecutionResult(stdout="", stderr="", exit_code=-8)
    py1 = ExecutionResult(stdout="0\n", stderr="", exit_code=0)
    res1 = compare_results("t17a", cxx_result=cxx1, py_result=py1)
    assert res1.outcome == Outcome.UB_EXCLUDED

    cxx2 = ExecutionResult(stdout="", stderr="", exit_code=136)
    py2 = ExecutionResult(stdout="0\n", stderr="", exit_code=0)
    res2 = compare_results("t17b", cxx_result=cxx2, py_result=py2)
    assert res2.outcome == Outcome.UB_EXCLUDED

def test_diff_result_to_dict():
    cxx = ExecutionResult(stdout="1\n", stderr="", exit_code=0)
    py = ExecutionResult(stdout="1\n", stderr="", exit_code=0)
    res = compare_results("t18", cxx_result=cxx, py_result=py)
    d = res.to_dict()
    assert d["case_id"] == "t18"
    assert d["outcome"] == "PASS"
    assert res.is_mismatch() is False
    assert d["cxx_result"]["exit_code"] == 0
    assert d["py_result"]["exit_code"] == 0
