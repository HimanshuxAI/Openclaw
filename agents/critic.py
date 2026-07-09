"""Pure risk review for bounded repair plans."""


LOW_CONFIDENCE = 0.45
HIGH_REGRESSION_RISK = 0.50


def review_plan(plan, prediction, simulation):
    """Review a plan without applying a patch or calling external tools."""
    risks = _risks(plan, prediction, simulation)
    action = _value(plan, "action", "SKIP")
    if "missing_candidate" in risks:
        action = "SKIP"
    elif risks and action == "ACT":
        action = "VALIDATE"
    return {
        "approved": not risks,
        "action": action,
        "risks": risks,
        "revision_required": bool(risks) and action != "SKIP",
    }


def _risks(plan, prediction, simulation):
    risks = []
    if not _patch(plan):
        risks.append("missing_candidate")
    touched_files = _value(simulation, "touched_files", [])
    if not isinstance(touched_files, list) or len(touched_files) != 1:
        risks.append("broad_scope")
    if _number(prediction, "confidence", 0.0) < LOW_CONFIDENCE:
        risks.append("low_confidence")
    if _number(simulation, "regression_risk", 1.0) >= HIGH_REGRESSION_RISK:
        risks.append("high_regression_risk")
    return risks


def _patch(plan):
    candidate = _value(plan, "candidate", None)
    if not isinstance(candidate, dict):
        return ""
    patch = candidate.get("patch", "")
    return patch if isinstance(patch, str) else ""


def _value(mapping, key, default):
    if isinstance(mapping, dict):
        return mapping.get(key, default)
    return getattr(mapping, key, default)


def _number(mapping, key, default):
    try:
        return float(_value(mapping, key, default) or 0.0)
    except (TypeError, ValueError):
        return float(default)
