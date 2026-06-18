# Repository Intelligence v1 Design

## Scope

Add deterministic, dependency-free repository retrieval to the existing
test-fixing prototype. Only relevant Python source chunks are passed to the
mock LLM. The execution loop, patch validation, and five-attempt limit remain
unchanged.

## Indexing

`rag/indexer.py` recursively scans regular `.py` files. It excludes test paths
and generated or vendor directories including `tests`, `venv`, `.venv`,
`build`, `dist`, `node_modules`, and `__pycache__`. Files are read as UTF-8;
unreadable files are skipped. Content is split on line boundaries into chunks
targeting 400 whitespace-delimited tokens. Each chunk stores repository-relative
POSIX path, text, and inclusive start/end line numbers.

The index is transient module state because the required retriever signature
does not accept a repository or index. Calling `index_repo()` replaces the
entire current index and also returns a copy. No data persists between Python
processes.

## Retrieval

`rag/retriever.py` tokenizes failure text into lowercase identifier-like terms,
removes common diagnostic noise, and ranks chunks by term frequency. Matches in
the file path receive extra weight so traceback paths outrank incidental code
matches. Only positive-score chunks are returned. Ties are deterministic by
file path and line range. The default and integration limit is five chunks.

This keyword scorer is the required fallback when BGE-M3 and Qdrant are absent.
Repository Intelligence v1 intentionally does not add optional dependency
adapters because they would add installation and runtime branches without being
needed for a working prototype.

## Context Building

`rag/context_builder.py` removes duplicate `(file, lines, content)` entries and
formats each block as `FILE: path (lines start-end)` followed by code. The
builder uses an 1,800-token content budget, leaving margin below the required
2,000-token ceiling. It includes complete chunks when possible and truncates a
final chunk only on line boundaries.

## Patch Integration

`patcher.generate_patch(failure_output, repo_path)` refreshes the repository
index, retrieves the top five chunks, builds the bounded context, and calls
`mock_llm_fix(failure_output, code_context)`. The marker-based mock continues to
return explicit patches from failure output, but its two-input interface proves
that a real LLM replacement receives both diagnostics and relevant code.
Indexing or retrieval errors degrade to empty context and never bypass patch
validation.

## Verification

Tests cover filtering, chunk boundaries and metadata, index replacement,
keyword/path ranking, configurable top-K behavior, duplicate removal, context
formatting and budget limits, patcher context delivery, and the existing
end-to-end fix. The complete pre-existing suite must continue to pass.
