"""C++ compilation and execution runner for differential testing."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

if sys.platform == "win32":
    try:
        import ctypes
        SEM_FAILCRITICALERRORS = 0x0001
        SEM_NOGPFAULTERRORBOX = 0x0002
        ctypes.windll.kernel32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX)
    except Exception:
        pass
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CxxCapabilities:
    """Probed capabilities of the C++ compiler."""
    compiler: str
    available: bool
    version: str = ""
    cxx17_supported: bool = False
    sanitizer_available: bool = False
    reason: str | None = None
    sanitizer_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "compiler": self.compiler,
            "available": self.available,
            "version": self.version,
            "cxx17_supported": self.cxx17_supported,
            "sanitizer_available": self.sanitizer_available,
            "reason": self.reason,
            "sanitizer_reason": self.sanitizer_reason,
        }


_CAPABILITIES_CACHE: dict[str, CxxCapabilities] = {}


def probe_cxx_capabilities(compiler: str | None = None, force_refresh: bool = False) -> CxxCapabilities:
    """Probe the compiler capabilities (version, C++17 support, sanitizer availability)."""
    if compiler is None:
        compiler = os.environ.get("CXX", "g++")

    if not force_refresh and compiler in _CAPABILITIES_CACHE:
        return _CAPABILITIES_CACHE[compiler]

    # Test 1: Can we run the compiler binary?
    try:
        proc = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if proc.returncode != 0:
            caps = CxxCapabilities(
                compiler=compiler,
                available=False,
                reason=f"Compiler exit status {proc.returncode}: {proc.stderr.strip()}",
            )
            _CAPABILITIES_CACHE[compiler] = caps
            return caps
        version_line = proc.stdout.splitlines()[0] if proc.stdout else ""
    except (OSError, subprocess.SubprocessError) as exc:
        caps = CxxCapabilities(
            compiler=compiler,
            available=False,
            reason=f"Failed to execute {compiler}: {exc}",
        )
        _CAPABILITIES_CACHE[compiler] = caps
        return caps

    # Test 2: Can we compile a C++17 minimal program?
    cxx17_supported = False
    cxx17_reason = None
    sanitizer_available = False
    sanitizer_reason = None

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "probe.cpp"
        exe = Path(td) / ("probe.exe" if sys.platform == "win32" else "probe")
        src.write_text("#include <iostream>\nint main() { return 0; }\n", encoding="utf-8")

        try:
            p_cxx17 = subprocess.run(
                [compiler, "-std=c++17", "-O0", str(src), "-o", str(exe)],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            if p_cxx17.returncode == 0:
                cxx17_supported = True
            else:
                cxx17_reason = f"C++17 build failed: {p_cxx17.stderr.strip()}"
        except (OSError, subprocess.SubprocessError) as exc:
            cxx17_reason = f"C++17 compilation execution error: {exc}"

        # Test 3: Can we compile with UBSan?
        if cxx17_supported:
            san_exe = Path(td) / ("probe_san.exe" if sys.platform == "win32" else "probe_san")
            try:
                p_san = subprocess.run(
                    [
                        compiler,
                        "-std=c++17",
                        "-O0",
                        "-fsanitize=signed-integer-overflow,integer-divide-by-zero",
                        "-fno-sanitize-recover=all",
                        str(src),
                        "-o",
                        str(san_exe),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10.0,
                )
                if p_san.returncode == 0:
                    sanitizer_available = True
                else:
                    sanitizer_reason = p_san.stderr.strip() or "Sanitizer build failed"
            except (OSError, subprocess.SubprocessError) as exc:
                sanitizer_reason = str(exc)

    caps = CxxCapabilities(
        compiler=compiler,
        available=cxx17_supported,
        version=version_line,
        cxx17_supported=cxx17_supported,
        sanitizer_available=sanitizer_available,
        reason=cxx17_reason,
        sanitizer_reason=sanitizer_reason,
    )
    _CAPABILITIES_CACHE[compiler] = caps
    return caps


@dataclass
class ExecutionResult:
    """Result of running a C++ or Python process."""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    output_capped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "output_capped": self.output_capped,
        }


@dataclass
class BuildResult:
    """Result of compiling a C++ program."""
    success: bool
    binary_path: Path | None = None
    compile_error: str | None = None
    flags: list[str] = field(default_factory=list)


class CxxBuildCache:
    """Build cache keyed by SHA-256 of source code and compiler flags."""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        if cache_dir is None:
            self.cache_dir = Path(tempfile.gettempdir()) / "cpp2py_cxx_cache"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_key(self, source_code: str, flags: list[str]) -> str:
        content = source_code + "\n" + " ".join(flags)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Path | None:
        ext = ".exe" if sys.platform == "win32" else ""
        candidate = self.cache_dir / f"{key}{ext}"
        if candidate.exists() and os.access(candidate, os.X_OK | os.R_OK):
            return candidate
        return None

    def put(self, key: str, binary_path: Path) -> Path:
        ext = ".exe" if sys.platform == "win32" else ""
        target = self.cache_dir / f"{key}{ext}"
        if binary_path.resolve() != target.resolve():
            shutil.copy2(binary_path, target)
        return target


def compile_cxx(
    source_code: str,
    overflow_policy: str = "assume_no_overflow",
    extra_flags: list[str] | None = None,
    cache: CxxBuildCache | None = None,
    compiler: str | None = None,
    build_dir: Path | None = None,
) -> BuildResult:
    """Compile C++ source code with g++ -std=c++17 -O0 and policy flags."""
    if compiler is None:
        compiler = os.environ.get("CXX", "g++")

    flags = ["-std=c++17", "-O0"]
    if overflow_policy == "wrap":
        flags.append("-fwrapv")
    elif overflow_policy == "trap":
        flags.append("-ftrapv")
    if sys.platform == "win32":
        flags.append("-D_CPP2PY_WIN32_GUARD=1")

    if extra_flags:
        flags.extend(extra_flags)

    key: str | None = None
    if cache is not None:
        key = cache.compute_key(source_code, flags)
        cached_bin = cache.get(key)
        if cached_bin is not None:
            return BuildResult(success=True, binary_path=cached_bin, flags=flags)

    if build_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="cpp2py_build_"))
    else:
        work_dir = build_dir
        work_dir.mkdir(parents=True, exist_ok=True)

    src_file = work_dir / "program.cpp"
    ext = ".exe" if sys.platform == "win32" else ""
    bin_file = work_dir / f"program{ext}"

    src_file.write_text(source_code, encoding="utf-8")

    cmd = [compiler, *flags]
    if sys.platform == "win32":
        veh_header = work_dir / "_cpp2py_win32_veh.h"
        veh_header.write_text(
            "#if defined(_WIN32)\n"
            "#include <windows.h>\n"
            "namespace {\n"
            "    struct _Cpp2pyVehInit {\n"
            "        static LONG WINAPI _Handler(PEXCEPTION_POINTERS ep) {\n"
            "            if (ep && ep->ExceptionRecord &&\n"
            "                (ep->ExceptionRecord->ExceptionCode == 0xC0000095 || ep->ExceptionRecord->ExceptionCode == 0xC0000094)) {\n"
            "                ExitProcess(ep->ExceptionRecord->ExceptionCode);\n"
            "            }\n"
            "            return EXCEPTION_CONTINUE_SEARCH;\n"
            "        }\n"
            "        _Cpp2pyVehInit() {\n"
            "            AddVectoredExceptionHandler(1, _Handler);\n"
            "        }\n"
            "    } _cpp2py_veh_init;\n"
            "}\n"
            "#endif\n",
            encoding="utf-8",
        )
        cmd.extend(["-include", str(veh_header)])

    cmd.extend([str(src_file), "-o", str(bin_file)])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return BuildResult(success=False, compile_error=str(exc), flags=flags)

    if proc.returncode != 0:
        return BuildResult(
            success=False,
            compile_error=proc.stderr.strip() or f"Compilation failed with exit code {proc.returncode}",
            flags=flags,
        )

    if cache is not None and key is not None:
        final_bin = cache.put(key, bin_file)
        return BuildResult(success=True, binary_path=final_bin, flags=flags)

    return BuildResult(success=True, binary_path=bin_file, flags=flags)


def compile_cxx_ubsan(
    source_code: str,
    overflow_policy: str = "assume_no_overflow",
    cache: CxxBuildCache | None = None,
    compiler: str | None = None,
    build_dir: Path | None = None,
) -> BuildResult:
    """Compile C++ source code with undefined behavior sanitizers."""
    san_flags = [
        "-fsanitize=signed-integer-overflow,integer-divide-by-zero",
        "-fno-sanitize-recover=all",
    ]
    return compile_cxx(
        source_code=source_code,
        overflow_policy=overflow_policy,
        extra_flags=san_flags,
        cache=cache,
        compiler=compiler,
        build_dir=build_dir,
    )


def _get_minimal_env() -> dict[str, str]:
    """Minimal environment for subprocess isolation."""
    env: dict[str, str] = {}
    for var in ("SYSTEMROOT", "PATH", "TEMP", "TMP"):
        if var in os.environ:
            env[var] = os.environ[var]
    return env


def run_cxx(
    binary_path: str | Path,
    stdin_text: str = "",
    timeout: float = 5.0,
    output_cap: int = 1048576,
    cwd: str | Path | None = None,
) -> ExecutionResult:
    """Run a compiled C++ binary under isolated conditions with stdin and resource limits."""
    temp_dir_obj: tempfile.TemporaryDirectory | None = None
    if cwd is None:
        temp_dir_obj = tempfile.TemporaryDirectory()
        run_cwd = Path(temp_dir_obj.name)
    else:
        run_cwd = Path(cwd)

    cmd = [str(binary_path)]
    stdin_bytes = stdin_text.encode("utf-8")

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(run_cwd),
            env=_get_minimal_env(),
        )
        try:
            raw_stdout, raw_stderr = proc.communicate(input=stdin_bytes, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return ExecutionResult(
                stdout="",
                stderr="Execution timed out",
                exit_code=-1,
                timed_out=True,
            )

        capped = False
        if len(raw_stdout) > output_cap:
            raw_stdout = raw_stdout[:output_cap]
            capped = True
        if len(raw_stderr) > output_cap:
            raw_stderr = raw_stderr[:output_cap]
            capped = True

        stdout = raw_stdout.decode("utf-8", errors="replace")
        stderr = raw_stderr.decode("utf-8", errors="replace")

        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            timed_out=False,
            output_capped=capped,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ExecutionResult(
            stdout="",
            stderr=f"Failed to execute binary: {exc}",
            exit_code=-1,
            timed_out=False,
        )
    finally:
        if temp_dir_obj is not None:
            try:
                temp_dir_obj.cleanup()
            except Exception:
                pass
