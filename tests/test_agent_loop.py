import agent_loop
from memory.store import load_memory, save_memory


FAILURE = {
    "passed": False,
    "output": "FAILED tests/test_math.py::test_add\nE AssertionError: expected 5",
    "errors": "",
}


def _record(patch, success, timestamp="2026-06-21T00:00:00+00:00"):
    return {
        "error_type": "AssertionError",
        "error_message": "expected <number>",
        "file": "tests/test_math.py",
        "patch": patch,
        "success": success,
        "timestamp": timestamp,
    }


def test_run_agent_returns_immediately_when_tests_pass(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: calls.append(path) or {"passed": True, "output": "", "errors": ""},
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert calls == [tmp_path]


def test_run_agent_stops_when_no_patch_is_generated(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: {"passed": False, "output": "failed", "errors": ""},
    )
    monkeypatch.setattr(agent_loop.patcher, "generate_patch", lambda failure, path: "")

    assert agent_loop.run_agent(tmp_path) is False


def test_run_agent_retests_after_applying_patch(monkeypatch, tmp_path):
    results = iter(
        [
            {"passed": False, "output": "failed", "errors": ""},
            {"passed": True, "output": "passed", "errors": ""},
        ]
    )
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(agent_loop.patcher, "generate_patch", lambda failure, path: "patch")
    monkeypatch.setattr(agent_loop.patcher, "apply_patch", lambda path, patch: True)

    assert agent_loop.run_agent(tmp_path) is True


def test_run_agent_stops_after_five_patch_attempts(monkeypatch, tmp_path):
    test_calls = 0
    patch_calls = 0

    def fail_tests(path):
        nonlocal test_calls
        test_calls += 1
        return {"passed": False, "output": "failed", "errors": ""}

    def apply(path, patch):
        nonlocal patch_calls
        patch_calls += 1
        return True

    monkeypatch.setattr(agent_loop.test_runner, "run_tests", fail_tests)
    monkeypatch.setattr(agent_loop.patcher, "generate_patch", lambda failure, path: "patch")
    monkeypatch.setattr(agent_loop.patcher, "apply_patch", apply)

    assert agent_loop.run_agent(tmp_path) is False
    assert patch_calls == agent_loop.MAX_STEPS == 5
    assert test_calls == agent_loop.MAX_STEPS + 1


def test_run_agent_stops_when_patch_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: {"passed": False, "output": "failed", "errors": ""},
    )
    monkeypatch.setattr(agent_loop.patcher, "generate_patch", lambda failure, path: "patch")
    monkeypatch.setattr(agent_loop.patcher, "apply_patch", lambda path, patch: False)

    assert agent_loop.run_agent(tmp_path) is False


def test_run_agent_reuses_exact_success_without_generation(monkeypatch, tmp_path):
    save_memory([_record("remembered-patch", True)])
    results = iter([FAILURE, {"passed": True, "output": "passed", "errors": ""}])
    applied = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch",
        lambda failure, path: (_ for _ in ()).throw(AssertionError("generator called")),
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda path, patch: applied.append(patch) or True,
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["remembered-patch"]


def test_run_agent_reuses_fuzzy_high_confidence_success(monkeypatch, tmp_path):
    save_memory([_record("remembered-patch", True)])
    fuzzy_failure = {
        "passed": False,
        "output": "FAILED tests/test_math.py::test_add\nE AssertionError: expected 8",
        "errors": "",
    }
    results = iter([fuzzy_failure, {"passed": True, "output": "passed", "errors": ""}])
    applied = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch",
        lambda failure, path: (_ for _ in ()).throw(AssertionError("generator called")),
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda path, patch: applied.append(patch) or True,
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["remembered-patch"]


def test_run_agent_does_not_replay_when_similarity_is_below_threshold(
    monkeypatch, tmp_path
):
    save_memory(
        [
            _record("weak-patch", True)
            | {
                "error_message": "a completely different assertion",
                "file": "other/test_math.py",
            }
        ]
    )
    results = iter([FAILURE, {"passed": True, "output": "passed", "errors": ""}])
    applied = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(agent_loop.patcher, "generate_patch", lambda failure, path: "fresh")
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda path, patch: applied.append(patch) or True,
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["fresh"]


def test_run_agent_does_not_repeat_a_patch_that_later_failed(monkeypatch, tmp_path):
    save_memory(
        [
            _record("old-patch", True, "2026-06-20T00:00:00+00:00"),
            _record("old-patch", False, "2026-06-21T00:00:00+00:00"),
        ]
    )
    results = iter([FAILURE, {"passed": True, "output": "passed", "errors": ""}])
    applied = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch", lambda failure, path: "fresh-patch"
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda path, patch: applied.append(patch) or True,
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["fresh-patch"]


def test_run_agent_falls_back_when_remembered_patch_is_stale(monkeypatch, tmp_path):
    save_memory([_record("stale-patch", True)])
    results = iter([FAILURE, {"passed": True, "output": "passed", "errors": ""}])
    applied = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch", lambda failure, path: "fresh-patch"
    )

    def apply(path, patch):
        applied.append(patch)
        return patch == "fresh-patch"

    monkeypatch.setattr(agent_loop.patcher, "apply_patch", apply)

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["stale-patch", "fresh-patch"]
    attempts = load_memory()
    assert any(record["patch"] == "stale-patch" and not record["success"] for record in attempts)
    assert attempts[-1]["patch"] == "fresh-patch"
    assert attempts[-1]["success"] is True


def test_run_agent_records_rejected_generated_patch(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: FAILURE)
    monkeypatch.setattr(agent_loop.patcher, "generate_patch", lambda failure, path: "bad-patch")
    monkeypatch.setattr(agent_loop.patcher, "apply_patch", lambda path, patch: False)

    assert agent_loop.run_agent(tmp_path) is False
    assert load_memory()[0]["patch"] == "bad-patch"
    assert load_memory()[0]["success"] is False


def test_run_agent_does_not_store_unstructured_noise(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: {"passed": False, "output": "process died", "errors": ""},
    )
    monkeypatch.setattr(agent_loop.patcher, "generate_patch", lambda failure, path: "")

    assert agent_loop.run_agent(tmp_path) is False
    assert load_memory() == []
