"""Differential testing comparator and outcome classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cpp2py.testing.cxx_runner import ExecutionResult


class Outcome(str, Enum):
    """Outcome classes defined in ARCHITECTURE.md §H.3."""
    PASS = "PASS"
    MISMATCH_STDOUT = "MISMATCH_STDOUT"
    MISMATCH_EXIT = "MISMATCH_EXIT"
    MISMATCH_ONE_SIDED_FAILURE = "MISMATCH_ONE_SIDED_FAILURE"
    BOTH_FAILED_AGREE = "BOTH_FAILED_AGREE"
    UB_EXCLUDED = "UB_EXCLUDED"
    TRANSLATE_REJECTED = "TRANSLATE_REJECTED"
    CPP_COMPILE_ERROR = "CPP_COMPILE_ERROR"
    TIMEOUT_CPP = "TIMEOUT_CPP"
    TIMEOUT_PY = "TIMEOUT_PY"
    SKIPPED = "SKIPPED"


def normalize_newlines(text: str) -> str:
    """Normalize CRLF to LF. Trailing whitespace is preserved."""
    return text.replace("\r\n", "\n")


@dataclass
class DiffResult:
    """Result of comparing a single C++ vs Python execution."""
    case_id: str
    outcome: Outcome
    reason: str
    cxx_result: ExecutionResult | None = None
    py_result: ExecutionResult | None = None
    ubsan_result: ExecutionResult | None = None
    cxx_compile_error: str | None = None
    translate_diagnostics: list[str] = field(default_factory=list)

    def is_mismatch(self) -> bool:
        """Return True if this outcome is a disagreement."""
        return self.outcome in {
            Outcome.MISMATCH_STDOUT,
            Outcome.MISMATCH_EXIT,
            Outcome.MISMATCH_ONE_SIDED_FAILURE,
            Outcome.TIMEOUT_CPP,
            Outcome.TIMEOUT_PY,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "cxx_result": self.cxx_result.to_dict() if self.cxx_result else None,
            "py_result": self.py_result.to_dict() if self.py_result else None,
            "ubsan_result": self.ubsan_result.to_dict() if self.ubsan_result else None,
            "cxx_compile_error": self.cxx_compile_error,
            "translate_diagnostics": self.translate_diagnostics,
        }


def _is_crash_or_uncaught(res: ExecutionResult, is_python: bool = False) -> bool:
    """Detect if process crashed via fatal signal/exception."""
    # Negative exit code indicates terminated by signal (POSIX) or Windows crash code
    if res.exit_code < 0:
        return True
    if res.exit_code in (134, 139, 3221225477, 3221225725):  # SIGABRT, SIGSEGV, STATUS_ACCESS_VIOLATION
        return True
    if is_python:
        if "Traceback (most recent call last):" in res.stderr:
            return True
    return False


def compare_results(
    case_id: str,
    cxx_result: ExecutionResult | None = None,
    py_result: ExecutionResult | None = None,
    ubsan_result: ExecutionResult | None = None,
    translate_success: bool = True,
    translate_diagnostics: list[str] | None = None,
    cxx_compile_success: bool = True,
    cxx_compile_error: str | None = None,
    skipped: bool = False,
    skip_reason: str | None = None,
    overflow_policy: str = "assume_no_overflow",
    expected_failure: bool = False,
) -> DiffResult:
    """Classify the comparison outcome according to ARCHITECTURE.md §H.3."""
    diag_list = list(translate_diagnostics or [])

    if skipped:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.SKIPPED,
            reason=skip_reason or "Test skipped due to missing capability",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    if not translate_success:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.TRANSLATE_REJECTED,
            reason="Translator rejected program: " + ("; ".join(diag_list) if diag_list else "errors reported"),
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    if not cxx_compile_success:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.CPP_COMPILE_ERROR,
            reason=f"C++ compiler rejected program: {cxx_compile_error or 'compile error'}",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    if cxx_result is None or py_result is None:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.SKIPPED,
            reason="Missing execution results",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    # 1. Check for timeouts
    if cxx_result.timed_out and py_result.timed_out:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.BOTH_FAILED_AGREE,
            reason="Both C++ and Python executions timed out",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )
    if cxx_result.timed_out:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.TIMEOUT_CPP,
            reason="C++ execution timed out",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )
    if py_result.timed_out:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.TIMEOUT_PY,
            reason="Python execution timed out",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    # 2. Check for undefined behavior in sanitizer build
    if ubsan_result is not None:
        if "runtime error:" in ubsan_result.stderr:
            return DiffResult(
                case_id=case_id,
                outcome=Outcome.UB_EXCLUDED,
                reason=f"Sanitizer detected undefined behavior: {ubsan_result.stderr.strip()}",
                cxx_result=cxx_result,
                py_result=py_result,
                ubsan_result=ubsan_result,
                cxx_compile_error=cxx_compile_error,
                translate_diagnostics=diag_list,
            )

    # 3. Division by zero and integer overflow hardware exception check (UB)
    cxx_crashed = _is_crash_or_uncaught(cxx_result, is_python=False)
    py_crashed = _is_crash_or_uncaught(py_result, is_python=True)

    # 3221225621 = 0xC0000095 (STATUS_INTEGER_OVERFLOW / divide error)
    # 3221225620 = 0xC0000094 (STATUS_INTEGER_DIVIDE_BY_ZERO)
    # -8 / 136 = SIGFPE
    if cxx_result.exit_code in (3221225621, 3221225620, -8, 136):
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.UB_EXCLUDED,
            reason=f"Hardware integer division/overflow exception in C++ (exit {cxx_result.exit_code})",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    if (cxx_result.exit_code != 0 or cxx_crashed) and "ZeroDivisionError" in py_result.stderr:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.UB_EXCLUDED,
            reason="Both crashed on suspected division by zero (ZeroDivisionError)",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    # 4. If both failed under trap policy or expected failure
    if cxx_result.exit_code != 0 and py_result.exit_code != 0:
        if overflow_policy == "trap" or expected_failure:
            return DiffResult(
                case_id=case_id,
                outcome=Outcome.BOTH_FAILED_AGREE,
                reason=f"Both failed as expected under trap policy / expected failure (C++: {cxx_result.exit_code}, Py: {py_result.exit_code})",
                cxx_result=cxx_result,
                py_result=py_result,
                ubsan_result=ubsan_result,
                cxx_compile_error=cxx_compile_error,
                translate_diagnostics=diag_list,
            )

    # 5. One-sided failure: exactly one program crashes/raises
    if cxx_crashed != py_crashed:
        return DiffResult(
            case_id=case_id,
            outcome=Outcome.MISMATCH_ONE_SIDED_FAILURE,
            reason=f"One-sided failure: C++ exit {cxx_result.exit_code} (crashed={cxx_crashed}), Python exit {py_result.exit_code} (crashed={py_crashed})",
            cxx_result=cxx_result,
            py_result=py_result,
            ubsan_result=ubsan_result,
            cxx_compile_error=cxx_compile_error,
            translate_diagnostics=diag_list,
        )

    # 6. Both finished without crash
    cxx_stdout = normalize_newlines(cxx_result.stdout)
    py_stdout = normalize_newlines(py_result.stdout)

    if cxx_stdout == py_stdout:
        if cxx_result.exit_code == py_result.exit_code:
            return DiffResult(
                case_id=case_id,
                outcome=Outcome.PASS,
                reason="Outputs and exit codes match",
                cxx_result=cxx_result,
                py_result=py_result,
                ubsan_result=ubsan_result,
                cxx_compile_error=cxx_compile_error,
                translate_diagnostics=diag_list,
            )
        else:
            return DiffResult(
                case_id=case_id,
                outcome=Outcome.MISMATCH_EXIT,
                reason=f"Stdout matches, but exit codes differ: C++ {cxx_result.exit_code} != Python {py_result.exit_code}",
                cxx_result=cxx_result,
                py_result=py_result,
                ubsan_result=ubsan_result,
                cxx_compile_error=cxx_compile_error,
                translate_diagnostics=diag_list,
            )

    # Stdout differs
    return DiffResult(
        case_id=case_id,
        outcome=Outcome.MISMATCH_STDOUT,
        reason="Stdout mismatch between C++ and Python",
        cxx_result=cxx_result,
        py_result=py_result,
        ubsan_result=ubsan_result,
        cxx_compile_error=cxx_compile_error,
        translate_diagnostics=diag_list,
    )


def compute_agreement_rate(counts: dict[Outcome, int]) -> tuple[float | None, int, int]:
    """Compute agreement rate as defined in ARCHITECTURE.md §H.3:
    rate = PASS / (PASS + MISMATCH_*)
    Returns (rate, pass_count, denominator).
    """
    pass_count = counts.get(Outcome.PASS, 0)
    mismatches = (
        counts.get(Outcome.MISMATCH_STDOUT, 0)
        + counts.get(Outcome.MISMATCH_EXIT, 0)
        + counts.get(Outcome.MISMATCH_ONE_SIDED_FAILURE, 0)
        + counts.get(Outcome.TIMEOUT_CPP, 0)
        + counts.get(Outcome.TIMEOUT_PY, 0)
    )
    denominator = pass_count + mismatches
    rate = (pass_count / denominator) if denominator > 0 else None
    return rate, pass_count, denominator
