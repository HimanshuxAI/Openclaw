import subprocess

from failure_graph import FAILED_NODE_PATTERN, FailureGraph


RISK_THRESHOLD = 0.75
DEFAULT_WEIGHTS = {
    "failure": 0.42,
    "change": 0.28,
    "centrality": 0.30,
}


def detect_change_set(repo_path):
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {"files": [], "functions": []}
    files = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().endswith(".py")
    ]
    return {"files": files, "functions": []}


def predict_failures(change_set, graph=None, memory=None):
    graph = graph or FailureGraph()
    memory = memory or []
    changed_nodes = _changed_nodes(change_set)
    predicted = set()
    at_risk_modules = []
    for node in changed_nodes:
        if node.startswith("file:"):
            at_risk_modules.append(node.removeprefix("file:"))
        for dependent in _impacted_nodes(graph, node):
            if dependent.startswith("test_case:"):
                predicted.add(dependent.removeprefix("test_case:"))
    risk_score = compute_risk_score(change_set, graph=graph, memory=memory)
    confidence = round(
        _confidence(predicted, changed_nodes, graph) * calibration_factor(memory),
        6,
    )
    failure_frequency = _failure_frequency(changed_nodes, graph, memory)
    change_frequency = _change_frequency(changed_nodes, graph)
    dependency_centrality = _dependency_centrality(changed_nodes, graph)
    return {
        "predicted_tests": sorted(predicted),
        "at_risk_modules": sorted(dict.fromkeys(at_risk_modules)),
        "risk_score": risk_score,
        "confidence": confidence,
        "change_frequency": change_frequency,
        "failure_frequency": failure_frequency,
        "dependency_centrality": dependency_centrality,
        "estimated_fix_cost": _estimated_fix_cost(changed_nodes, dependency_centrality),
        "estimated_failure_cost": _estimated_failure_cost(
            predicted,
            failure_frequency,
            dependency_centrality,
        ),
    }


def compute_risk_score(change_set, graph=None, memory=None):
    graph = graph or FailureGraph()
    changed_nodes = _changed_nodes(change_set)
    if not changed_nodes:
        return 0.0
    scores = []
    historical = _historical_failures(memory or [])
    max_failure = max([1, *graph.failure_counts.values(), *historical.values()])
    max_change = max([1, *graph.change_counts.values()])
    for node in changed_nodes:
        failure = max(graph.failure_counts.get(node, 0), historical.get(node, 0))
        change = graph.change_counts.get(node, 0) + 1
        centrality = graph.dependency_centrality(node)
        score = (
            (failure / max_failure) * DEFAULT_WEIGHTS["failure"]
            + min(1.0, change / max_change) * DEFAULT_WEIGHTS["change"]
            + min(1.0, centrality / 5) * DEFAULT_WEIGHTS["centrality"]
        )
        scores.append(score)
    return round(min(1.0, max(scores)), 6)


def identify_hotspots(graph, limit=5):
    hotspots = []
    max_failure = max([1, *graph.failure_counts.values()])
    max_change = max([1, *graph.change_counts.values()])
    for node in graph.nodes:
        if not (node.startswith("file:") or node.startswith("function:")):
            continue
        score = (
            (graph.failure_counts.get(node, 0) / max_failure) * DEFAULT_WEIGHTS["failure"]
            + (graph.change_counts.get(node, 0) / max_change) * DEFAULT_WEIGHTS["change"]
            + min(1.0, graph.dependency_centrality(node) / 5) * DEFAULT_WEIGHTS["centrality"]
        )
        hotspots.append({"node": node, "hotspot_score": round(score, 6)})
    hotspots.sort(key=lambda item: (item["hotspot_score"], item["node"]), reverse=True)
    return hotspots[:limit]


def update_prediction_accuracy(predictions, outcomes):
    predicted = set(predictions.get("predicted_tests", []))
    actual = set(FAILED_NODE_PATTERN.findall(outcomes or ""))
    correct = predicted & actual
    false_positives = predicted - actual
    false_negatives = actual - predicted
    total_predictions = len(predicted)
    return {
        "correct_predictions": len(correct),
        "false_positives": len(false_positives),
        "false_negatives": len(false_negatives),
        "total_predictions": total_predictions,
        "prediction_accuracy": round(
            len(correct) / total_predictions if total_predictions else 1.0,
            6,
        ),
    }


def calibration_factor(records):
    values = [
        float(record.get("prediction_accuracy"))
        for record in records or []
        if isinstance(record, dict) and record.get("prediction_accuracy") is not None
    ]
    if not values:
        return 1.0
    recent = values[-10:]
    average = sum(recent) / len(recent)
    return round(max(0.25, min(1.25, 0.5 + average)), 6)


def _changed_nodes(change_set):
    nodes = []
    for file_path in change_set.get("files", []):
        nodes.append(file_path if file_path.startswith("file:") else f"file:{file_path}")
    for function in change_set.get("functions", []):
        nodes.append(function if function.startswith("function:") else f"function:{function}")
    return nodes


def _confidence(predicted, changed_nodes, graph):
    if not changed_nodes:
        return 0.0
    evidence = len(predicted)
    evidence += sum(1 for node in changed_nodes if graph.failure_counts.get(node, 0))
    evidence += sum(1 for node in changed_nodes if graph.change_counts.get(node, 0))
    return round(min(1.0, evidence / (len(changed_nodes) + 2)), 6)


def _historical_failures(memory):
    counts = {}
    for record in memory:
        file_path = record.get("file", "")
        if file_path and record.get("success") is False:
            counts[f"file:{file_path}"] = counts.get(f"file:{file_path}", 0) + 1
    return counts


def _impacted_nodes(graph, node):
    impacted = set(graph.dependents_of(node))
    direct = graph.edges.get(node, {}).get("affects", set())
    impacted.update(direct)
    for target in direct:
        impacted.update(graph.dependents_of(target))
    return impacted


def _failure_frequency(changed_nodes, graph, memory):
    historical = _historical_failures(memory or [])
    return sum(
        max(graph.failure_counts.get(node, 0), historical.get(node, 0))
        for node in changed_nodes
    )


def _change_frequency(changed_nodes, graph):
    return sum(graph.change_counts.get(node, 0) + 1 for node in changed_nodes)


def _dependency_centrality(changed_nodes, graph):
    return sum(graph.dependency_centrality(node) for node in changed_nodes)


def _estimated_fix_cost(changed_nodes, dependency_centrality):
    return round(
        min(2.0, 0.25 + len(changed_nodes) * 0.15 + dependency_centrality * 0.03),
        6,
    )


def _estimated_failure_cost(predicted, failure_frequency, dependency_centrality):
    return round(
        min(
            5.0,
            1.0
            + len(predicted) * 0.35
            + failure_frequency * 0.25
            + dependency_centrality * 0.05,
        ),
        6,
    )
