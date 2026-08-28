---
id: M3-jira-automation
title: M3 — Pipeline Jira automation
type: milestone
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-208
---

# M3 — Pipeline Jira automation

**Closed 2026-07-06.** Jira: RHAIFIRST-208, child RHAIFIRST-209.

## Goal

Make the pipeline's Jira interaction complete enough that a human watching Jira can see what the pipeline
is doing without reading CI logs.

## Delivered

- Epics and their parent STRAT auto-assigned to the `rhoaieng` automation bot when processing starts
- Parent STRAT auto-transitioned to In Progress when epic work begins
- Idempotent: safe to run repeatedly with no side effects ([ADR-0009])

## Outcome

Delivered. Combined with PR links posted as Jira comments (`e9d023d`), Jira became the shared human
interface to an autonomous pipeline — which is what makes [ADR-0007] load-bearing rather than incidental.

## Tasks

- [[task-auto-assign-epics-to-automationbot]]
