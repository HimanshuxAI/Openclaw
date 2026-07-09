"""Named, label-only Phase 9 repair strategies."""


minimal_patch = "minimal_patch"
rollback = "rollback"
guard_clause = "guard_clause"
retry_logic = "retry_logic"

STRATEGIES = (minimal_patch, rollback, guard_clause, retry_logic)

__all__ = [
    "STRATEGIES",
    "guard_clause",
    "minimal_patch",
    "retry_logic",
    "rollback",
    "select_strategy",
]


def select_strategy(action, history, repository_id):
    """Choose the best verified local strategy without generating a patch."""
    rates = _verified_rates(action, history, repository_id)
    if not rates or max(rates.values()) <= 0:
        return minimal_patch
    return max(rates, key=lambda name: (rates[name], name))


def _verified_rates(action, history, repository_id):
    if history is None:
        return {}

    totals = {}
    verified = {}
    try:
        records = iter(history)
    except TypeError:
        return {}

    for record in records:
        if not isinstance(record, dict):
            continue
        strategy = record.get("strategy")
        if (
            record.get("repository_id") != repository_id
            or record.get("action_taken") != action
            or strategy not in STRATEGIES
        ):
            continue
        totals[strategy] = totals.get(strategy, 0) + 1
        if record.get("verified") is True:
            verified[strategy] = verified.get(strategy, 0) + 1

    return {
        strategy: verified.get(strategy, 0) / total
        for strategy, total in totals.items()
    }
