"""Evidence and uncertainty checks that fail closed around repair actions."""

import math


ACTIONS = frozenset({"ACT", "VALIDATE", "SKIP"})


def assess_pre_execution(decision, critique, simulation):
    """Assess whether a proposed action has enough local execution evidence."""
    sources = []
    missing = []
    contract_failures = []

    if _valid_decision(decision):
        sources.append("decision")
    else:
        missing.append("decision")
        contract_failures.append("invalid_decision")

    if _valid_critique(critique):
        sources.append("critic")
        if not critique["approved"]:
            missing.append("critic_not_approved")
    else:
        missing.append("critic")
        contract_failures.append("invalid_critique")

    if valid_simulation(simulation):
        sources.append("simulation")
    else:
        missing.append("simulation")
        contract_failures.append("invalid_simulation")

    sufficient = (
        not contract_failures
        and isinstance(critique, dict)
        and critique.get("approved") is True
    )
    return _report(
        "pre_execution",
        sufficient,
        _score(sources, 3),
        sources,
        missing,
        contract_failures,
    )


def assess_verification(verification):
    """Require valid subset and full-suite evidence before accepting a repair."""
    sources = []
    missing = []
    contract_failures = []
    if not isinstance(verification, dict):
        return _report(
            "verification",
            False,
            0.0,
            sources,
            ["verification"],
            ["invalid_verification"],
        )

    if verification.get("state") == "passed" and verification.get("tests_passed") is True:
        sources.append("verification_state")
    else:
        missing.append("verification_state")

    for key in ("subset_result", "full_result"):
        if valid_test_result(verification.get(key)):
            sources.append(key)
        else:
            missing.append(key)
            contract_failures.append("invalid_test_result")

    sufficient = len(sources) == 3 and not contract_failures
    return _report(
        "verification",
        sufficient,
        _score(sources, 3),
        sources,
        missing,
        contract_failures,
    )


def downgrade_action(action, report):
    """Conservatively lower an unsupported action without inventing certainty."""
    if action != "ACT" or not isinstance(report, dict) or report.get("sufficient"):
        return action
    if report.get("uncertainty") == "high":
        return "SKIP"
    return "VALIDATE"


def valid_simulation(simulation):
    """Return whether simulation output has the fields needed for risk review."""
    return (
        isinstance(simulation, dict)
        and isinstance(simulation.get("touched_files"), list)
        and _finite_number(simulation.get("regression_risk"))
        and _finite_number(simulation.get("pass_likelihood"))
    )


def valid_test_result(result):
    """Return whether a test-run result is structurally trustworthy."""
    if not isinstance(result, dict):
        return False
    if not {"passed", "output", "errors"}.issubset(result):
        return False
    if not isinstance(result.get("passed"), bool):
        return False
    if not isinstance(result["output"], str):
        return False
    if not isinstance(result["errors"], str):
        return False
    exit_code = result.get("exit_code")
    return exit_code is None or (
        isinstance(exit_code, int) and not isinstance(exit_code, bool)
    )


def _valid_decision(decision):
    return isinstance(decision, dict) and decision.get("decision") in ACTIONS


def _valid_critique(critique):
    return isinstance(critique, dict) and isinstance(critique.get("approved"), bool)


def _finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _score(sources, total):
    return round(len(sources) / total if total else 0.0, 6)


def _report(stage, sufficient, score, sources, missing, contract_failures):
    if sufficient:
        uncertainty = "low"
    elif contract_failures:
        uncertainty = "high"
    else:
        uncertainty = "medium"
    reason = (contract_failures or missing or [""])[0]
    return {
        "stage": stage,
        "sufficient": sufficient,
        "score": score,
        "uncertainty": uncertainty,
        "sources": sources,
        "missing": missing,
        "contract_failures": contract_failures,
        "reason": reason,
    }
