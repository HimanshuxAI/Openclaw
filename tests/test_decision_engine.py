import decision_engine
import policy_engine
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


def _policy(tmp_path):
    return policy_engine.PolicyEngine(
        path=tmp_path / "policy_history.jsonl",
        state_path=tmp_path / "policy_state.json",
        epsilon=0.0,
    )


def test_should_act_compares_expected_failure_loss_to_action_cost():
    assert should_act(_prediction()) is True
    assert should_act(_prediction(estimated_fix_cost=2.0)) is False


def test_evaluate_returns_act_for_high_value_high_confidence_prediction(tmp_path):
    decision = evaluate(
        _prediction(risk_score=0.9, confidence=0.85),
        policy=_policy(tmp_path),
    )

    assert decision["decision"] == ACT
    assert decision["expected_failure_loss"] > decision["expected_action_cost"]


def test_evaluate_returns_validate_for_medium_expected_value(tmp_path):
    decision = evaluate(
        _prediction(
            risk_score=0.62,
            confidence=0.58,
            estimated_failure_cost=1.5,
            estimated_fix_cost=0.45,
        ),
        policy=_policy(tmp_path),
    )

    assert decision["decision"] == VALIDATE


def test_evaluate_returns_skip_when_action_cost_exceeds_expected_loss(tmp_path):
    decision = evaluate(
        _prediction(risk_score=0.2, confidence=0.5),
        policy=_policy(tmp_path),
    )

    assert decision["decision"] == SKIP
    assert decision["expected_failure_loss"] < decision["expected_action_cost"]


def test_evaluate_uses_policy_engine_when_supplied():
    class StubPolicy:
        def predict(self, features):
            assert features["centrality"] == 5
            return {
                "decision": ACT,
                "policy_score": 0.88,
                "explored": False,
                "features": features,
            }

    decision = decision_engine.evaluate(_prediction(), policy=StubPolicy())

    assert decision["decision"] == ACT
    assert decision["policy_score"] == 0.88
    assert decision["features"]["risk_score"] == 0.8
