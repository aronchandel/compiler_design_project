"""Unit tests for cpp2py/localisation/ranking.py.

Verifies additive scoring weights and suspect ranking on hand-computed expectations.
"""

from __future__ import annotations

import pytest

from cpp2py.localisation.ranking import RankingWeights, rank_operations
from cpp2py.source import Pos, SourceSpan


def test_additive_scoring_hand_computed():
    slice_ops = {
        "op_output": 0,
        "op_A": 1,
        "op_B": 0,
        "op_C": 2,
        "op_D": 4,
    }

    # Op A: changed by first divergent pass (+5), slice d=1 (+2) -> score 7
    # Op B: non-NONE risk in plan (+3), risk!=NONE & chose NATIVE (+4), slice d=0 (+3) -> score 10
    # Op C: slice d=2 (+1), touched by any pass (+1) -> score 2
    # Op D: slice d=4 (+0) -> score 0

    first_pass = "constant_fold"
    ops_changed = ["op_A"]
    all_touched = ["op_A", "op_C"]

    plan = {
        "decisions": [
            {
                "op_id": "op_B",
                "action": "NATIVE",
                "risks": ["DIV_TRUNC_DIFFERS"],
                "reason": "optimistic",
            }
        ]
    }

    spans = {
        "op_B": SourceSpan("test.cpp", Pos(5, 5, 0), Pos(5, 15, 0)),
    }

    suspects = rank_operations(
        slice_ops=slice_ops,
        first_divergent_pass=first_pass,
        ops_changed_by_first_pass=ops_changed,
        all_touched_ops=all_touched,
        plan_dict=plan,
        op_spans=spans,
        top_k=5,
    )

    assert len(suspects) >= 4
    # Top 1 must be op_B with score 10
    assert suspects[0].op_id == "op_B"
    assert suspects[0].score == 10
    assert suspects[0].rank == 1
    assert suspects[0].span is not None

    # Top 2 must be op_A with score 7
    assert suspects[1].op_id == "op_A"
    assert suspects[1].score == 7
    assert suspects[1].rank == 2

    # Top 3 must be op_output (slice d=0 -> +3)
    assert suspects[2].op_id == "op_output"
    assert suspects[2].score == 3
    assert suspects[2].rank == 3

    # Top 4 must be op_C with score 2
    assert suspects[3].op_id == "op_C"
    assert suspects[3].score == 2
    assert suspects[3].rank == 4
