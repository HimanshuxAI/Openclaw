# OpenClaw

Run pytest. Apply a validated patch. Repeat until the tests pass.

OpenClaw is an early test-fixing prototype for Python repositories. It runs a
small, bounded repair loop and leaves every applied change visible in Git.

## What It Does

- Loads an existing Git repository or clones one from a URL.
- Resets the target to a clean `HEAD` before each run.
- Runs the repository's pytest suite and captures failures.
- Retrieves small, relevant Python source chunks for each failure.
- Accepts a unified diff from the current mock patch generator.
- Rejects unsafe or malformed patches before they touch the repository.
- Applies valid patches and reruns pytest.
- Stops when tests pass, a patch fails validation, or five attempts are used.

## Demo

Start with a real failure:

```python
# calculator.py
def add(left, right):
    return left - right
```

```python
# test_calculator.py
from calculator import add

PATCH = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def add(left, right):
-    return left - right
+    return left + right
"""


def test_add():
    if add(2, 3) != 5:
        print("OPENCLAW_PATCH_START")
        print(PATCH)
        print("OPENCLAW_PATCH_END")
    assert add(2, 3) == 5
```

```console
$ python3 -m pytest -q
F                                                                        [100%]
=================================== FAILURES ===================================
___________________________________ test_add ___________________________________

>       assert add(2, 3) == 5
E       assert -1 == 5

1 failed in 0.04s
```

In the current mock mode, the failing test emits a candidate diff between
`OPENCLAW_PATCH_START` and `OPENCLAW_PATCH_END`. OpenClaw validates that diff,
applies it, and tests again:

```console
$ python3 main.py --repo /tmp/openclaw-demo
[openclaw] Resetting repository before run: /tmp/openclaw-demo
[openclaw] Fix attempt 1/5
[openclaw] SUCCESS: tests pass

$ git -C /tmp/openclaw-demo diff -- calculator.py
diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def add(left, right):
-    return left - right
+    return left + right

$ cd /tmp/openclaw-demo && python3 -m pytest -q
.                                                                        [100%]
1 passed in 0.03s
```

The repair is an ordinary unstaged Git diff. Review it, keep it, or discard it.

## Why This Matters

Most coding tools stop after suggesting code. The developer still has to run
tests, interpret the failure, apply the edit, and verify the result.

OpenClaw tests one narrower idea: make that feedback loop executable,
inspectable, and bounded.

## How It Works

```text
run pytest
    ↓
extract the failure
    ↓
retrieve relevant Python code
    ↓
request a unified diff
    ↓
validate and apply the patch
    ↓
run pytest again
```

The loop performs at most five fix attempts. It stops immediately when there is
no patch or when patch validation fails.

## Quick Start

Requirements: Python 3.9+, Git, and pytest.

From the OpenClaw checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install pytest
python3 -m pytest -q
```

Before running OpenClaw on a target, commit or back up its work. OpenClaw runs
`git reset --hard HEAD` and `git clean -fd`. This discards tracked changes and
non-ignored untracked files in the target repository.

Run against a local repository:

```bash
python3 main.py --repo /absolute/path/to/clean-target-repository
```

Or clone a repository into a new directory first:

```bash
python3 main.py \
  --url https://example.com/owner/project.git \
  --clone-path /tmp/project-openclaw
```

Successful fixes currently require pytest failure output containing an explicit
mock patch block:

```text
OPENCLAW_PATCH_START
diff --git a/module.py b/module.py
--- a/module.py
+++ b/module.py
@@ -1 +1 @@
-old_code()
+fixed_code()
OPENCLAW_PATCH_END
```

Without that block, OpenClaw stops safely without editing the repository.

## Project Structure

```text
main.py                 CLI and repository setup
repo_manager.py         Clone, load, and reset Git repositories
test_runner.py          Run pytest and capture its result
agent_loop.py           Bounded test → patch → retest loop
patcher.py              Mock generation and safe diff application
utils.py                Failure extraction and console output
rag/indexer.py          Chunk Python source files
rag/retriever.py        Rank chunks against a test failure
rag/context_builder.py  Build small, deduplicated code context
tests/                  Unit and end-to-end coverage
```

## Current Limitations

- Patch generation is mocked. No real language model is connected yet.
- Successful mock fixes require an explicit unified diff in pytest output.
- Only pytest is supported.
- Repository retrieval indexes Python files only.
- Tests execute locally with the current user's permissions. There is no
  sandbox.
- Repository state is not remembered between runs.
- OpenClaw is not fully autonomous or production-ready.

## Roadmap

1. Connect a real model to failure output and retrieved code context.
2. Improve retrieval quality without expanding prompt size.
3. Isolate test execution and support additional test runners.

## Philosophy

- Tight loops over broad plans.
- Deterministic limits over open-ended execution.
- Small, reviewable diffs over file rewrites.
- Stop safely when evidence is missing.

## License

MIT
