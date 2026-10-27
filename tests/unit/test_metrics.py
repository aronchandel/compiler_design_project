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
    assert compute_agreement_rate(100, 100) == 1.0

def test_agreement_rate_partial() -> None:
    assert compute_agreement_rate(3, 4) == 0.75

def test_agreement_rate_zero_denominator() -> None:
    assert compute_agreement_rate(0, 0) is None
    assert compute_agreement_rate(5, -1) is None

def test_static_metrics_perfect() -> None:
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
    assert res.ratio_e_to_b1 == 0.5

def test_static_metrics_synthetic_hand_computed() -> None:
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
        {"file": "p.cpp", "line": 7, "col": 1, "inserted_helper": False},
        {"file": "p.cpp", "line": 8, "col": 1, "inserted_helper": False},
        {"file": "p.cpp", "line": 9, "col": 1, "inserted_helper": True},
        {"file": "p.cpp", "line": 10, "col": 1, "inserted_helper": True},
    ] + [
        {"file": "p.cpp", "line": 11 + i, "col": 1, "inserted_helper": False} for i in range(10)
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
    res = compute_dynamic_helper_metrics(100, 25)
    assert res.total_executions == 100
    assert res.differs_from_native == 25
    assert res.equals_native == 75
    assert res.empirically_unnecessary_ratio == 0.75
    assert res.label == "empirically unnecessary on this corpus"

def test_dynamic_metrics_zero_executions() -> None:
    res = compute_dynamic_helper_metrics(0, 0)
    assert res.total_executions == 0
    assert res.empirically_unnecessary_ratio is None

def test_soundness_violations_detected() -> None:
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
    results_e = [
        {"case_id": "case_ub", "category": "overflow", "outcome": "MISMATCH_STDOUT", "has_ub": True},
    ]
    results_b1 = [
        {"case_id": "case_ub", "category": "overflow", "outcome": "PASS", "has_ub": True},
    ]
    violations = find_soundness_violations(results_e, results_b1)
    assert len(violations) == 0

def test_mrr_hand_computed() -> None:
    ranks = [1, 2, 4, None]
    mrr = compute_mrr(ranks)
    assert mrr == 0.4375

def test_top_k_hit_rate_hand_computed() -> None:
    ranks = [1, 2, 4, None]
    assert compute_hit_rate(ranks, 1) == 0.25
    assert compute_hit_rate(ranks, 3) == 0.50

def test_localisation_metrics_summary() -> None:
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

    assert loc.mrr == pytest.approx(0.5083, abs=0.001)

def test_timing_stats_hand_computed() -> None:
    samples = [0.10, 0.12, 0.15, 0.20, 0.25]
    stats = compute_timing_stats(samples)
    assert stats.median_seconds == 0.15
    assert stats.min_seconds == 0.10
    assert stats.max_seconds == 0.25
    assert stats.spread_seconds == 0.15
    assert stats.samples == samples
