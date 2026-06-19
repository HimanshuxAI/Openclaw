# Repository Intelligence v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supply the patch-generating mock LLM with at most five relevant Python source chunks instead of no repository context.

**Architecture:** A transient index stores line-aware source chunks, a deterministic keyword retriever ranks them against pytest failures, and a bounded formatter builds the LLM context. `patcher.generate_patch()` refreshes and consumes this pipeline without changing the execution loop.

**Tech Stack:** Python 3 standard library, pytest, in-memory keyword ranking

---

## File Structure

- `rag/__init__.py`: marks the repository-intelligence package.
- `rag/indexer.py`: scan/filter Python files and create 400-token chunks.
- `rag/retriever.py`: rank current chunks by failure keyword frequency.
- `rag/context_builder.py`: deduplicate and format context below 2,000 tokens.
- `patcher.py`: pass failure output and retrieved context to the mock LLM.
- `tests/test_indexer.py`: indexing and metadata behavior.
- `tests/test_retriever.py`: relevance ranking and top-K behavior.
- `tests/test_context_builder.py`: formatting, deduplication, and limits.
- `tests/test_patcher.py`: context integration contract.
- `README.md`: indexing and retrieval usage.

### Task 1: Source Indexing

**Files:**
- Create: `rag/__init__.py`
- Create: `rag/indexer.py`
- Create: `tests/test_indexer.py`

- [x] **Step 1: Write failing indexer tests**

Create repositories containing source, test, non-Python, ignored-directory,
empty, and large Python files. Assert only source chunks are returned, paths are
relative POSIX strings, line ranges are inclusive, chunks target at most 400
tokens for ordinary lines, and calling `index_repo()` replaces the prior index.

- [x] **Step 2: Run tests and observe the missing-module failure**

Run: `python -m pytest tests/test_indexer.py -q`
Expected: collection fails because `rag.indexer` does not exist.

- [x] **Step 3: Implement the indexer**

Define `CHUNK_TOKENS = 400`, `IGNORED_DIRS`, module-level `_INDEX`,
`index_repo(repo_path)`, and `get_index()`. Resolve the repository root, sort
`Path.rglob("*.py")`, reject ignored path components, read UTF-8,
accumulate complete lines until adding a line would exceed 400 tokens, and store
`{"file": relative, "content": text, "lines": (start, end)}`.

- [x] **Step 4: Run indexer tests**

Run: `python -m pytest tests/test_indexer.py -q`
Expected: all indexer tests pass.

### Task 2: Retrieval and Context Building

**Files:**
- Create: `rag/retriever.py`
- Create: `rag/context_builder.py`
- Create: `tests/test_retriever.py`
- Create: `tests/test_context_builder.py`

- [x] **Step 1: Write failing retrieval and formatting tests**

Seed the index with auth, billing, and unrelated chunks. Assert traceback file
names and diagnostic identifiers rank matching chunks first, `k` is honored,
zero-match queries return no chunks, duplicate chunks appear once, headers show
paths and inclusive ranges, and output remains below 2,000 whitespace tokens.

- [x] **Step 2: Run tests and observe missing-module failures**

Run: `python -m pytest tests/test_retriever.py tests/test_context_builder.py -q`
Expected: collection fails because the retriever and builder do not exist.

- [x] **Step 3: Implement deterministic ranking and formatting**

Tokenize identifiers with a regular expression, remove a fixed stop-word set,
score content term frequency plus path frequency and an exact-path bonus, sort
by negative score/file/line, and return only positive scores. Format unique blocks under
`MAX_CONTEXT_TOKENS = 1800` using a conservative whitespace/character estimate,
truncating only the last block on line boundaries.

- [x] **Step 4: Run retrieval and formatting tests**

Run: `python -m pytest tests/test_retriever.py tests/test_context_builder.py -q`
Expected: all selected tests pass.

### Task 3: Patcher Integration and Documentation

**Files:**
- Modify: `patcher.py`
- Modify: `tests/test_patcher.py`
- Modify: `README.md`

- [x] **Step 1: Write a failing patcher integration test**

Create a repository with a source file containing a failure identifier,
monkeypatch `mock_llm_fix`, call `generate_patch()`, and assert the mock receives
the original failure plus a context string containing only the relevant file.
Keep the existing one-argument mock tests backward compatible through a default
empty context parameter.

- [x] **Step 2: Run the integration test and observe the missing context**

Run: `python -m pytest tests/test_patcher.py -q`
Expected: the new assertion fails because `generate_patch()` discards repo path.

- [x] **Step 3: Integrate repository intelligence**

Import `index_repo`, `retrieve_context`, and `build_context`; refresh the index,
retrieve with `k=5`, build context, and call
`mock_llm_fix(failure_output, code_context)`. On `OSError` or `ValueError`, call
the mock with empty context so retrieval cannot break safe loop termination.

- [x] **Step 4: Document indexing and agent operation**

Add commands showing `index_repo("/path/to/repo")` and the existing
`python3 main.py --repo /path/to/repo` flow. State that v1 uses deterministic
in-memory keyword retrieval because BGE-M3/Qdrant are optional and unavailable.

- [x] **Step 5: Run full verification**

Run: `python -m pytest -q`
Expected: all old and new tests pass.

Run: `python -m compileall -q rag patcher.py tests`
Expected: exit 0 with no output.

Run: `git diff --check`
Expected: exit 0 with no output.
