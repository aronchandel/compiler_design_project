"""Unit tests for evaluation metrics on synthetic inputs with hand-computed expectations (AC8.8)."""

from __future__ import annotations

import pytest
from cpp2py.evaluation.metrics import (
    DynamicHelperMetrics,
    LocalisationMetrics,
    SoundnessViolation,
    StaticHelperMetrics,
    TimingStats,
    compute_agreement_rate,
    compute_dynamic_helper_metrics,
    compute_hit_rate,
    compute_localisation_metrics,
    compute_mrr,
    compute_static_helper_metrics,
    compute_timing_stats,
    find_soundness_violations,
)


def test_agreement_rate_perfect() -> None:
    """Hand-computed: 100/100 -> 1.0."""
    assert compute_agreement_rate(100, 100) == 1.0


def test_agreement_rate_partial() -> None:
    """Hand-computed: 3 / 4 -> 0.75."""
    assert compute_agreement_rate(3, 4) == 0.75


def test_agreement_rate_zero_denominator() -> None:
    """Hand-computed: 0 denominator returns None."""
    assert compute_agreement_rate(0, 0) is None
    assert compute_agreement_rate(5, -1) is None


def test_static_metrics_perfect() -> None:
    """Hand-computed: 10 TP, 10 TN -> precision 1.0, recall 1.0, F1 1.0, 0 unnecessary."""
    labels = []
    decisions = []
    for i in range(10):
        labels.append({"file": "a.cpp", "line": i + 1, "col": 1, "label": "needs_helper", "reason": ""})
        decisions.append({"file": "a.cpp", "line": i + 1, "col": 1, "inserted_helper": True})
    for i in range(10, 20):
        labels.append({"file": "a.cpp", "line": i + 1, "col": 1, "label": "native_ok", "reason": ""})
        decisions.append({"file": "a.cpp", "line": i + 1, "col": 1, "inserted_helper": False})

    res = compute_static_helper_metrics(decisions, labels, helpers_b1_count=20)
    assert res.tp == 10
    assert res.fp == 0
    assert res.tn == 10
    assert res.fn == 0
    assert res.precision == 1.0
    assert res.recall == 1.0
    assert res.f1 == 1.0
    assert res.unnecessary_helpers_count == 0
    assert res.ratio_e_to_b1 == 0.5  # 10 / 20


def test_static_metrics_synthetic_hand_computed() -> None:
    """Hand-computed synthetic contingency table:
    Ground truth:
      - 8 sites 'needs_helper'
      - 12 sites 'native_ok'
    E decisions:
      - For 6 'needs_helper': inserted helper -> TP = 6
      - For 2 'needs_helper': omitted helper -> FN = 2
      - For 2 'native_ok': inserted helper -> FP = 2
      - For 10 'native_ok': omitted helper -> TN = 10

    Calculations:
      Precision = TP / (TP + FP) = 6 / (6 + 2) = 6/8 = 0.75
      Recall    = TP / (TP + FN) = 6 / (6 + 2) = 6/8 = 0.75
      F1        = 2 * (0.75 * 0.75) / (0.75 + 0.75) = 0.75
      Unnecessary helpers = FP = 2
      Ratio E / B1 = (6 + 2) / 20 = 8 / 20 = 0.40
    """
    labels = [
        {"file": "p.cpp", "line": 1, "col": 1, "label": "needs_helper", "reason": "r"},
        {"file": "p.cpp", "line": 2, "col": 1, "label": "needs_helper", "reason": "r"},
        {"file": "p.cpp", "line": 3, "col": 1, "label": "needs_helper", "reason": "r"},
        {"file": "p.cpp", "line": 4, "col": 1, "label": "needs_helper", "reason": "r"},
        {"file": "p.cpp", "line": 5, "col": 1, "label": "needs_helper", "reason": "r"},
        {"file": "p.cpp", "line": 6, "col": 1, "label": "needs_helper", "reason": "r"},
        {"file": "p.cpp", "line": 7, "col": 1, "label": "needs_helper", "reason": "r"},
        {"file": "p.cpp", "line": 8, "col": 1, "label": "needs_helper", "reason": "r"},
    ] + [
        {"file": "p.cpp", "line": 9 + i, "col": 1, "label": "native_ok", "reason": "safe"} for i in range(12)
    ]

    decisions = [
        {"file": "p.cpp", "line": 1, "col": 1, "inserted_helper": True},
        {"file": "p.cpp", "line": 2, "col": 1, "inserted_helper": True},
        {"file": "p.cpp", "line": 3, "col": 1, "inserted_helper": True},
        {"file": "p.cpp", "line": 4, "col": 1, "inserted_helper": True},
        {"file": "p.cpp", "line": 5, "col": 1, "inserted_helper": True},
        {"file": "p.cpp", "line": 6, "col": 1, "inserted_helper": True},
        {"file": "p.cpp", "line": 7, "col": 1, "inserted_helper": False},  # FN
        {"file": "p.cpp", "line": 8, "col": 1, "inserted_helper": False},  # FN
        {"file": "p.cpp", "line": 9, "col": 1, "inserted_helper": True},   # FP
        {"file": "p.cpp", "line": 10, "col": 1, "inserted_helper": True},  # FP
    ] + [
        {"file": "p.cpp", "line": 11 + i, "col": 1, "inserted_helper": False} for i in range(10)  # TN
    ]

    res = compute_static_helper_metrics(decisions, labels, helpers_b1_count=20)
    assert res.tp == 6
    assert res.fn == 2
    assert res.fp == 2
    assert res.tn == 10
    assert res.precision == 0.75
    assert res.recall == 0.75
    assert res.f1 == 0.75
    assert res.unnecessary_helpers_count == 2
    assert len(res.unnecessary_sites) == 2
    assert res.ratio_e_to_b1 == 0.4


