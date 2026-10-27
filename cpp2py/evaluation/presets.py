from __future__ import annotations

from typing import Any
from cpp2py.config import CompilerConfig, CompatMode, TargetModel, OverflowPolicy

PRESETS: dict[str, CompatMode] = {
    "B0": CompatMode.NAIVE,
    "B1": CompatMode.ALWAYS,
    "E": CompatMode.RANGE_GUIDED,
}

def get_preset_config(
    preset: str,
    base: CompilerConfig | None = None,
    assumed_ranges: dict[str, Any] | None = None,
    target: TargetModel | None = None,
    snapshot_dir: str | None = None,
    transform_log_path: str | None = None,
) -> CompilerConfig:
    normalized = preset.strip().upper()
    if normalized not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r}; expected one of {list(PRESETS.keys())}")

    compat_mode = PRESETS[normalized]

    if base is not None:
        return CompilerConfig(
            target=target or base.target,
            compat_mode=compat_mode,
            assumed_ranges=assumed_ranges if assumed_ranges is not None else base.assumed_ranges,
            snapshot_dir=snapshot_dir or base.snapshot_dir,
            fold_constants=base.fold_constants,
            idiomatic_loops=base.idiomatic_loops,
            transform_log_path=transform_log_path or base.transform_log_path,
            ranges_out=base.ranges_out,
            compat_plan_out=base.compat_plan_out,
            verify_ir_between_passes=base.verify_ir_between_passes,
        )

    return CompilerConfig(
        target=target or TargetModel(),
        compat_mode=compat_mode,
        assumed_ranges=assumed_ranges or {},
        snapshot_dir=snapshot_dir,
        fold_constants=True,
        idiomatic_loops=False,
        transform_log_path=transform_log_path,
        ranges_out=None,
        compat_plan_out=None,
        verify_ir_between_passes=True,
    )

def b0_config(**kwargs: Any) -> CompilerConfig:
    return get_preset_config("B0", **kwargs)

def b1_config(**kwargs: Any) -> CompilerConfig:
    return get_preset_config("B1", **kwargs)

def e_config(**kwargs: Any) -> CompilerConfig:
    return get_preset_config("E", **kwargs)
