# Test-Fixing Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Python agent that safely applies mock-generated unified diffs until pytest passes or five attempts are exhausted.

**Architecture:** Flat functional modules separate repository preparation, pytest execution, failure parsing, patch validation, and loop control. Git performs both patch validation and application after Python rejects unsafe patch metadata and paths.

**Tech Stack:** Python 3 standard library, Git CLI, pytest for tests

---

## File Structure

- `repo_manager.py`: clone, validate, and reset Git repositories.
- `test_runner.py`: invoke pytest and normalize its result.
- `utils.py`: concise failure extraction and plain output logging.
- `patcher.py`: deterministic mock response plus strict unified-diff application.
- `agent_loop.py`: bounded synchronous repair loop.
- `main.py`: command-line repository selection and exit status.
- `tests/`: behavior and integration coverage for every module.

### Task 1: Repository, Test, and Utility Functions

**Files:**
- Create: `tests/test_repo_manager.py`
- Create: `tests/test_test_runner.py`
- Create: `tests/test_utils.py`
- Create: `repo_manager.py`
- Create: `test_runner.py`
- Create: `utils.py`

- [x] **Step 1: Write failing tests**

Test that local loading rejects non-Git paths, reset restores tracked files and removes untracked files, cloning checks out a local source repository, pytest results preserve stdout/stderr/exit status semantics, and failure extraction prefers stderr only when stdout is empty.

- [x] **Step 2: Verify the tests fail**

Run: `python -m pytest tests/test_repo_manager.py tests/test_test_runner.py tests/test_utils.py -q`
Expected: collection errors because the modules do not exist.

- [x] **Step 3: Implement minimal functions**

Use `subprocess.run(..., capture_output=True, text=True, check=False)` throughout. Validate repositories with `git rev-parse --is-inside-work-tree`; reset with `git reset --hard HEAD` followed by `git clean -fd`; run tests with `sys.executable -m pytest`; expose `extract_failure` and `log` without a logging framework.

- [x] **Step 4: Verify the tests pass**

Run: `python -m pytest tests/test_repo_manager.py tests/test_test_runner.py tests/test_utils.py -q`
Expected: all selected tests pass.

### Task 2: Safe Patch Generation and Application

**Files:**
- Create: `tests/test_patcher.py`
- Create: `patcher.py`

- [x] **Step 1: Write failing safety tests**

Test extraction of a diff between `OPENCLAW_PATCH_START` and `OPENCLAW_PATCH_END`, successful modification of one existing regular file, and rejection of traversal, absolute, `.git`, symlink, new-file, deletion, rename, binary, malformed, and inapplicable patches. Assert rejected patches do not change tracked content.

- [x] **Step 2: Verify the tests fail**

Run: `python -m pytest tests/test_patcher.py -q`
Expected: collection error because `patcher.py` does not exist.

- [x] **Step 3: Implement minimal safe patching**

Parse `diff --git`, `---`, and `+++` headers with `shlex`; require matching existing `a/path` and `b/path`; resolve each target beneath the repository; reject unsafe metadata and patches over 100 KiB; run `git apply --check --whitespace=error-all -` and only then `git apply --whitespace=error-all -`, passing the patch on stdin.

- [x] **Step 4: Verify the patch tests pass**

Run: `python -m pytest tests/test_patcher.py -q`
Expected: all patch generation and safety tests pass.

### Task 3: Agent Loop, CLI, and Simulation

**Files:**
- Create: `tests/test_agent_loop.py`
- Create: `tests/test_main.py`
- Create: `tests/test_end_to_end.py`
- Create: `agent_loop.py`
- Create: `main.py`
- Modify: `README.md`

- [x] **Step 1: Write failing loop and CLI tests**

Test immediate success, failure when no patch is generated, success after an applied patch, termination after exactly five failing runs, mutually exclusive `--repo`/`--url`, URL destination handling, and process exit codes. The end-to-end test creates a temporary Git repository whose failing test emits a marked patch, then verifies the agent applies it and pytest passes.

- [x] **Step 2: Verify the tests fail**

Run: `python -m pytest tests/test_agent_loop.py tests/test_main.py tests/test_end_to_end.py -q`
Expected: collection errors because loop and CLI modules do not exist.

- [x] **Step 3: Implement the five-step loop and CLI**

Define `MAX_STEPS = 5`; have `run_agent(repo_path)` return a boolean; stop on pass, absent patch, or rejected patch. Use argparse with a required mutually exclusive source group and optional `--clone-path`; prepare/reset once before entering the loop; return shell status 0 only when tests pass.

- [x] **Step 4: Document operation**

Replace the broad roadmap README with prototype scope, prerequisites, mock patch marker format, local and clone commands, safety limits, and the statement that reset discards repository changes before each run.

- [x] **Step 5: Run complete verification**

Run: `python -m pytest -q`
Expected: all tests pass.

Run: `python -m compileall -q main.py repo_manager.py test_runner.py patcher.py agent_loop.py utils.py tests`
Expected: exit status 0 with no output.

Run: `git diff --check`
Expected: exit status 0 with no output.
