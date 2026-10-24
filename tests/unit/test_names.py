import pytest
from cpp2py.codegen.names import NameMangler


def test_mangler_plain_identifier():
    mangler = NameMangler()
    assert mangler.mangle("my_var") == "my_var"
    assert mangler.mangle("count") == "count"


def test_mangler_python_keywords():
    mangler = NameMangler()
    assert mangler.mangle("lambda") == "lambda_"
    assert mangler.mangle("def") == "def_"
    assert mangler.mangle("pass") == "pass_"


def test_mangler_builtins_and_special():
    mangler = NameMangler()
    assert mangler.mangle("print") == "print_"
    assert mangler.mangle("sys") == "sys_"
    assert mangler.mangle("main") == "main_"
    assert mangler.mangle("_tokens") == "_tokens_"
    assert mangler.mangle("_cpp_div") == "_cpp_div_"


def test_mangler_collision_resolution():
    mangler = NameMangler()
    # First allocate lambda_
    first = mangler.mangle("lambda")
    assert first == "lambda_"
    # Second allocate a C++ variable named lambda_
    second = mangler.mangle("lambda_")
    assert second == "lambda__"


def test_mangler_idempotency_for_same_cxx_name():
    mangler = NameMangler()
    assert mangler.mangle("x") == "x"
    assert mangler.mangle("x") == "x"
