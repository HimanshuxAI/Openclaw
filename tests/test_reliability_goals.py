from reliability import goals


def test_goal_round_trips_with_fixed_repair_constraints(tmp_path):
    goal = goals.start_goal("run-1", "repo-a", max_steps=5, root=tmp_path)
    progressed = goals.record_goal_step(goal, "planner", root=tmp_path)
    finished = goals.finish_goal(progressed, "passed", root=tmp_path)

    assert goal["completed_steps"] == []
    assert progressed["completed_steps"] == ["planner"]
    assert finished["state"] == "terminal"
    assert finished["terminal_state"] == "passed"
    assert goals.load_goal("run-1", root=tmp_path) == finished


def test_starting_a_run_again_creates_a_fresh_goal_instead_of_resuming_stale_state(
    tmp_path,
):
    first = goals.start_goal("run-1", "repo-a", max_steps=5, root=tmp_path)
    goals.record_goal_step(first, "planner", root=tmp_path)

    fresh = goals.start_goal("run-1", "repo-a", max_steps=5, root=tmp_path)

    assert fresh["state"] == "active"
    assert fresh["completed_steps"] == []
    assert fresh["terminal_state"] == ""


def test_load_goal_fails_closed_for_missing_or_malformed_state(tmp_path):
    assert goals.load_goal("run-1", root=tmp_path) == {}

    (tmp_path / "goal-run-1.json").write_text("not json", encoding="utf-8")

    assert goals.load_goal("run-1", root=tmp_path) == {}
