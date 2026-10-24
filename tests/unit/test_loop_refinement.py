"""Unit tests for loop range analysis, widening and branch refinement."""

import pytest
from cpp2py.compiler import compile_source
from cpp2py.config import CompilerConfig, CompatMode
from cpp2py.analysis.intervals import Interval


def compile_and_get_ranges(code: str, assumed_ranges: dict | None = None):
    config = CompilerConfig(
        compat_mode=CompatMode.RANGE_GUIDED,
        assumed_ranges=assumed_ranges or {},
    )
    res = compile_source(code, "test.cpp", config)
    assert res.success, f"Compilation failed: {[d.message for d in res.diagnostics.errors]}"
    return res


def test_loop_counter_increment():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int sum = 0;
        for (int i = 0; i < 10; ++i) {
            sum += i;
        }
        cout << sum << endl;
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    # Range guided output shouldn't use any helpers since counters are non-negative
    assert "_cpp_" not in res.python_source


def test_loop_counter_decrement():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int i = 10;
        while (i > 0) {
            i = i - 1;
        }
        cout << i << endl;
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    assert "_cpp_" not in res.python_source


def test_loop_widening_termination():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int i = 0;
        int n;
        cin >> n;
        while (i < n) {
            i += 1;
        }
        cout << i << endl;
        return 0;
    }
    """
    # Should converge without error
    res = compile_and_get_ranges(code)
    assert res.success


def test_branch_refinement_greater_equal():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        if (x >= 0) {
            cout << x / 2 << endl;
        }
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    # In then branch, x >= 0 and divisor 2 >= 1, so no helper needed for x / 2!
    assert "_cpp_div" not in res.python_source


def test_branch_refinement_greater_than():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        if (x > 5) {
            cout << x / 3 << endl;
        }
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    assert "_cpp_div" not in res.python_source


def test_branch_refinement_less_than():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        if (x < 0) {
            cout << x / 2 << endl;
        }
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    # In then branch, x < 0, so x / 2 requires _cpp_div!
    assert "_cpp_div" in res.python_source


def test_branch_refinement_less_equal():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        if (x <= -1) {
            cout << x / 2 << endl;
        }
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    assert "_cpp_div" in res.python_source


def test_branch_refinement_equality():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        if (x == 42) {
            cout << x / 6 << endl;
        }
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    # x == 42 is positive, no helper needed
    assert "_cpp_div" not in res.python_source


def test_branch_refinement_not_equal():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        if (x != 0) {
            cout << 100 / x << endl;
        }
        return 0;
    }
    """
    res = compile_and_get_ranges(code)
    # x != 0 means x can still be negative, so 100 / x needs helper
    assert "_cpp_div" in res.python_source


def test_dead_branch_no_crash():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x = 10;
        if (x < 0) {
            cout << 100 / 0 << endl;
        }
        return 0;
    }
    """
    # Dead branch x < 0 when x = 10
    res = compile_and_get_ranges(code)
    assert res.success


def test_assumed_range_eliminates_helper():
    code = """
    #include <iostream>
    using namespace std;
    int main() {
        int x;
        cin >> x;
        cout << x / 2 << endl;
        return 0;
    }
    """
    # Without assumption: needs helper
    res_no_assume = compile_and_get_ranges(code)
    assert "_cpp_div" in res_no_assume.python_source

    # With assumption x in [0, 1000]: no helper needed!
    res_assume = compile_and_get_ranges(code, assumed_ranges={"main.x": Interval(0, 1000)})
    assert "_cpp_div" not in res_assume.python_source
