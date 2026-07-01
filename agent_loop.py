import re
import time

import patcher
import predictor
import test_runner
from correctness import cluster_failure, extract_test_intent, suggest_generalizations
from failure_graph import FailureGraph
from memory.patterns import extract_error_type, extract_file, normalize_error_message
from memory.selector import (
    REPLAY_THRESHOLD,
    find_fix_templates,
    find_similar_cases,
    similarity_score,
)
from memory.store import add_record, load_memory
from rag.router import extract_pytest_node
from utils import extract_failure, log


MAX_STEPS = 5
REGRESSION_GUARD_LIMIT = 10
FAILED_NODE_PATTERN = re.compile(r"(?:^|\n)FAILED\s+([^\s]+::[^\s]+)")
PYTEST_STOP_REASONS = {
    2: "pytest was interrupted",
    3: "pytest had an internal error",
    4: "pytest could not run because of a usage error",
    5: "pytest collected no tests",
}


def _signature(failure):
    return (
        extract_error_type(failure),
        normalize_error_message(failure),
        extract_file(failure),
    )


def _phase4_summary(score):
    return {
        "cluster": score.get("cluster", ""),
        "intent_vector": score.get("intent", {}).get("vector", []),
        "confidence": float(score.get("confidence", 0.0) or 0.0),
        "score_signals": score.get("signals", {}),
    }


def _fallback_phase4(failure):
    intent = extract_test_intent(failure)
    return {
        "cluster": cluster_failure(failure),
        "intent_vector": intent["vector"],
        "confidence": 0.0,
        "score_signals": {},
    }


def _log_phase4(score):
    summary = _phase4_summary(score)
    intent = ",".join(summary["intent_vector"][:6]) or "none"
    signals = ",".join(
        f"{name}:{value:.2f}"
        for name, value in sorted(summary["score_signals"].items())
        if isinstance(value, (int, float))
    ) or "none"
    log(
        "PHASE4: "
        f"cluster={summary['cluster'] or 'unknown'} "
        f"intent={intent} "
        f"confidence={summary['confidence']:.2f} "
        f"signals={signals}"
    )


def _record_attempt(failure, patch, success, score=None, outcome=None):
    error_type, error_message, file = _signature(failure)
    if not error_type or not error_message:
        return
    phase4 = _phase4_summary(score or {}) if score else _fallback_phase4(failure)
    outcome = outcome or ("passed" if success else "failed")
    try:
        add_record(
            {
                "error_type": error_type,
                "error_message": error_message,
                "file": file,
                "patch": patch,
                "success": success,
                "cluster": phase4["cluster"],
                "intent_vector": phase4["intent_vector"],
                "score": phase4["confidence"],
                "confidence": phase4["confidence"],
                "score_signals": phase4["score_signals"],
                "outcome": outcome,
            }
        )
        log(
            "LEARNING: "
            f"cluster={phase4['cluster'] or 'unknown'} "
            f"confidence={phase4['confidence']:.2f} "
            f"outcome={outcome}"
        )
    except (OSError, ValueError):
        log("Memory write skipped")


def _reusable_patch(failure, memory):
    error_type, error_message, file = _signature(failure)
    if not error_type or not error_message or not file:
        return ""

    for match in find_similar_cases(failure, memory):
        case = match["record"]
        patch = case["patch"]
        if match["score"] < REPLAY_THRESHOLD or not case["success"] or not patch:
            continue
        comparable = [
            record
            for record in memory
            if record["patch"] == patch
            and similarity_score(failure, record) >= REPLAY_THRESHOLD
        ]
        latest = max(comparable, key=lambda record: record["timestamp"], default=None)
        if latest and latest["success"]:
            return patch
    return ""


def _template_patches(failure, memory):
    patches = []
    for template in find_fix_templates(failure, memory):
        patch = template["record"]["patch"]
        if patch and patch not in patches:
            patches.append(patch)
    return patches


