"""Persist explicit, bounded repair goals without silently resuming stale work."""

import json
import os
from pathlib import Path
import re
import tempfile

from memory.phase9 import default_root


IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
GOAL_KEYS = frozenset(
    {
        "run_id",
        "repository_id",
        "objective",
        "max_steps",
        "state",
        "completed_steps",
        "terminal_state",
    }
)


def start_goal(run_id, repository_id, max_steps, root=None):
    """Start a fresh bounded repair goal, replacing stale state for this run ID."""
    goal = {
        "run_id": run_id,
        "repository_id": repository_id,
        "objective": "restore_verified_pytest",
        "max_steps": max_steps,
        "state": "active",
        "completed_steps": [],
        "terminal_state": "",
    }
    _require_valid(goal)
    _save(goal, root)
    return _copy(goal)


def record_goal_step(goal, step, root=None):
    """Persist one completed role step while a goal remains active."""
    updated = _copy(goal)
    _require_valid(updated)
    if updated["state"] != "active" or not _valid_token(step):
        raise ValueError("Invalid active goal step")
    updated["completed_steps"].append(step)
    _save(updated, root)
    return _copy(updated)


def finish_goal(goal, terminal_state, root=None):
    """Record a terminal state for a valid active repair goal."""
    updated = _copy(goal)
    _require_valid(updated)
    if updated["state"] != "active" or not _valid_token(terminal_state):
        raise ValueError("Invalid terminal goal state")
    updated["state"] = "terminal"
    updated["terminal_state"] = terminal_state
    _save(updated, root)
    return _copy(updated)


def load_goal(run_id, root=None):
    """Return validated state or an empty dict for absent or corrupt goal data."""
    if not _valid_identifier(run_id):
        return {}
    path = _path(run_id, root)
    try:
        goal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not _valid_goal(goal) or goal["run_id"] != run_id:
        return {}
    return _copy(goal)


def _path(run_id, root=None):
    directory = Path(root).expanduser() if root is not None else default_root()
    return directory / f"goal-{run_id}.json"


def _save(goal, root):
    path = _path(goal["run_id"], root)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(goal, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _require_valid(goal):
    if not _valid_goal(goal):
        raise ValueError("Invalid repair goal")


def _valid_goal(goal):
    return (
        isinstance(goal, dict)
        and set(goal) == GOAL_KEYS
        and _valid_identifier(goal.get("run_id"))
        and _valid_identifier(goal.get("repository_id"))
        and goal.get("objective") == "restore_verified_pytest"
        and isinstance(goal.get("max_steps"), int)
        and not isinstance(goal.get("max_steps"), bool)
        and goal["max_steps"] > 0
        and goal.get("state") in {"active", "terminal"}
        and isinstance(goal.get("completed_steps"), list)
        and all(_valid_token(step) for step in goal["completed_steps"])
        and isinstance(goal.get("terminal_state"), str)
        and (
            goal["terminal_state"] == ""
            or _valid_token(goal["terminal_state"])
        )
    )


def _valid_identifier(value):
    return isinstance(value, str) and bool(IDENTIFIER_PATTERN.fullmatch(value))


def _valid_token(value):
    return isinstance(value, str) and bool(TOKEN_PATTERN.fullmatch(value))


def _copy(goal):
    try:
        return json.loads(json.dumps(goal, sort_keys=True))
    except (TypeError, ValueError):
        raise ValueError("Invalid repair goal") from None
