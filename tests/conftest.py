import os
import subprocess
import sys
from pathlib import Path
import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig

@pytest.fixture
def run_cli():
    def _run(*args, **kwargs):
        cmd = [sys.executable, "-m", "cpp2py", *args]
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            **kwargs,
        )
    return _run

@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parent.parent
