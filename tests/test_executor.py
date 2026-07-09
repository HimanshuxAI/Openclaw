from agents import executor


def _plan(approved=True, executable=True, patch="patch-a"):
    return {
        "approved": approved,
        "executable": executable,
        "candidate": {"patch": patch},
    }


def test_executor_never_applies_unapproved_or_non_executable_plans(tmp_path):
    calls = []

    rejected = executor.execute(
        _plan(approved=False),
        tmp_path,
        lambda path, patch: calls.append((path, patch)) or True,
    )
    non_executable = executor.execute(
        _plan(executable=False),
        tmp_path,
        lambda path, patch: calls.append((path, patch)) or True,
    )

    assert rejected == {"state": "not_executed", "applied": False, "patch": "patch-a"}
    assert non_executable == {
        "state": "not_executed",
        "applied": False,
        "patch": "patch-a",
    }
    assert calls == []


def test_executor_applies_an_approved_candidate_once_and_retains_it_for_verification(
    tmp_path,
):
    calls = []

    result = executor.execute(
        _plan(),
        tmp_path,
        lambda path, patch: calls.append((path, patch)) or True,
    )

    assert result == {"state": "applied", "applied": True, "patch": "patch-a"}
    assert calls == [(tmp_path, "patch-a")]


def test_executor_returns_not_executed_when_existing_preflight_apply_rejects_candidate(tmp_path):
    result = executor.execute(_plan(), tmp_path, lambda path, patch: False)

    assert result == {"state": "not_executed", "applied": False, "patch": "patch-a"}
