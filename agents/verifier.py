"""Classify repair outcomes from regression and full-suite test evidence."""


def verify(execution, run_subset, run_full, revert, simulation):
    """Verify an applied patch, reverting once whenever evidence is negative."""
    if not _value(execution, "applied", False):
        return _report("not_executed", False, simulation)

    patch = _value(execution, "patch", "")
    subset = _run(run_subset)
    if not _passed(subset):
        return _report(
            "regressed",
            False,
            simulation,
            subset_result=subset,
            reverted=_revert(revert, patch),
        )

    full = _run(run_full)
    if not _passed(full):
        return _report(
            "failed",
            False,
            simulation,
            subset_result=subset,
            full_result=full,
            reverted=_revert(revert, patch),
        )

    return _report(
        "passed",
        True,
        simulation,
        subset_result=subset,
        full_result=full,
    )


def _run(callback):
    try:
        return callback()
    except (OSError, RuntimeError, ValueError):
        return {}


def _revert(callback, patch):
    try:
        return bool(callback(patch))
    except (OSError, RuntimeError, ValueError):
        return False


def _passed(result):
    return isinstance(result, dict) and result.get("passed") is True


def _report(
    state,
    tests_passed,
    simulation,
    subset_result=None,
    full_result=None,
    reverted=False,
):
    return {
        "state": state,
        "tests_passed": tests_passed,
        "regression_safe": state != "regressed",
        "performance_ok": _number(simulation, "pass_likelihood") > 0.0,
        "dependency_safe": state != "not_executed",
        "subset_result": subset_result,
        "full_result": full_result,
        "reverted": reverted,
    }


def _value(mapping, key, default):
    if isinstance(mapping, dict):
        return mapping.get(key, default)
    return getattr(mapping, key, default)


def _number(mapping, key):
    try:
        return float(_value(mapping, key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
