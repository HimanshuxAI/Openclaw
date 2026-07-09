"""Source-free, durable evidence storage for Phase 9 orchestration."""

import json
import math
import os
from pathlib import Path


LOG_NAMES = frozenset({"decisions", "plans", "failures", "strategies"})
FORBIDDEN_KEYS = frozenset({"patch", "source", "code", "code_context"})


def default_root():
    """Return the configurable directory that holds Phase 9 JSONL logs."""
    override = os.environ.get("OPENCLAW_PHASE9_MEMORY_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openclaw" / "phase9"


def append_record(name, record, root=None):
    """Atomically append one valid, source-free record to a named Phase 9 log."""
    path = _path(name, root)
    stored = _safe_record_copy(record)
    if stored is None:
        raise ValueError("Invalid Phase 9 record")

    records = load_records(name, root=root)
    records.append(stored)
    _write_records(path, records)


def load_records(name, root=None):
    """Return valid records from a named Phase 9 JSONL log, or an empty list."""
    path = _path(name, root)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []

    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (RecursionError, TypeError, ValueError):
            continue
        stored = _safe_record_copy(record)
        if stored is not None:
            records.append(stored)
    return records


def _path(name, root=None):
    _validate_log_name(name)
    directory = Path(root).expanduser() if root is not None else default_root()
    return directory / f"{name}.jsonl"


def _validate_log_name(name):
    if not isinstance(name, str) or name not in LOG_NAMES:
        raise ValueError("Unknown Phase 9 log")


def _valid_record(record):
    if not isinstance(record, dict):
        return False
    if not isinstance(record.get("run_id"), str):
        return False
    if "repository_id" in record and not isinstance(record["repository_id"], str):
        return False
    if not _is_json_value(record):
        return False
    return not _contains_forbidden_key(record)


def _contains_forbidden_key(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_KEYS or _contains_forbidden_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _is_json_value(value, ancestors=None):
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if not isinstance(value, (dict, list)):
        return False

    ancestors = set() if ancestors is None else ancestors
    identifier = id(value)
    if identifier in ancestors:
        return False
    ancestors.add(identifier)
    try:
        if isinstance(value, list):
            return all(_is_json_value(item, ancestors) for item in value)
        return all(
            isinstance(key, str) and _is_json_value(item, ancestors)
            for key, item in value.items()
        )
    finally:
        ancestors.remove(identifier)


def _json_copy(record):
    return json.loads(json.dumps(record, sort_keys=True, allow_nan=False))


def _safe_record_copy(record):
    try:
        if not _valid_record(record):
            return None
        return _json_copy(record)
    except (RecursionError, TypeError, ValueError):
        return None


def _write_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = "".join(
        json.dumps(record, sort_keys=True, allow_nan=False) + "\n" for record in records
    )
    try:
        temporary.write_text(encoded, encoding="utf-8")
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
