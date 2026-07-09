from agents import verifier


def _execution(applied=True):
    return {"state": "applied" if applied else "not_executed", "applied": applied, "patch": "patch-a"}


def _result(passed):
    return {"passed": passed, "output": "", "errors": "", "exit_code": 0 if passed else 1}


def _simulation():
    return {"pass_likelihood": 0.8}


def test_verifier_does_not_run_tests_or_revert_when_nothing_was_applied():
    calls = []

    report = verifier.verify(
        _execution(applied=False),
        lambda: calls.append("subset") or _result(True),
        lambda: calls.append("full") or _result(True),
        lambda patch: calls.append(("revert", patch)) or True,
        _simulation(),
    )

    assert report["state"] == "not_executed"
    assert report["tests_passed"] is False
    assert calls == []


def test_verifier_reverts_once_when_regression_subset_fails():
    calls = []

    report = verifier.verify(
        _execution(),
        lambda: calls.append("subset") or _result(False),
        lambda: calls.append("full") or _result(True),
        lambda patch: calls.append(("revert", patch)) or True,
        _simulation(),
    )

    assert report["state"] == "regressed"
    assert report["tests_passed"] is False
    assert report["regression_safe"] is False
    assert report["reverted"] is True
    assert calls == ["subset", ("revert", "patch-a")]


def test_verifier_reverts_once_when_full_suite_fails_after_subset_passes():
    calls = []

    report = verifier.verify(
        _execution(),
        lambda: calls.append("subset") or _result(True),
        lambda: calls.append("full") or _result(False),
        lambda patch: calls.append(("revert", patch)) or True,
        _simulation(),
    )

    assert report["state"] == "failed"
    assert report["tests_passed"] is False
    assert report["reverted"] is True
    assert calls == ["subset", "full", ("revert", "patch-a")]


def test_verifier_reports_a_pass_only_after_subset_and_full_suite_pass():
    calls = []

    report = verifier.verify(
        _execution(),
        lambda: calls.append("subset") or _result(True),
        lambda: calls.append("full") or _result(True),
        lambda patch: calls.append(("revert", patch)) or True,
        _simulation(),
    )

    assert report["state"] == "passed"
    assert report["tests_passed"] is True
    assert report["regression_safe"] is True
    assert report["dependency_safe"] is True
    assert report["performance_ok"] is True
    assert report["reverted"] is False
    assert calls == ["subset", "full"]
