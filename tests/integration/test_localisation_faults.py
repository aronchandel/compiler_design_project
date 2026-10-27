from __future__ import annotations

import json
from pathlib import Path
import pytest

from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode
from cpp2py.localisation import DISCLAIMER_SENTENCE, localise
from cpp2py.testing.cxx_runner import compile_cxx, probe_cxx_capabilities, run_cxx
from cpp2py.testing.py_runner import run_python
from tests.faults import (
    patch_fault_f1_floor_div,
    patch_fault_f2_mod_plan_native,
    patch_fault_f3_generator_mod,
    patch_fault_f4_builder_swap_sub,
    patch_fault_f5_fold_mul_as_add,
)

pytestmark = pytest.mark.requires_cxx

def _check_cxx_available() -> bool:
    caps = probe_cxx_capabilities()
    return caps.available

def _run_and_localise_case(
    tmp_path: Path,
    cpp_source: str,
    stdin_text: str = "",
    compat_mode: CompatMode = CompatMode.RANGE_GUIDED,
) -> tuple[Path, str, int]:
    if not _check_cxx_available():
        pytest.skip("g++ not available")

    case_dir = tmp_path / "case"
    case_dir.mkdir(parents=True, exist_ok=True)
    snap_dir = case_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    build_res = compile_cxx(cpp_source, build_dir=tmp_path / "cxx_build")
    assert build_res.success, f"g++ build failed: {build_res.error_message}"
    assert build_res.binary_path is not None
    cxx_exec = run_cxx(build_res.binary_path, stdin_text=stdin_text)

    cfg = CompilerConfig(
        snapshot_dir=snap_dir,
        transform_log_path=snap_dir / "transform_log.jsonl",
        fold_constants=True,
        compat_mode=compat_mode,
    )
    comp_res = compile_source(cpp_source, "program.cpp", config=cfg)
    assert comp_res.success, f"cpp2py failed: {[d.message for d in comp_res.diagnostics]}"
    assert comp_res.python_source is not None

    (case_dir / "program.cpp").write_text(cpp_source, encoding="utf-8")
    (case_dir / "input.txt").write_text(stdin_text, encoding="utf-8")
    (case_dir / "cxx_output.txt").write_text(cxx_exec.stdout, encoding="utf-8")
    (case_dir / "output.py").write_text(comp_res.python_source, encoding="utf-8")

    meta = {
        "case_id": "test_fault",
        "cxx_exit_code": cxx_exec.exit_code,
        "category": "arithmetic",
        "has_ub": False,
    }
    (case_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return case_dir, cxx_exec.stdout, cxx_exec.exit_code

def test_fault_f1_floor_division(tmp_path: Path) -> None:
    cpp_source = """#include <iostream>
int main() {
    int x = -7 / 2;
    std::cout << x << std::endl;
    return 0;
}
"""
    with patch_fault_f1_floor_div():
        case_dir, cxx_out, cxx_ec = _run_and_localise_case(tmp_path, cpp_source)

    report = localise(case_dir, top_k=5)
    assert report.stage_verdict == "after_constant_fold", f"Got stage: {report.stage_verdict}"
    assert len(report.suspects) >= 1

    top3 = report.suspects[:3]
    assert any(s.opcode in ("div", "assign") or "div" in str(s.evidence).lower() for s in top3)
    assert DISCLAIMER_SENTENCE in report.disclaimer

def test_fault_f2_mod_plan_native(tmp_path: Path) -> None:
    cpp_source = """#include <iostream>
int main() {
    int a;
    std::cin >> a;
    int b = a % 3;
    std::cout << b << std::endl;
    return 0;
}
"""
    with patch_fault_f2_mod_plan_native():
        case_dir, cxx_out, cxx_ec = _run_and_localise_case(tmp_path, cpp_source, stdin_text="-7\n")

    report = localise(case_dir, top_k=5)
    assert report.stage_verdict == "codegen_or_plan", f"Got stage: {report.stage_verdict}"
    assert len(report.suspects) >= 1
    top3 = report.suspects[:3]

    assert any(s.opcode == "mod" or "mod" in str(s.evidence).lower() for s in top3)
    assert DISCLAIMER_SENTENCE in report.disclaimer

def test_fault_f3_generator_mod(tmp_path: Path) -> None:
    cpp_source = """#include <iostream>
int main() {
    int a;
    std::cin >> a;
    int b = a % 3;
    std::cout << b << std::endl;
    return 0;
}
"""
    with patch_fault_f3_generator_mod():
        case_dir, cxx_out, cxx_ec = _run_and_localise_case(tmp_path, cpp_source, stdin_text="-7\n")

    report = localise(case_dir, top_k=5)
    assert report.stage_verdict == "codegen_or_plan", f"Got stage: {report.stage_verdict}"
    assert len(report.suspects) >= 1
    top3 = report.suspects[:3]
    assert any(s.opcode == "mod" or "mod" in str(s.evidence).lower() for s in top3)
    assert DISCLAIMER_SENTENCE in report.disclaimer

def test_fault_f4_builder_swap_sub(tmp_path: Path) -> None:
    cpp_source = """#include <iostream>
int main() {
    int a = 10 - 3;
    std::cout << a << std::endl;
    return 0;
}
"""
    with patch_fault_f4_builder_swap_sub():
        case_dir, cxx_out, cxx_ec = _run_and_localise_case(tmp_path, cpp_source)

    report = localise(case_dir, top_k=5)
    assert report.stage_verdict == "ir_generation", f"Got stage: {report.stage_verdict}"
    assert len(report.suspects) >= 1
    top3 = report.suspects[:3]
    assert any(s.opcode == "sub" or "sub" in str(s.evidence).lower() for s in top3)
    assert DISCLAIMER_SENTENCE in report.disclaimer

def test_fault_f5_fold_mul_as_add(tmp_path: Path) -> None:
    cpp_source = """#include <iostream>
int main() {
    int a = 5 * 4;
    std::cout << a << std::endl;
    return 0;
}
"""
    with patch_fault_f5_fold_mul_as_add():
        case_dir, cxx_out, cxx_ec = _run_and_localise_case(tmp_path, cpp_source)

    report = localise(case_dir, top_k=5)
    assert report.stage_verdict == "after_constant_fold", f"Got stage: {report.stage_verdict}"
    assert len(report.suspects) >= 1
    top3 = report.suspects[:3]
    assert any(s.opcode in ("mul", "assign") or "mul" in str(s.evidence).lower() for s in top3)
    assert DISCLAIMER_SENTENCE in report.disclaimer
