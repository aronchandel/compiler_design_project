from __future__ import annotations

import random
from typing import Any

from cpp2py.testing.corpus import TestCase
from cpp2py.testing.testgen.inputs import generate_input_stream

GENERATOR_VERSION = "1.0"

_NONZERO_DIVISORS = [1, -1, 2, -2, 3, -3, 5, 7, -7, 10, -10]

def _gen_arith_expr(
    rng: random.Random,
    vars_available: list[str],
    depth: int = 0,
    max_depth: int = 2,
) -> str:
    if depth >= max_depth or (vars_available and rng.random() < 0.4):

        if vars_available and rng.random() < 0.6:
            return rng.choice(vars_available)
        val = rng.choice([0, 1, -1, 2, -2, 3, 5, 10, 42, -42, 100])
        return str(val) if val >= 0 else f"({val})"

    op = rng.choice(["+", "-", "*", "/", "%"])
    left = _gen_arith_expr(rng, vars_available, depth + 1, max_depth)
    if op in ("/", "%"):

        div_val = rng.choice(_NONZERO_DIVISORS)
        right = str(div_val) if div_val >= 0 else f"({div_val})"
    else:
        right = _gen_arith_expr(rng, vars_available, depth + 1, max_depth)

    return f"({left} {op} {right})"

def generate_program_case(
    seed: int,
    case_id: str,
    assumed_ranges: dict[str, tuple[int | None, int | None]] | None = None,
) -> TestCase:
    rng = random.Random(seed)

    lines: list[str] = [
        "#include <iostream>",
        "using namespace std;",
        "",
        "int main() {",
    ]

    var_names = ["a", "b", "c", "x", "y"]
    num_vars = rng.randint(2, len(var_names))
    active_vars = var_names[:num_vars]

    use_long_long = rng.random() < 0.25
    int_vars = active_vars[:-1] if use_long_long else active_vars
    ll_vars = [active_vars[-1]] if use_long_long else []

    if int_vars:
        decl_parts = [f"{v} = {rng.choice([0, 1, -1, 2, 5, 10])}" for v in int_vars]
        lines.append(f"    int {', '.join(decl_parts)};")
    if ll_vars:
        decl_parts = [f"{v} = {rng.choice([10000000000, -10000000000, 42])}" for v in ll_vars]
        lines.append(f"    long long {', '.join(decl_parts)};")

    read_vars: list[str] = []
    if rng.random() < 0.7:
        num_read = rng.randint(1, min(2, len(int_vars)))
        read_vars = int_vars[:num_read]
        lines.append(f"    cin >> {' >> '.join(read_vars)};")

    num_stmts = rng.randint(2, 4)
    for stmt_idx in range(num_stmts):
        stmt_kind = rng.choice(["assign", "assign", "if", "loop"])

        if stmt_kind == "assign":
            target = rng.choice(int_vars)
            expr = _gen_arith_expr(rng, int_vars, depth=0, max_depth=2)
            lines.append(f"    {target} = {expr};")

        elif stmt_kind == "if":
            v1 = rng.choice(int_vars)
            v2 = rng.choice(int_vars)
            cmp_op = rng.choice(["<", "<=", ">", ">=", "==", "!="])
            target = rng.choice(int_vars)
            e1 = _gen_arith_expr(rng, int_vars, depth=1, max_depth=2)
            e2 = _gen_arith_expr(rng, int_vars, depth=1, max_depth=2)
            lines.append(f"    if ({v1} {cmp_op} {v2}) {{")
            lines.append(f"        {target} = {e1};")
            lines.append("    } else {")
            lines.append(f"        {target} = {e2};")
            lines.append("    }")

        elif stmt_kind == "loop":

            bound = rng.randint(2, 5)
            loop_var = f"iter_{stmt_idx}"
            target = rng.choice(int_vars)
            delta = rng.choice([1, -1, 2, -2, 3])
            lines.append(f"    for (int {loop_var} = 0; {loop_var} < {bound}; {loop_var} = {loop_var} + 1) {{")
            lines.append(f"        {target} = {target} + {delta};")
            lines.append("    }")

    for v in active_vars:
        lines.append(f"    cout << {v} << endl;")

    lines.append("    return 0;")
    lines.append("}")
    lines.append("")

    source_code = "\n".join(lines)

    inputs: list[str] = []
    if read_vars:

        for _ in range(rng.randint(1, 3)):
            in_str = generate_input_stream(
                rng,
                num_inputs=len(read_vars),
                assumed_ranges=assumed_ranges,
                var_names=read_vars,
            )
            inputs.append(in_str)
    else:
        inputs = [""]

    config_overrides: dict[str, Any] = {}
    if assumed_ranges:
        config_overrides["assumed_ranges"] = assumed_ranges

    return TestCase(
        case_id=case_id,
        program_source=source_code,
        inputs=inputs,
        origin="generated",
        seed=seed,
        config_overrides=config_overrides,
        notes=f"Generated case with seed {seed}, generator v{GENERATOR_VERSION}",
    )

def generate_suite(
    count: int = 200,
    base_seed: int = 1,
    assumed_ranges: dict[str, tuple[int | None, int | None]] | None = None,
) -> list[TestCase]:
    suite: list[TestCase] = []
    for i in range(count):
        seed = base_seed + i
        case_id = f"gen_seed_{seed}_{i}"
        suite.append(generate_program_case(seed, case_id, assumed_ranges))
    return suite
