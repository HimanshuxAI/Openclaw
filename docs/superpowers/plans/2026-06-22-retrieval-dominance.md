# Retrieval Dominance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenClaw retrieve function-level evidence, replay high-confidence fixes, reject unsafe Python patches before application, and expose efficiency metrics.

**Architecture:** A stdlib AST index supplies slices and shallow dependency edges to a deterministic failure router. Retrieval ranks only route-eligible slices under the existing context cap; memory replay and patch preflight remain fail-closed; the synchronous loop applies one file/one hunk per test run.

**Tech Stack:** Python 3 standard library (`ast`, `difflib`, `importlib`, `py_compile`, `subprocess`, `tempfile`), Git, pytest

---

### Task 1: Failure Classification and Evidence Extraction

**Files:**
- Create: `rag/router.py`
- Create: `tests/test_router.py`

- [ ] **Step 1: Write failing classification tests**

```python
from rag.router import analyze_failure


def test_analyze_failure_classifies_and_extracts_traceback():
    failure = "FAILED tests/test_total.py::test_total\napp/service.py:14: TypeError: bad"
    evidence = analyze_failure(failure)
    assert evidence["kind"] == "type"
    assert evidence["node"] == ("tests/test_total.py", "test_total")
    assert ("app/service.py", 14) in evidence["locations"]


def test_analyze_failure_routes_known_errors():
    assert analyze_failure("SyntaxError: invalid syntax")["kind"] == "syntax"
    assert analyze_failure("ModuleNotFoundError: no module named 'billing'")["kind"] == "import"
    assert analyze_failure("E assert total == 5")["kind"] == "assertion"
    assert analyze_failure("ValueError: bad value")["kind"] == "runtime"
    assert analyze_failure("collection stopped")["kind"] == "unknown"
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run: `python3 -m pytest tests/test_router.py -q`

Expected: FAIL because `rag.router` does not exist.

- [ ] **Step 3: Implement deterministic routing**

```python
def analyze_failure(failure_text):
    return {
        "kind": classify_failure(failure_text),
        "locations": extract_locations(failure_text),
        "node": extract_pytest_node(failure_text),
        "identifiers": extract_identifiers(failure_text),
        "error_type": extract_error_type(failure_text),
    }
```

Use compiled regular expressions for pytest nodes and `.py:<line>` traceback
locations. Preserve location order and remove duplicates.

- [ ] **Step 4: Run router tests**

Run: `python3 -m pytest tests/test_router.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit the router and tests with Lore trailers recording regex-only routing.

### Task 2: AST Slice Index

**Files:**
- Modify: `rag/indexer.py`
- Modify: `tests/test_indexer.py`

- [ ] **Step 1: Replace line-chunk expectations with slice tests**

```python
def test_index_repo_emits_module_function_and_method_slices(tmp_path):
    source = "import os\n\ndef charge():\n    return send()\n\nclass Service:\n    def run(self):\n        return charge()\n"
    (tmp_path / "service.py").write_text(source, encoding="utf-8")
    chunks = index_repo(tmp_path)
    assert [(c["kind"], c["scope"]) for c in chunks] == [
        ("module", "<module>"),
        ("function", "charge"),
        ("method", "Service.run"),
    ]
    assert chunks[1]["calls"] == ("send",)


def test_index_repo_includes_tests_and_falls_back_for_syntax_error(tmp_path):
    (tmp_path / "test_bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    chunks = index_repo(tmp_path)
    assert chunks[0]["is_test"] is True
    assert chunks[0]["kind"] == "syntax"
```

- [ ] **Step 2: Run indexer tests and confirm old chunker fails**

Run: `python3 -m pytest tests/test_indexer.py -q`

Expected: FAIL on missing slice metadata and excluded tests.

- [ ] **Step 3: Implement AST extraction**

Add helpers `_scope_slice`, `_module_slice`, `_syntax_slices`, `_calls`, and
`_imports`. Include decorator lines via `min(node.lineno, decorator.lineno)` and
use `node.end_lineno`. Store immutable tuples for metadata. Keep `_INDEX`
transient and return copied dictionaries.

