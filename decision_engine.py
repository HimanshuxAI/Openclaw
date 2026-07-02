ACT = "ACT"
VALIDATE = "VALIDATE"
SKIP = "SKIP"

DEFAULT_FIX_COST = 0.5
DEFAULT_FAILURE_COST = 1.0
ACT_RISK_THRESHOLD = 0.75
ACT_CONFIDENCE_THRESHOLD = 0.70
VALIDATE_RISK_THRESHOLD = 0.45
VALIDATE_CONFIDENCE_THRESHOLD = 0.45


def should_act(prediction):
    expected_failure_loss = (
        _value(prediction, "risk_score", 0.0)
        * _value(prediction, "confidence", 0.0)
        * _value(prediction, "estimated_failure_cost", DEFAULT_FAILURE_COST)
    )
    expected_action_cost = _value(
        prediction,
        "estimated_fix_cost",
        DEFAULT_FIX_COST,
    )
    return expected_failure_loss > expected_action_cost


def evaluate(prediction):
    expected_failure_loss = round(
        _value(prediction, "risk_score", 0.0)
        * _value(prediction, "confidence", 0.0)
        * _value(prediction, "estimated_failure_cost", DEFAULT_FAILURE_COST),
        6,
    )
    expected_action_cost = round(
        _value(prediction, "estimated_fix_cost", DEFAULT_FIX_COST),
        6,
    )
    risk = _value(prediction, "risk_score", 0.0)
    confidence = _value(prediction, "confidence", 0.0)
    if (
        expected_failure_loss > expected_action_cost
        and risk >= ACT_RISK_THRESHOLD
        and confidence >= ACT_CONFIDENCE_THRESHOLD
    ):
        decision = ACT
    elif (
        expected_failure_loss > expected_action_cost
        or (
            risk >= VALIDATE_RISK_THRESHOLD
            and confidence >= VALIDATE_CONFIDENCE_THRESHOLD
        )
    ):
        decision = VALIDATE
    else:
        decision = SKIP
    return {
        "decision": decision,
        "expected_failure_loss": expected_failure_loss,
        "expected_action_cost": expected_action_cost,
        "risk_score": risk,
        "confidence": confidence,
    }


def _value(prediction, key, default):
    if isinstance(prediction, dict):
        return float(prediction.get(key, default) or 0.0)
    return float(getattr(prediction, key, default) or 0.0)
