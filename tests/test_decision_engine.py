from decision_engine import ACT, SKIP, VALIDATE, evaluate, should_act


def _prediction(**overrides):
    values = {
        "risk_score": 0.8,
        "confidence": 0.8,
        "change_frequency": 3,
        "failure_frequency": 4,
        "dependency_centrality": 5,
        "estimated_fix_cost": 0.4,
        "estimated_failure_cost": 2.0,
    }
    values.update(overrides)
    return values


def test_should_act_compares_expected_failure_loss_to_action_cost():
    assert should_act(_prediction()) is True
    assert should_act(_prediction(estimated_fix_cost=2.0)) is False


def test_evaluate_returns_act_for_high_value_high_confidence_prediction():
    decision = evaluate(_prediction(risk_score=0.9, confidence=0.85))

    assert decision["decision"] == ACT
    assert decision["expected_failure_loss"] > decision["expected_action_cost"]


def test_evaluate_returns_validate_for_medium_expected_value():
    decision = evaluate(
        _prediction(
            risk_score=0.62,
            confidence=0.58,
            estimated_failure_cost=1.5,
            estimated_fix_cost=0.45,
        )
    )

    assert decision["decision"] == VALIDATE


def test_evaluate_returns_skip_when_action_cost_exceeds_expected_loss():
    decision = evaluate(_prediction(risk_score=0.2, confidence=0.5))

    assert decision["decision"] == SKIP
    assert decision["expected_failure_loss"] < decision["expected_action_cost"]
