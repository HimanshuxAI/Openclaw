"""Build minimal, reversible repair plans from ranked patch candidates."""

import hashlib

from strategies import select_strategy


MINIMAL_STEPS = (
    "analyze_context",
    "select_strategy",
    "apply_candidate",
    "verify_scope",
)


def create_plan(
    prediction,
    decision,
    candidates,
    simulation=None,
    history=None,
    repository_id="",
):
    """Return a deterministic, bounded plan without applying a candidate."""
    candidate_list = list(candidates or [])
    candidate = candidate_list[0].copy() if candidate_list else None
    action = _action(decision)
    strategy = select_strategy(action, history, repository_id)
    executable = action == "ACT" and bool(_patch(candidate))
    return {
        "plan_id": _plan_id(action, strategy, candidate),
        "action": action,
        "strategy": strategy,
        "candidate": candidate,
        "candidate_count": len(candidate_list),
        "steps": list(MINIMAL_STEPS),
        "reversible": bool(_patch(candidate)),
        "executable": executable,
        "simulation": dict(simulation or {}),
        "prediction": dict(prediction or {}),
    }


def _action(decision):
    if isinstance(decision, dict):
        return decision.get("decision", "SKIP")
    return getattr(decision, "decision", "SKIP")


def _patch(candidate):
    if not isinstance(candidate, dict):
        return ""
    patch = candidate.get("patch", "")
    return patch if isinstance(patch, str) else ""


def _plan_id(action, strategy, candidate):
    payload = "|".join((str(action), str(strategy), _patch(candidate)))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"plan-{digest}"
