"""Compose bounded Phase 9 roles without giving the coordinator tool authority."""

from agents import critic, executor, planner, verifier
from reliability import evidence, guardrails


MAX_CRITIC_ROUNDS = 2


def run_candidate(
    repo_path,
    prediction,
    decision,
    candidates,
    simulation,
    history,
    goal,
    attempt,
    apply_patch,
    run_subset,
    run_full,
    revert,
):
    """Run one candidate through planning, critique, evidence, and verification."""
    repository_id = goal.get("repository_id", "") if isinstance(goal, dict) else ""
    plan = planner.create_plan(
        prediction,
        decision,
        candidates,
        simulation=simulation,
        history=history,
        repository_id=repository_id,
    )
    critique, critic_rounds = _critique(plan, prediction, simulation)
    plan["approved"] = critique["approved"]

    actual_decision = _decision_with_action(decision, plan["action"])
    pre_evidence = evidence.assess_pre_execution(
        actual_decision,
        critique,
        simulation,
    )
    action = evidence.downgrade_action(actual_decision["decision"], pre_evidence)
    _set_action(plan, action)
    actual_decision = _decision_with_action(decision, action)
    authorization = guardrails.authorize_action(
        goal,
        plan,
        actual_decision,
        pre_evidence,
        attempt,
    )
    if not authorization["authorized"]:
        return _not_executed(
            plan,
            critique,
            actual_decision,
            pre_evidence,
            authorization,
            critic_rounds,
        )

    execution = executor.execute(plan, repo_path, apply_patch)
    verification = verifier.verify(execution, run_subset, run_full, revert, simulation)
    return {
        "plan": plan,
        "critique": critique,
        "actual_decision": actual_decision,
        "pre_evidence": pre_evidence,
        "post_evidence": evidence.assess_verification(verification),
        "authorization": authorization,
        "execution": execution,
        "verification": verification,
        "critic_rounds": critic_rounds,
    }


def _critique(plan, prediction, simulation):
    review = None
    rounds = 0
    for _ in range(MAX_CRITIC_ROUNDS):
        rounds += 1
        review = critic.review_plan(plan, prediction, simulation)
        _set_action(plan, review["action"])
        if not review["revision_required"]:
            break
    return review, rounds


def _set_action(plan, action):
    plan["action"] = action
    candidate = plan.get("candidate") or {}
    patch = candidate.get("patch", "") if isinstance(candidate, dict) else ""
    plan["executable"] = action == "ACT" and isinstance(patch, str) and bool(patch)


def _decision_with_action(decision, action):
    values = decision.copy() if isinstance(decision, dict) else {}
    values["decision"] = action
    return values


def _not_executed(
    plan,
    critique,
    actual_decision,
    pre_evidence,
    authorization,
    critic_rounds,
):
    verification = {
        "state": "not_executed",
        "tests_passed": False,
        "regression_safe": True,
        "performance_ok": False,
        "dependency_safe": False,
        "subset_result": None,
        "full_result": None,
        "reverted": False,
    }
    return {
        "plan": plan,
        "critique": critique,
        "actual_decision": actual_decision,
        "pre_evidence": pre_evidence,
        "post_evidence": evidence.assess_verification(verification),
        "authorization": authorization,
        "execution": {"state": "not_executed", "applied": False, "patch": ""},
        "verification": verification,
        "critic_rounds": critic_rounds,
    }
