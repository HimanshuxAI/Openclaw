from utils import extract_failure


def test_extract_failure_combines_nonempty_test_streams():
    result = {"output": "failure output\n", "errors": "warning\n"}

    assert extract_failure(result) == "failure output\n\nwarning"


def test_extract_failure_uses_stderr_when_stdout_is_empty():
    result = {"output": "", "errors": "pytest failed to start\n"}

    assert extract_failure(result) == "pytest failed to start"
