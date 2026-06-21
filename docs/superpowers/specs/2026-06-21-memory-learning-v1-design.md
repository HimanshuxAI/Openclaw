# Memory + Learning v1 Design

## Scope

Add bounded local learning to the existing test-fixing loop. OpenClaw records
meaningful failure/patch outcomes and directly reuses a previously successful
patch only for the same normalized failure. Existing patch validation remains
the final authority before any remembered patch is applied.

## Storage

`memory/store.py` persists a JSON list at `~/.openclaw/memory.json`. The
`OPENCLAW_MEMORY_PATH` environment variable overrides this location for tests
and local control. Records contain exactly `error_type`, `error_message`,
`file`, `patch`, `success`, and an ISO-8601 UTC `timestamp`.

Writes are atomic through a sibling temporary file and `os.replace`. Only the
most recent 100 valid records are retained. Missing, unreadable, or malformed
memory degrades to an empty list so memory cannot prevent test fixing.

## Failure Patterns

`memory/patterns.py` extracts exception names ending in `Error` or `Exception`,
with an `AssertionError` fallback for pytest assertion output. It normalizes the
most relevant diagnostic line by removing ANSI formatting, pytest prefixes,
volatile line numbers, hexadecimal addresses, and repeated whitespace. It also
extracts the first referenced Python file for matching and storage.

A failure is meaningful only when both error type and normalized message are
non-empty. Full pytest output and repository context are never stored.

## Selection

`memory/selector.py` scores each record using:

- exact error type: 50 points;
- exact file: 40 points;
- normalized message similarity: up to 30 points.

Only positive matches are returned. Results are ordered by score, then newest
timestamp, and limited to three records.

Direct reuse is stricter than retrieval: error type, normalized message, and
file must all exactly match a successful record. A patch is excluded if a later
record shows that patch failed for the same failure. This avoids repeating a
known failed fix.

## Loop Integration

Before patch generation, the loop loads memory and asks the selector for prior
cases. An eligible successful patch is tried first. If it is unsafe or no longer
applies, the loop records the failure and tries the existing generator once.

After a patch is applied, the loop reruns pytest and records whether the full
suite passed. Missing patches and rejected generated patches are recorded only
when the failure is meaningful. Memory read/write errors never bypass patch
validation and never crash the repair loop.

## Verification

Tests cover atomic bounded storage, malformed data, pattern extraction and
normalization, deterministic top-three ranking, exact reuse, failed-patch
suppression, fallback after stale memory, and a two-run demonstration where the
second run succeeds from memory while generation is disabled.
