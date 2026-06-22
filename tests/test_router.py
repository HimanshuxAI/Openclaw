import pytest

from rag.router import analyze_failure


def test_analyze_failure_classifies_and_extracts_traceback_evidence():
    failure = (
        "FAILED tests/test_total.py::test_total - TypeError\n"
        "tests/test_total.py:8: in test_total\n"
        "app/service.py:14: in calculate_total\n"
        "E TypeError: unsupported operand"
    )

    evidence = analyze_failure(failure)

    assert evidence["kind"] == "type"
    assert evidence["node"] == ("tests/test_total.py", "test_total")
    assert evidence["locations"] == (
        ("tests/test_total.py", 8),
        ("app/service.py", 14),
    )
    assert evidence["error_type"] == "TypeError"
    assert "calculate_total" in evidence["identifiers"]


@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        ("SyntaxError: invalid syntax", "syntax"),
        ("IndentationError: unexpected indent", "syntax"),
        ("ImportError: cannot import name 'charge'", "import"),
        ("ModuleNotFoundError: No module named 'billing'", "import"),
        ("E assert total == 5", "assertion"),
        ("AssertionError: expected 5", "assertion"),
        ("TypeError: unsupported operand", "type"),
        ("AttributeError: object has no attribute 'total'", "type"),
        ("ValueError: invalid value", "runtime"),
        ("collection stopped", "unknown"),
    ],
)
def test_analyze_failure_routes_known_failure_types(failure, kind):
    assert analyze_failure(failure)["kind"] == kind


def test_analyze_failure_deduplicates_locations_in_source_order():
    failure = "app/service.py:14: boom\napp/service.py:14: repeated\napp/api.py:9: outer"

    assert analyze_failure(failure)["locations"] == (
        ("app/service.py", 14),
        ("app/api.py", 9),
    )
