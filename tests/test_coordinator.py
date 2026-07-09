from agents import coordinator


def _prediction(confidence=0.9):
    return {"risk_score": 0.9, "confidence": confidence}


def _decision(action="ACT"):
    return {"decision": action}


def _candidate():
    return [{"patch": "patch-a", "score": {"confidence": 0.9}}]


def _simulation():
    return {
        "touched_files": ["service.py"],
        "regression_risk": 0.1,
        "pass_likelihood": 0.9,
    }


def _goal():
    return {"run_id": "run-1", "repository_id": "repo-a", "state": "active", "max_steps": 5}


def _result(passed=True):
    return {"passed": passed, "output": "", "errors": "", "exit_code": 0 if passed else 1}


def test_coordinator_runs_safe_candidate_through_execution_and_verification_once():
    calls = []
    outcome = coordinator.run_candidate(
        repo_path="/repo",
        prediction=_prediction(),
        decision=_decision(),
        candidates=_candidate(),
        simulation=_simulation(),
        history=[],
        goal=_goal(),
        attempt=1,
        apply_patch=lambda path, patch: calls.append(("apply", path, patch)) or True,
        run_subset=lambda: calls.append("subset") or _result(),
        run_full=lambda: calls.append("full") or _result(),
        revert=lambda patch: calls.append(("revert", patch)) or True,
    )

    assert outcome["actual_decision"]["decision"] == "ACT"
    assert outcome["verification"]["state"] == "passed"
    assert outcome["authorization"] == {"authorized": True, "reason": ""}
    assert outcome["critic_rounds"] == 1
    assert calls == [("apply", "/repo", "patch-a"), "subset", "full"]


def test_coordinator_stops_before_executor_when_critic_or_evidence_rejects_plan():
    calls = []
    outcome = coordinator.run_candidate(
        repo_path="/repo",
        prediction=_prediction(confidence=0.2),
        decision=_decision(),
        candidates=_candidate(),
        simulation=_simulation(),
        history=[],
        goal=_goal(),
        attempt=1,
        apply_patch=lambda path, patch: calls.append(("apply", path, patch)) or True,
        run_subset=lambda: calls.append("subset") or _result(),
        run_full=lambda: calls.append("full") or _result(),
        revert=lambda patch: calls.append(("revert", patch)) or True,
    )

    assert outcome["actual_decision"]["decision"] == "VALIDATE"
    assert outcome["verification"]["state"] == "not_executed"
    assert outcome["authorization"]["authorized"] is False
    assert calls == []
    assert outcome["critic_rounds"] == 2


def test_coordinator_reverts_when_phase10_rejects_malformed_full_test_evidence():
    calls = []
    outcome = coordinator.run_candidate(
        repo_path="/repo",
        prediction=_prediction(),
        decision=_decision(),
        candidates=_candidate(),
        simulation=_simulation(),
        history=[],
        goal=_goal(),
        attempt=1,
        apply_patch=lambda path, patch: calls.append(("apply", path, patch)) or True,
        run_subset=lambda: calls.append("subset") or _result(),
        run_full=lambda: calls.append("full") or {"passed": True},
        revert=lambda patch: calls.append(("revert", patch)) or True,
    )

    assert outcome["post_evidence"]["sufficient"] is False
    assert outcome["verification"]["state"] == "failed"
    assert outcome["verification"]["reverted"] is True
    assert calls == [("apply", "/repo", "patch-a"), "subset", "full", ("revert", "patch-a")]
