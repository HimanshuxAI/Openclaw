import subprocess

from correctness import (
    cluster_failure,
    decision_metrics,
    prediction_accuracy,
    extract_test_intent,
    impact_score,
    learned_signal_weights,
    regression_risk,
    simulate_patch,
    suggest_generalizations,
)


def test_cluster_failure_groups_common_failure_types():
    assert cluster_failure("E   AssertionError: expected 5") == "assertion"
    assert cluster_failure("E   TypeError: unsupported operand") == "type_error"
    assert cluster_failure("E   ModuleNotFoundError: No module named 'service'") == "import"
    assert cluster_failure("FAILED tests/test_calc.py::test_add\nE   assert -1 == 5") == "assertion"


def test_extract_test_intent_captures_assertions_values_and_identifiers():
    failure = """FAILED tests/test_calc.py::test_add
>       assert add(2, 3) == 5
E       assert -1 == 5
E        +  where -1 = add(2, 3)
"""

    intent = extract_test_intent(failure)

    assert intent["cluster"] == "assertion"
    assert intent["node"] == "tests/test_calc.py::test_add"
    assert "assert add(2, 3) == 5" in intent["assertions"]
    assert "5" in intent["expected"]
    assert "-1" in intent["actual"]
    assert "add" in intent["identifiers"]
    assert {"add", "5"}.issubset(set(intent["vector"]))


def test_learned_signal_weights_move_toward_successful_predictors():
    memory = [
        {
            "cluster": "assertion",
            "score_signals": {"intent": 0.90, "minimality": 0.20},
            "success": True,
        },
        {
            "cluster": "assertion",
            "score_signals": {"intent": 0.10, "minimality": 0.95},
            "success": False,
        },
    ]

    weights = learned_signal_weights(memory, "assertion")

    assert weights["intent"] > weights["minimality"]


def test_learned_signal_weights_ignore_partial_repairs():
    memory = [
        {
            "cluster": "assertion",
            "score_signals": {"minimality": 1.0, "relevance": 1.0},
            "success": False,
            "outcome": "partial",
        }
    ]

    weights = learned_signal_weights(memory, "assertion")

    assert weights["minimality"] == 0.18
    assert weights["relevance"] == 0.16


def test_prediction_accuracy_summarizes_false_positive_and_negative_rates():
    metrics = prediction_accuracy(
        [
            {"correct_predictions": 2, "false_positives": 1, "false_negatives": 1},
            {"correct_predictions": 1, "false_positives": 0, "false_negatives": 2},
        ]
    )

    assert metrics["prediction_accuracy"] == 0.75
    assert metrics["false_positive_rate"] == 0.25
    assert metrics["false_negative_rate"] == 0.5


def test_decision_metrics_summarize_cost_and_action_quality():
    metrics = decision_metrics(
        [
            {"decision": "ACT", "outcome": "prevented", "cost_saved": 1.5},
            {"decision": "ACT", "outcome": "unnecessary", "cost_saved": -0.5},
            {"decision": "VALIDATE", "outcome": "validated", "cost_saved": 0.0},
        ]
    )

    assert metrics["decision_accuracy"] == 0.5
    assert metrics["prevented_failures"] == 1
    assert metrics["unnecessary_actions"] == 1
    assert metrics["cost_saved"] == 1.0


def test_suggest_generalizations_finds_same_line_replacement_elsewhere(git_repo):
    (git_repo / "alpha.py").write_text(
        "def total(items):\n    return len(items) + 1\n", encoding="utf-8"
    )
    (git_repo / "beta.py").write_text(
        "def count(items):\n    return len(items) + 1\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(git_repo), "add", "alpha.py", "beta.py"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "add counters"], check=True)
    patch = """diff --git a/alpha.py b/alpha.py
--- a/alpha.py
+++ b/alpha.py
@@ -1,2 +1,2 @@
 def total(items):
-    return len(items) + 1
+    return len(items)
"""

    suggestions = suggest_generalizations(git_repo, patch)

    assert len(suggestions) == 1
    assert "diff --git a/beta.py b/beta.py" in suggestions[0]
    assert "-    return len(items) + 1" in suggestions[0]
    assert "+    return len(items)" in suggestions[0]


def test_simulate_patch_reports_dependents_patterns_and_risk(git_repo):
    (git_repo / "service.py").write_text(
        "def normalize(value):\n    return value.strip()\n", encoding="utf-8"
    )
    (git_repo / "api.py").write_text(
        "from service import normalize\n\n"
        "def clean(value):\n"
        "    return normalize(value)\n",
        encoding="utf-8",
    )
    tests = git_repo / "tests"
    tests.mkdir()
    (tests / "test_api.py").write_text(
        "from api import clean\n\n"
        "def test_clean():\n"
        "    assert clean(' x ') == 'x'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "simulation"], check=True)
    patch = """diff --git a/service.py b/service.py
--- a/service.py
+++ b/service.py
@@ -1,2 +1,2 @@
 def normalize(value):
-    return value.strip()
+    return value.strip().lower()
"""

    simulation = simulate_patch(git_repo, patch)

    assert simulation["touched_files"] == ["service.py"]
    assert "function:service.py::normalize" in simulation["touched_nodes"]
    assert "test_case:tests/test_api.py::test_clean" in simulation["dependent_tests"]
    assert simulation["impact_score"] > 0
    assert 0 <= simulation["regression_risk"] <= 1
    assert simulation["pass_likelihood"] < 1
    assert impact_score(git_repo, patch) == simulation["impact_score"]
    assert regression_risk(git_repo, patch) == simulation["regression_risk"]
