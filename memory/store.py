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


def _memory_path():
    override = os.environ.get("OPENCLAW_MEMORY_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openclaw" / "memory.json"


def _valid_record(record):
    if not isinstance(record, dict) or set(record) != REQUIRED_FIELDS:
        return False
    string_fields = REQUIRED_FIELDS - {"success"}
    if not all(isinstance(record[field], str) for field in string_fields):
        return False
    return isinstance(record["success"], bool)


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
