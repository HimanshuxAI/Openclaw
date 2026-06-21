# NVIDIA Model Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate safe patch candidates with NVIDIA Nemotron when configured, while retaining deterministic mock fallback behavior.

**Architecture:** A lazy-loaded client owns credentials, prompting, streaming, and diff extraction. `patcher.py` remains responsible for repository context and delegates proposal generation before applying its unchanged safety checks.

**Tech Stack:** Python 3, OpenAI Python SDK, NVIDIA OpenAI-compatible API, pytest

---

### Task 1: Streaming NVIDIA Client

**Files:**
- Create: `tests/test_llm_client.py`
- Create: `llm_client.py`

- [x] **Step 1: Write failing client tests**

Use a fake `openai` module and environment variables. Assert missing keys and
missing SDK return an empty string; client configuration uses the NVIDIA base
URL without exposing the key; request parameters match the model example;
failure plus bounded context appear in the prompt; reasoning deltas are ignored;
content deltas aggregate; plain and fenced diffs extract; request errors and
non-diff responses return empty output.

- [x] **Step 2: Verify tests fail because the module is absent**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: collection fails because `llm_client.py` does not exist.

- [x] **Step 3: Implement the minimal client**

Define endpoint/model constants, `_build_prompt`, `_extract_unified_diff`, and
`generate_nvidia_patch(failure_text, code_context)`. Read only environment
configuration, lazy-import `OpenAI`, configure a finite timeout, stream the
official Nemotron request, ignore `reasoning_content`, concatenate final content,
and return only extracted unified-diff text.

- [x] **Step 4: Verify client tests pass**

Run: `python -m pytest tests/test_llm_client.py -q`
Expected: all client tests pass without network access.

### Task 2: Patcher Routing, Setup, And Verification

**Files:**
- Modify: `tests/test_patcher.py`
- Modify: `patcher.py`
- Create: `requirements.txt`
- Create: `.env.example`
- Modify: `.gitignore`
- Modify: `README.md`

- [x] **Step 1: Write failing routing tests**

Assert configured real-model output is returned before the mock, empty/error
real-model output falls back to explicit markers, and absent credentials preserve
the existing mock behavior. Monkeypatch the client function; never use a real key.

- [x] **Step 2: Verify routing tests fail on current mock-only behavior**

Run: `python -m pytest tests/test_patcher.py -q`
Expected: new NVIDIA routing assertions fail while existing safety tests pass.

- [x] **Step 3: Integrate proposal routing**

Import `generate_nvidia_patch`, build context as before, call it only when
`NVIDIA_API_KEY` is non-empty, return a usable model diff, and otherwise call
`mock_llm_fix`. Do not change `apply_patch` or validation.

- [x] **Step 4: Add safe environment/dependency setup**

Add `openai>=1.0` to `requirements.txt`; add empty `NVIDIA_API_KEY`, default
base URL/model, and timeout names to `.env.example`; ignore `.env` and `.env.*`
except `.env.example`.

- [x] **Step 5: Document model setup and fallback**

Document key rotation, `pip install -r requirements.txt`, environment exports,
model defaults, reasoning behavior, safe patch validation, and mock fallback.
State that no credential is accepted through the web UI.

- [x] **Step 6: Run full verification and secret scan**

Run: `python -m pytest -q`
Expected: all tests pass without a real API request.

Run: `python -m compileall -q llm_client.py patcher.py tests`
Expected: exit 0 with no output.

Run: `git diff --check`
Expected: exit 0 with no output.

Run: `rg -n 'nvapi-[A-Za-z0-9]' . --glob '!.git/**' --glob '!.omx/**'`
Expected: no matches.
