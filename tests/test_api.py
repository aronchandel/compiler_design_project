from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)

HELLO_WORLD = """\
int main() {
    int x = 42;
    return 0;
}
"""

SIMPLE_ARITHMETIC = """\
int add(int a, int b) {
    return a + b;
}

int main() {
    int result = add(3, 4);
    return 0;
}
"""

UNSUPPORTED_TEMPLATES = """\
template<typename T>
T identity(T x) {
    return x;
}
int main() {
    return identity<int>(0);
}
"""

class TestHealth:
    def test_health_returns_200(self):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_health_schema(self):
        r = client.get("/api/health")
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_seconds" in data
        assert data["service"] == "cpp2py"

    def test_health_uptime_is_non_negative(self):
        r = client.get("/api/health")
        assert r.json()["uptime_seconds"] >= 0

class TestTranslateSuccess:
    def test_translate_hello_world(self):
        r = client.post("/api/translate", json={"source_code": HELLO_WORLD})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["python_source"] is not None
        assert len(data["python_source"]) > 0
        assert "diagnostics" in data

    def test_translate_simple_arithmetic(self):
        r = client.post("/api/translate", json={"source_code": SIMPLE_ARITHMETIC})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "def add" in data["python_source"] or "add" in data["python_source"]

    def test_translate_returns_duration(self):
        r = client.post("/api/translate", json={"source_code": HELLO_WORLD})
        data = r.json()
        assert data["duration_ms"] >= 0

    def test_translate_returns_line_counts(self):
        r = client.post("/api/translate", json={"source_code": HELLO_WORLD})
        data = r.json()
        assert data["line_count_cpp"] is not None
        assert data["line_count_cpp"] > 0

    def test_translate_compat_modes(self):
        for compat in ("naive", "always", "range_guided"):
            r = client.post("/api/translate", json={
                "source_code": HELLO_WORLD,
                "compat": compat,
            })
            assert r.status_code == 200, f"Failed for compat={compat}"

    def test_translate_overflow_policies(self):
        for policy in ("assume_no_overflow", "wrap", "trap"):
            r = client.post("/api/translate", json={
                "source_code": HELLO_WORLD,
                "overflow": policy,
            })
            assert r.status_code == 200, f"Failed for overflow={policy}"

    def test_translate_no_fabrication(self):
        r = client.post("/api/translate", json={"source_code": UNSUPPORTED_TEMPLATES})
        data = r.json()

        if not data["success"]:
            assert data["python_source"] is None
            assert data["error_count"] > 0

    def test_translate_function_count(self):
        r = client.post("/api/translate", json={"source_code": SIMPLE_ARITHMETIC})
        data = r.json()
        if data["success"]:
            assert data["function_count"] is not None
            assert data["function_count"] >= 1

    def test_translate_case_a_constant_arithmetic(self):
        code = """#include <iostream>
int main() {
    int x = 3 * 4 + 2;
    std::cout << x;
    return 0;
}"""
        r = client.post("/api/translate", json={"source_code": code, "fold_constants": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "x = 14" in data["python_source"]
        # Also run it through execute endpoint
        run_res = client.post("/api/execute", json={"python_source": data["python_source"]})
        assert run_res.status_code == 200
        assert run_res.json()["stdout"].strip() == "14"

    def test_translate_case_b_enabled_vs_disabled(self):
        code = """#include <iostream>
int main() {
    int x = 3 * 4 + 2;
    std::cout << x;
    return 0;
}"""
        r_on = client.post("/api/translate", json={"source_code": code, "fold_constants": True})
        r_off = client.post("/api/translate", json={"source_code": code, "fold_constants": False})
        assert r_on.status_code == 200 and r_off.status_code == 200
        data_on = r_on.json()
        data_off = r_off.json()
        assert data_on["success"] is True and data_off["success"] is True

        # Enabled performs IR transformation and emits folded constant
        assert "x = 14" in data_on["python_source"]
        assert "assign 14" in data_on["ir_source"]

        # Disabled preserves operations in both IR and Python
        assert "x = 3 * 4 + 2" in data_off["python_source"]
        assert "mul 3, 4" in data_off["ir_source"]
        assert "add" in data_off["ir_source"]

    def test_translate_case_c_nonconstant_expression(self):
        code = """#include <iostream>
int main() {
    int a;
    std::cin >> a;
    int x = a * 4 + 2;
    std::cout << x;
    return 0;
}"""
        r = client.post("/api/translate", json={"source_code": code, "fold_constants": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        # Runtime-dependent expression must NOT be replaced with a constant
        assert "a * 4 + 2" in data["python_source"]
        # Run with runtime input 5: 5 * 4 + 2 = 22
        run_res = client.post("/api/execute", json={"python_source": data["python_source"], "stdin": "5\n"})
        assert run_res.status_code == 200
        assert run_res.json()["stdout"].strip() == "22"

    def test_translate_case_d_overflow_sensitive(self):
        code = """#include <iostream>
int main() {
    int x = 2147483647 + 1;
    std::cout << x;
    return 0;
}"""
        r = client.post("/api/translate", json={"source_code": code, "overflow": "wrap", "fold_constants": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        # Warning emitted because folding skipped on overflow
        assert any(d["code"] == "W6004" for d in data["diagnostics"])
        # Preserves wrap compatibility helper
        assert "_wrap_i32" in data["python_source"]
        # Runtime execution produces wrapped two's-complement value
        run_res = client.post("/api/execute", json={"python_source": data["python_source"]})
        assert run_res.status_code == 200
        assert run_res.json()["stdout"].strip() == "-2147483648"

    def test_translate_constant_folding_enabled(self):
        code = "int main() { int x = 2 + 3; return x; }"
        r = client.post("/api/translate", json={"source_code": code, "fold_constants": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "x = 5" in data["python_source"]
        assert "2 + 3" not in data["python_source"]
        assert data["ir_source"] is not None
        assert "assign 5" in data["ir_source"]

    def test_translate_constant_folding_disabled(self):
        code = "int main() { int x = 2 + 3; return x; }"
        r = client.post("/api/translate", json={"source_code": code, "fold_constants": False})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "x = 2 + 3" in data["python_source"]
        assert data["ir_source"] is not None
        assert "add 2, 3" in data["ir_source"]

    def test_translate_constant_folding_complex_arithmetic(self):
        code = "int main() { int x = (2 + 3) * (10 - 6) / 2; return x; }"
        r = client.post("/api/translate", json={"source_code": code, "fold_constants": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "x = 10" in data["python_source"]

    def test_translate_constant_folding_div_zero_preserved(self):
        code = "int main() { int x = 10 / 0; return x; }"
        r = client.post("/api/translate", json={"source_code": code, "fold_constants": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert any(d["code"] == "W6004" for d in data["diagnostics"])

    def test_translate_constant_folding_overflow_preserved(self):
        code = "int main() { int x = 2147483647 + 1; return x; }"
        r = client.post("/api/translate", json={"source_code": code, "fold_constants": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert any(d["code"] == "W6004" for d in data["diagnostics"])

class TestTranslateInvalid:
    def test_empty_source_code(self):
        r = client.post("/api/translate", json={"source_code": ""})
        assert r.status_code == 422

    def test_whitespace_only_source_code(self):
        r = client.post("/api/translate", json={"source_code": "   \n   "})
        assert r.status_code == 422

    def test_missing_source_code(self):
        r = client.post("/api/translate", json={})
        assert r.status_code == 422

    def test_invalid_compat_mode(self):
        r = client.post("/api/translate", json={
            "source_code": HELLO_WORLD,
            "compat": "invalid_mode",
        })
        assert r.status_code == 422

    def test_invalid_overflow_policy(self):
        r = client.post("/api/translate", json={
            "source_code": HELLO_WORLD,
            "overflow": "undefined_behavior",
        })
        assert r.status_code == 422

    def test_source_too_large(self):
        big_source = "// comment\n" * 30_000
        r = client.post("/api/translate", json={"source_code": big_source})
        assert r.status_code == 422

    def test_bad_json_returns_422(self):
        r = client.post(
            "/api/translate",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422

    def test_syntax_error_returns_diagnostics(self):
        bad_cpp = "int main( { return 0; }"
        r = client.post("/api/translate", json={"source_code": bad_cpp})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert data["python_source"] is None
        assert data["error_count"] > 0
        assert len(data["diagnostics"]) > 0

class TestTranslateDiagnostics:
    def test_diagnostic_has_required_fields(self):
        bad_cpp = "int main( { return 0; }"
        r = client.post("/api/translate", json={"source_code": bad_cpp})
        data = r.json()
        for diag in data["diagnostics"]:
            assert "severity" in diag
            assert "code" in diag
            assert "message" in diag

    def test_severity_values_are_valid(self):
        bad_cpp = "int main( { return 0; }"
        r = client.post("/api/translate", json={"source_code": bad_cpp})
        data = r.json()
        valid_severities = {"error", "warning", "note"}
        for diag in data["diagnostics"]:
            assert diag["severity"] in valid_severities

class TestDifftestStatus:
    def test_status_returns_200(self):
        r = client.get("/api/difftest/status")
        assert r.status_code == 200

    def test_status_schema(self):
        r = client.get("/api/difftest/status")
        data = r.json()
        assert "cxx_available" in data
        assert "message" in data
        assert isinstance(data["cxx_available"], bool)

    def test_status_message_is_informative(self):
        r = client.get("/api/difftest/status")
        data = r.json()
        assert len(data["message"]) > 0

class TestDifftestRun:
    def test_run_returns_200(self):
        r = client.post("/api/difftest/run", json={"suite": "curated", "count": 5})
        assert r.status_code == 200

    def test_run_when_no_cxx_returns_unavailable(self):
        r = client.post("/api/difftest/run", json={"suite": "curated"})
        data = r.json()

        assert r.status_code == 200
        assert "available" in data

    def test_run_invalid_suite(self):
        r = client.post("/api/difftest/run", json={"suite": "nonexistent"})
        assert r.status_code == 422

    def test_run_invalid_compat(self):
        r = client.post("/api/difftest/run", json={"suite": "curated", "compat": "bad"})
        assert r.status_code == 422

    def test_run_count_out_of_range(self):
        r = client.post("/api/difftest/run", json={"suite": "generated", "count": 200})
        assert r.status_code == 422

class TestSemanticDifferences:
    def test_returns_200(self):
        r = client.get("/api/report/semantic-differences")
        assert r.status_code == 200

    def test_has_differences_list(self):
        r = client.get("/api/report/semantic-differences")
        data = r.json()
        assert isinstance(data["differences"], list)
        assert len(data["differences"]) > 0

    def test_has_disclaimer(self):
        r = client.get("/api/report/semantic-differences")
        data = r.json()
        assert "disclaimer" in data
        assert len(data["disclaimer"]) > 0

class TestFidelityReport:
    def test_returns_200_for_valid_source(self):
        r = client.post("/api/report/fidelity", json={"source_code": HELLO_WORLD})
        assert r.status_code == 200

    def test_report_has_schema_version(self):
        r = client.post("/api/report/fidelity", json={"source_code": HELLO_WORLD})
        data = r.json()
        assert "schema_version" in data

    def test_report_has_run_metadata(self):
        r = client.post("/api/report/fidelity", json={"source_code": HELLO_WORLD})
        data = r.json()
        assert "run_metadata" in data
        meta = data["run_metadata"]
        assert "tool_version" in meta

    def test_report_empty_source_returns_422(self):
        r = client.post("/api/report/fidelity", json={"source_code": ""})
        assert r.status_code == 422

    def test_report_for_failed_translation(self):
        bad_cpp = "int main( { return 0; }"
        r = client.post("/api/report/fidelity", json={"source_code": bad_cpp})
        assert r.status_code == 200
        data = r.json()

        assert "schema_version" in data

    def test_report_includes_semantic_differences(self):
        r = client.post("/api/report/fidelity", json={"source_code": HELLO_WORLD})
        data = r.json()
        assert "potential_semantic_differences" in data
        assert isinstance(data["potential_semantic_differences"], list)


class TestExecuteEndpoint:
    def test_execute_basic_python(self):
        py_code = "print('Hello, world!')"
        r = client.post("/api/execute", json={"python_source": py_code})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["exit_code"] == 0
        assert data["stdout"].strip() == "Hello, world!"
        assert data["stderr"] == ""
        assert data["duration_ms"] >= 0
        assert data["timed_out"] is False

    def test_execute_with_stdin_multiline_and_spaces(self):
        py_code = """import sys
tokens = sys.stdin.read().split()
nums = [int(t) for t in tokens]
print("SUM:", sum(nums))
"""
        stdin_content = "10 20\n30   40\n50\n"
        r = client.post("/api/execute", json={"python_source": py_code, "stdin": stdin_content})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["stdout"].strip() == "SUM: 150"

    def test_execute_cpp_source_translation_and_run(self):
        cpp_code = """#include <iostream>
int main() {
    int x;
    std::cin >> x;
    std::cout << x * 2;
    return 0;
}"""
        r = client.post("/api/execute", json={"source_code": cpp_code, "stdin": "21\n"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["exit_code"] == 0
        assert data["stdout"].strip() == "42"

    def test_execute_cpp_bubble_sort_runtime_array(self):
        code = """#include <iostream>
using namespace std;

void bubble_sort(int arr[], int n) {
    for (int i = 0; i < n - 1; i++) {
        for (int j = 0; j < n - i - 1; j++) {
            if (arr[j] > arr[j + 1]) {
                int temp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = temp;
            }
        }
    }
}

int main() {
    int n;
    cin >> n;
    int arr[n];
    for (int i = 0; i < n; i++) {
        cin >> arr[i];
    }
    bubble_sort(arr, n);
    for (int i = 0; i < n; i++) {
        cout << arr[i] << " ";
    }
    return 0;
}"""
        r = client.post("/api/execute", json={"source_code": code, "stdin": "5\n64 34 25 12 22\n"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["exit_code"] == 0
        assert data["stdout"].strip() == "12 22 25 34 64"

    def test_execute_runtime_error_nonzero_exit(self):
        py_code = """import sys
print("Starting")
x = 10 // 0
"""
        r = client.post("/api/execute", json={"python_source": py_code})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert data["exit_code"] != 0
        assert "ZeroDivisionError" in data["stderr"]
        assert "Starting" in data["stdout"]

    def test_execute_timeout_handling(self):
        py_code = """import time
time.sleep(2)
print("Finished")
"""
        r = client.post("/api/execute", json={"python_source": py_code, "timeout": 0.2})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert data["timed_out"] is True
        assert data["exit_code"] == -1
        assert "timed out" in data["stderr"].lower()

    def test_execute_compilation_failure(self):
        bad_cpp = "int main( { return 0; }"
        r = client.post("/api/execute", json={"source_code": bad_cpp})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert data["exit_code"] == 2
        assert "Compilation failed" in data["stderr"]

    def test_execute_missing_payload(self):
        r = client.post("/api/execute", json={})
        assert r.status_code == 422

    def test_execute_syntax_error_in_python(self):
        py_code = "def broken_func("
        r = client.post("/api/execute", json={"python_source": py_code})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert data["exit_code"] == 1
        assert "SyntaxError" in data["stderr"]

