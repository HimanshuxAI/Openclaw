# Minimal Web UI Design

## Scope

Add a dependency-free local frontend for the existing OpenClaw agent. The UI
accepts one local Git repository path, states the reset behavior explicitly,
runs the existing synchronous loop, and displays its captured output. It does
not add authentication, remote execution, job queues, or configuration panels.

## Interface

The page uses a warm white background, charcoal text, thin neutral borders, and
one muted green status accent. The top bar contains only the OpenClaw wordmark
and a `Local prototype` status. The primary panel contains:

- a direct `Fix failing tests. Keep the diff.` heading;
- one labeled absolute repository-path input;
- a visible warning that tracked and non-ignored untracked changes are removed;
- a single black `Run OpenClaw` button;
- a result panel for idle, running, success, stopped, and error states.

A compact lower strip describes validated patches, five-attempt execution, and
bounded local learning. The page is responsive down to mobile width, keyboard
accessible, and respects reduced-motion preferences.

## Local Server

`web_server.py` uses `http.server.HTTPServer` and serves assets from `web/`. It
binds to `127.0.0.1:8000` by default. `POST /api/run` accepts JSON containing a
non-empty `repo` string, rejects bodies over 64 KiB, validates the local Git
repository, resets it through `reset_repo`, runs `run_agent`, captures existing
console output, and returns JSON with `success`, `repo`, and `output`.

The server is intentionally single-threaded because the current loop and stdout
capture are synchronous. Known repository/input errors return a JSON error
without exposing a traceback. Static file serving remains same-origin; no CORS
headers are added.

## Files

- `web_server.py`: local HTTP transport and agent adapter.
- `web/index.html`: semantic page structure.
- `web/styles.css`: visual system and responsive behavior.
- `web/app.js`: form submission and result-state rendering.
- `tests/test_web_server.py`: adapter validation and captured-output behavior.
- `tests/test_web_assets.py`: required UI content and asset references.

## Verification

Unit tests cover missing paths, reset/run order, success/failure responses, and
captured logs. Asset tests cover the warning, form labels, endpoint wiring, and
responsive stylesheet. Full project tests and compilation must pass. A local
server browser check must verify the page loads, has no console errors, submits
invalid input safely, and remains usable at desktop and mobile widths.
