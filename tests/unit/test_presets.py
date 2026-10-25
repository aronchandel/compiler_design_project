"""Unit tests for evaluation preset configurations (ARCH §J.1, §J.3, AC8.4)."""

from __future__ import annotations

import pytest
from cpp2py.config import CompilerConfig, CompatMode, OverflowPolicy, TargetModel
from cpp2py.evaluation.presets import (
    PRESETS,
    b0_config,
    b1_config,
    e_config,
    get_preset_config,
)


def test_presets_catalogue() -> None:
    """Verify that B0, B1, and E are registered with their respective modes."""
    assert "B0" in PRESETS
    assert "B1" in PRESETS
    assert "E" in PRESETS
    assert PRESETS["B0"] == CompatMode.NAIVE
    assert PRESETS["B1"] == CompatMode.ALWAYS
    assert PRESETS["E"] == CompatMode.RANGE_GUIDED


def test_preset_fairness_default() -> None:
    """AC8.4: Verify that B0, B1, E default configs differ ONLY in compat_mode."""
    c_b0 = b0_config()
    c_b1 = b1_config()
    c_e = e_config()

    # Differ in compat_mode
    assert c_b0.compat_mode == CompatMode.NAIVE
    assert c_b1.compat_mode == CompatMode.ALWAYS
    assert c_e.compat_mode == CompatMode.RANGE_GUIDED

    # Identical in all other attributes
    for c in (c_b0, c_b1, c_e):
        assert c.target == TargetModel()
        assert c.fold_constants is True
        assert c.idiomatic_loops is False
        assert c.assumed_ranges == {}
        assert c.snapshot_dir is None
        assert c.transform_log_path is None
        assert c.ranges_out is None
        assert c.compat_plan_out is None
        assert c.verify_ir_between_passes is True


def test_preset_fairness_custom_target() -> None:
    """Verify that preset fairness holds when configuring custom TargetModel."""
    custom_target = TargetModel(int_bits=32, overflow_policy=OverflowPolicy.WRAP)
    c_b0 = b0_config(target=custom_target)
    c_b1 = b1_config(target=custom_target)
    c_e = e_config(target=custom_target)

    assert c_b0.target == custom_target
    assert c_b1.target == custom_target
    assert c_e.target == custom_target
    assert c_b0.compat_mode != c_b1.compat_mode
    assert c_b1.compat_mode != c_e.compat_mode


def test_preset_fairness_assumed_ranges() -> None:
    """Verify that preset fairness preserves assumed_ranges identically."""
    ranges = {"main.x": [0, 100]}
    c_b0 = b0_config(assumed_ranges=ranges)
    c_b1 = b1_config(assumed_ranges=ranges)
    c_e = e_config(assumed_ranges=ranges)

    assert c_b0.assumed_ranges == ranges
    assert c_b1.assumed_ranges == ranges
    assert c_e.assumed_ranges == ranges


def test_preset_from_base_config() -> None:
    """Verify presets constructed from an existing base config."""
    base = CompilerConfig(
        target=TargetModel(overflow_policy=OverflowPolicy.TRAP),
        fold_constants=False,
        idiomatic_loops=True,
    )
    b0 = get_preset_config("B0", base=base)
    b1 = get_preset_config("B1", base=base)
    e = get_preset_config("E", base=base)

    assert b0.fold_constants is False
    assert b1.fold_constants is False
    assert e.fold_constants is False
    assert b0.idiomatic_loops is True
    assert b1.idiomatic_loops is True
    assert e.idiomatic_loops is True
    assert b0.target.overflow_policy == OverflowPolicy.TRAP
    assert b1.target.overflow_policy == OverflowPolicy.TRAP
    assert e.target.overflow_policy == OverflowPolicy.TRAP


def test_preset_unknown_raises() -> None:
    """Verify that requesting an unregistered preset raises ValueError."""
    with pytest.raises(ValueError, match="Unknown preset"):
        get_preset_config("B2")
