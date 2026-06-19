import agent_loop


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
