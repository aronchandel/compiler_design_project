from __future__ import annotations

import re
from pathlib import Path
import pytest

def _get_doc_path() -> Path:
    curr = Path(__file__).resolve().parent
    while curr != curr.parent:
        if (curr / "pyproject.toml").exists():
            return curr / "docs" / "LIMITATIONS.md"
        curr = curr.parent
    return Path("docs/LIMITATIONS.md")

def test_limitations_file_exists() -> None:
    doc_path = _get_doc_path()
    assert doc_path.exists(), f"docs/LIMITATIONS.md does not exist at {doc_path}"

def test_limitations_covers_k3_items() -> None:
    content = _get_doc_path().read_text(encoding="utf-8")
    lower = content.lower()

    assert "subset" in lower
    assert "arrays" in lower or "pointers" in lower
    assert "global" in lower
    assert "intra-procedural" in lower
    assert "interval" in lower
    assert "relational" in lower
    assert "narrowing" in lower
    assert "recursion" in lower
    assert "undefined behaviour" in lower or "undefined behavior" in lower
    assert "equivalence" in lower or "proven" in lower or "tested" in lower

def test_limitations_covers_assumptions_s1_s6() -> None:
    content = _get_doc_path().read_text(encoding="utf-8")
    for s_id in ("S1", "S2", "S3", "S4", "S5", "S6"):
        assert s_id in content, f"Missing assumption {s_id} in docs/LIMITATIONS.md"

def test_limitations_covers_threats_to_validity() -> None:
    content = _get_doc_path().read_text(encoding="utf-8")
    lower = content.lower()
    assert "threats to validity" in lower
    assert "bias" in lower or "generator" in lower
    assert "timing" in lower or "noise" in lower
    assert "shared" in lower or "model" in lower

def test_limitations_cites_result_files() -> None:
    content = _get_doc_path().read_text(encoding="utf-8")
    assert "metrics.json" in content
    assert "tables.md" in content or "tables.csv" in content
    assert "timing.json" in content
    assert "raw.json" in content

def test_limitations_no_hand_typed_statistics() -> None:
    content = _get_doc_path().read_text(encoding="utf-8")

    ALLOWED_NUMBERS = {
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "10", "17", "32", "64",
        "2026", "18", "25",
        "4001", "4002",
    }

    all_numbers = re.findall(r"\b\d+\b", content)
    unauthorized_numbers = [n for n in all_numbers if n not in ALLOWED_NUMBERS]

    assert not unauthorized_numbers, (
        f"docs/LIMITATIONS.md contains unauthorized hand-typed numbers: {unauthorized_numbers}. "
        "All experimental numbers must come from generated result files."
    )
