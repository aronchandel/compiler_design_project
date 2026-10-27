from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cpp2py.analysis.intervals import Interval
from cpp2py.analysis.risk import Risk
from cpp2py.config import CompatMode, OverflowPolicy

class CompatAction(Enum):
    NATIVE = "native"
    HELPER = "helper"

    def __str__(self) -> str:
        return self.value

@dataclass(frozen=True, slots=True)
class CompatDecision:
    op_id: str
    risks: set[Risk]
    action: CompatAction
    helper: str | None
    reason: str
    operand_ranges: tuple[Interval, ...]
    result_range: Interval
    policy: OverflowPolicy
    wrap_int_min_div: bool = False
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_id": self.op_id,
            "action": self.action.value,
            "helper": self.helper,
            "reason": self.reason,
            "wrap_int_min_div": self.wrap_int_min_div,
            "policy": self.policy.value,
            "risks": sorted(r.value for r in self.risks),
            "operand_ranges": [r.to_dict() for r in self.operand_ranges],
            "result_range": self.result_range.to_dict(),
        }

@dataclass
class CompatPlan:
    mode: CompatMode
    policy: OverflowPolicy
    decisions: dict[str, CompatDecision] = field(default_factory=dict)
    assumptions: list[tuple[str, Interval]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "policy": self.policy.value,
            "counts": self.counts,
            "assumptions": [
                {"target": target, "range": r.to_dict()}
                for target, r in sorted(self.assumptions, key=lambda x: x[0])
            ],
            "decisions": {
                op_id: self.decisions[op_id].to_dict()
                for op_id in sorted(self.decisions.keys())
            },
        }
