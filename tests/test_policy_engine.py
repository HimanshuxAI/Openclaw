import json

import policy_engine


def test_compute_reward_rewards_prevented_failures_and_penalizes_misses():
    assert policy_engine.compute_reward(
        {
            "action_taken": "ACT",
            "actual_outcome": "SUCCESS",
            "failure_cost_saved": 2.5,
            "actual_cost": 0.4,
        }
    ) == 2.5
    assert policy_engine.compute_reward(
        {
            "action_taken": "ACT",
            "actual_outcome": "FAILURE",
            "actual_cost": 0.6,
        }
    ) == -0.6
    assert policy_engine.compute_reward(
        {
            "action_taken": "SKIP",
            "actual_outcome": "FAILURE",
            "failure_cost": 3.0,
        }
    ) == -3.0


def test_policy_predicts_with_linear_score_and_thresholds(tmp_path):
    engine = policy_engine.PolicyEngine(
        path=tmp_path / "policy_history.jsonl",
        state_path=tmp_path / "policy_state.json",
        epsilon=0.0,
        weights={
            "risk_score": 0.6,
            "confidence": 0.4,
            "failure_frequency": 0.0,
            "change_frequency": 0.0,
            "centrality": 0.0,
        },
        threshold=0.7,
        lower_threshold=0.35,
    )

    assert engine.predict({"risk_score": 0.9, "confidence": 0.8})["decision"] == "ACT"
    assert (
        engine.predict({"risk_score": 0.4, "confidence": 0.35})["decision"]
        == "VALIDATE"
    )
    assert engine.predict({"risk_score": 0.1, "confidence": 0.2})["decision"] == "SKIP"


def test_update_appends_history_and_adjusts_policy_weights(tmp_path):
    engine = policy_engine.PolicyEngine(
        path=tmp_path / "policy_history.jsonl",
        state_path=tmp_path / "policy_state.json",
        epsilon=0.0,
        learning_rate=0.1,
        threshold=0.15,
        lower_threshold=0.05,
        weights={
            "risk_score": 0.1,
            "confidence": 0.1,
            "failure_frequency": 0.0,
            "change_frequency": 0.0,
            "centrality": 0.0,
        },
    )
    decision = engine.predict({"risk_score": 1.0, "confidence": 1.0})

    updated = engine.update(
        decision,
        {
            "actual_outcome": "SUCCESS",
            "actual_cost": 0.25,
            "failure_cost_saved": 1.5,
            "failure_cost": 1.5,
        },
    )

    assert updated["reward"] == 1.5
    assert updated["weights"]["risk_score"] > 0.1
    assert updated["epsilon"] < 0.1
    lines = (tmp_path / "policy_history.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert entry["risk_score"] == 1.0
    assert entry["action_taken"] == decision["decision"]
    assert entry["actual_outcome"] == "SUCCESS"
    assert entry["reward"] == 1.5


def test_epsilon_exploration_can_take_random_action(tmp_path):
    engine = policy_engine.PolicyEngine(
        path=tmp_path / "policy_history.jsonl",
        state_path=tmp_path / "policy_state.json",
        epsilon=1.0,
        random_seed=7,
    )

    decision = engine.predict({"risk_score": 0.99, "confidence": 0.99})

    assert decision["decision"] in {"ACT", "VALIDATE", "SKIP"}
    assert decision["explored"] is True
