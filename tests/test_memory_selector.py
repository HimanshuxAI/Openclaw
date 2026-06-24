from memory.selector import (
    REPLAY_THRESHOLD,
    find_fix_templates,
    find_similar_cases,
    similarity_score,
)


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

    assert [match["record"]["patch"] for match in matches] == [
        "exact",
        "same-error",
        "same-file",
    ]
    assert matches[0]["score"] == 1.0
    assert matches[0]["record"] == exact
    assert "score" not in exact


def test_find_similar_cases_uses_message_similarity_within_same_type():
    close = _case(message="name 'users' is not defined", patch="close")
    distant = _case(message="database connection refused", patch="distant")

    matches = find_similar_cases("NameError: name 'user' is not defined", [distant, close])

    assert matches[0]["record"]["patch"] == "close"


def test_find_similar_cases_prefers_newest_record_for_equal_scores():
    older = _case(patch="older", timestamp="2026-06-20T00:00:00+00:00")
    newer = _case(patch="newer", timestamp="2026-06-21T00:00:00+00:00")

    matches = find_similar_cases(
        "FAILED tests/test_auth.py\nNameError: name 'user' is not defined",
        [older, newer],
    )

    assert [match["record"]["patch"] for match in matches] == ["newer", "older"]


def test_find_similar_cases_returns_at_most_three_positive_matches():
    cases = [_case(patch=f"patch-{number}") for number in range(5)]

    matches = find_similar_cases("NameError: name 'user' is not defined", cases)

    assert len(matches) == 3
    assert find_similar_cases("SyntaxError: completely unrelated", [_case()]) == []


def test_similarity_score_allows_normalized_numeric_variation_to_replay():
    case = _case(
        error_type="AssertionError",
        message="expected <number> but received <number>",
        file="tests/test_total.py",
    )
    failure = "tests/test_total.py:8: AssertionError: expected 5 but received 4"

    assert REPLAY_THRESHOLD == 0.88
    assert similarity_score(failure, case) >= REPLAY_THRESHOLD


def test_similarity_score_gives_basename_match_less_weight_than_full_path():
    case = _case(file="tests/unit/test_auth.py")
    full = similarity_score(
        "tests/unit/test_auth.py:3: NameError: name 'user' is not defined", case
    )
    basename = similarity_score(
        "other/test_auth.py:3: NameError: name 'user' is not defined", case
    )

    assert basename < full


def test_find_fix_templates_groups_successful_repeated_patterns():
    repeated = [
        _case(patch="template", timestamp="2026-06-20T00:00:00+00:00"),
        _case(patch="template", timestamp="2026-06-21T00:00:00+00:00"),
        _case(patch="failed", success=False, timestamp="2026-06-22T00:00:00+00:00"),
    ]

    templates = find_fix_templates(
        "FAILED tests/test_auth.py\nNameError: name 'user' is not defined",
        repeated,
    )

    assert templates[0]["record"]["patch"] == "template"
    assert templates[0]["count"] == 2
    assert all(template["record"]["success"] for template in templates)
