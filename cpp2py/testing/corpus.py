from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class TestCase:
    __test__ = False
    case_id: str
    program_source: str
    inputs: list[str] = field(default_factory=lambda: [""])
    origin: str = "curated"
    seed: int | None = None
    config_overrides: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    expected_stdout: str | None = None
    cpp_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "origin": self.origin,
            "seed": self.seed,
            "config_overrides": self.config_overrides,
            "notes": self.notes,
            "num_inputs": len(self.inputs),
        }

def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()

def load_curated_cases(cases_dir: str | Path | None = None) -> list[TestCase]:
    if cases_dir is None:
        cases_path = _find_repo_root() / "tests" / "differential" / "cases"
    else:
        cases_path = Path(cases_dir)

    if not cases_path.exists():
        return []

    cases: list[TestCase] = []
    case_dirs = sorted([d for d in cases_path.iterdir() if d.is_dir()], key=lambda d: d.name)

    for cdir in case_dirs:
        prog_file = cdir / "program.cpp"
        if not prog_file.exists():
            continue

        program_source = prog_file.read_text(encoding="utf-8")
        meta_file = cdir / "meta.json"
        meta: dict[str, Any] = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        inputs: list[str] = []
        inputs_dir = cdir / "inputs"
        if inputs_dir.exists() and inputs_dir.is_dir():
            in_files = sorted(inputs_dir.glob("*.in"), key=lambda p: p.name)
            for inf in in_files:
                inputs.append(inf.read_text(encoding="utf-8"))

        if not inputs:
            single_in = cdir / "input.txt"
            if single_in.exists():
                inputs.append(single_in.read_text(encoding="utf-8"))
            else:
                inputs.append("")

        cases.append(
            TestCase(
                case_id=cdir.name,
                program_source=program_source,
                inputs=inputs,
                origin="curated",
                seed=meta.get("seed"),
                config_overrides=meta.get("config_overrides", {}),
                notes=meta.get("notes", ""),
                cpp_path=prog_file,
            )
        )

    return cases

def load_example_cases(examples_dir: str | Path | None = None) -> list[TestCase]:
    if examples_dir is None:
        examples_path = _find_repo_root() / "examples"
    else:
        examples_path = Path(examples_dir)

    if not examples_path.exists():
        return []

    cases: list[TestCase] = []
    for cpp_file in sorted(examples_path.rglob("*.cpp"), key=lambda p: str(p)):
        expected_file = cpp_file.with_suffix(".expected")
        if not expected_file.exists():
            continue

        program_source = cpp_file.read_text(encoding="utf-8")
        expected_stdout = expected_file.read_text(encoding="utf-8")

        in_file = cpp_file.with_suffix(".in")
        if in_file.exists():
            stdin_text = in_file.read_text(encoding="utf-8")
        else:
            stdin_text = ""

        rel_id = str(cpp_file.relative_to(examples_path)).replace("\\", "/").replace(".cpp", "")
        case_id = f"example_{rel_id}"

        cases.append(
            TestCase(
                case_id=case_id,
                program_source=program_source,
                inputs=[stdin_text],
                origin="example",
                expected_stdout=expected_stdout,
                cpp_path=cpp_file,
            )
        )

    return cases
