from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cpp2py.source import SourceSpan

@dataclass
class Suspect:
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
    changed_by_first_divergent_pass: int = 5
    non_none_risk_in_plan: int = 3
    risk_not_none_and_native: int = 4
    depended_on_assumed_range: int = 2
    touched_by_any_pass: int = 1
    slice_distance_base: int = 3

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

    candidates: set[str] = set(slice_ops.keys()) | ops_first_pass

    for op_id, dec in decisions_by_op.items():
        risks = dec.get("risks", [])
        if any(r.upper() != "NONE" for r in risks):
            candidates.add(op_id)

    if not candidates and decisions_by_op:
        candidates = set(decisions_by_op.keys())

    suspects_map: dict[str, Suspect] = {}

    for op_id in candidates:
        score = 0
        evidence: list[str] = []

        if op_id in ops_first_pass:
            score += weights.changed_by_first_divergent_pass
            evidence.append(
                f"changed by first divergent pass ({first_divergent_pass}) (+{weights.changed_by_first_divergent_pass})"
            )

        if op_id in decisions_by_op:
            dec = decisions_by_op[op_id]
            risks = dec.get("risks", [])
            has_risk = bool(risks and any(r.upper() != "NONE" for r in risks))
            action = dec.get("action", "").upper()

            if has_risk:
                score += weights.non_none_risk_in_plan
                evidence.append(f"non-NONE risk in plan ({', '.join(risks)}) (+{weights.non_none_risk_in_plan})")

            if has_risk and action == "NATIVE":
                score += weights.risk_not_none_and_native
                evidence.append(f"risk != NONE and plan chose NATIVE (+{weights.risk_not_none_and_native})")

            reason = dec.get("reason", "").lower()
            if "assumed" in reason or dec.get("depended_on_assumption", False):
                score += weights.depended_on_assumed_range
                evidence.append(f"depended on assumed range (+{weights.depended_on_assumed_range})")

        if op_id in slice_ops:
            d = slice_ops[op_id]
            slice_bonus = max(0, weights.slice_distance_base - d)
            if slice_bonus > 0:
                score += slice_bonus
                evidence.append(f"in def-use slice at distance {d} (+{slice_bonus})")
            else:
                evidence.append(f"in def-use slice at distance {d}")

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

    sorted_suspects = sorted(
        suspects_map.values(),
        key=lambda s: (-s.score, slice_ops.get(s.op_id, 999), s.op_id),
    )

    for idx, s in enumerate(sorted_suspects):
        s.rank = idx + 1

    return sorted_suspects[:top_k]