def _finish(success, metrics, started_at):
    elapsed_ms = max(0, round((time.monotonic() - started_at) * 1000))
    fix_multiplication = metrics["propagated_fixes"] / max(1, metrics["attempts"])
    log(
        "METRICS: "
        f"attempts={metrics['attempts']} "
        f"model_calls={metrics['model_calls']} "
        f"memory_replays={metrics['memory_replays']} "
        f"context_tokens={metrics['context_tokens']} "
        f"propagated_fixes={metrics['propagated_fixes']} "
        f"regression_rejections={metrics['regression_rejections']} "
        f"fix_multiplication={fix_multiplication:.2f} "
        f"elapsed_ms={elapsed_ms} "
        f"passed={str(success).lower()}"
    )
    return success


def _generated_patch(failure, repo_path, memory, run_metrics):
    generation_metrics = {}
    patches = patcher.generate_patch_candidates(
        failure,
        repo_path,
        metrics=generation_metrics,
        memory=memory,
    )
    run_metrics["model_calls"] += generation_metrics.get("model_calls", 0)
    run_metrics["context_tokens"] += generation_metrics.get("context_tokens", 0)
    return patches


def _failing_test_nodes(failure):
    nodes = set(FAILED_NODE_PATTERN.findall(failure))
    node = extract_pytest_node(failure)
    if node:
        nodes.add(f"{node[0]}::{node[1]}")
    return nodes


def _failure_count(failure):
    nodes = _failing_test_nodes(failure)
    return len(nodes) if nodes else 1


def _regression_nodes(repo_path, failure):
    failing = _failing_test_nodes(failure)
    if not failing:
        return []
    return [
        node
        for node in test_runner.collect_tests(repo_path)
        if node not in failing
    ][:REGRESSION_GUARD_LIMIT]


def _regression_guard(repo_path, failure, patch, baseline_nodes=None):
    del failure, patch
    nodes = baseline_nodes if baseline_nodes is not None else []
    if not nodes:
        return True
    result = test_runner.run_test_subset(repo_path, nodes)
    return result["passed"]


def _candidate_patches(failure, repo_path, memory, metrics, include_generated=True):
    patches = []
    remembered_patch = _reusable_patch(failure, memory)
    if remembered_patch:
        metrics["memory_replays"] += 1
        return [remembered_patch]
    template_patches = _template_patches(failure, memory)
    for patch in template_patches:
        if patch not in patches:
            metrics["memory_replays"] += 1
            patches.append(patch)
    if patches or not include_generated:
        return patches
    return _generated_patch(failure, repo_path, memory, metrics)


def _try_ranked_candidates(repo_path, failure, ranked, baseline_nodes):
    applied_candidate = False
    for candidate in ranked:
        patch = candidate["patch"]
        score = candidate.get("score", {})
        _log_phase4(score)
        if not patcher.apply_patch(repo_path, patch):
            _record_attempt(failure, patch, False, score)
            continue
        applied_candidate = True
        if not _regression_guard(repo_path, failure, patch, baseline_nodes):
            _record_attempt(failure, patch, False, score)
            patcher.revert_patch(repo_path, patch)
            log("Rejected candidate: regression guard failed")
            continue
        return patch, test_runner.run_tests(repo_path), applied_candidate
    return "", None, applied_candidate


def _log_root_causes(graph, failure):
    nodes = _failing_test_nodes(failure)
    if not nodes:
        return
    graph.update_after_test_run(failure)
    causes = graph.get_root_causes(sorted(nodes))[:3]
    if not causes:
        return
    summary = ",".join(f"{cause['node']}:{cause['score']:.2f}" for cause in causes)
    log(f"PHASE5: root_causes={summary}")


def _apply_generalizations(repo_path, patch, metrics):
    candidates = patcher.safe_generalization_patches(repo_path, patch)
    propagated = 0
    for candidate in candidates:
        if not patcher.apply_patch(repo_path, candidate):
            continue
        result = test_runner.run_tests(repo_path)
        if result["passed"]:
            propagated += 1
            metrics["propagated_fixes"] += 1
            continue
        metrics["regression_rejections"] += 1
        patcher.revert_patch(repo_path, candidate)
    suggested = max(0, len(suggest_generalizations(repo_path, patch)) - propagated)
    metrics["suggested_generalizations"] += suggested
    log(f"GENERALIZATION: propagated={propagated} suggested={suggested}")
    return propagated


