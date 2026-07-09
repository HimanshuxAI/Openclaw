"""Apply only critic-approved repair candidates through the existing patcher."""


def execute(plan, repo_path, apply_patch):
    """Apply an approved candidate once and retain its patch for verification."""
    candidate = _value(plan, "candidate", None)
    patch = _patch(candidate)
    if not _value(plan, "approved", False) or not _value(plan, "executable", False):
        return _result(False, patch)
    if not patch:
        return _result(False, patch)
    try:
        applied = bool(apply_patch(repo_path, patch))
    except (OSError, RuntimeError, ValueError):
        applied = False
    return _result(applied, patch)


def _result(applied, patch):
    return {
        "state": "applied" if applied else "not_executed",
        "applied": applied,
        "patch": patch,
    }


def _value(mapping, key, default):
    if isinstance(mapping, dict):
        return mapping.get(key, default)
    return getattr(mapping, key, default)


def _patch(candidate):
    if not isinstance(candidate, dict):
        return ""
    patch = candidate.get("patch", "")
    return patch if isinstance(patch, str) else ""
