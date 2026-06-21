import patcher
import test_runner
from memory.patterns import extract_error_type, extract_file, normalize_error_message
from memory.selector import find_similar_cases
from memory.store import add_record, load_memory
from utils import extract_failure, log


MAX_STEPS = 5


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

    def exact(record):
        return (
            record["error_type"] == error_type
            and record["error_message"] == error_message
            and record["file"] == file
        )

    latest_outcome = {}
    for record in memory:
        if not exact(record) or not record["patch"]:
            continue
        previous = latest_outcome.get(record["patch"])
        if previous is None or record["timestamp"] >= previous[0]:
            latest_outcome[record["patch"]] = (record["timestamp"], record["success"])

    for case in find_similar_cases(failure, memory):
        outcome = latest_outcome.get(case["patch"])
        if exact(case) and case["success"] and case["patch"] and outcome and outcome[1]:
            return case["patch"]
    return ""


def run_agent(repo_path):
    result = test_runner.run_tests(repo_path)
    if result["passed"]:
        log("SUCCESS: tests already pass")
        return True

    for step in range(1, MAX_STEPS + 1):
        log(f"Fix attempt {step}/{MAX_STEPS}")
        failure = extract_failure(result)
        memory = load_memory()
        remembered_patch = _reusable_patch(failure, memory)
        patch = remembered_patch or patcher.generate_patch(failure, repo_path)
        if not patch:
            _record_attempt(failure, "", False)
            log("STOPPED: mock LLM did not produce a patch")
            return False
        if not patcher.apply_patch(repo_path, patch):
            _record_attempt(failure, patch, False)
            if not remembered_patch:
                log("STOPPED: patch was unsafe or could not be applied")
                return False
            log("Remembered patch was rejected; trying generated patch")
            patch = patcher.generate_patch(failure, repo_path)
            if not patch or patch == remembered_patch:
                if not patch:
                    _record_attempt(failure, "", False)
                log("STOPPED: no new patch was available")
                return False
            if not patcher.apply_patch(repo_path, patch):
                _record_attempt(failure, patch, False)
                log("STOPPED: generated patch was unsafe or could not be applied")
                return False

        result = test_runner.run_tests(repo_path)
        _record_attempt(failure, patch, result["passed"])
        if result["passed"]:
            log("SUCCESS: tests pass")
            return True

    log(f"STOPPED: tests still fail after {MAX_STEPS} fix attempts")
    return False
