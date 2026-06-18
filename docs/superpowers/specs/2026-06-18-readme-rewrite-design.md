# README Rewrite Design

## Objective

Replace the current implementation-oriented README with a capability-first
document that helps a developer understand, evaluate, and run OpenClaw in under
two minutes without overstating the prototype.

## Narrative

The README opens with one concrete claim: OpenClaw runs pytest and applies
validated patches in a bounded retry loop. It then lists only implemented
behavior. A terminal demo shows a failing calculator test, the three visible
agent log stages, the resulting diff, and the passing test.

The demo explicitly identifies mock mode. Today, the failure output must contain
an `OPENCLAW_PATCH_START` / `OPENCLAW_PATCH_END` unified diff. Repository
intelligence retrieves bounded code context, but no real model is connected.

## Operation And Safety

Quick Start uses the existing `main.py --repo` interface and lists Python, Git,
and pytest as prerequisites. The destructive startup behavior (`git reset
--hard HEAD` plus `git clean -fd`) appears before the run command. Clone mode is
shown separately.

## Trust Boundaries

Limitations state that OpenClaw is a local pytest prototype, has no long-term
memory, is not fully autonomous, does not support arbitrary model-generated
fixes yet, and is not production-ready. The roadmap contains only real model
integration, stronger retrieval, and broader test/project support.

## Style

Use short paragraphs, direct headings, terminal/code blocks, and flat bullets.
Avoid badges, slogans, buzzwords, unsupported performance claims, and broad
future architecture descriptions.
