import inspect

from agents import critic


def _safe_plan(action="ACT", candidate=True):
    return {
        "action": action,
        "candidate": {"patch": "diff"} if candidate else None,
        "executable": candidate,
    }


def _safe_prediction(confidence=0.9):
    return {"confidence": confidence}


def _safe_simulation(touched_files=None, regression_risk=0.1):
    return {
        "touched_files": touched_files or ["service.py"],
        "regression_risk": regression_risk,
    }


def test_critic_approves_a_safe_one_file_plan():
    review = critic.review_plan(
        _safe_plan(),
        _safe_prediction(),
        _safe_simulation(),
    )

    assert review == {
        "approved": True,
        "action": "ACT",
        "risks": [],
        "revision_required": False,
    }


def test_critic_downgrades_act_for_low_confidence_high_risk_or_broad_scope():
    review = critic.review_plan(
        _safe_plan(),
        _safe_prediction(confidence=0.2),
        _safe_simulation(touched_files=["a.py", "b.py"], regression_risk=0.5),
    )

    assert review["approved"] is False
    assert review["action"] == "VALIDATE"
    assert review["risks"] == [
        "broad_scope",
        "low_confidence",
        "high_regression_risk",
    ]
    assert review["revision_required"] is True


def test_critic_stops_when_an_act_plan_has_no_candidate():
    review = critic.review_plan(
        _safe_plan(candidate=False),
        _safe_prediction(),
        _safe_simulation(),
    )

    assert review["approved"] is False
    assert review["action"] == "SKIP"
    assert review["risks"] == ["missing_candidate"]


def test_critic_is_tool_free():
    source = inspect.getsource(critic)

    assert "patcher" not in source
    assert "test_runner" not in source