def test_dynamic_metrics_hand_computed() -> None:
    """Hand-computed:
    Total helper executions = 100
    Executions differing from native operator = 25
    Executions equal to native operator = 75
    Empirically unnecessary ratio = 75 / 100 = 0.75
    """
    res = compute_dynamic_helper_metrics(100, 25)
    assert res.total_executions == 100
    assert res.differs_from_native == 25
    assert res.equals_native == 75
    assert res.empirically_unnecessary_ratio == 0.75
    assert res.label == "empirically unnecessary on this corpus"


def test_dynamic_metrics_zero_executions() -> None:
    """Hand-computed: 0 total executions gives None ratio."""
    res = compute_dynamic_helper_metrics(0, 0)
    assert res.total_executions == 0
    assert res.empirically_unnecessary_ratio is None


def test_soundness_violations_detected() -> None:
    """AC8.6: E mismatches while B1 passes on UB-free input -> flagged as soundness violation."""
    results_e = [
        {"case_id": "case1", "category": "div", "outcome": "MISMATCH_STDOUT", "has_ub": False},
        {"case_id": "case2", "category": "mod", "outcome": "PASS", "has_ub": False},
    ]
    results_b1 = [
        {"case_id": "case1", "category": "div", "outcome": "PASS", "has_ub": False},
        {"case_id": "case2", "category": "mod", "outcome": "PASS", "has_ub": False},
    ]
    violations = find_soundness_violations(results_e, results_b1)
    assert len(violations) == 1
    assert violations[0].case_id == "case1"
    assert violations[0].category == "div"


def test_soundness_violations_ignored_on_ub() -> None:
    """Cases with undefined behaviour are excluded from soundness violation list."""
    results_e = [
        {"case_id": "case_ub", "category": "overflow", "outcome": "MISMATCH_STDOUT", "has_ub": True},
    ]
    results_b1 = [
        {"case_id": "case_ub", "category": "overflow", "outcome": "PASS", "has_ub": True},
    ]
    violations = find_soundness_violations(results_e, results_b1)
    assert len(violations) == 0


def test_mrr_hand_computed() -> None:
    """Hand-computed MRR:
    Ranks: [1, 2, 4, None]
    Reciprocal ranks: [1/1, 1/2, 1/4, 0] = [1.0, 0.5, 0.25, 0.0]
    Sum = 1.75
    MRR = 1.75 / 4 = 0.4375
    """
    ranks = [1, 2, 4, None]
    mrr = compute_mrr(ranks)
    assert mrr == 0.4375


def test_top_k_hit_rate_hand_computed() -> None:
    """Hand-computed Hit Rates:
    Ranks: [1, 2, 4, None]
    N = 4
    Top-1: rank == 1 -> [1] -> 1/4 = 0.25
    Top-3: rank <= 3 -> [1, 2] -> 2/4 = 0.50
    """
    ranks = [1, 2, 4, None]
    assert compute_hit_rate(ranks, 1) == 0.25
    assert compute_hit_rate(ranks, 3) == 0.50


def test_localisation_metrics_summary() -> None:
    """Verify compute_localisation_metrics on structured fault results."""
    fault_results = [
        {"id": "F1", "rank": 1},
        {"id": "F2", "rank": 2},
        {"id": "F3", "rank": 3},
        {"id": "F4", "rank": 5},
    ]
    loc = compute_localisation_metrics(fault_results)
    assert loc.n == 4
    assert loc.top1_hits == 1
    assert loc.top1_rate == 0.25
    assert loc.top3_hits == 3
    assert loc.top3_rate == 0.75
    # Reciprocal ranks: 1.0 + 0.5 + 0.333333 + 0.2 = 2.033333 / 4 = 0.5083
    assert loc.mrr == pytest.approx(0.5083, abs=0.001)


def test_timing_stats_hand_computed() -> None:
    """Hand-computed:
    Samples: [0.10, 0.12, 0.15, 0.20, 0.25]
    Median: 0.15
    Min: 0.10
    Max: 0.25
    Spread: 0.25 - 0.10 = 0.15
    """
    samples = [0.10, 0.12, 0.15, 0.20, 0.25]
    stats = compute_timing_stats(samples)
    assert stats.median_seconds == 0.15
    assert stats.min_seconds == 0.10
    assert stats.max_seconds == 0.25
    assert stats.spread_seconds == 0.15
    assert stats.samples == samples
