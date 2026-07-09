import strategies


def test_strategy_module_exports_label_only_strategy_names():
    assert strategies.minimal_patch == "minimal_patch"
    assert strategies.rollback == "rollback"
    assert strategies.guard_clause == "guard_clause"
    assert strategies.retry_logic == "retry_logic"
    assert strategies.STRATEGIES == (
        strategies.minimal_patch,
        strategies.rollback,
        strategies.guard_clause,
        strategies.retry_logic,
    )


def test_strategy_selection_prefers_highest_verified_rate_for_matching_action_and_repository():
    history = [
        {
            "repository_id": "repo-a",
            "action_taken": "ACT",
            "strategy": "guard_clause",
            "verified": True,
        },
        {
            "repository_id": "repo-a",
            "action_taken": "ACT",
            "strategy": "guard_clause",
            "verified": True,
        },
        {
            "repository_id": "repo-a",
            "action_taken": "ACT",
            "strategy": "guard_clause",
            "verified": False,
        },
        {
            "repository_id": "repo-a",
            "action_taken": "ACT",
            "strategy": "minimal_patch",
            "verified": True,
        },
        {
            "repository_id": "repo-b",
            "action_taken": "ACT",
            "strategy": "retry_logic",
            "verified": True,
        },
        {
            "repository_id": "repo-a",
            "action_taken": "VALIDATE",
            "strategy": "retry_logic",
            "verified": True,
        },
    ]

    assert strategies.select_strategy("ACT", history, "repo-a") == "minimal_patch"


def test_strategy_selection_breaks_equal_verified_rates_by_strategy_name():
    history = [
        {
            "repository_id": "repo-a",
            "action_taken": "ACT",
            "strategy": "guard_clause",
            "verified": True,
        },
        {
            "repository_id": "repo-a",
            "action_taken": "ACT",
            "strategy": "retry_logic",
            "verified": True,
        },
    ]

    assert strategies.select_strategy("ACT", history, "repo-a") == "retry_logic"


def test_strategy_selection_falls_back_without_matching_history_and_never_mutates_history():
    history = [
        {
            "repository_id": "repo-b",
            "action_taken": "ACT",
            "strategy": "guard_clause",
            "verified": True,
            "patch": "not generated or altered",
        },
        {"invalid": "record"},
    ]
    expected = [record.copy() for record in history]

    assert strategies.select_strategy("ACT", history, "repo-a") == "minimal_patch"
    assert strategies.select_strategy("ACT", None, "repo-a") == "minimal_patch"
    assert history == expected
