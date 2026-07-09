from reliability import evidence


def _decision(action="ACT"):
    return {"decision": action}


def _critique(approved=True):
    return {"approved": approved}


def _simulation():
    return {
        "touched_files": ["service.py"],
        "regression_risk": 0.1,
        "pass_likelihood": 0.9,
    }


def _test_result(passed=True):
    return {"passed": passed, "output": "", "errors": "", "exit_code": 0 if passed else 1}


def test_valid_pre_execution_evidence_is_sufficient_and_low_uncertainty():
    report = evidence.assess_pre_execution(
        _decision(),
        _critique(),
        _simulation(),
    )

    assert report["stage"] == "pre_execution"
    assert report["sufficient"] is True
    assert report["score"] == 1.0
    assert report["uncertainty"] == "low"
    assert report["contract_failures"] == []


def test_insufficient_critic_evidence_downgrades_act_to_validate():
    report = evidence.assess_pre_execution(
        _decision(),
        _critique(approved=False),
        _simulation(),
    )

    assert report["sufficient"] is False
    assert report["reason"] == "critic_not_approved"
    assert evidence.downgrade_action("ACT", report) == "VALIDATE"


def test_malformed_simulation_is_contract_failure_and_never_sufficient():
    report = evidence.assess_pre_execution(
        _decision(),
        _critique(),
        {"touched_files": "service.py", "regression_risk": "low"},
    )

    assert report["sufficient"] is False
    assert "invalid_simulation" in report["contract_failures"]
    assert report["uncertainty"] == "high"


def test_malformed_tool_result_is_never_a_verified_pass():
    report = evidence.assess_verification(
        {
            "state": "passed",
            "tests_passed": True,
            "subset_result": _test_result(),
            "full_result": {"passed": "yes"},
        }
    )

    assert report["sufficient"] is False
    assert "invalid_test_result" in report["contract_failures"]


def test_valid_verification_evidence_preserves_a_verified_repair_path():
    report = evidence.assess_verification(
        {
            "state": "passed",
            "tests_passed": True,
            "subset_result": _test_result(),
            "full_result": _test_result(),
        }
    )

    assert report["sufficient"] is True
    assert report["score"] == 1.0
    assert evidence.downgrade_action("ACT", report) == "ACT"