- [ ] **Step 4: Run indexer tests**

Run: `python3 -m pytest tests/test_indexer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit AST slicing separately from retrieval behavior.

### Task 3: Routed Retrieval and Whole-Scope Budgeting

**Files:**
- Modify: `rag/retriever.py`
- Modify: `rag/context_builder.py`
- Modify: `tests/test_retriever.py`
- Modify: `tests/test_context_builder.py`

- [ ] **Step 1: Write failing route and budget tests**

```python
def test_assertion_route_returns_test_then_called_target(tmp_path):
    # test_total calls calculate_total; unrelated health_check exists.
    index_repo(tmp_path)
    chunks = retrieve_context("FAILED tests/test_total.py::test_total\nE assert total == 5")
    assert [chunk["file"] for chunk in chunks] == [
        "tests/test_total.py",
        "app/service.py",
    ]


def test_context_builder_skips_oversized_scope_without_truncating():
    context = build_context([oversized_scope, small_scope])
    assert "oversized" not in context
    assert small_scope["content"].strip() in context
```

Add one test for each route and a deterministic tie test. Add a history test
where a successful record for the matching error type/file breaks a tie.

- [ ] **Step 2: Run retrieval tests and confirm failures**

Run: `python3 -m pytest tests/test_retriever.py tests/test_context_builder.py -q`

Expected: FAIL because retrieval is keyword-only and context truncates scopes.

- [ ] **Step 3: Implement route candidate selection and scoring**

Keep `retrieve_context(failure_text, k=5, memory=None)`. Analyze the failure,
select candidates according to the design routes, score candidates with named
integer constants, sort by `(-score, file, start_line)`, and strip internal
metadata from returned chunks.

- [ ] **Step 4: Enforce whole-scope context**

Add optional `scope` labels to headers. Skip complete scopes that exceed the
remaining budget; only `kind == "syntax"` windows may be line-trimmed. Export
`estimate_tokens(text)` for metrics and tests.

- [ ] **Step 5: Run retrieval tests**

Run: `python3 -m pytest tests/test_retriever.py tests/test_context_builder.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Commit routing and budgeting together because the route order defines budget
priority.

### Task 4: Fuzzy Memory Replay v2

**Files:**
- Modify: `memory/selector.py`
- Modify: `agent_loop.py`
- Modify: `tests/test_memory_selector.py`
- Modify: `tests/test_agent_loop.py`
- Modify: `tests/test_memory_learning.py`

- [ ] **Step 1: Write failing scored-selection tests**

```python
def test_find_similar_cases_returns_confidence_without_mutating_record():
    matches = find_similar_cases(failure, [record])
    assert matches[0]["record"] == record
    assert 0.88 <= matches[0]["score"] <= 1.0


def test_agent_replays_fuzzy_high_confidence_case(monkeypatch, tmp_path):
    # Numeric differences normalize away; same error type and file.
    assert run_agent(tmp_path) is True
    assert generated == []
```

Add threshold-below, basename-only, latest-failure suppression, and failed-only
case tests.

- [ ] **Step 2: Run memory and loop tests**

Run: `python3 -m pytest tests/test_memory_selector.py tests/test_agent_loop.py tests/test_memory_learning.py -q`

Expected: FAIL because matches have no scores and replay requires exact text.

- [ ] **Step 3: Implement scored matches**

Return `{"score": score, "record": record.copy()}` for the top three. Define
`REPLAY_THRESHOLD = 0.88`. Calculate latest outcomes by signature and patch,
then let `_reusable_patch` select only successful records at or above the
threshold whose latest outcome remains successful.

- [ ] **Step 4: Run memory and loop tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

Commit the compatible memory replay upgrade.

### Task 5: Single-Hunk Python Patch Preflight

**Files:**
- Modify: `patcher.py`
- Modify: `tests/test_patcher.py`

- [ ] **Step 1: Write failing safety tests**

