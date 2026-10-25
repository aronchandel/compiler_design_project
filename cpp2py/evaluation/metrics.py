"""Evaluation metrics per ARCH §J.2.

Provides pure functions and data structures for:
- Agreement rate and denominator accounting
- Static helper precision, recall, and unnecessary helper counts
- Dynamic unnecessary helper ratio
- Soundness violations detection
- Localisation hit rates and Mean Reciprocal Rank (MRR)
- Code size and readability proxies
- Runtime timing aggregation
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StaticHelperMetrics:
    """Metrics comparing helper insertion decisions against ground truth labels."""
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None
    helpers_e: int
    helpers_b1: int
    ratio_e_to_b1: float | None
    unnecessary_helpers_count: int
    unnecessary_sites: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "helpers_e": self.helpers_e,
            "helpers_b1": self.helpers_b1,
            "ratio_e_to_b1": self.ratio_e_to_b1,
            "unnecessary_helpers_count": self.unnecessary_helpers_count,
            "unnecessary_sites": self.unnecessary_sites,
        }


@dataclass(frozen=True)
class DynamicHelperMetrics:
    """Metrics measuring helper executions dynamically."""
    total_executions: int
    differs_from_native: int
    equals_native: int
    empirically_unnecessary_ratio: float | None
    label: str = "empirically unnecessary on this corpus"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_executions": self.total_executions,
            "differs_from_native": self.differs_from_native,
            "equals_native": self.equals_native,
            "empirically_unnecessary_ratio": self.empirically_unnecessary_ratio,
            "label": self.label,
        }


@dataclass(frozen=True)
class SoundnessViolation:
    """An individual case where E mismatches while B1 passes on UB-free input."""
    case_id: str
    category: str
    e_outcome: str
    b1_outcome: str
    details: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "e_outcome": self.e_outcome,
            "b1_outcome": self.b1_outcome,
            "details": self.details,
        }


@dataclass(frozen=True)
class LocalisationMetrics:
    """Evaluation metrics for fault localisation across N seeded faults."""
    n: int
    top1_hits: int
    top1_rate: float
    top3_hits: int
    top3_rate: float
    mrr: float
    fault_ranks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "top1_hits": self.top1_hits,
            "top1_rate": self.top1_rate,
            "top3_hits": self.top3_hits,
            "top3_rate": self.top3_rate,
            "mrr": self.mrr,
            "fault_ranks": self.fault_ranks,
        }


@dataclass(frozen=True)
class TimingStats:
    """Timing stats over N>=5 executions with median and spread."""
    median_seconds: float
    min_seconds: float
    max_seconds: float
    spread_seconds: float
    samples: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "median_seconds": self.median_seconds,
            "min_seconds": self.min_seconds,
            "max_seconds": self.max_seconds,
            "spread_seconds": self.spread_seconds,
            "samples": self.samples,
        }


# --- Pure calculation functions ---

def compute_agreement_rate(numerator: int, denominator: int) -> float | None:
    """Compute agreement rate as numerator / denominator, or None if denominator is 0."""
    if denominator <= 0:
        return None
    return numerator / denominator


def compute_static_helper_metrics(
    eval_decisions: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    helpers_b1_count: int | None = None,
) -> StaticHelperMetrics:
    """Compute precision, recall, F1, unnecessary helper sites and ratios.

    Definitions:
    Ground truth:
      - 'needs_helper' is POSITIVE (helper is required for C++ semantics)
      - 'native_ok' is NEGATIVE (native operator suffices)
    E decision:
      - inserted helper (needs_helper) vs omitted (native_ok)
    TP: E inserted helper AND label is 'needs_helper'
    FP: E inserted helper AND label is 'native_ok' (unnecessary helper!)
    TN: E omitted helper AND label is 'native_ok'
    FN: E omitted helper AND label is 'needs_helper' (soundness risk!)
    """
    # Key labels by (file, line, col)
    label_map: dict[tuple[str, int, int], dict[str, Any]] = {}
    for lbl in labels:
        key = (lbl.get("file", ""), int(lbl.get("line", 0)), int(lbl.get("col", 0)))
        label_map[key] = lbl

    tp = 0
    fp = 0
    tn = 0
    fn = 0
    helpers_e = 0
    unnecessary_sites: list[dict[str, Any]] = []

    for dec in eval_decisions:
        key = (dec.get("file", ""), int(dec.get("line", 0)), int(dec.get("col", 0)))
        inserted = bool(dec.get("inserted_helper", False))
        if inserted:
            helpers_e += 1

        lbl_info = label_map.get(key)
        if lbl_info is None:
            continue

        lbl_val = lbl_info.get("label", "")
        if lbl_val == "needs_helper":
            if inserted:
                tp += 1
            else:
                fn += 1
        elif lbl_val == "native_ok":
            if inserted:
                fp += 1
                unnecessary_sites.append({
                    "file": dec.get("file"),
                    "line": dec.get("line"),
                    "col": dec.get("col"),
                    "op": dec.get("op"),
                    "reason": lbl_info.get("reason", ""),
                })
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if fp == 0 else 0.0)
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    b1_count = helpers_b1_count if helpers_b1_count is not None else (tp + fp + tn + fn)
    ratio_e_to_b1 = (helpers_e / b1_count) if b1_count > 0 else 1.0

    return StaticHelperMetrics(
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        helpers_e=helpers_e,
        helpers_b1=b1_count,
        ratio_e_to_b1=round(ratio_e_to_b1, 4),
        unnecessary_helpers_count=fp,
        unnecessary_sites=unnecessary_sites,
    )


def compute_dynamic_helper_metrics(
    total_executions: int,
    differs_from_native: int,
) -> DynamicHelperMetrics:
    """Compute empirical dynamic unnecessary helper ratio.

    ARCH §J.2: executions where helper result equals native operator ÷ total helper executions.
    """
    if total_executions <= 0:
        return DynamicHelperMetrics(
            total_executions=0,
            differs_from_native=0,
            equals_native=0,
            empirically_unnecessary_ratio=None,
        )

    equals_native = total_executions - differs_from_native
    ratio = equals_native / total_executions
    return DynamicHelperMetrics(
        total_executions=total_executions,
        differs_from_native=differs_from_native,
        equals_native=equals_native,
        empirically_unnecessary_ratio=round(ratio, 4),
    )


def find_soundness_violations(
    results_e: list[dict[str, Any]],
    results_b1: list[dict[str, Any]],
) -> list[SoundnessViolation]:
    """Find all cases where E mismatches but B1 passes on UB-free inputs."""
    b1_by_id: dict[str, dict[str, Any]] = {r["case_id"]: r for r in results_b1}
    violations: list[SoundnessViolation] = []

    for r_e in results_e:
        cid = r_e["case_id"]
        r_b1 = b1_by_id.get(cid)
        if not r_b1:
            continue

        # Skip cases that have UB
        if r_e.get("has_ub", False) or r_b1.get("has_ub", False):
            continue
        if r_e.get("outcome") == "UB_EXCLUDED" or r_b1.get("outcome") == "UB_EXCLUDED":
            continue

        e_mismatch = (r_e.get("outcome") == "MISMATCH_STDOUT" or r_e.get("outcome") == "MISMATCH_EXIT_CODE")
        b1_pass = (r_b1.get("outcome") == "PASS")

        if e_mismatch and b1_pass:
            violations.append(SoundnessViolation(
                case_id=cid,
                category=r_e.get("category", "unknown"),
                e_outcome=r_e.get("outcome", ""),
                b1_outcome=r_b1.get("outcome", ""),
                details=r_e.get("diff_reason", "E diverged while B1 agreed with C++ reference"),
            ))

    return violations


def compute_mrr(ranks: list[int | None]) -> float:
    """Compute Mean Reciprocal Rank (MRR) over ranks (1-based, None if unranked)."""
    if not ranks:
        return 0.0
    reciprocals = [(1.0 / r) if (r is not None and r > 0) else 0.0 for r in ranks]
    return round(sum(reciprocals) / len(ranks), 4)


def compute_hit_rate(ranks: list[int | None], k: int) -> float:
    """Compute Top-k hit rate over ranks (1-based, None if unranked)."""
    if not ranks or k <= 0:
        return 0.0
    hits = sum(1 for r in ranks if (r is not None and 1 <= r <= k))
    return round(hits / len(ranks), 4)


def compute_localisation_metrics(fault_results: list[dict[str, Any]]) -> LocalisationMetrics:
    """Compute localisation summary metrics (Top-1, Top-3, MRR, N)."""
    n = len(fault_results)
    ranks: list[int | None] = [f.get("rank") for f in fault_results]

    top1_rate = compute_hit_rate(ranks, 1)
    top3_rate = compute_hit_rate(ranks, 3)
    mrr = compute_mrr(ranks)

    top1_hits = sum(1 for r in ranks if r == 1)
    top3_hits = sum(1 for r in ranks if r is not None and 1 <= r <= 3)

    return LocalisationMetrics(
        n=n,
        top1_hits=top1_hits,
        top1_rate=top1_rate,
        top3_hits=top3_hits,
        top3_rate=top3_rate,
        mrr=mrr,
        fault_ranks=fault_results,
    )


def compute_timing_stats(times: list[float]) -> TimingStats:
    """Compute median, min, max, spread from execution times (N>=5)."""
    if not times:
        return TimingStats(0.0, 0.0, 0.0, 0.0, [])
    med = float(statistics.median(times))
    min_t = float(min(times))
    max_t = float(max(times))
    spread = float(max_t - min_t)
    return TimingStats(
        median_seconds=round(med, 6),
        min_seconds=round(min_t, 6),
        max_seconds=round(max_t, 6),
        spread_seconds=round(spread, 6),
        samples=[round(t, 6) for t in times],
    )
