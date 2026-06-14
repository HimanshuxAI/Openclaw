# OpenClaw

> Phase 1: Building the foundation for a persistent AI software engineer.

---

# Problem Statement

Current AI coding assistants have a fundamental limitation.

They generate code, but they do not truly work on software projects.

Common failure modes:

- They forget previous sessions.
- They cannot maintain long-term project context.
- They have limited understanding of large repositories.
- They rely on the user to provide the same information repeatedly.
- They do not plan complex engineering tasks.
- They cannot reliably execute development workflows.

As projects grow, these limitations become bottlenecks.

The objective of OpenClaw is to solve this problem by creating an AI system that can understand, remember, and operate on real codebases over time.

---

# Objective

Build a persistent AI software engineer that can:

- Understand repositories
- Remember previous work
- Plan multi-step tasks
- Use development tools
- Continue projects across sessions

---

# Phase 1 Scope

Phase 1 focuses on building the core infrastructure.

## Goals

- [ ] NVIDIA API integration
- [ ] FastAPI backend
- [ ] Basic conversation engine
- [ ] Memory architecture
- [ ] Initial project structure

Phase 1 is not intended to be a fully autonomous coding agent.

Its purpose is to establish the foundation for future development.

---

# High Level Architecture

```text
User
  |
  v
Memory
  |
  v
Planner
  |
  v
Repository Context
  |
  v
Tool Executor
  |
  v
NVIDIA Nemotron
  |
  v
Response
```

---

# Long-Term Vision

A user should eventually be able to write:

```text
Continue my SaaS project.
Finish the authentication module.
Run the tests.
Fix any failures.
Commit the changes.
```

The system should execute that workflow with minimal guidance.

---

# Planned Components

## Memory

Store:

- User preferences
- Project summaries
- Previous decisions
- Important context

## Repository Intelligence

- Code indexing
- Context retrieval
- Semantic search

## Planning

Convert high-level goals into executable tasks.

## Tool Use

- File operations
- Terminal execution
- Git integration
- GitHub integration

---

# Technology Stack

| Layer | Technology |
|--------|-------------|
| LLM | NVIDIA Nemotron |
| Backend | FastAPI |
| Memory | Supabase |
| Vector Database | Qdrant |
| Embeddings | BGE-M3 |
| Language | Python |

---

# Project Structure

```text
openclaw/
├── app/
├── api/
├── memory/
├── rag/
├── planner/
├── tools/
├── tests/
└── docs/
```

---

# Development Roadmap

## Phase 1

- [ ] Basic infrastructure
- [ ] NVIDIA integration
- [ ] Memory foundation

## Phase 2

- [ ] Repository indexing
- [ ] Vector search
- [ ] Tool execution

## Phase 3

- [ ] Planning engine
- [ ] Autonomous workflows
- [ ] VS Code integration

---

# Status

This repository represents the first phase of the project.

The immediate goal is to build a robust foundation before adding advanced autonomous capabilities.

---

# License

MIT
