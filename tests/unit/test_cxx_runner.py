"""Unit tests for C++ runner, capability probe, and build cache."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cpp2py.testing.cxx_runner import (
    BuildResult,
    CxxBuildCache,
    CxxCapabilities,
    ExecutionResult,
    compile_cxx,
    probe_cxx_capabilities,
    run_cxx,
)


def test_capabilities_to_dict():
    caps = CxxCapabilities(
        compiler="g++",
        available=True,
        version="g++ 11.2.0",
        cxx17_supported=True,
        sanitizer_available=True,
    )
    d = caps.to_dict()
    assert d["compiler"] == "g++"
    assert d["available"] is True
    assert d["cxx17_supported"] is True
    assert d["sanitizer_available"] is True


def test_capabilities_probe_caching():
    c1 = probe_cxx_capabilities("nonexistent_compiler_xyz123")
    assert c1.available is False
    assert "Failed to execute" in (c1.reason or "") or "Compiler exit status" in (c1.reason or "")

    c2 = probe_cxx_capabilities("nonexistent_compiler_xyz123")
    assert c1 is c2  # cached


def test_build_cache_keying():
    with tempfile.TemporaryDirectory() as td:
        cache = CxxBuildCache(cache_dir=td)
        k1 = cache.compute_key("int main() { return 0; }", ["-std=c++17", "-O0"])
        k2 = cache.compute_key("int main() { return 0; }", ["-std=c++17", "-O0"])
        k3 = cache.compute_key("int main() { return 0; }", ["-std=c++17", "-O0", "-fwrapv"])
        k4 = cache.compute_key("int main() { return 1; }", ["-std=c++17", "-O0"])

        assert k1 == k2
        assert k1 != k3
        assert k1 != k4


def test_build_cache_put_and_get():
    with tempfile.TemporaryDirectory() as td:
        cache = CxxBuildCache(cache_dir=td)
        dummy_bin = Path(td) / ("dummy.exe" if sys.platform == "win32" else "dummy")
        dummy_bin.write_bytes(b"dummy binary content")
        os.chmod(dummy_bin, 0o755)

        key = "abc123sha"
        stored = cache.put(key, dummy_bin)
        assert stored.exists()

        retrieved = cache.get(key)
        assert retrieved is not None
        assert retrieved.exists()


def test_run_cxx_output_cap():
    # Test capping on a synthetic large output
    huge_text = "A" * 2000
    with tempfile.TemporaryDirectory() as td:
        fake_bin = Path(td) / "fake.bat" if sys.platform == "win32" else Path(td) / "fake.sh"
        if sys.platform == "win32":
            fake_bin.write_text(f"@echo off\necho {huge_text}\n", encoding="utf-8")
        else:
            fake_bin.write_text(f"#!/bin/sh\necho '{huge_text}'\n", encoding="utf-8")
            os.chmod(fake_bin, 0o755)

        res = run_cxx(fake_bin, output_cap=50)
        assert res.output_capped is True
        assert len(res.stdout) <= 50


def test_run_cxx_timeout():
    # Test timeout with a slow script
    with tempfile.TemporaryDirectory() as td:
        slow_bin = Path(td) / "slow.bat" if sys.platform == "win32" else Path(td) / "slow.sh"
        if sys.platform == "win32":
            py_exe = sys.executable.replace("\\", "\\\\")
            slow_bin.write_text(f'@echo off\n"{sys.executable}" -c "import time; time.sleep(5)"\n', encoding="utf-8")
        else:
            slow_bin.write_text(f'#!/bin/sh\n"{sys.executable}" -c "import time; time.sleep(5)"\n', encoding="utf-8")
            os.chmod(slow_bin, 0o755)

        res = run_cxx(slow_bin, timeout=0.5)
        assert res.timed_out is True
        assert res.exit_code == -1
