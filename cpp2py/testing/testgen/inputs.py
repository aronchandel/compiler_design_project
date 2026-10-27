from __future__ import annotations

import random

INT_MAX_32 = 2147483647
INT_MIN_32 = -2147483648

BOUNDARY_VALUES: list[int] = [
    0,
    1,
    -1,
    2,
    -2,
    3,
    -3,
    7,
    -7,
    10,
    -10,
    100,
    -100,
    INT_MAX_32,
    INT_MAX_32 - 1,
    INT_MIN_32,
    INT_MIN_32 + 1,
]

def generate_input_value(
    rng: random.Random,
    assumed_range: tuple[int | None, int | None] | None = None,
) -> int:
    lo = assumed_range[0] if assumed_range is not None and assumed_range[0] is not None else INT_MIN_32
    hi = assumed_range[1] if assumed_range is not None and assumed_range[1] is not None else INT_MAX_32

    valid_boundaries = [v for v in BOUNDARY_VALUES if lo <= v <= hi]
    if lo not in valid_boundaries and lo >= INT_MIN_32:
        valid_boundaries.append(lo)
    if hi not in valid_boundaries and hi <= INT_MAX_32:
        valid_boundaries.append(hi)
    mid = (lo + hi) // 2
    if mid not in valid_boundaries:
        valid_boundaries.append(mid)

    if valid_boundaries and rng.random() < 0.6:
        return rng.choice(valid_boundaries)

    safe_lo = max(lo, -10000)
    safe_hi = min(hi, 10000)
    if safe_lo <= safe_hi:
        return rng.randint(safe_lo, safe_hi)
    return rng.randint(lo, hi)

def generate_input_stream(
    rng: random.Random,
    num_inputs: int,
    assumed_ranges: dict[str, tuple[int | None, int | None]] | None = None,
    var_names: list[str] | None = None,
) -> str:
    tokens: list[str] = []
    assumed = assumed_ranges or {}

    for i in range(num_inputs):
        var_name = var_names[i] if var_names and i < len(var_names) else None
        rng_spec = assumed.get(var_name) if var_name else None
        val = generate_input_value(rng, rng_spec)
        tokens.append(str(val))

    if not tokens:
        return ""
    return " ".join(tokens) + "\n"
