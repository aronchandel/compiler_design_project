"""Regression persistence for failing differential test cases."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import cpp2py
from cpp2py.testing.comparator import DiffResult
from cpp2py.testing.corpus import TestCase, _find_repo_root
from cpp2py.testing.testgen.programs import GENERATOR_VERSION


def get_default_regression_dir() -> Path:
    """Return default regression directory path (tests/regression)."""
    return _find_repo_root() / "tests" / "regression"


def compute_case_sha8(program_source: str, input_text: str) -> str:
    """Compute 8-character hex SHA-256 for program source and input text."""
    content = program_source + "\n---\n" + input_text
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]


def save_regression_case(
    case: TestCase,
    input_text: str,
    result: DiffResult,
    snapshot_source_dir: Path | None = None,
    regression_base_dir: str | Path | None = None,
    status: str = "open",
    first_seen: str = "2026-10-25",
) -> Path:
    """Persist a failing case to tests/regression/<sha8>/."""
    base_path = Path(regression_base_dir) if regression_base_dir else get_default_regression_dir()
    sha8 = compute_case_sha8(case.program_source, input_text)
    case_dir = base_path / sha8
    case_dir.mkdir(parents=True, exist_ok=True)

    # 1. program.cpp
    (case_dir / "program.cpp").write_text(case.program_source, encoding="utf-8")

    # 2. input.txt
    (case_dir / "input.txt").write_text(input_text, encoding="utf-8")

    # 3. meta.json
    meta_path = case_dir / "meta.json"
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            if existing.get("status") in ("known_limitation", "fixed") and status == "open":
                status = existing["status"]
                if existing.get("notes"):
                    result_notes = existing["notes"]
                else:
                    result_notes = result.reason
            else:
                result_notes = result.reason
        except Exception:
            result_notes = result.reason
    else:
        result_notes = result.reason

    meta: dict[str, Any] = {
        "sha8": sha8,
        "seed": case.seed,
        "generator_version": GENERATOR_VERSION,
        "tool_version": cpp2py.__version__,
        "config": case.config_overrides,
        "outcome": result.outcome.value,
        "first_seen": first_seen,
        "status": status,
        "notes": result_notes,
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # 4. snapshots/
    snap_target = case_dir / "snapshots"
    if snapshot_source_dir is not None and snapshot_source_dir.exists():
        if snap_target.exists():
            shutil.rmtree(snap_target)
        shutil.copytree(snapshot_source_dir, snap_target)
    else:
        snap_target.mkdir(parents=True, exist_ok=True)

    return case_dir


def load_regression_cases(regression_base_dir: str | Path | None = None) -> list[TestCase]:
    """Load all regression test cases from tests/regression/."""
    base_path = Path(regression_base_dir) if regression_base_dir else get_default_regression_dir()
    if not base_path.exists():
        return []

    cases: list[TestCase] = []
    case_dirs = sorted([d for d in base_path.iterdir() if d.is_dir()], key=lambda d: d.name)

    for cdir in case_dirs:
        prog_file = cdir / "program.cpp"
        if not prog_file.exists():
            continue

        program_source = prog_file.read_text(encoding="utf-8")
        in_file = cdir / "input.txt"
        input_text = in_file.read_text(encoding="utf-8") if in_file.exists() else ""

        meta_file = cdir / "meta.json"
        meta: dict[str, Any] = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        cases.append(
            TestCase(
                case_id=f"regression_{cdir.name}",
                program_source=program_source,
                inputs=[input_text],
                origin="regression",
                seed=meta.get("seed"),
                config_overrides=meta.get("config", {}),
                notes=meta.get("notes", ""),
                cpp_path=prog_file,
            )
        )

    return cases
