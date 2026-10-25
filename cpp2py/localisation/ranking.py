"""Additive suspicion ranking for failure localisation.

Conforms to ARCH §I.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cpp2py.source import SourceSpan


@dataclass
class Suspect:
    """A ranked suspect operation."""
    op_id: str
    score: int
    evidence: list[str] = field(default_factory=list)
    span: SourceSpan | None = None
    rank: int = 1
    opcode: str = ""

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "rank": self.rank,
            "op_id": self.op_id,
            "score": self.score,
            "evidence": list(self.evidence),
        }
        if self.opcode:
            res["opcode"] = self.opcode
        if self.span is not None:
            res["span"] = {
                "file": self.span.file,
                "line": self.span.start.line,
                "col": self.span.start.col,
            }
        return res


@dataclass
class RankingWeights:
    """Configurable additive weights for ranking evidence."""
    changed_by_first_divergent_pass: int = 5
    non_none_risk_in_plan: int = 3
    risk_not_none_and_native: int = 4
    depended_on_assumed_range: int = 2
    touched_by_any_pass: int = 1
    slice_distance_base: int = 3  # +max(0, base - d)


def rank_operations(
    slice_ops: dict[str, int],
    first_divergent_pass: str | None = None,
    ops_changed_by_first_pass: list[str] | None = None,
    all_touched_ops: list[str] | None = None,
    plan_dict: dict[str, Any] | None = None,
    op_spans: dict[str, SourceSpan] | None = None,
    op_opcodes: dict[str, str] | None = None,
    weights: RankingWeights | None = None,
    top_k: int = 5,
) -> list[Suspect]:
    """Score and rank candidate operations.

    Default weights follow ARCH §I.2:
      changed by first divergent pass: +5
      non-NONE risk in plan: +3
      risk != NONE and plan chose NATIVE: +4
      depended on assumed range: +2
      slice distance d: +max(0, 3 - d)
      touched by any pass: +1
    """
    if weights is None:
        weights = RankingWeights()

    ops_first_pass = set(ops_changed_by_first_pass or [])
    ops_all_passes = set(all_touched_ops or [])
    spans = op_spans or {}
    opcodes = op_opcodes or {}

    decisions_by_op: dict[str, dict[str, Any]] = {}
    if plan_dict and "decisions" in plan_dict:
        raw_dec = plan_dict["decisions"]
        if isinstance(raw_dec, dict):
            decisions_by_op = raw_dec
        elif isinstance(raw_dec, list):
            decisions_by_op = {d["op_id"]: d for d in raw_dec if "op_id" in d}

    # Candidate operations to consider: all ops in slice plus ops changed by divergent pass
    candidates: set[str] = set(slice_ops.keys()) | ops_first_pass

    # Also include any operation with non-NONE risk in plan
    for op_id, dec in decisions_by_op.items():
        risks = dec.get("risks", [])
        if any(r.upper() != "NONE" for r in risks):
            candidates.add(op_id)

    # If still empty, include all decisions from plan
    if not candidates and decisions_by_op:
        candidates = set(decisions_by_op.keys())

    suspects_map: dict[str, Suspect] = {}

    for op_id in candidates:
        score = 0
        evidence: list[str] = []

        # 1. Changed by first divergent pass (+5)
        if op_id in ops_first_pass:
            score += weights.changed_by_first_divergent_pass
            evidence.append(
                f"changed by first divergent pass ({first_divergent_pass}) (+{weights.changed_by_first_divergent_pass})"
            )

        # Check plan properties
        if op_id in decisions_by_op:
            dec = decisions_by_op[op_id]
            risks = dec.get("risks", [])
            has_risk = bool(risks and any(r.upper() != "NONE" for r in risks))
            action = dec.get("action", "").upper()

            # 2. non-NONE risk in plan (+3)
            if has_risk:
                score += weights.non_none_risk_in_plan
                evidence.append(f"non-NONE risk in plan ({', '.join(risks)}) (+{weights.non_none_risk_in_plan})")

            # 3. risk != NONE and plan chose NATIVE (+4)
            if has_risk and action == "NATIVE":
                score += weights.risk_not_none_and_native
                evidence.append(f"risk != NONE and plan chose NATIVE (+{weights.risk_not_none_and_native})")

            # 4. Depended on assumed range (+2)
            reason = dec.get("reason", "").lower()
            if "assumed" in reason or dec.get("depended_on_assumption", False):
                score += weights.depended_on_assumed_range
                evidence.append(f"depended on assumed range (+{weights.depended_on_assumed_range})")

        # 5. In slice at distance d: +max(0, 3 - d)
        if op_id in slice_ops:
            d = slice_ops[op_id]
            slice_bonus = max(0, weights.slice_distance_base - d)
            if slice_bonus > 0:
                score += slice_bonus
                evidence.append(f"in def-use slice at distance {d} (+{slice_bonus})")
            else:
                evidence.append(f"in def-use slice at distance {d}")

        # 6. Touched by any pass (+1)
        if op_id in ops_all_passes and op_id not in ops_first_pass:
            score += weights.touched_by_any_pass
            evidence.append(f"touched by transformation pass (+{weights.touched_by_any_pass})")

        suspects_map[op_id] = Suspect(
            op_id=op_id,
            score=score,
            evidence=evidence,
            span=spans.get(op_id),
            opcode=opcodes.get(op_id, ""),
        )

    # Sort suspects: score descending, then slice distance ascending, then op_id
    sorted_suspects = sorted(
        suspects_map.values(),
        key=lambda s: (-s.score, slice_ops.get(s.op_id, 999), s.op_id),
    )

    # Assign 1-based ranks
    for idx, s in enumerate(sorted_suspects):
        s.rank = idx + 1

    return sorted_suspects[:top_k]
