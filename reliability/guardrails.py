"""Pure authorization checks that keep repair work within its explicit goal."""

from strategies import STRATEGIES


def authorize_action(goal, plan, decision, evidence, attempt):
    """Authorize only a bounded, evidence-backed action with verification planned."""
    if not isinstance(goal, dict) or goal.get("state") != "active":
        return _deny("goal_not_active")
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        return _deny("invalid_attempt")
    if attempt > goal.get("max_steps", 0):
        return _deny("attempt_budget_exhausted")
    if not isinstance(plan, dict) or plan.get("repository_id") != goal.get(
        "repository_id"
    ):
        return _deny("goal_mismatch")
    if plan.get("action") != _decision_action(decision):
        return _deny("action_mismatch")
    if plan.get("strategy") not in STRATEGIES:
        return _deny("unapproved_strategy")
    if plan.get("approved") is not True:
        return _deny("plan_not_approved")
    if not isinstance(evidence, dict) or evidence.get("sufficient") is not True:
        return _deny("insufficient_evidence")
    if "verify_scope" not in plan.get("steps", []):
        return _deny("verification_not_planned")
    if plan.get("action") == "ACT" and plan.get("executable") is not True:
        return _deny("plan_not_executable")
    return {"authorized": True, "reason": ""}


def _decision_action(decision):
    if isinstance(decision, dict):
        return decision.get("decision")
    return getattr(decision, "decision", None)


def _deny(reason):
    return {"authorized": False, "reason": reason}
