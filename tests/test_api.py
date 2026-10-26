"""
Backend API tests.

Tests health endpoint, translation success/failure, malformed requests,
edge cases, and Phase 6/7 endpoint availability.

These tests use FastAPI's TestClient (synchronous) and never require g++.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Minimal C++ programs for testing
# ---------------------------------------------------------------------------

HELLO_WORLD = """\
int main() {
    int x = 42;
    return 0;
}
"""

# A simple supported program that the compiler should accept
SIMPLE_ARITHMETIC = """\
int add(int a, int b) {
    return a + b;
}

int main() {
    int result = add(3, 4);
    return 0;
}
"""

# Something that uses unsupported constructs → should produce errors
UNSUPPORTED_TEMPLATES = """\
template<typename T>
T identity(T x) {
    return x;
}
int main() {
    return identity<int>(0);
}
"""


# ===========================================================================
# Health endpoint
# ===========================================================================

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


# ===========================================================================
# Translate endpoint — valid requests
# ===========================================================================

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
        """Ensure non-translatable code does not return fabricated Python."""
        r = client.post("/api/translate", json={"source_code": UNSUPPORTED_TEMPLATES})
        data = r.json()
        # Either succeeds (if templates supported) or fails honestly
        if not data["success"]:
            assert data["python_source"] is None
            assert data["error_count"] > 0

    def test_translate_function_count(self):
        r = client.post("/api/translate", json={"source_code": SIMPLE_ARITHMETIC})
        data = r.json()
        if data["success"]:
            assert data["function_count"] is not None
            assert data["function_count"] >= 1


# ===========================================================================
# Translate endpoint — invalid / malformed requests
# ===========================================================================

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
        big_source = "// comment\n" * 30_000  # well over 256KB
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


# ===========================================================================
# Translate endpoint — diagnostic shape
# ===========================================================================

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


# ===========================================================================
# Differential testing status endpoint
# ===========================================================================

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


# ===========================================================================
# Differential testing run endpoint
# ===========================================================================

class TestDifftestRun:
    def test_run_returns_200(self):
        r = client.post("/api/difftest/run", json={"suite": "curated", "count": 5})
        assert r.status_code == 200

    def test_run_when_no_cxx_returns_unavailable(self):
        r = client.post("/api/difftest/run", json={"suite": "curated"})
        data = r.json()
        # If g++ not available, response is structured (not 500)
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


# ===========================================================================
# Phase 7 — Semantic differences
# ===========================================================================

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


# ===========================================================================
# Phase 7 — Fidelity report
# ===========================================================================

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
        # Should still return a report, not crash
        assert "schema_version" in data

    def test_report_includes_semantic_differences(self):
        r = client.post("/api/report/fidelity", json={"source_code": HELLO_WORLD})
        data = r.json()
        assert "potential_semantic_differences" in data
        assert isinstance(data["potential_semantic_differences"], list)
