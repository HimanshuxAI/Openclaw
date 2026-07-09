import inspect

from reliability import guardrails


def _goal(**overrides):
    values = {
        "run_id": "run-1",
        "repository_id": "repo-a",
        "state": "active",
        "max_steps": 5,
    }
    values.update(overrides)
    return values


def _plan(**overrides):
    values = {
        "repository_id": "repo-a",
        "action": "ACT",
        "strategy": "minimal_patch",
        "approved": True,
        "executable": True,
        "steps": ["analyze_context", "verify_scope"],
    }
    values.update(overrides)
    return values


def _decision(action="ACT"):
    return {"decision": action}


def _evidence(sufficient=True):
    return {"sufficient": sufficient}


def test_guardrail_authorizes_a_bounded_verified_plan():
    assert guardrails.authorize_action(
        _goal(),
        _plan(),
        _decision(),
        _evidence(),
        attempt=1,
    ) == {"authorized": True, "reason": ""}


def test_guardrail_rejects_budget_goal_scope_strategy_and_evidence_violations():
    assert guardrails.authorize_action(
        _goal(), _plan(), _decision(), _evidence(), attempt=6
    ) == {"authorized": False, "reason": "attempt_budget_exhausted"}
    assert guardrails.authorize_action(
        _goal(repository_id="repo-a"),
        _plan(repository_id="repo-b"),
        _decision(),
        _evidence(),
        attempt=1,
    ) == {"authorized": False, "reason": "goal_mismatch"}
    assert guardrails.authorize_action(
        _goal(), _plan(strategy="invent_patch"), _decision(), _evidence(), attempt=1
    ) == {"authorized": False, "reason": "unapproved_strategy"}
    assert guardrails.authorize_action(
        _goal(), _plan(), _decision(), _evidence(False), attempt=1
    ) == {"authorized": False, "reason": "insufficient_evidence"}


def test_guardrail_rejects_action_mismatch_and_execution_without_a_verification_step():
    assert guardrails.authorize_action(
        _goal(), _plan(), _decision("SKIP"), _evidence(), attempt=1
    ) == {"authorized": False, "reason": "action_mismatch"}
    assert guardrails.authorize_action(
        _goal(), _plan(steps=["apply_candidate"]), _decision(), _evidence(), attempt=1
    ) == {"authorized": False, "reason": "verification_not_planned"}


def test_guardrails_are_pure_and_never_reference_executor_code():
    assert "executor" not in inspect.getsource(guardrails)
