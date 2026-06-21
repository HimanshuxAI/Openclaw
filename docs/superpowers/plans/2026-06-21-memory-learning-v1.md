# Memory + Learning v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist bounded fix outcomes and reuse exact successful patches without repeating fixes known to fail.

**Architecture:** Three small functional modules own JSON persistence, failure normalization, and deterministic matching. The existing agent loop queries memory before generation, routes every remembered patch through the existing validator, and records the verified outcome.

**Tech Stack:** Python 3 standard library, JSON, pytest

---

## File Structure

- `memory/__init__.py`: package marker.
- `memory/store.py`: validate, load, atomically save, and append records.
- `memory/patterns.py`: extract error type, normalized message, and file.
- `memory/selector.py`: score and return the top three cases.
- `agent_loop.py`: reuse successful patches and record outcomes.
- `tests/test_memory_store.py`: persistence and size-limit coverage.
- `tests/test_memory_patterns.py`: extraction and normalization coverage.
- `tests/test_memory_selector.py`: deterministic ranking coverage.
- `tests/test_agent_loop.py`: reuse, suppression, recording, and fallback.
- `tests/test_memory_learning.py`: repeated-run improvement demonstration.
- `README.md`: memory location and current behavior.

### Task 1: Bounded JSON Storage

**Files:**
- Create: `memory/__init__.py`
- Create: `memory/store.py`
- Create: `tests/test_memory_store.py`

- [x] **Step 1: Write failing storage tests**

Use `OPENCLAW_MEMORY_PATH` to isolate each test. Assert missing/malformed files
load as `[]`, valid records round-trip, invalid records are rejected, atomic
save leaves valid JSON, `add_record()` appends a timestamp when absent, and only
the newest 100 records remain.

- [x] **Step 2: Verify the tests fail because the module is absent**

Run: `python -m pytest tests/test_memory_store.py -q`
Expected: collection fails with `ModuleNotFoundError: memory`.

- [x] **Step 3: Implement minimal storage**

Define `MAX_RECORDS = 100`, `REQUIRED_FIELDS`, `_memory_path()`, record
validation, `load_memory()`, `save_memory(memory)`, and `add_record(record)`.
Use `json.dump(..., indent=2)`, a sibling `.tmp` file, and `os.replace`.

- [x] **Step 4: Verify storage tests pass**

Run: `python -m pytest tests/test_memory_store.py -q`
Expected: all storage tests pass.

### Task 2: Failure Patterns And Case Selection

**Files:**
- Create: `memory/patterns.py`
- Create: `memory/selector.py`
- Create: `tests/test_memory_patterns.py`
- Create: `tests/test_memory_selector.py`

- [x] **Step 1: Write failing extraction and ranking tests**

Cover `ImportError`, `ModuleNotFoundError`, `NameError`, explicit and pytest-style
`AssertionError`, ANSI removal, volatile number/address normalization, first
Python file extraction, same-type/file weighting, message similarity, newest
tie-breaking, positive matches only, and the three-result limit.

- [x] **Step 2: Verify the tests fail because modules are absent**

Run: `python -m pytest tests/test_memory_patterns.py tests/test_memory_selector.py -q`
Expected: collection fails for the new modules.

- [x] **Step 3: Implement patterns and selection**

Use regular expressions for extraction/normalization and
`difflib.SequenceMatcher` for message similarity. Score exact error type at 50,
exact file at 40, similarity at up to 30, then sort by score and ISO timestamp.

- [x] **Step 4: Verify pattern and selector tests pass**

Run: `python -m pytest tests/test_memory_patterns.py tests/test_memory_selector.py -q`
Expected: all selected tests pass.

### Task 3: Loop Learning And Demonstration

**Files:**
- Modify: `agent_loop.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_agent_loop.py`
- Create: `tests/test_memory_learning.py`
- Modify: `README.md`
- Modify: `.gitignore`

- [x] **Step 1: Write failing loop-memory tests**

Assert exact successful memory bypasses generation, a later failed record
suppresses the same patch, stale remembered patches fall back to generation,
generated successes/failures are stored, and unstructured noise is not stored.
Set a per-test memory path with an autouse fixture.

- [x] **Step 2: Write a failing repeated-run demonstration**

Create a committed broken calculator repository. Let the first run consume its
mock diff and store success. Reset the repository, remove the marker from current
failure output by monkeypatching generation to fail, and assert the second run
still succeeds by reusing memory.

- [x] **Step 3: Verify loop-memory tests fail for missing integration**

Run: `python -m pytest tests/test_agent_loop.py tests/test_memory_learning.py -q`
Expected: new reuse/record assertions fail while existing loop tests remain valid.

- [x] **Step 4: Integrate memory without weakening patch safety**

Load cases before generation. Reuse only exact successful records not invalidated
by a failed record for the same failure. Route reused and generated patches
through `patcher.apply_patch`. Record meaningful outcomes with UTC timestamps;
on stale reuse, record failure and try generation once.

- [x] **Step 5: Document memory behavior**

Add the default path, environment override, 100-record limit, exact-match reuse,
and no-context/no-embedding guarantees to `README.md`. Ignore a workspace-local
`.openclaw-memory.json` override.

- [x] **Step 6: Run full verification**

Run: `python -m pytest -q`
Expected: all tests pass.

Run: `python -m compileall -q memory agent_loop.py tests`
Expected: exit 0 with no output.

Run: `git diff --check`
Expected: exit 0 with no output.
