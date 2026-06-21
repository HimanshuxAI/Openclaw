from memory.selector import find_similar_cases


def _case(
    error_type="NameError",
    message="name 'user' is not defined",
    file="tests/test_auth.py",
    patch="patch",
    success=True,
    timestamp="2026-06-21T00:00:00+00:00",
):
    return {
        "error_type": error_type,
        "error_message": message,
        "file": file,
        "patch": patch,
        "success": success,
        "timestamp": timestamp,
    }


def test_find_similar_cases_weights_same_error_and_file_highest():
    exact = _case(patch="exact")
    same_error = _case(file="tests/test_other.py", patch="same-error")
    same_file = _case(error_type="AssertionError", patch="same-file")

    matches = find_similar_cases(
        "FAILED tests/test_auth.py::test_login\nE NameError: name 'user' is not defined",
        [same_file, same_error, exact],
    )

    assert [match["patch"] for match in matches] == ["exact", "same-error", "same-file"]


def test_find_similar_cases_uses_message_similarity_within_same_type():
    close = _case(message="name 'users' is not defined", patch="close")
    distant = _case(message="database connection refused", patch="distant")

    matches = find_similar_cases("NameError: name 'user' is not defined", [distant, close])

    assert matches[0]["patch"] == "close"


def test_find_similar_cases_prefers_newest_record_for_equal_scores():
    older = _case(patch="older", timestamp="2026-06-20T00:00:00+00:00")
    newer = _case(patch="newer", timestamp="2026-06-21T00:00:00+00:00")

    matches = find_similar_cases(
        "FAILED tests/test_auth.py\nNameError: name 'user' is not defined",
        [older, newer],
    )

    assert [match["patch"] for match in matches] == ["newer", "older"]


def test_find_similar_cases_returns_at_most_three_positive_matches():
    cases = [_case(patch=f"patch-{number}") for number in range(5)]

    matches = find_similar_cases("NameError: name 'user' is not defined", cases)

    assert len(matches) == 3
    assert find_similar_cases("SyntaxError: completely unrelated", [_case()]) == []
