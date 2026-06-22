# Retrieval Dominance Design

## Goal

Increase OpenClaw's fix rate while reducing prompt size and model calls. The
system should behave as a bounded patch engine: classify the failure, retrieve
only structurally relevant Python scopes, replay a proven patch when confidence
is high, and reject risky patches before touching the target checkout.

## Constraints

- Use only the Python standard library for parsing, ranking, and validation.
- Keep the existing synchronous five-attempt agent loop.
- Keep model context below 2,000 estimated tokens; use 1,800 as the hard cap.
- Index Python only, including tests for retrieval.
- Never allow generated or remembered patches to modify tests.
- Each iteration may modify one existing Python file with one diff hunk.
- Do not build a full-repository semantic model or persistent vector index.

## Architecture

### Slice Index

`rag/indexer.py` parses each Python file with `ast`. It emits one slice for each
top-level function, async function, and class method. A small module slice holds
imports and top-level assignments. Each internal slice records:

- repository-relative file path;
- source text and exact line range;
- qualified scope name and slice kind;
- imported module/symbol names;
- statically visible call names;
- whether the file is a test.

Nested functions stay inside their enclosing function slice. Decorators belong
to the decorated scope. When a file cannot be parsed, the indexer emits bounded
line windows so syntax failures remain retrievable. Symlinks and ignored build,
environment, cache, and VCS directories remain excluded.

### Failure Classification

`rag/router.py` classifies failure text into exactly one of:

- `syntax`: `SyntaxError` and `IndentationError`;
- `import`: `ImportError` and `ModuleNotFoundError`;
- `assertion`: pytest assertion output and `AssertionError`;
- `type`: `TypeError` and typing-related attribute failures;
- `runtime`: all other structured exceptions;
- `unknown`: no structured signal.

It also extracts traceback `(file, line)` locations, the failing pytest node,
and useful identifiers. Classification and extraction are deterministic regex
operations over normalized pytest output.

### Retrieval Routes

`rag/retriever.py` applies a fixed route per class:

- `syntax`: the slice or fallback window containing the reported line, then its
  module imports.
- `import`: the importing scope/module slice, then the local definition or
  module named by the failure.
- `assertion`: the failing test scope, then production scopes directly called
  by that test. No unrelated callers are included.
- `type`: traceback scopes, direct callees referenced by those scopes, then
  imports needed to read those scopes.
- `runtime`: traceback scopes from innermost outward, then one direct caller or
  callee edge when space remains.
- `unknown`: current keyword ranking, limited to two slices.

Ranking is stable and additive:

1. exact traceback file and containing line;
2. exact failing test scope or referenced identifier;
3. direct call/import edge;
4. successful historical fixes for the same error type and file;
5. keyword overlap.

Ties sort by file and starting line. Retrieval returns no more than five public
chunks with the existing `file`, `content`, and `lines` contract.

### Context Budget

`rag/context_builder.py` retains the 1,800-token estimate cap. It consumes
ranked slices in order, removes duplicates, and never includes a partial scope.
If the next complete scope does not fit, it is skipped and the builder tries the
next smaller scope. Syntax fallback windows may be trimmed on line boundaries.
Headers identify the scope as well as file and lines.

### Memory Replay v2

The existing JSON record remains compatible. The failure signature is derived
from `(error_type, normalized_message, file)` rather than stored twice.
`memory/selector.py` returns matches with explicit confidence scores from 0 to
1 using:

- error type equality: 0.35;
- normalized message similarity: 0.35;
- file equality or basename equality: 0.20;
- successful latest outcome for the patch: 0.10.

A patch bypasses the model only when confidence is at least `0.88`, its latest
record is successful, and no later record marks that same patch unsuccessful
for the current signature. Lower-confidence successful cases influence
retrieval ranking but are not applied automatically. Failed patches are never
repeated for a matching signature.

### Patch Preflight

`patcher.py` keeps the existing path and unified-diff validation, then adds:

1. exactly one `diff --git` block and one hunk;
2. target must be an existing non-test `.py` file;
3. `git apply --check` in the real repository;
4. apply the patch in a temporary detached Git worktree;
5. compile the changed file with `py_compile`;
6. resolve its imports with `importlib.util.find_spec`, ignoring relative
   imports and imports that already existed unresolved before the patch;
7. remove the temporary worktree;
8. apply the already validated patch to the real repository.

The temporary worktree prevents syntax or import checks from mutating the real
checkout. A failed cleanup is reported as rejection and does not apply the
patch. Test files are retrieval evidence only and cannot be changed.

### Micro-Iteration Loop

The outer loop remains bounded by `MAX_STEPS = 5`. A successful preflight
applies one file/one hunk and immediately reruns pytest. The next failure is
classified and retrieved again from the updated checkout. OpenClaw does not ask
the model for a multi-part repair and never applies multiple hunks in one step.

If a remembered patch is rejected, its failed outcome is recorded and exactly
one generated fallback is attempted for that iteration. Other unsafe generated
patches stop the run, preserving current fail-closed behavior.

## Metrics

`agent_loop.py` records one in-process run summary and prints it at termination:

- fix attempts;
- model calls;
- memory replays;
- retrieved context token estimate;
- elapsed milliseconds;
- final pass/fail state.

No prompts, repository context, or reasoning are persisted. Tests assert the
counters; external benchmarking can aggregate the log lines later.

## Error Handling

- AST failures degrade to bounded syntax windows.
- Empty retrieval produces an empty model context rather than full-file input.
- Invalid memory records remain ignored by the current store.
- Static-check errors reject the patch and preserve the target repository.
- Temporary-worktree creation or cleanup errors reject the patch.
- Metrics failures never affect repair behavior.

## Testing

Unit tests cover AST boundaries, decorators, syntax fallback, every failure
route, deterministic ranking, whole-scope budgeting, fuzzy memory thresholds,
failed-patch suppression, one-hunk enforcement, test-file rejection, syntax
preflight, import preflight, and metrics. End-to-end tests prove:

1. an assertion retrieves only its test and target scopes;
2. a high-confidence learned patch skips model generation;
3. a syntax-invalid diff never changes the checkout;
4. two independent defects converge through separate micro iterations.

## Non-Goals

- interprocedural type inference;
- dynamic call-graph execution;
- embeddings or vector databases;
- repository-wide summaries;
- model self-reflection or planning;
- support for non-Python test runners.
