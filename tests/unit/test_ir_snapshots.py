import json
from pathlib import Path
import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig

def test_snapshots_files_present(tmp_path):
    cpp_code = "int main() { int x = 42; return 0; }"
    snap_dir = tmp_path / "snap"
    config = CompilerConfig(snapshot_dir=str(snap_dir))
    res = compile_source(cpp_code, "test.cpp", config)
    assert res.success

    assert (snap_dir / "00_ir_initial.ir.txt").exists()
    assert (snap_dir / "00_ir_initial.ir.json").exists()
    assert (snap_dir / "01_ir_final.ir.txt").exists()
    assert (snap_dir / "01_ir_final.ir.json").exists()
    assert (snap_dir / "output.py").exists()
    assert (snap_dir / "manifest.json").exists()

def test_snapshots_manifest_content_and_no_timestamps(tmp_path):
    cpp_code = "int main() { int x = 42; return 0; }"
    snap_dir = tmp_path / "snap"
    config = CompilerConfig(snapshot_dir=str(snap_dir))
    res = compile_source(cpp_code, "test.cpp", config)
    assert res.success

    manifest_path = snap_dir / "manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "tool_version" in manifest_data
    assert "source_sha256" in manifest_data
    assert "config" in manifest_data
    assert "stages" in manifest_data
    assert "diagnostics" in manifest_data

    manifest_raw = manifest_path.read_text(encoding="utf-8").lower()
    assert "timestamp" not in manifest_raw
    assert "time" not in manifest_raw
    assert "date" not in manifest_raw

def test_snapshots_deterministic_byte_identical(tmp_path):
    cpp_code = "int main() { int a = 1, b = 2; int c = a + b; return 0; }"
    dir1 = tmp_path / "snap1"
    dir2 = tmp_path / "snap2"

    config1 = CompilerConfig(snapshot_dir=str(dir1))
    config2 = CompilerConfig(snapshot_dir=str(dir2))

    res1 = compile_source(cpp_code, "test.cpp", config1)
    res2 = compile_source(cpp_code, "test.cpp", config2)
    assert res1.success and res2.success

    files = [
        "00_ir_initial.ir.txt",
        "00_ir_initial.ir.json",
        "01_ir_final.ir.txt",
        "01_ir_final.ir.json",
        "output.py",
        "manifest.json",
    ]

    for fname in files:
        b1 = (dir1 / fname).read_bytes()
        b2 = (dir2 / fname).read_bytes()
        assert b1 == b2, f"Snapshot file {fname} not byte-identical across runs!"

def test_snapshots_ir_json_structure(tmp_path):
    cpp_code = "int main() { int x = 10; return 0; }"
    snap_dir = tmp_path / "snap"
    config = CompilerConfig(snapshot_dir=str(snap_dir))
    res = compile_source(cpp_code, "test.cpp", config)
    assert res.success

    ir_json_path = snap_dir / "00_ir_initial.ir.json"
    data = json.loads(ir_json_path.read_text(encoding="utf-8"))

    assert "functions" in data
    assert len(data["functions"]) == 1
    func_data = data["functions"][0]
    assert func_data["name"] == "main"
    assert "body" in func_data
    assert len(func_data["body"]) >= 2
    assert func_data["body"][0]["opcode"] == "declare"

def test_snapshots_output_py_matches_compilation_result(tmp_path):
    cpp_code = "int main() { return 0; }"
    snap_dir = tmp_path / "snap"
    config = CompilerConfig(snapshot_dir=str(snap_dir))
    res = compile_source(cpp_code, "test.cpp", config)
    assert res.success

    out_py_path = snap_dir / "output.py"
    assert out_py_path.read_text(encoding="utf-8") == res.python_source
