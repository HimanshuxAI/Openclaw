import pytest

from memory.patterns import extract_error_type, extract_file, normalize_error_message


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("E   ImportError: cannot import name 'client'", "ImportError"),
        ("E   ModuleNotFoundError: No module named 'payments'", "ModuleNotFoundError"),
        ("E   NameError: name 'user' is not defined", "NameError"),
        ("raise AssertionError('wrong total')", "AssertionError"),
        ("> assert total == 10\nE assert 9 == 10", "AssertionError"),
        ("process exited unexpectedly", ""),
    ],
)
def test_extract_error_type(failure, expected):
    assert extract_error_type(failure) == expected


def test_normalize_error_message_removes_volatile_diagnostic_values():
    failure = (
        "\x1b[31mE NameError: name 'widget_42' is not defined "
        "at 0xABCDEF on line 17\x1b[0m"
    )

    assert normalize_error_message(failure) == (
        "name 'widget_42' is not defined at <address> on line <number>"
    )


def test_normalize_error_message_handles_pytest_assertion_output():
    failure = "FAILED tests/test_total.py::test_total\nE   assert 9 == 10"

    assert normalize_error_message(failure) == "assert <number> == <number>"


def test_extract_file_returns_first_python_file_reference():
    failure = (
        "FAILED tests/test_auth.py::test_login\n"
        "app/auth.py:42: NameError: user is not defined"
    )

    assert extract_file(failure) == "tests/test_auth.py"


def test_extract_file_returns_empty_when_no_python_file_is_present():
    assert extract_file("NameError: user is not defined") == ""
