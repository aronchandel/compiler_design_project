"""Evaluation package for cpp2py (Phase 8).

Implements preset configurations, evaluation metrics, experiments runner,
fault injection catalogue for failure localisation, and table reporting.
"""

from __future__ import annotations

__all__ = [
    "PRESETS",
    "get_preset_config",
]

from cpp2py.evaluation.presets import PRESETS, get_preset_config
