# NVIDIA Model Integration Design

## Scope

Replace mock-only patch generation with an optional NVIDIA Nemotron request
while retaining deterministic offline tests and the marker-based fallback. The
model proposes a unified diff; existing path validation and `git apply --check`
remain the only route to repository modification.

## Security

Credentials are read only from `NVIDIA_API_KEY`. No API key is accepted as a
source constant, CLI argument, browser field, log value, or memory record.
`.env.example` documents variable names with empty placeholders, and `.env` is
ignored. The exposed credential supplied during development must be revoked and
replaced before use.

## Client

`llm_client.py` lazy-imports the OpenAI Python SDK and targets
`https://integrate.api.nvidia.com/v1`. Defaults match NVIDIA's hosted example:

- model: `nvidia/nemotron-3-super-120b-a12b`;
- temperature: `1`;
- top-p: `0.95`;
- maximum output tokens: `16384`;
- thinking enabled with a `16384` reasoning budget;
- streaming enabled.

The coding-agent request also sets `force_nonempty_content`. Model and base URL
may be overridden with `NVIDIA_MODEL` and `NVIDIA_BASE_URL` for compatible
deployments. A finite client timeout defaults to 120 seconds.

The prompt includes only the current pytest failure and bounded repository
context. It instructs the model to return one textual unified diff for existing
files, with no file creation, deletion, rename, binary change, explanation, or
Markdown. Streaming reasoning content is ignored; only final content is
collected.

## Response Handling

The client accepts either a plain response beginning with `diff --git` or one
`diff` Markdown fence and extracts the patch text. Missing credentials, missing
SDK, request errors, and responses without a diff return an empty string. They
never expose credentials or partial reasoning.

`patcher.generate_patch()` builds context as before. When `NVIDIA_API_KEY` is
set, it requests a real patch. If no usable diff is returned, it falls back to
the existing `OPENCLAW_PATCH_START` marker mock. Offline behavior therefore
remains available and existing tests stay deterministic.

## Dependencies And Documentation

`requirements.txt` adds only `openai>=1.0`. README documents installation,
credential rotation, environment variables, real-model behavior, and the mock
fallback. The web UI inherits this behavior because it calls the same loop.

## Verification

Tests use a fake OpenAI module to verify endpoint/client configuration, prompt
content, streaming aggregation, reasoning exclusion, fenced/plain diff parsing,
missing-key behavior, request-error fallback, and patcher routing. No live API
request or real credential is used in automated verification. A secret scan
must confirm no `nvapi-` token appears in tracked or untracked project files.