```python
def test_apply_patch_rejects_multiple_hunks(git_repo):
    assert apply_patch(git_repo, MULTI_HUNK_PATCH) is False


def test_apply_patch_rejects_test_file_changes(git_repo):
    assert apply_patch(git_repo, TEST_FILE_PATCH) is False


def test_apply_patch_rejects_syntax_error_without_changing_checkout(git_repo):
    before = (git_repo / "module.py").read_text()
    assert apply_patch(git_repo, SYNTAX_ERROR_PATCH) is False
    assert (git_repo / "module.py").read_text() == before
```

Add valid Python, unresolved-new-import, and temporary-worktree-cleanup tests.

- [ ] **Step 2: Run patcher tests and confirm unsafe patches pass old checks**

Run: `python3 -m pytest tests/test_patcher.py -q`

Expected: FAIL on the new safety assertions.

- [ ] **Step 3: Enforce structural micro-patch rules**

Refactor validation to return the single target path or `None`. Require one diff
block, one `@@` header, `.py`, and a non-test path. Update the model prompt to
request one file and one hunk.

- [ ] **Step 4: Implement temporary-worktree preflight**

Use `tempfile.TemporaryDirectory`, `git worktree add --detach`, apply the patch,
run `py_compile`, compare pre/post absolute import sets, and check only newly
introduced imports with a subprocess using `importlib.util.find_spec`. Always
run `git worktree remove --force` in `finally`. Apply to the real checkout only
after all checks and successful cleanup.

- [ ] **Step 5: Run patcher tests**

Run: `python3 -m pytest tests/test_patcher.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

Commit preflight independently because it changes the acceptance boundary.

### Task 6: Generation Metrics and Micro-Iteration Evidence

**Files:**
- Modify: `patcher.py`
- Modify: `agent_loop.py`
- Modify: `tests/test_patcher.py`
- Modify: `tests/test_agent_loop.py`
- Modify: `tests/test_end_to_end.py`

- [ ] **Step 1: Write failing metrics and convergence tests**

```python
def test_generate_patch_reports_context_and_model_call(monkeypatch, git_repo):
    metrics = {}
    generate_patch(failure, git_repo, metrics=metrics)
    assert metrics == {"context_tokens": metrics["context_tokens"], "model_calls": 1}


def test_two_defects_are_fixed_by_two_single_hunk_iterations(git_repo):
    assert run_agent(git_repo) is True
    assert run_tests(git_repo)["passed"] is True
```

Capture the terminal summary and assert attempts, model calls, memory replays,
context tokens, elapsed milliseconds, and final state are present.

- [ ] **Step 2: Run focused tests and confirm failures**

Run: `python3 -m pytest tests/test_patcher.py tests/test_agent_loop.py tests/test_end_to_end.py -q`

Expected: FAIL because metrics are not exposed.

- [ ] **Step 3: Add backward-compatible metrics collection**

Change the signature to `generate_patch(failure_output, repo_path, metrics=None)`.
Populate the provided dictionary without changing the string return value.
Pass loaded memory into retrieval to avoid a second memory read.

- [ ] **Step 4: Add loop summary**

Use `time.monotonic()` and a local dictionary in `run_agent`. Emit exactly one
terminal `METRICS:` log for every exit path. Increment replay and attempt counts
at their decision points; merge generation metrics after every model attempt.

- [ ] **Step 5: Run focused tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

Commit metrics and end-to-end micro-iteration proof.

### Task 7: Documentation and Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update current capability and limitation sections**

Document AST slice retrieval, fixed failure routes, 1,800-token cap, fuzzy
high-confidence replay, single-file/single-hunk Python patches, test-edit
rejection, and preflight limitations. Do not describe dynamic call analysis or
production readiness.

- [ ] **Step 2: Run the complete verification suite**

Run: `python3 -m pytest -q`

Expected: all tests pass.

Run: `python3 -m compileall -q main.py repo_manager.py test_runner.py patcher.py agent_loop.py utils.py llm_client.py web_server.py rag memory`

Expected: exit code 0 with no output.

- [ ] **Step 3: Run security and scope checks**

Run: `rg -n 'nvapi-[A-Za-z0-9]' . --glob '!.git/**' --glob '!.omx/**'`

Expected: no matches.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 4: Commit**

Commit documentation and any final test corrections with complete `Tested:` and
`Not-tested:` Lore trailers.
