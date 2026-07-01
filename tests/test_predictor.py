import subprocess

from failure_graph import FailureGraph
from predictor import (
    compute_risk_score,
    identify_hotspots,
    predict_failures,
    update_prediction_accuracy,
)


def test_predict_failures_uses_changed_nodes_history_and_dependents(git_repo):
    (git_repo / "service.py").write_text(
        "def normalize(value):\n    return value.strip()\n", encoding="utf-8"
    )
    tests = git_repo / "tests"
    tests.mkdir()
    (tests / "test_service.py").write_text(
        "from service import normalize\n\n"
        "def test_normalize():\n"
        "    assert normalize(' x ') == 'x'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(git_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qm", "predict"], check=True)
    graph = FailureGraph.build(git_repo)
    graph.update_after_change({"files": ["service.py"]})
    graph.update_after_test_run(
        "FAILED tests/test_service.py::test_normalize - AssertionError"
    )

    prediction = predict_failures({"files": ["service.py"]}, graph=graph)

    assert prediction["predicted_tests"] == ["tests/test_service.py::test_normalize"]
    assert prediction["at_risk_modules"] == ["service.py"]
    assert prediction["risk_score"] > 0.5
    assert prediction["confidence"] > 0


def test_compute_risk_score_increases_for_hot_changed_files():
    graph = FailureGraph()
    graph.nodes.update({"file:core.py", "test_case:tests/test_core.py::test_core"})
    graph._add_edge("file:core.py", "affects", "test_case:tests/test_core.py::test_core")
    graph._rebuild_reverse_edges()
    graph.failure_counts["file:core.py"] = 3
    graph.change_counts["file:core.py"] = 4

    risk = compute_risk_score({"files": ["core.py"]}, graph=graph)

    assert risk > 0.7


def test_identify_hotspots_ranks_failure_change_and_centrality():
    graph = FailureGraph()
    graph.nodes.update({"file:core.py", "file:leaf.py", "function:core.py::parse"})
    graph._add_edge("file:core.py", "affects", "function:core.py::parse")
    graph._add_edge("file:leaf.py", "imports", "file:core.py")
    graph._rebuild_reverse_edges()
    graph.failure_counts["file:core.py"] = 3
    graph.change_counts["file:core.py"] = 2

    hotspots = identify_hotspots(graph, limit=2)

    assert hotspots[0]["node"] == "file:core.py"
    assert hotspots[0]["hotspot_score"] > hotspots[-1]["hotspot_score"]


def test_update_prediction_accuracy_reports_calibration_counts():
    metrics = update_prediction_accuracy(
        {"predicted_tests": ["tests/test_a.py::test_a", "tests/test_b.py::test_b"]},
        "FAILED tests/test_a.py::test_a - AssertionError\n"
        "FAILED tests/test_c.py::test_c - AssertionError",
    )

    assert metrics["correct_predictions"] == 1
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["prediction_accuracy"] == 0.5
