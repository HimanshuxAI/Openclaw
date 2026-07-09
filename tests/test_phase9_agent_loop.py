import agent_loop
from memory import phase9
from reliability import goals


def _prediction():
    return {
        "predicted_tests": [],
        "at_risk_modules": ["service.py"],
        "risk_score": 0.9,
        "confidence": 0.9,
        "change_frequency": 2,
        "failure_frequency": 3,
        "dependency_centrality": 4,
        "estimated_fix_cost": 0.2,
        "estimated_failure_cost": 2.0,
    }


def _policy(updates):
    class StubPolicy:
        def predict(self, features):
            return {
                "decision": "ACT",
                "features": features,
                "policy_score": 0.9,
                "explored": False,
            }

        def update(self, decision, outcome):
            updates.append((decision, outcome))
            return {
                "reward": 1.2,
                "weights": {"risk_score": 0.4},
                "epsilon": 0.09,
                "threshold": 0.7,
                "lower_threshold": 0.35,
            }

    return StubPolicy()


def _outcome(decision, state="passed", authorized=True, reason=""):
    action = decision["decision"]
    return {
        "plan": {
            "plan_id": "plan-1",
            "repository_id": "repo-a",
            "action": action,
            "strategy": "minimal_patch",
            "candidate_count": 1,
            "reversible": True,
            "executable": action == "ACT",
            "steps": ["analyze_context", "verify_scope"],
            "simulation": {
                "impact_score": 1.0,
                "regression_risk": 0.1,
                "pass_likelihood": 0.9,
            },
        },
        "critique": {"risks": [] if authorized else ["low_confidence"]},
        "actual_decision": {**decision, "decision": action},
        "pre_evidence": {
            "sufficient": authorized,
            "score": 0.9 if authorized else 0.0,
            "uncertainty": "low" if authorized else "high",
            "contract_failures": [] if authorized else ["invalid_simulation"],
            "reason": reason,
        },
        "post_evidence": {"sufficient": state == "passed"},
        "authorization": {"authorized": authorized, "reason": reason},
        "execution": {"applied": authorized and action == "ACT", "patch": "patch-a"},
        "verification": {
            "state": state,
            "tests_passed": state == "passed",
            "reverted": state == "regressed",
        },
        "critic_rounds": 1,
    }


def _install_prediction(monkeypatch):
    monkeypatch.setattr(
        agent_loop.predictor,
        "detect_change_set",
        lambda path: {"files": ["service.py"], "functions": []},
    )
    monkeypatch.setattr(
        agent_loop.predictor,
        "predict_failures",
        lambda *args, **kwargs: _prediction(),
    )


def test_preemptive_action_records_phase9_evidence_and_updates_policy_once(
    monkeypatch, tmp_path, capsys
):
    updates = []
    coordinator_calls = []
    _install_prediction(monkeypatch)
    monkeypatch.setattr(agent_loop, "_run_id", lambda: "run-fixed")
    monkeypatch.setattr(agent_loop.policy_engine, "PolicyEngine", lambda: _policy(updates))
    monkeypatch.setattr(
        agent_loop.coordinator,
        "run_candidate",
        lambda *args, **kwargs: coordinator_calls.append((args, kwargs))
        or _outcome(args[2]),
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda *args, **kwargs: ["patch-a"],
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "rank_patch_candidates",
        lambda *args, **kwargs: [{"patch": "patch-a", "score": {"confidence": 0.9}}],
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("direct apply")),
    )
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: {"passed": True, "output": "", "errors": "", "exit_code": 0},
    )

    assert agent_loop.run_agent(tmp_path) is True

    assert len(coordinator_calls) == 1
    assert len(updates) == 1
    assert updates[0][0]["decision"] == "ACT"
    assert phase9.load_records("decisions")
    assert phase9.load_records("plans")
    assert phase9.load_records("strategies")
    goal = goals.load_goal("run-fixed")
    assert goal["state"] == "terminal"
    assert goal["completed_steps"] == ["planner", "critic", "executor", "verifier"]
    output = capsys.readouterr().out
    assert "PHASE9:" in output
    assert "PHASE10:" in output
    assert "plan_success_rate=" in output
    assert "evidence_gate_rejections=" in output


def test_guard_rejection_never_directly_applies_a_patch_and_updates_policy_once(
    monkeypatch, tmp_path
):
    updates = []
    _install_prediction(monkeypatch)
    monkeypatch.setattr(agent_loop.policy_engine, "PolicyEngine", lambda: _policy(updates))
    monkeypatch.setattr(
        agent_loop.coordinator,
        "run_candidate",
        lambda *args, **kwargs: _outcome(
            {**args[2], "decision": "SKIP"},
            state="not_executed",
            authorized=False,
            reason="insufficient_evidence",
        ),
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "generate_patch_candidates",
        lambda *args, **kwargs: ["patch-a"],
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "rank_patch_candidates",
        lambda *args, **kwargs: [{"patch": "patch-a", "score": {"confidence": 0.9}}],
    )
    monkeypatch.setattr(
        agent_loop.patcher,
        "apply_patch",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("direct apply")),
    )
    monkeypatch.setattr(
        agent_loop.test_runner,
        "run_tests",
        lambda path: {"passed": True, "output": "", "errors": "", "exit_code": 0},
    )

    assert agent_loop.run_agent(tmp_path) is True

    assert len(updates) == 1
    assert updates[0][0]["decision"] == "SKIP"
