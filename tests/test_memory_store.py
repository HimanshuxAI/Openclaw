import json

import pytest

from memory.store import MAX_RECORDS, add_record, load_memory, save_memory


def _record(number=1):
    return {
        "error_type": "AssertionError",
        "error_message": f"expected value {number}",
        "file": "test_example.py",
        "patch": f"patch-{number}",
        "success": True,
        "timestamp": f"2026-06-21T00:00:{number:02d}+00:00",
    }


def test_load_memory_returns_empty_for_missing_or_malformed_file(memory_path):
    assert load_memory() == []

    memory_path.write_text("not json", encoding="utf-8")

    assert load_memory() == []


def test_save_memory_round_trips_valid_records_atomically(memory_path):
    records = [_record()]

    save_memory(records)

    assert load_memory() == records
    assert json.loads(memory_path.read_text(encoding="utf-8")) == records
    assert not memory_path.with_suffix(".json.tmp").exists()


def test_save_memory_rejects_invalid_records():
    invalid = _record()
    del invalid["patch"]

    with pytest.raises(ValueError, match="Invalid memory record"):
        save_memory([invalid])


def test_add_record_adds_utc_timestamp_when_absent():
    record = _record()
    del record["timestamp"]

    stored = add_record(record)

    assert stored["timestamp"].endswith("+00:00")
    assert load_memory() == [stored]


def test_save_memory_keeps_only_the_latest_hundred_records():
    records = [_record(number) for number in range(1, 106)]

    save_memory(records)

    saved = load_memory()
    assert MAX_RECORDS == 100
    assert len(saved) == MAX_RECORDS
    assert saved[0]["patch"] == "patch-6"
    assert saved[-1]["patch"] == "patch-105"


def test_load_memory_ignores_invalid_records_in_an_existing_file(memory_path):
    memory_path.write_text(json.dumps([_record(), {"noise": True}]), encoding="utf-8")

    assert load_memory() == [_record()]
