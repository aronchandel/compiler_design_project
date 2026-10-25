"""Unit tests for fault injection catalogue and context manager safety (ARCH §J.4)."""

from __future__ import annotations

import pytest
import cpp2py.compat.helpers as helpers_mod
import cpp2py.compat.policy as policy_mod
import cpp2py.codegen.python_gen as pygen_mod
import cpp2py.transforms.constant_fold as fold_mod
import cpp2py.ir.builder as builder_mod
from cpp2py.analysis.intervals import Interval
from cpp2py.evaluation.faults import (
    FAULTS,
    patch_f01_floor_div,
    patch_f02_mod_plan_native,
    patch_f03_generator_mod,
    patch_f04_builder_swap_sub,
    patch_f05_fold_mul_as_add,
    patch_f06_generator_div,
    patch_f07_builder_swap_div,
    patch_f08_builder_swap_mod,
    patch_f09_fold_sub_as_add,
    patch_f10_div_plan_native,
    patch_f11_wrap_off_by_one,
    patch_f12_widening_error,
)


def test_catalogue_minimum_count() -> None:
    """Verify that FAULTS catalogue contains >= 10 faults per specification."""
    assert len(FAULTS) >= 10
    ids = [f.id for f in FAULTS]
    assert len(ids) == len(set(ids)), f"Duplicate fault IDs: {ids}"


def test_fault_structure_complete() -> None:
    """Verify that every fault definition has all required fields."""
    for f in FAULTS:
        assert f.id.startswith("F")
        assert len(f.name) > 0
        assert len(f.description) > 0
        assert f.expected_stage in ("after_constant_fold", "codegen_or_plan", "ir_generation")
        assert f.expected_suspect_opcode in ("div", "mod", "sub", "mul")
        assert "#include <iostream>" in f.sample_program
        assert len(f.expected_cxx_output) > 0
        assert callable(f.patch_manager)


def test_fault_restore_on_normal_exit() -> None:
    """Verify that context manager restores original attribute on normal exit."""
    orig_fold_run = fold_mod.ConstantFoldPass.run
    with patch_f01_floor_div():
        assert fold_mod.ConstantFoldPass.run != orig_fold_run
    assert fold_mod.ConstantFoldPass.run == orig_fold_run


def test_fault_restore_on_exception() -> None:
    """Verify that context manager restores original attribute even when an exception is raised."""
    orig_decide = policy_mod.decide
    with pytest.raises(RuntimeError, match="deliberate failure"):
        with patch_f02_mod_plan_native():
            assert policy_mod.decide != orig_decide
            raise RuntimeError("deliberate failure")
    assert policy_mod.decide == orig_decide


def test_fault_restore_all_context_managers() -> None:
    """Verify attribute restoration across all 12 fault context managers."""
    # F03
    orig_mod_build = pygen_mod.IRToPythonGenerator._build_ast_for_instr
    with patch_f03_generator_mod():
        assert pygen_mod.IRToPythonGenerator._build_ast_for_instr != orig_mod_build
    assert pygen_mod.IRToPythonGenerator._build_ast_for_instr == orig_mod_build

    # F04
    orig_sub_lower = builder_mod.IRBuilder._lower_expr
    with patch_f04_builder_swap_sub():
        assert builder_mod.IRBuilder._lower_expr != orig_sub_lower
    assert builder_mod.IRBuilder._lower_expr == orig_sub_lower

    # F05
    orig_mul_run = fold_mod.ConstantFoldPass.run
    with patch_f05_fold_mul_as_add():
        assert fold_mod.ConstantFoldPass.run != orig_mul_run
    assert fold_mod.ConstantFoldPass.run == orig_mul_run

    # F06
    orig_div_build = pygen_mod.IRToPythonGenerator._build_ast_for_instr
    with patch_f06_generator_div():
        assert pygen_mod.IRToPythonGenerator._build_ast_for_instr != orig_div_build
    assert pygen_mod.IRToPythonGenerator._build_ast_for_instr == orig_div_build

    # F07
    orig_div_lower = builder_mod.IRBuilder._lower_expr
    with patch_f07_builder_swap_div():
        assert builder_mod.IRBuilder._lower_expr != orig_div_lower
    assert builder_mod.IRBuilder._lower_expr == orig_div_lower

    # F08
    orig_mod_lower = builder_mod.IRBuilder._lower_expr
    with patch_f08_builder_swap_mod():
        assert builder_mod.IRBuilder._lower_expr != orig_mod_lower
    assert builder_mod.IRBuilder._lower_expr == orig_mod_lower

    # F09
    orig_sub_run = fold_mod.ConstantFoldPass.run
    with patch_f09_fold_sub_as_add():
        assert fold_mod.ConstantFoldPass.run != orig_sub_run
    assert fold_mod.ConstantFoldPass.run == orig_sub_run

    # F10
    orig_div_decide = policy_mod.decide
    with patch_f10_div_plan_native():
        assert policy_mod.decide != orig_div_decide
    assert policy_mod.decide == orig_div_decide

    # F11
    orig_wrap = helpers_mod._wrap_i32
    with patch_f11_wrap_off_by_one():
        assert helpers_mod._wrap_i32 != orig_wrap
    assert helpers_mod._wrap_i32 == orig_wrap

    # F12
    orig_widen = Interval.widen_to_type_bounds
    with patch_f12_widening_error():
        assert Interval.widen_to_type_bounds != orig_widen
    assert Interval.widen_to_type_bounds == orig_widen
