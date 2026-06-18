# Test-Fixing Agent Design

## Scope

Build a minimal synchronous Python prototype that prepares a Git repository,
runs pytest, asks a deterministic mock LLM for a unified diff, applies the diff
through strict validation, and repeats for at most five iterations.

The prototype has no persistence, planner, database, network API, asynchronous
work, or orchestration framework.

## Components

- `main.py`: parse `--repo` or `--url` and start one agent run.
- `repo_manager.py`: clone repositories, validate local repositories, and reset
  tracked and untracked content to a clean Git state.
- `test_runner.py`: run `python -m pytest` and return stdout, stderr, and a
  boolean pass result.
- `patcher.py`: produce a deterministic mock patch and validate/apply unified
  diffs with Git.
- `agent_loop.py`: execute the bounded test, patch, retest loop.
- `utils.py`: extract concise failure context and print simple status messages.

## Execution Flow

`main.py` resolves the repository, resets it once, then calls the loop. Each
iteration runs pytest. A successful run exits immediately. A failure is reduced
to useful output and passed to the mock patch generator. Missing, invalid, or
inapplicable patches stop the run without further edits. An applied patch is
kept for the next iteration. Reaching five failed iterations returns failure.

## Mock LLM

The mock is deliberately narrow and deterministic. It recognizes an explicit
`OPENCLAW_PATCH` unified-diff block in pytest output. This makes the prototype
fully exercisable without pretending to solve arbitrary code failures. Unknown
failures return no patch and stop safely. A real LLM can later replace only the
mock function while preserving patch validation.

## Patch Safety

Only textual unified diffs accepted by `git apply` are allowed. Validation
rejects empty or oversized patches, binary patches, combined diffs, renames,
copies, file creation/deletion, absolute paths, traversal paths, `.git` paths,
nonexistent files, symlinks, and targets outside the repository. The patch must
also pass `git apply --check` before `git apply` runs. Failed validation or
application leaves the repository unchanged.

## Verification

Unit tests cover repository operations, test result capture, failure parsing,
mock extraction, valid patch application, unsafe patch rejection, successful
iteration, patch failure, and maximum-step termination. An end-to-end temporary
Git repository demonstrates a failing test, patch application, and passing
retest.
