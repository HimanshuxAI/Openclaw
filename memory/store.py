from datetime import datetime, timezone
import json
import os
from pathlib import Path


MAX_RECORDS = 100
REQUIRED_FIELDS = {
    "error_type",
    "error_message",
    "file",
    "patch",
    "success",
    "timestamp",
}
OPTIONAL_FIELDS = {
    "cluster",
    "intent_vector",
    "score",
    "confidence",
    "score_signals",
    "outcome",
}


def _memory_path():
    override = os.environ.get("OPENCLAW_MEMORY_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openclaw" / "memory.json"


def _valid_record(record):
    if not isinstance(record, dict):
        return False
    keys = set(record)
    if not REQUIRED_FIELDS.issubset(keys) or not keys.issubset(REQUIRED_FIELDS | OPTIONAL_FIELDS):
        return False
    string_fields = REQUIRED_FIELDS - {"success"}
    if not all(isinstance(record[field], str) for field in string_fields):
        return False
    if not isinstance(record["success"], bool):
        return False
    if "cluster" in record and not isinstance(record["cluster"], str):
        return False
    if "intent_vector" in record and not (
        isinstance(record["intent_vector"], list)
        and all(isinstance(value, str) for value in record["intent_vector"])
    ):
        return False
    if "score" in record and not isinstance(record["score"], (int, float)):
        return False
    if "confidence" in record and not isinstance(record["confidence"], (int, float)):
        return False
    if "score_signals" in record and not (
        isinstance(record["score_signals"], dict)
        and all(isinstance(key, str) for key in record["score_signals"])
        and all(isinstance(value, (int, float)) for value in record["score_signals"].values())
    ):
        return False
    if "outcome" in record and not isinstance(record["outcome"], str):
        return False
    return True


def load_memory():
    path = _memory_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [record for record in data if _valid_record(record)][-MAX_RECORDS:]


def save_memory(memory):
    if not isinstance(memory, list) or not all(_valid_record(record) for record in memory):
        raise ValueError("Invalid memory record")

    records = [record.copy() for record in memory[-MAX_RECORDS:]]
    path = _memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def add_record(record):
    stored = record.copy()
    stored.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    if not _valid_record(stored):
        raise ValueError("Invalid memory record")
    memory = load_memory()
    memory.append(stored)
    save_memory(memory)
    return stored.copy()
