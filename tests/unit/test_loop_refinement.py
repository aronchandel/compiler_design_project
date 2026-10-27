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

    res_no_assume = compile_and_get_ranges(code)
    assert "_cpp_div" in res_no_assume.python_source

    res_assume = compile_and_get_ranges(code, assumed_ranges={"main.x": Interval(0, 1000)})
    assert "_cpp_div" not in res_assume.python_source
