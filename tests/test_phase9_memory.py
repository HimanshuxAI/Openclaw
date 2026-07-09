import json
import multiprocessing
import os
from pathlib import Path
import time

import pytest

from memory import phase9


def _root():
    return Path(os.environ["OPENCLAW_PHASE9_MEMORY_DIR"])


def _record(name, **overrides):
    common = {
        "run_id": "run-1",
        "repository_id": "repo-a",
        "plan_id": "plan-1",
    }
    records = {
        "decisions": common
        | {
            "proposed_action": "ACT",
            "action_taken": "ACT",
            "verification_state": "passed",
            "evidence_score": 0.8,
            "uncertainty": "low",
            "reason": "verified",
        },
        "plans": common
        | {
            "action": "ACT",
            "strategy": "minimal_patch",
            "candidate_count": 1,
            "reversible": True,
            "executable": True,
            "steps": ["analyze_context", "verify_scope"],
            "impact_score": 1.0,
            "regression_risk": 0.1,
            "pass_likelihood": 0.9,
        },
        "failures": common
        | {
            "verification_state": "failed",
            "reason": "test_failure",
            "tool_contract_failures": ["invalid_test_result"],
        },
        "strategies": common
        | {
            "strategy": "guard_clause",
            "action_taken": "ACT",
            "verified": True,
            "failure_cost_saved": 1.5,
            "action_cost": 0.3,
        },
    }
    record = records[name].copy()
    record.update(overrides)
    return record


def _append_strategy_after_start(root, run_id, start):
    start.wait(timeout=10)
    phase9.append_record(
        "strategies",
        _record("strategies", run_id=run_id),
        root=root,
    )


@pytest.mark.parametrize("name", sorted(phase9.LOG_NAMES))
def test_phase9_records_round_trip_in_separate_source_free_jsonl_logs(name):
    record = _record(name)

    phase9.append_record(name, record)

    assert phase9.default_root() == _root()
    assert phase9.load_records(name) == [record]
    assert json.loads((_root() / f"{name}.jsonl").read_text(encoding="utf-8")) == record


def test_phase9_load_records_treats_missing_and_malformed_content_as_empty_history():
    path = _root() / "failures.jsonl"

    assert phase9.load_records("failures") == []

    path.parent.mkdir(parents=True)
    path.write_text("not valid json\n[\"not a record\"]\n", encoding="utf-8")

    assert phase9.load_records("failures") == []


def test_phase9_load_records_skips_malformed_entries_without_losing_valid_history():
    path = _root() / "plans.jsonl"
    record = _record("plans")
    path.parent.mkdir(parents=True)
    path.write_text(
        "not valid json\n" + json.dumps(record) + "\n" + json.dumps({"run_id": 3}) + "\n",
        encoding="utf-8",
    )

    assert phase9.load_records("plans") == [record]


def test_phase9_load_records_skips_deeply_nested_json_and_keeps_valid_history():
    path = _root() / "plans.jsonl"
    valid_record = _record("plans", run_id="valid-run")
    deeply_nested_record = (
        '{"run_id":"deep-run","details":'
        + '{"details":' * 500
        + "null"
        + "}" * 500
        + "}"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        deeply_nested_record + "\n" + json.dumps(valid_record) + "\n",
        encoding="utf-8",
    )

    assert phase9.load_records("plans") == [valid_record]


def test_phase9_append_uses_a_lock_unique_temp_and_keeps_sequential_appends(monkeypatch):
    lock_calls = []
    replacements = []
    temporary_paths = []
    original_flock = phase9.fcntl.flock
    original_replace = phase9.os.replace
    original_mkstemp = phase9.tempfile.mkstemp

    def capture_flock(handle, operation):
        lock_calls.append(operation)
        return original_flock(handle, operation)

    def capture_replace(temporary, destination):
        replacements.append((Path(temporary), Path(destination)))
        return original_replace(temporary, destination)

    def capture_mkstemp(*args, **kwargs):
        descriptor, temporary = original_mkstemp(*args, **kwargs)
        temporary_paths.append(Path(temporary))
        return descriptor, temporary

    monkeypatch.setattr(phase9.fcntl, "flock", capture_flock)
    monkeypatch.setattr(phase9.os, "replace", capture_replace)
    monkeypatch.setattr(phase9.tempfile, "mkstemp", capture_mkstemp)

    first = _record("strategies", run_id="run-1")
    second = _record("strategies", run_id="run-2")
    phase9.append_record("strategies", first)
    phase9.append_record("strategies", second)

    assert phase9.load_records("strategies") == [first, second]
    assert len(set(temporary_paths)) == 2
    assert all(path.parent == _root() for path in temporary_paths)
    assert all(not path.exists() for path in temporary_paths)
    assert len(replacements) == 2
    assert phase9.fcntl.LOCK_EX in lock_calls
    assert phase9.fcntl.LOCK_UN in lock_calls


def test_phase9_lock_keeps_all_simultaneous_same_log_appends(monkeypatch):
    context = multiprocessing.get_context("fork")
    start = context.Event()
    original_read_records = phase9._read_records

    def delayed_read_records(name, path):
        records = original_read_records(name, path)
        time.sleep(0.05)
        return records

    monkeypatch.setattr(phase9, "_read_records", delayed_read_records)
    processes = [
        context.Process(
            target=_append_strategy_after_start,
            args=(str(_root()), f"run-{index}", start),
        )
        for index in range(4)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=10)

    assert all(process.exitcode == 0 for process in processes)
    assert {record["run_id"] for record in phase9.load_records("strategies")} == {
        "run-0",
        "run-1",
        "run-2",
        "run-3",
    }


@pytest.mark.parametrize("name", ["unknown", "", None, 3])
def test_phase9_rejects_invalid_log_names(name):
    with pytest.raises(ValueError):
        phase9.load_records(name)
    with pytest.raises(ValueError):
        phase9.append_record(name, _record("plans"))


@pytest.mark.parametrize(
    ("name", "record"),
    [
        ("plans", {"run_id": "run-1"}),
        ("decisions", _record("decisions", diff="def leaked(): pass")),
        (
            "plans",
            _record("plans", candidate_text="def leaked(): pass"),
        ),
        ("failures", _record("failures", tool_contract_failures=["invalid result"])),
        ("strategies", _record("strategies", verified=1)),
        ("strategies", _record("strategies", action_cost=float("nan"))),
    ],
)
def test_phase9_rejects_unknown_source_bearing_or_schema_invalid_records(name, record):
    with pytest.raises(ValueError, match="Invalid Phase 9 record"):
        phase9.append_record(name, record)


@pytest.mark.parametrize("name", sorted(phase9.LOG_NAMES))
def test_phase9_rejects_every_missing_required_field(name):
    record = _record(name)
    for field in tuple(record):
        incomplete = record.copy()
        del incomplete[field]
        with pytest.raises(ValueError, match="Invalid Phase 9 record"):
            phase9.append_record(name, incomplete)


def test_phase9_rejects_cyclic_records_as_non_json():
    record = _record("plans")
    record["steps"].append(record)

    with pytest.raises(ValueError, match="Invalid Phase 9 record"):
        phase9.append_record("plans", record)
