"""Source-free, durable evidence storage for Phase 9 orchestration."""

from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import re
import tempfile


LOG_NAMES = frozenset({"decisions", "plans", "failures", "strategies"})
ACTION_VALUES = frozenset({"ACT", "VALIDATE", "SKIP"})
STRATEGY_VALUES = frozenset(
    {"minimal_patch", "rollback", "guard_clause", "retry_logic"}
)
UNCERTAINTY_VALUES = frozenset({"low", "medium", "high"})
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def default_root():
    """Return the configurable directory that holds Phase 9 JSONL logs."""
    override = os.environ.get("OPENCLAW_PHASE9_MEMORY_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openclaw" / "phase9"


def append_record(name, record, root=None):
    """Atomically append one valid, source-free record to a named Phase 9 log."""
    path = _path(name, root)
    stored = _validated_copy(name, record)
    if stored is None:
        raise ValueError("Invalid Phase 9 record")

    with _locked(path, fcntl.LOCK_EX, create=True):
        records = _read_records(name, path)
        records.append(stored)
        _write_records(path, records)


def load_records(name, root=None):
    """Return valid records from a named Phase 9 JSONL log, or an empty list."""
    path = _path(name, root)
    if not path.parent.exists():
        return []
    with _locked(path, fcntl.LOCK_SH, create=False):
        return _read_records(name, path)


def _path(name, root=None):
    _validate_log_name(name)
    directory = Path(root).expanduser() if root is not None else default_root()
    return directory / f"{name}.jsonl"


def _validate_log_name(name):
    if not isinstance(name, str) or name not in LOG_NAMES:
        raise ValueError("Unknown Phase 9 log")


@contextmanager
def _locked(path, operation, create):
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), operation)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_records(name, path):
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
        stored = _validated_copy(name, record)
        if stored is not None:
            records.append(stored)
    return records


def _validated_copy(name, record):
    try:
        if not _valid_record(name, record):
            return None
        return json.loads(json.dumps(record, sort_keys=True, allow_nan=False))
    except (RecursionError, TypeError, ValueError):
        return None


def _valid_record(name, record):
    if not isinstance(record, dict):
        return False
    validators = {
        "decisions": _valid_decision,
        "plans": _valid_plan,
        "failures": _valid_failure,
        "strategies": _valid_strategy,
    }
    return validators[name](record)


def _valid_decision(record):
    required = {
        "run_id",
        "repository_id",
        "plan_id",
        "proposed_action",
        "action_taken",
        "verification_state",
        "evidence_score",
        "uncertainty",
        "reason",
    }
    return (
        set(record) == required
        and _valid_common(record)
        and record["proposed_action"] in ACTION_VALUES
        and record["action_taken"] in ACTION_VALUES
        and _valid_token(record["verification_state"])
        and _valid_number(record["evidence_score"])
        and record["uncertainty"] in UNCERTAINTY_VALUES
        and _valid_token(record["reason"])
    )


def _valid_plan(record):
    required = {
        "run_id",
        "repository_id",
        "plan_id",
        "action",
        "strategy",
        "candidate_count",
        "reversible",
        "executable",
        "steps",
        "impact_score",
        "regression_risk",
        "pass_likelihood",
    }
    allowed = required | {"critic_risks"}
    return (
        required.issubset(record)
        and set(record).issubset(allowed)
        and _valid_common(record)
        and record["action"] in ACTION_VALUES
        and record["strategy"] in STRATEGY_VALUES
        and _valid_nonnegative_integer(record["candidate_count"])
        and isinstance(record["reversible"], bool)
        and isinstance(record["executable"], bool)
        and _valid_tokens(record["steps"])
        and _valid_number(record["impact_score"])
        and _valid_number(record["regression_risk"])
        and _valid_number(record["pass_likelihood"])
        and (
            "critic_risks" not in record or _valid_tokens(record["critic_risks"])
        )
    )


def _valid_failure(record):
    required = {
        "run_id",
        "repository_id",
        "plan_id",
        "verification_state",
        "reason",
        "tool_contract_failures",
    }
    return (
        set(record) == required
        and _valid_common(record)
        and _valid_token(record["verification_state"])
        and _valid_token(record["reason"])
        and _valid_tokens(record["tool_contract_failures"])
    )


def _valid_strategy(record):
    required = {
        "run_id",
        "repository_id",
        "plan_id",
        "strategy",
        "action_taken",
        "verified",
        "failure_cost_saved",
        "action_cost",
    }
    return (
        set(record) == required
        and _valid_common(record)
        and record["strategy"] in STRATEGY_VALUES
        and record["action_taken"] in ACTION_VALUES
        and isinstance(record["verified"], bool)
        and _valid_number(record["failure_cost_saved"])
        and _valid_number(record["action_cost"])
    )


def _valid_common(record):
    return all(
        _valid_identifier(record[key])
        for key in ("run_id", "repository_id", "plan_id")
    )


def _valid_identifier(value):
    return isinstance(value, str) and bool(IDENTIFIER_PATTERN.fullmatch(value))


def _valid_token(value):
    return isinstance(value, str) and bool(TOKEN_PATTERN.fullmatch(value))


def _valid_tokens(value):
    return isinstance(value, list) and all(_valid_token(item) for item in value)


def _valid_nonnegative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _write_records(path, records):
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
