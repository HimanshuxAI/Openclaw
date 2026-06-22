import time

import patcher
import test_runner
from memory.patterns import extract_error_type, extract_file, normalize_error_message
from memory.selector import REPLAY_THRESHOLD, find_similar_cases, similarity_score
from memory.store import add_record, load_memory
from utils import extract_failure, log


MAX_STEPS = 5
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


def _record_attempt(failure, patch, success):
    error_type, error_message, file = _signature(failure)
    if not error_type or not error_message:
        return
    try:
        add_record(
            {
                "error_type": error_type,
                "error_message": error_message,
                "file": file,
                "patch": patch,
                "success": success,
            }
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


def _finish(success, metrics, started_at):
    elapsed_ms = max(0, round((time.monotonic() - started_at) * 1000))
    log(
        "METRICS: "
        f"attempts={metrics['attempts']} "
        f"model_calls={metrics['model_calls']} "
        f"memory_replays={metrics['memory_replays']} "
        f"context_tokens={metrics['context_tokens']} "
        f"elapsed_ms={elapsed_ms} "
        f"passed={str(success).lower()}"
    )
    return success


def _generated_patch(failure, repo_path, memory, run_metrics):
    generation_metrics = {}
    patch = patcher.generate_patch(
        failure,
        repo_path,
        metrics=generation_metrics,
        memory=memory,
    )
    run_metrics["model_calls"] += generation_metrics.get("model_calls", 0)
    run_metrics["context_tokens"] += generation_metrics.get("context_tokens", 0)
    return patch


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
    }
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
        memory = load_memory()
        remembered_patch = _reusable_patch(failure, memory)
        if remembered_patch:
            metrics["memory_replays"] += 1
        patch = remembered_patch or _generated_patch(
            failure, repo_path, memory, metrics
        )
        if not patch:
            _record_attempt(failure, "", False)
            log("STOPPED: no patch was produced")
            return _finish(False, metrics, started_at)
        if not patcher.apply_patch(repo_path, patch):
            _record_attempt(failure, patch, False)
            if not remembered_patch:
                log("STOPPED: patch was unsafe or could not be applied")
                return _finish(False, metrics, started_at)
            log("Remembered patch was rejected; trying generated patch")
            patch = _generated_patch(failure, repo_path, memory, metrics)
            if not patch or patch == remembered_patch:
                if not patch:
                    _record_attempt(failure, "", False)
                log("STOPPED: no new patch was available")
                return _finish(False, metrics, started_at)
            if not patcher.apply_patch(repo_path, patch):
                _record_attempt(failure, patch, False)
                log("STOPPED: generated patch was unsafe or could not be applied")
                return _finish(False, metrics, started_at)

        result = test_runner.run_tests(repo_path)
        _record_attempt(failure, patch, result["passed"])
        if result["passed"]:
            log("SUCCESS: tests pass")
            return _finish(True, metrics, started_at)
        stop_reason = _pytest_stop_reason(result)
        if stop_reason:
            log(f"STOPPED: {stop_reason}")
            return _finish(False, metrics, started_at)

    log(f"STOPPED: tests still fail after {MAX_STEPS} fix attempts")
    return _finish(False, metrics, started_at)
