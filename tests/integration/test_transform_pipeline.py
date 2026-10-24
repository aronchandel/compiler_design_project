"""Integration tests for transformation pipeline (Phase 4).

Covers AC4.2, AC4.3, AC4.5, AC4.7, AC4.9, AC4.10.
"""

import json
import subprocess
import sys
from pathlib import Path
import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode
from cpp2py.ir.printer import format_module
from cpp2py.transforms.log import TransformLog


def test_ac4_2_fold_demo_stage4_ir_and_stage5_python_and_exec(tmp_path, repo_root):
    """AC4.2: fold_demo.cpp: --dump-ir equals ARCH §D.4 Stage 4; generated Python equals Stage 5; stdout 48."""
    cpp_file = repo_root / "examples" / "worked" / "fold_demo.cpp"
    assert cpp_file.exists()
    cpp_text = cpp_file.read_text(encoding="utf-8")

    res = compile_source(cpp_text, str(cpp_file), CompilerConfig(fold_constants=True))
    assert res.success, [d.message for d in res.diagnostics]

    # Verify Stage 4 IR
    expected_stage4_ir = (
        "function main() -> i32 {\n"
        "  op_0   declare a : i32                 ; L5:5\n"
        "  op_2   a = assign 42                   ; L5:5     [derived from op_1]\n"
        "  op_3   declare b : i32                 ; L6:5\n"
        "  op_5   t2 = add a, 6                   ; L6:13    [derived from op_4]\n"
        "  op_6   b = assign t2                   ; L6:5\n"
        "  op_7   print b, endl                   ; L7:5\n"
        "  op_8   return 0                        ; L8:5\n"
        "}\n"
    )
    actual_ir = format_module(res.ir)
    assert actual_ir == expected_stage4_ir

    # Verify Stage 5 Python
    expected_python_body = (
        "def main():\n"
        "    a = 42\n"
        "    b = a + 6\n"
        "    print(b)\n"
        "    return 0"
    )
    assert expected_python_body in res.python_source

    # Run generated Python -> stdout 48
    proc = subprocess.run(
        [sys.executable, "-c", res.python_source],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "48"


def test_ac4_3_transform_log_fold_demo(tmp_path, repo_root):
    """AC4.3: --transform-log of fold_demo.cpp is valid JSONL with 6 records (4 REPLACE, 2 DELETE) and replay test passes."""
    cpp_file = repo_root / "examples" / "worked" / "fold_demo.cpp"
    cpp_text = cpp_file.read_text(encoding="utf-8")
    log_path = tmp_path / "fold.jsonl"

    config = CompilerConfig(
        fold_constants=True,
        transform_log_path=str(log_path),
    )
    res = compile_source(cpp_text, str(cpp_file), config)
    assert res.success

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6

    records = [json.loads(line) for line in lines]

    # Check 6 records structure and order from ARCH §D.4:
    # 1. op_1 REPLACE (6*7 -> 42)
    assert records[0]["seq"] == 1
    assert records[0]["pass"] == "constant_fold"
    assert records[0]["op_id"] == "op_1"
    assert records[0]["kind"] == "REPLACE"
    assert records[0]["before"] == "t0 = mul 6, 7"
    assert records[0]["after"] == "t0 = assign 42"
    assert records[0]["derived_from"] == []

    # 2. op_2 REPLACE (a = assign t0 -> a = assign 42)
    assert records[1]["seq"] == 2
    assert records[1]["pass"] == "constant_fold"
    assert records[1]["op_id"] == "op_2"
    assert records[1]["kind"] == "REPLACE"
    assert records[1]["before"] == "a = assign t0"
    assert records[1]["after"] == "a = assign 42"
    assert records[1]["derived_from"] == ["op_1"]

    # 3. op_4 REPLACE (2*3 -> 6)
    assert records[2]["seq"] == 3
    assert records[2]["pass"] == "constant_fold"
    assert records[2]["op_id"] == "op_4"
    assert records[2]["kind"] == "REPLACE"
    assert records[2]["before"] == "t1 = mul 2, 3"
    assert records[2]["after"] == "t1 = assign 6"
    assert records[2]["derived_from"] == []

    # 4. op_5 REPLACE (t2 = add a, t1 -> t2 = add a, 6)
    assert records[3]["seq"] == 4
    assert records[3]["pass"] == "constant_fold"
    assert records[3]["op_id"] == "op_5"
    assert records[3]["kind"] == "REPLACE"
    assert records[3]["before"] == "t2 = add a, t1"
    assert records[3]["after"] == "t2 = add a, 6"
    assert records[3]["derived_from"] == ["op_4"]

    # 5. op_1 DELETE
    assert records[4]["seq"] == 5
    assert records[4]["pass"] == "dead_temps"
    assert records[4]["op_id"] == "op_1"
    assert records[4]["kind"] == "DELETE"
    assert records[4]["before"] == "t0 = assign 42"
    assert records[4]["after"] is None

    # 6. op_4 DELETE
    assert records[5]["seq"] == 6
    assert records[5]["pass"] == "dead_temps"
    assert records[5]["op_id"] == "op_4"
    assert records[5]["kind"] == "DELETE"
    assert records[5]["before"] == "t1 = assign 6"
    assert records[5]["after"] is None

    # Replay test: applying log to initial IR reproduces the final IR exactly!
    # Compile with no fold to get initial IR
    res_initial = compile_source(cpp_text, str(cpp_file), CompilerConfig(fold_constants=False))
    log_obj = TransformLog.read_jsonl(log_path)
    replayed_ir = log_obj.replay(res_initial.ir)
    assert format_module(replayed_ir) == format_module(res.ir)


def test_ac4_7_regression_earlier_examples_both_modes(tmp_path, repo_root):
    """AC4.7: All Phase 1 and Phase 3 examples produce .expected output with folding on and --no-fold."""
    for phase in ("phase1", "phase3"):
        ex_dir = repo_root / "examples" / phase
        if not ex_dir.exists():
            continue
        expected_files = list(ex_dir.glob("*.expected"))
        for exp in expected_files:
            cpp_file = ex_dir / f"{exp.stem}.cpp"
            if not cpp_file.exists():
                continue
            cpp_text = cpp_file.read_text(encoding="utf-8")
            expected_out = exp.read_text(encoding="utf-8").replace("\r\n", "\n")

            in_file = ex_dir / f"{exp.stem}.in"
            stdin_text = in_file.read_text(encoding="utf-8") if in_file.exists() else ""

            # Test 1: folding on
            res_fold = compile_source(cpp_text, str(cpp_file), CompilerConfig(fold_constants=True))
            assert res_fold.success, f"Failed fold on {cpp_file}: {[d.message for d in res_fold.diagnostics]}"
            proc1 = subprocess.run([sys.executable, "-c", res_fold.python_source], input=stdin_text, text=True, capture_output=True)
            assert proc1.returncode == 0
            assert proc1.stdout.replace("\r\n", "\n") == expected_out

            # Test 2: --no-fold
            res_nofold = compile_source(cpp_text, str(cpp_file), CompilerConfig(fold_constants=False))
            assert res_nofold.success, f"Failed no-fold on {cpp_file}: {[d.message for d in res_nofold.diagnostics]}"
            proc2 = subprocess.run([sys.executable, "-c", res_nofold.python_source], input=stdin_text, text=True, capture_output=True)
            assert proc2.returncode == 0
            assert proc2.stdout.replace("\r\n", "\n") == expected_out

    # Also test Phase 4 examples with folding on
    p4_dir = repo_root / "examples" / "phase4"
    if p4_dir.exists():
        for exp in p4_dir.glob("*.expected"):
            cpp_file = p4_dir / f"{exp.stem}.cpp"
            if not cpp_file.exists():
                continue
            cpp_text = cpp_file.read_text(encoding="utf-8")
            expected_out = exp.read_text(encoding="utf-8").replace("\r\n", "\n")
            res_fold = compile_source(cpp_text, str(cpp_file), CompilerConfig(fold_constants=True))
            assert res_fold.success
            proc = subprocess.run([sys.executable, "-c", res_fold.python_source], text=True, capture_output=True)
            assert proc.returncode == 0
            assert proc.stdout.replace("\r\n", "\n") == expected_out


def test_ac4_9_snapshots_per_pass_and_manifest(tmp_path, repo_root):
    """AC4.9: Snapshot directory lists NN_after_<pass> only for passes that changed IR; manifest matches."""
    cpp_file = repo_root / "examples" / "worked" / "fold_demo.cpp"
    cpp_text = cpp_file.read_text(encoding="utf-8")
    snap_dir = tmp_path / "snap"

    config = CompilerConfig(
        fold_constants=True,
        snapshot_dir=str(snap_dir),
    )
    res = compile_source(cpp_text, str(cpp_file), config)
    assert res.success

    # Snapshots present:
    # 00_ir_initial
    # 01_after_constant_fold
    # 02_after_dead_temps
    # 03_ir_final
    assert (snap_dir / "00_ir_initial.ir.txt").exists()
    assert (snap_dir / "01_after_constant_fold.ir.txt").exists()
    assert (snap_dir / "02_after_dead_temps.ir.txt").exists()
    assert (snap_dir / "03_ir_final.ir.txt").exists()
    assert (snap_dir / "output.py").exists()
    assert (snap_dir / "manifest.json").exists()

    manifest = json.loads((snap_dir / "manifest.json").read_text(encoding="utf-8"))
    stages = manifest["stages"]
    assert stages == [
        {"name": "00_ir_initial", "changed": False},
        {"name": "01_after_constant_fold", "changed": True},
        {"name": "02_after_dead_temps", "changed": True},
        {"name": "03_ir_final", "changed": False},
    ]


def test_ac4_10_no_analysis_or_compat_directories():
    """AC4.10: Phase boundary discipline: No testing/ or localisation/ directories; / and % produce W6001 in naive mode."""
    repo_cpp2py = Path("cpp2py")
    assert not (repo_cpp2py / "testing").exists()
    assert not (repo_cpp2py / "localisation").exists()

    # / and % on non-folded expressions emit W6001 in naive mode
    code = "using namespace std; int main() { int a; cin >> a; cout << a / 2 << a % 2 << endl; return 0; }"
    res = compile_source(code, "test.cpp", CompilerConfig(fold_constants=True, compat_mode=CompatMode.NAIVE))
    assert res.success
    w6001_warnings = [d for d in res.diagnostics if d.code == "W6001"]
    assert len(w6001_warnings) >= 2
