import subprocess

from correctness import (
    cluster_failure,
    extract_test_intent,
    learned_signal_weights,
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