def _pytest_stop_reason(result):
    exit_code = result.get("exit_code", 1)
    if exit_code in (0, 1):
        return ""
    return PYTEST_STOP_REASONS.get(exit_code, f"pytest exited with code {exit_code}")


def run_agent(repo_path):
    started_at = time.monotonic()
    metrics = {
        "attempts": 0,
        "model_calls": 0,
        "memory_replays": 0,
        "context_tokens": 0,
        "propagated_fixes": 0,
        "suggested_generalizations": 0,
        "regression_rejections": 0,
    }
    graph = FailureGraph.build(repo_path)
    result = test_runner.run_tests(repo_path)
    if result["passed"]:
        log("SUCCESS: tests already pass")
        return _finish(True, metrics, started_at)
    stop_reason = _pytest_stop_reason(result)
    if stop_reason:
        log(f"STOPPED: {stop_reason}")
        return _finish(False, metrics, started_at)

    for step in range(1, MAX_STEPS + 1):
        metrics["attempts"] += 1
        log(f"Fix attempt {step}/{MAX_STEPS}")
        failure = extract_failure(result)
        _log_root_causes(graph, failure)
        memory = load_memory()
        memory_patches = _candidate_patches(
            failure, repo_path, memory, metrics, include_generated=False
        )
        generated_used = False
        patches = memory_patches
        if not patches:
            patches = _generated_patch(failure, repo_path, memory, metrics)
            generated_used = True
        ranked = patcher.rank_patch_candidates(repo_path, patches, failure, memory=memory)
        if not ranked and not generated_used:
            patches = _generated_patch(failure, repo_path, memory, metrics)
            generated_used = True
            ranked = patcher.rank_patch_candidates(
                repo_path, patches, failure, memory=memory
            )
        if not ranked:
            _record_attempt(failure, "", False)
            log("STOPPED: no confident patch was produced")
            return _finish(False, metrics, started_at)

        baseline_nodes = _regression_nodes(repo_path, failure)
        patch, candidate_result, applied_candidate = _try_ranked_candidates(
            repo_path, failure, ranked, baseline_nodes
        )
        if not patch and not generated_used:
            generated = _generated_patch(failure, repo_path, memory, metrics)
            generated_used = True
            ranked = patcher.rank_patch_candidates(
                repo_path, generated, failure, memory=memory
            )
            patch, candidate_result, applied_candidate = _try_ranked_candidates(
                repo_path, failure, ranked, baseline_nodes
            )

        if patch and candidate_result:
            previous_failure_count = _failure_count(failure)
            result = candidate_result
            score = next(
                (
                    candidate.get("score", {})
                    for candidate in ranked
                    if candidate.get("patch") == patch
                ),
                {},
            )
            outcome = "passed" if result["passed"] else "failed"
            if (
                not result["passed"]
                and _failure_count(extract_failure(result)) < previous_failure_count
            ):
                outcome = "partial"
            _record_attempt(failure, patch, result["passed"], score, outcome=outcome)
            if result["passed"]:
                _apply_generalizations(repo_path, patch, metrics)
                log("SUCCESS: tests pass")
                return _finish(True, metrics, started_at)
            stop_reason = _pytest_stop_reason(result)
            if stop_reason:
                log(f"STOPPED: {stop_reason}")
                return _finish(False, metrics, started_at)
            continue

        if not applied_candidate:
            log("STOPPED: patch was unsafe or could not be applied")
            return _finish(False, metrics, started_at)
        log("STOPPED: all ranked patches were rejected")
        return _finish(False, metrics, started_at)

    log(f"STOPPED: tests still fail after {MAX_STEPS} fix attempts")
    return _finish(False, metrics, started_at)
