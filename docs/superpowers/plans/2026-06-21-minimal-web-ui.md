# Minimal Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal warm-white local web console that runs the existing OpenClaw loop against an explicitly selected repository.

**Architecture:** A Python standard-library HTTP server owns static delivery and one synchronous JSON endpoint. Plain HTML, CSS, and JavaScript own the interface, with no build step or frontend dependency.

**Tech Stack:** Python `http.server`, HTML5, CSS, browser JavaScript, pytest

---

### Task 1: Local Server Adapter

**Files:**
- Create: `tests/test_web_server.py`
- Create: `web_server.py`

- [x] **Step 1: Write failing server-adapter tests**

Test that `execute_agent(repo_path)` rejects blank input, loads and resets before
running, captures existing log output, returns the resolved repository and
success boolean, preserves a normal stopped result, and converts known
repository errors into a response-safe exception.

- [x] **Step 2: Verify tests fail for the missing module**

Run: `python -m pytest tests/test_web_server.py -q`
Expected: collection fails because `web_server.py` does not exist.

- [x] **Step 3: Implement server and adapter**

Define `WEB_ROOT`, `MAX_REQUEST_BYTES`, `execute_agent(repo_path)`,
`OpenClawHandler`, and `serve(host="127.0.0.1", port=8000)`. Capture stdout with
`redirect_stdout`, use the existing load/reset/run functions, serve `web/` via
`SimpleHTTPRequestHandler`, and implement only `POST /api/run` with strict JSON
validation and JSON error responses.

- [x] **Step 4: Verify server tests pass**

Run: `python -m pytest tests/test_web_server.py -q`
Expected: all server-adapter tests pass.

### Task 2: Minimal Whitish Interface

**Files:**
- Create: `tests/test_web_assets.py`
- Create: `web/index.html`
- Create: `web/styles.css`
- Create: `web/app.js`
- Modify: `README.md`

- [x] **Step 1: Write failing asset-contract tests**

Assert the page has a labeled repository form, reset warning, status/result
regions, stylesheet and script references; CSS defines warm-white variables,
responsive rules, visible focus, and reduced motion; JavaScript posts JSON to
`/api/run`, disables duplicate submission, and renders returned output safely
through `textContent`.

- [x] **Step 2: Verify tests fail because assets are absent**

Run: `python -m pytest tests/test_web_assets.py -q`
Expected: failures for missing `web/` assets.

- [x] **Step 3: Implement semantic HTML and restrained styling**

Build a single responsive page with top bar, direct hero, repository action
card, destructive reset note, run button, output console, and three compact
capability notes. Use system fonts, a `#f7f7f3` background, charcoal foreground,
thin borders, small radii, and one muted green status color.

- [x] **Step 4: Implement client behavior**

Submit `{repo}` to `/api/run`, show running state, render success/stopped/error
states without `innerHTML`, keep the button disabled during a request, and
return focus to the result status when complete.

- [x] **Step 5: Document local UI startup**

Add `python3 web_server.py --port 8000` and `http://127.0.0.1:8000` to README,
including the loopback-only, synchronous, destructive-reset constraints.

- [x] **Step 6: Verify asset tests pass**

Run: `python -m pytest tests/test_web_assets.py -q`
Expected: all asset-contract tests pass.

### Task 3: Full And Browser Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-06-21-minimal-web-ui.md`

- [x] **Step 1: Run full automated verification**

Run: `python -m pytest -q`
Expected: all tests pass.

Run: `python -m compileall -q web_server.py tests`
Expected: exit 0 with no output.

Run: `git diff --check`
Expected: exit 0 with no output.

- [x] **Step 2: Start the local server**

Run: `python web_server.py --port 8000`
Expected: server listens on `http://127.0.0.1:8000`.

- [ ] **Step 3: Verify in browser at desktop and mobile widths**

Confirm the page has no console errors, the form is keyboard usable, blank or
invalid paths return a readable error, output remains contained, the reset
warning is visible, and the layout does not overflow at 375 px width.
