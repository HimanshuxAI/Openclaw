# OpenClaw

Run pytest. Apply a validated patch. Repeat until the tests pass.

OpenClaw is an early test-fixing prototype for Python repositories. It runs a
small, bounded repair loop and leaves every applied change visible in Git.

## What It Does

- Loads an existing Git repository or clones one from a URL.
- Resets the target to a clean `HEAD` before each run.
- Runs the repository's pytest suite and captures failures.
- Retrieves small, relevant Python source chunks for each failure.
- Reuses an exact successful fix from bounded local memory when available.
- Requests a unified diff from NVIDIA Nemotron when configured.
- Retains the explicit marker patch as an offline fallback.
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
check successful past fixes
    ↓
retrieve relevant Python code
    ↓
request a unified diff
    ↓
validate and apply the patch
    ↓
run pytest again
    ↓
record the verified outcome
```

The loop performs at most five fix attempts. A remembered patch still passes
normal validation. If it is stale, OpenClaw records the failure and tries the
current generator once.

## Quick Start

Requirements: Python 3.9+ and Git.

From the OpenClaw checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m pytest -q
```

### NVIDIA Nemotron

The credential shared during setup was exposed. Revoke it in NVIDIA's dashboard
and create a replacement before running OpenClaw.

Export the replacement in your shell:

```bash
export NVIDIA_API_KEY="your-rotated-key"
export NVIDIA_MODEL="nvidia/nemotron-3-super-120b-a12b"
```

OpenClaw sends the pytest failure and less than 2,000 estimated tokens of
retrieved code context to NVIDIA's OpenAI-compatible endpoint. Nemotron streams
reasoning and final content; OpenClaw ignores the reasoning stream and accepts
only final unified-diff content.

Optional endpoint settings are documented in `.env.example`. OpenClaw does not
load `.env` files automatically. The web UI never accepts or displays API keys.

### Local web UI

Start the dependency-free local interface:

```bash
python3 web_server.py --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The server binds to
loopback by default and runs one repository synchronously. Enter either an
absolute local path or an HTTPS Git URL. Remote repositories are cloned into
`~/.openclaw/repos` and reused on later runs. The server performs the same
destructive reset as the CLI, so commit or back up local targets first.

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

Without `NVIDIA_API_KEY`, the offline mock accepts pytest failure output
containing an explicit patch block:

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

Without a model diff, that marker block, or an exact successful memory match,
OpenClaw stops safely without editing the repository.

### Local memory

OpenClaw stores up to 100 structured outcomes in:

```text
~/.openclaw/memory.json
```

Override the location when needed:

```bash
export OPENCLAW_MEMORY_PATH=/absolute/path/to/openclaw-memory.json
```

Memory contains only normalized error details, the referenced file, the patch,
its verified outcome, and a timestamp. It never stores repository context. A
successful patch is reused only when error type, normalized message, and file
all match. A patch that later fails for that case is not repeated.

## Project Structure

```text
main.py                 CLI and repository setup
web_server.py           Loopback-only local web interface
repo_manager.py         Clone, load, and reset Git repositories
test_runner.py          Run pytest and capture its result
agent_loop.py           Bounded test → patch → retest loop
patcher.py              Model routing and safe diff application
llm_client.py           NVIDIA Nemotron streaming client
utils.py                Failure extraction and console output
rag/indexer.py          Chunk Python source files
rag/retriever.py        Rank chunks against a test failure
rag/context_builder.py  Build small, deduplicated code context
memory/store.py         Persist the latest 100 fix outcomes
memory/patterns.py      Normalize failure details
memory/selector.py      Rank and select prior cases
web/                     Static HTML, CSS, and browser JavaScript
tests/                  Unit and end-to-end coverage
```

## Current Limitations

- Hosted generation requires a rotated NVIDIA API key and network access.
- Model output can be missing or invalid; unsafe diffs are rejected and the loop
  stops or uses an available offline fallback.
- Offline new fixes require an explicit unified diff in pytest output; exact
  learned fixes can be reused without generating it again.
- Only pytest is supported.
- Repository retrieval indexes Python files only.
- Tests execute locally with the current user's permissions. There is no
  sandbox.
- Memory covers structured failure/patch outcomes only. It is not project or
  conversation memory.
- OpenClaw is not fully autonomous or production-ready.

## Roadmap

1. Improve retrieval quality without expanding prompt size.
2. Add model-call diagnostics without storing prompts or reasoning.
3. Isolate test execution and support additional test runners.

## Philosophy

- Tight loops over broad plans.
- Deterministic limits over open-ended execution.
- Small, reviewable diffs over file rewrites.
- Stop safely when evidence is missing.

## License

MIT
