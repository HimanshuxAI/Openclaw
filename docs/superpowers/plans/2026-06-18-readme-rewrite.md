# README Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `README.md` with a credible, capability-first guide that developers can evaluate and run in under two minutes.

**Architecture:** The document follows the user-required ten-section narrative and treats the current marker-based mock as an explicit limitation. Commands map directly to `main.py`, and the demo reflects actual loop log messages and patch behavior.

**Tech Stack:** GitHub-flavored Markdown, existing Python CLI

---

### Task 1: Rewrite And Verify README

**Files:**
- Modify: `README.md`

- [x] **Step 1: Replace the README**

Write these sections in order: title/hook, What It Does, Demo, Why This Matters,
How It Works, Quick Start, Project Structure, Current Limitations, Roadmap, and
Philosophy. Keep paragraphs under four lines. Include the real reset warning,
five-attempt limit, mock patch-marker boundary, safe patch restrictions, local
and clone commands, and repository-intelligence modules.

- [x] **Step 2: Validate claims against code**

Check all README identifiers and commands against `main.py`, `agent_loop.py`,
`patcher.py`, `repo_manager.py`, and `rag/`. Search for prohibited claims such
as production-ready, autonomous, and long-term memory; any occurrence must be
an explicit negation or roadmap item.

- [x] **Step 3: Validate Markdown and regressions**

Run: `git diff --check -- README.md`
Expected: exit 0 with no output.

Run: `python main.py --help`
Expected: exit 0 and options `--repo`, `--url`, and `--clone-path`.

Run: `python -m pytest -q`
Expected: all tests pass.
