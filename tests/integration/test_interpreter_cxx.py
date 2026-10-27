from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, OverflowPolicy, TargetModel
from cpp2py.localisation.ir_interpreter import interpret_module
from cpp2py.testing.cxx_runner import compile_cxx, probe_cxx_capabilities, run_cxx

pytestmark = pytest.mark.requires_cxx

KNOWN_UB_CASES = {
    "case_17_int_min_div_neg_one_wrap",
    "case_18_int_min_mod_neg_one_wrap",
    "phase4_fold_overflow_kept",
    "phase5_boundary_int_min",
}

def _check_cxx_available() -> bool:
    caps = probe_cxx_capabilities()
    return caps.available

def test_interpreter_vs_cxx_curated_cases(tmp_path: Path) -> None:
    if not _check_cxx_available():
        pytest.skip("g++ not available")

    cases_dir = Path("tests/differential/cases")
    assert cases_dir.exists(), "Curated cases directory not found"

    build_dir = tmp_path / "cxx_curated"
    build_dir.mkdir(parents=True, exist_ok=True)

    disagreements = []
    tested_count = 0

    for case_p in sorted(cases_dir.iterdir()):
        if not case_p.is_dir():
            continue
        cid = case_p.name
        if cid in KNOWN_UB_CASES:
            continue

        meta_p = case_p / "meta.json"
        ov_policy = "assume_no_overflow"
        if meta_p.exists():
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            ov_policy = meta.get("config_overrides", {}).get("overflow_policy", "assume_no_overflow")

        src = (case_p / "program.cpp").read_text(encoding="utf-8")
        in_p = case_p / "input.txt"
        inp = in_p.read_text(encoding="utf-8") if in_p.exists() else ""

        b_res = compile_cxx(src, overflow_policy=ov_policy, build_dir=build_dir / cid)
        assert b_res.success, f"g++ compile failed for {cid}: {b_res.compile_error}"
        assert b_res.binary_path is not None
        cxx_res = run_cxx(b_res.binary_path, stdin_text=inp)

        pol_enum = OverflowPolicy.ASSUME_NO_OVERFLOW
        if ov_policy == "wrap":
            pol_enum = OverflowPolicy.WRAP
        elif ov_policy == "trap":
            pol_enum = OverflowPolicy.TRAP

        target = TargetModel(overflow_policy=pol_enum)
        cfg = CompilerConfig(target=target, fold_constants=False)
        comp_res = compile_source(src, "program.cpp", config=cfg)
        assert comp_res.success and comp_res.ir is not None, f"IR generation failed for {cid}"

        interp_res = interpret_module(comp_res.ir, stdin_text=inp, target=target, overflow_policy=ov_policy)

        norm_interp = interp_res.stdout.replace("\r\n", "\n").strip()
        norm_cxx = cxx_res.stdout.replace("\r\n", "\n").strip()

        tested_count += 1
        if norm_interp != norm_cxx or interp_res.exit_code != cxx_res.exit_code:
            disagreements.append(
                f"Case {cid}: interp(stdout={norm_interp!r}, ec={interp_res.exit_code}) != cxx(stdout={norm_cxx!r}, ec={cxx_res.exit_code})"
            )

    assert not disagreements, f"Disagreements found in curated cases:\n" + "\n".join(disagreements)
    assert tested_count >= 40, f"Expected at least 40 curated cases tested, got {tested_count}"

def test_interpreter_vs_cxx_examples(tmp_path: Path) -> None:
    if not _check_cxx_available():
        pytest.skip("g++ not available")

    example_dirs = [
        Path("examples/phase1"),
        Path("examples/phase3"),
        Path("examples/phase4"),
        Path("examples/phase5"),
        Path("examples/worked"),
    ]

    build_dir = tmp_path / "cxx_examples"
    build_dir.mkdir(parents=True, exist_ok=True)

    disagreements = []
    tested_count = 0

    for ed in example_dirs:
        for cpp_p in sorted(ed.glob("*.cpp")):
            cid = f"{ed.name}_{cpp_p.stem}"
            if cid in KNOWN_UB_CASES:
                continue

            src = cpp_p.read_text(encoding="utf-8")
            in_p = cpp_p.with_suffix(".in")
            inp = in_p.read_text(encoding="utf-8") if in_p.exists() else ""

            b_res = compile_cxx(src, build_dir=build_dir / cid)
            if not b_res.success:
                disagreements.append(f"g++ compile failed for {cid}: {b_res.compile_error}")
                continue
            assert b_res.binary_path is not None
            cxx_res = run_cxx(b_res.binary_path, stdin_text=inp)

            target = TargetModel()
            cfg = CompilerConfig(target=target, fold_constants=False)
            comp_res = compile_source(src, cpp_p.name, config=cfg)
            if not comp_res.success or comp_res.ir is None:
                disagreements.append(f"cpp2py compile failed for {cid}")
                continue

            interp_res = interpret_module(comp_res.ir, stdin_text=inp, target=target)

            norm_interp = interp_res.stdout.replace("\r\n", "\n").strip()
            norm_cxx = cxx_res.stdout.replace("\r\n", "\n").strip()

            tested_count += 1
            if norm_interp != norm_cxx or interp_res.exit_code != cxx_res.exit_code:
                disagreements.append(
                    f"Example {cid}: interp(stdout={norm_interp!r}, ec={interp_res.exit_code}) != cxx(stdout={norm_cxx!r}, ec={cxx_res.exit_code})"
                )

    assert not disagreements, f"Disagreements found in examples:\n" + "\n".join(disagreements)
    assert tested_count >= 35, f"Expected at least 35 examples tested, got {tested_count}"
