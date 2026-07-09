from agents import planner


def _candidate(patch="diff --git a/service.py b/service.py"):
    return {"patch": patch, "score": {"confidence": 0.9}}


def test_create_plan_is_minimal_reversible_and_uses_the_top_candidate():
    candidates = [_candidate(), _candidate("second")]
    plan = planner.create_plan(
        {"risk_score": 0.9, "confidence": 0.8},
        {"decision": "ACT"},
        candidates,
        simulation={"touched_files": ["service.py"], "pass_likelihood": 0.9},
        repository_id="repo-a",
    )

    assert plan["action"] == "ACT"
    assert plan["candidate"] == candidates[0]
    assert plan["candidate_count"] == 2
    assert plan["strategy"] == "minimal_patch"
    assert plan["repository_id"] == "repo-a"
    assert plan["steps"] == [
        "analyze_context",
        "select_strategy",
        "apply_candidate",
        "verify_scope",
    ]
    assert plan["reversible"] is True
    assert plan["executable"] is True
    assert plan["plan_id"].startswith("plan-")


def test_create_plan_prefers_matching_verified_strategy_history_without_mutating_inputs():
    prediction = {"confidence": 0.9}
    decision = {"decision": "ACT"}
    candidates = [_candidate()]
    history = [
        {
            "repository_id": "repo-a",
            "action_taken": "ACT",
            "strategy": "guard_clause",
            "verified": True,
        }
    ]

    plan = planner.create_plan(
        prediction,
        decision,
        candidates,
        history=history,
        repository_id="repo-a",
    )

    assert plan["strategy"] == "guard_clause"
    assert prediction == {"confidence": 0.9}
    assert decision == {"decision": "ACT"}
    assert candidates == [_candidate()]
    assert history[0]["strategy"] == "guard_clause"


def test_create_plan_is_deterministic_and_stops_execution_without_a_candidate():
    first = planner.create_plan(
        {"confidence": 0.9},
        {"decision": "ACT"},
        [],
        repository_id="repo-a",
    )
    second = planner.create_plan(
        {"confidence": 0.9},
        {"decision": "ACT"},
        [],
        repository_id="repo-a",
    )

    assert first["plan_id"] == second["plan_id"]
    assert first["candidate"] is None
    assert first["reversible"] is False
    assert first["executable"] is False
