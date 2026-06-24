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


def _accept_all_patches(monkeypatch):
    monkeypatch.setattr(
        agent_loop.patcher,
        "rank_patch_candidates",
        lambda path, patches, failure, memory=None: [
            {"patch": patch, "score": {"confidence": 0.90}}
            for patch in patches
            if patch
        ],
    )
    monkeypatch.setattr(agent_loop, "_regression_guard", lambda *args: True)


def test_run_agent_returns_immediately_when_tests_pass(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: calls.append(path) or {"passed": True, "output": "", "errors": ""},
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert calls == [tmp_path]
    output = capsys.readouterr().out
    assert "METRICS: attempts=0" in output
    assert "model_calls=0" in output
    assert "memory_replays=0" in output
    assert "context_tokens=0" in output
    assert "passed=true" in output


def test_run_agent_stops_before_generation_when_pytest_collects_no_tests(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: {
            "passed": False,
            "output": "no tests ran in 0.00s",
            "errors": "",
            "exit_code": 5,
        },
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("generator called")
        ),
    )

    assert agent_loop.run_agent(tmp_path) is False
    output = capsys.readouterr().out
    assert "STOPPED: pytest collected no tests" in output
    assert "METRICS: attempts=0 model_calls=0" in output


def test_run_agent_stops_when_no_patch_is_generated(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: {"passed": False, "output": "failed", "errors": ""},
    )
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch_candidates", lambda failure, path, **kwargs: []
    )

    assert agent_loop.run_agent(tmp_path) is False


def test_run_agent_retests_after_applying_patch(monkeypatch, tmp_path):
    results = iter(
        [
            {"passed": False, "output": "failed", "errors": ""},
            {"passed": True, "output": "passed", "errors": ""},
        ]
    )
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch_candidates", lambda failure, path, **kwargs: ["patch"]
    )
    monkeypatch.setattr(agent_loop.patcher, "apply_patch", lambda path, patch: True)

    assert agent_loop.run_agent(tmp_path) is True


def test_run_agent_applies_best_scored_candidate_first(monkeypatch, tmp_path):
    results = iter(
        [
            FAILURE,
            {"passed": True, "output": "passed", "errors": "", "exit_code": 0},
        ]
    )
    applied = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda failure, path, **kwargs: ["weak-patch", "strong-patch"],
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "rank_patch_candidates",
        lambda path, patches, failure, memory=None: [
            {"patch": "strong-patch", "score": {"confidence": 0.95}},
            {"patch": "weak-patch", "score": {"confidence": 0.72}},
        ],
    )
    monkeypatch.setattr(agent_loop, "_regression_guard", lambda *args: True)
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda path, patch: applied.append(patch) or True,
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["strong-patch"]


def test_run_agent_rejects_regression_candidate_and_falls_back(monkeypatch, tmp_path):
    results = iter(
        [
            FAILURE,
            {"passed": True, "output": "passed", "errors": "", "exit_code": 0},
        ]
    )
    applied = []
    reverted = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda failure, path, **kwargs: ["regresses", "safe"],
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "rank_patch_candidates",
        lambda path, patches, failure, memory=None: [
            {"patch": "regresses", "score": {"confidence": 0.94}},
            {"patch": "safe", "score": {"confidence": 0.90}},
        ],
    )
    monkeypatch.setattr(
        agent_loop,
        "_regression_guard",
        lambda repo, failure, patch, baseline_nodes=None: patch == "safe",
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda path, patch: applied.append(patch) or True,
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "revert_patch",
        lambda path, patch: reverted.append(patch) or True,
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["regresses", "safe"]
    assert reverted == ["regresses"]


def test_regression_nodes_excludes_all_currently_failing_tests(monkeypatch, tmp_path):
    failure = (
        "FAILED tests/test_calc.py::test_add - AssertionError\n"
        "FAILED tests/test_calc.py::test_multiply - AssertionError\n"
    )
    monkeypatch.setattr(
        agent_loop.test_runner,
        "collect_tests",
        lambda path: [
            "tests/test_calc.py::test_add",
            "tests/test_calc.py::test_multiply",
            "tests/test_calc.py::test_divide",
        ],
    )

    assert agent_loop._regression_nodes(tmp_path, failure) == [
        "tests/test_calc.py::test_divide"
    ]


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
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch_candidates", lambda failure, path, **kwargs: ["patch"]
    )
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
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch_candidates", lambda failure, path, **kwargs: ["patch"]
    )
    monkeypatch.setattr(agent_loop.patcher, "apply_patch", lambda path, patch: False)

    assert agent_loop.run_agent(tmp_path) is False


def test_run_agent_reuses_exact_success_without_generation(monkeypatch, tmp_path, capsys):
    save_memory([_record("remembered-patch", True)])
    results = iter([FAILURE, {"passed": True, "output": "passed", "errors": ""}])
    applied = []
    monkeypatch.setattr(agent_loop.test_runner, "run_tests", lambda path: next(results))
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda failure, path, **kwargs: (_ for _ in ()).throw(
            AssertionError("generator called")
        ),
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda path, patch: applied.append(patch) or True,
    )

    assert agent_loop.run_agent(tmp_path) is True
    assert applied == ["remembered-patch"]
    assert "memory_replays=1" in capsys.readouterr().out


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
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda failure, path, **kwargs: (_ for _ in ()).throw(
            AssertionError("generator called")
        ),
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
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch_candidates", lambda failure, path, **kwargs: ["fresh"]
    )
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
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda failure, path, **kwargs: ["fresh-patch"],
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
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda failure, path, **kwargs: ["fresh-patch"],
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
    _accept_all_patches(monkeypatch)
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch_candidates", lambda failure, path, **kwargs: ["bad-patch"]
    )
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
    monkeypatch.setattr(
        agent_loop.patcher, "generate_patch_candidates", lambda failure, path, **kwargs: []
    )

    assert agent_loop.run_agent(tmp_path) is False
    assert load_memory() == []
