import json
import os
from pathlib import Path

import pytest

from memory import phase9


def _root():
    return Path(os.environ["OPENCLAW_PHASE9_MEMORY_DIR"])


def _record(run_id="run-1", **overrides):
    record = {
        "run_id": run_id,
        "repository_id": "repo-a",
        "plan_id": "plan-1",
        "strategy": "guard_clause",
        "verified": True,
    }
    record.update(overrides)
    return record


def test_phase9_records_round_trip_in_separate_source_free_jsonl_logs():
    strategy = _record()
    decision = _record(run_id="run-2", decision="ACT")

    phase9.append_record("strategies", strategy)
    phase9.append_record("decisions", decision)

    assert phase9.default_root() == _root()
    assert phase9.load_records("strategies") == [strategy]
    assert phase9.load_records("decisions") == [decision]
    assert json.loads((_root() / "strategies.jsonl").read_text(encoding="utf-8")) == strategy
    assert json.loads((_root() / "decisions.jsonl").read_text(encoding="utf-8")) == decision


def test_phase9_load_records_treats_missing_and_malformed_content_as_empty_history():
    path = _root() / "failures.jsonl"

    assert phase9.load_records("failures") == []

    path.parent.mkdir(parents=True)
    path.write_text("not valid json\n[\"not a record\"]\n", encoding="utf-8")

    assert phase9.load_records("failures") == []


def test_phase9_load_records_skips_malformed_entries_without_losing_valid_history():
    path = _root() / "plans.jsonl"
    record = _record()
    path.parent.mkdir(parents=True)
    path.write_text(
        "not valid json\n" + json.dumps(record) + "\n" + json.dumps({"run_id": 3}) + "\n",
        encoding="utf-8",
    )

    assert phase9.load_records("plans") == [record]


def test_phase9_load_records_skips_deeply_nested_json_and_keeps_valid_history():
    path = _root() / "plans.jsonl"
    valid_record = _record(run_id="valid-run")
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


def test_phase9_append_uses_atomic_replace_and_stores_independent_copies(monkeypatch):
    record = _record(details={"state": "original"})
    path = _root() / "strategies.jsonl"
    replacements = []
    original_replace = phase9.os.replace

    def capture_replace(temporary, destination):
        replacements.append((Path(temporary), Path(destination)))
        original_replace(temporary, destination)

    monkeypatch.setattr(phase9.os, "replace", capture_replace)

    phase9.append_record("strategies", record)
    record["details"]["state"] = "mutated"
    loaded = phase9.load_records("strategies")
    loaded[0]["details"]["state"] = "changed after read"

    assert replacements == [(path.with_suffix(".jsonl.tmp"), path)]
    assert not path.with_suffix(".jsonl.tmp").exists()
    assert phase9.load_records("strategies") == [_record(details={"state": "original"})]


@pytest.mark.parametrize("name", ["unknown", "", None, 3])
def test_phase9_rejects_invalid_log_names(name):
    with pytest.raises(ValueError):
        phase9.load_records(name)
    with pytest.raises(ValueError):
        phase9.append_record(name, _record())


@pytest.mark.parametrize(
    "record",
    [
        [],
        {},
        {"run_id": 3},
        {"run_id": "run-1", "repository_id": 3},
        {"run_id": "run-1", "patch": "diff --git a/file.py"},
        {"run_id": "run-1", "source": "VALUE = 1"},
        {"run_id": "run-1", "code": "VALUE = 1"},
        {"run_id": "run-1", "code_context": "line 1"},
        {"run_id": "run-1", "details": {"code": "VALUE = 1"}},
        {"run_id": "run-1", "details": object()},
        {"run_id": "run-1", "metric": float("nan")},
    ],
)
def test_phase9_rejects_invalid_or_source_bearing_records(record):
    with pytest.raises(ValueError, match="Invalid Phase 9 record"):
        phase9.append_record("plans", record)


def test_phase9_rejects_cyclic_records_as_non_json():
    record = _record()
    record["details"] = record

    with pytest.raises(ValueError, match="Invalid Phase 9 record"):
        phase9.append_record("plans", record)
