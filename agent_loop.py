import patcher
import test_runner
from utils import extract_failure, log


MAX_STEPS = 5


def run_agent(repo_path):
    result = test_runner.run_tests(repo_path)
    if result["passed"]:
        log("SUCCESS: tests already pass")
        return True

    for step in range(1, MAX_STEPS + 1):
        log(f"Fix attempt {step}/{MAX_STEPS}")
        failure = extract_failure(result)
        patch = patcher.generate_patch(failure, repo_path)
        if not patch:
            log("STOPPED: mock LLM did not produce a patch")
            return False
        if not patcher.apply_patch(repo_path, patch):
            log("STOPPED: patch was unsafe or could not be applied")
            return False

        result = test_runner.run_tests(repo_path)
        if result["passed"]:
            log("SUCCESS: tests pass")
            return True

    log(f"STOPPED: tests still fail after {MAX_STEPS} fix attempts")
    return False
