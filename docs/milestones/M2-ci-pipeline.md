---
id: M2-ci-pipeline
title: M2 — CI pipeline and dashboard
type: milestone
status: done
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-200
---

# M2 — CI pipeline and dashboard

**Closed 2026-07-06.** Jira: RHAIFIRST-200, children RHAIFIRST-201/202/203/204/205/210/211/213.

## Goal

Productionize `epic-code-gen` as a GitLab CI pipeline with durable artifact storage and a dashboard.

## Delivered

- Fat CI image with all language runtimes plus Claude Code, on Quay ([ADR-0011])
- GitLab CI pipeline, manual trigger, thin shell orchestration ([ADR-0010])
- `run_pipeline.py` CI adaptation with the nine-state machine and convergence loop ([ADR-0009])
- Data repo with strategy/epic/version layout and an append-only run log ([ADR-0008])
- Dashboard with three views: strategy drilldown, Jira state log, cost & telemetry

Three new repos were created for this milestone ([ADR-0005]).

## Outcome

Delivered and running. It also created the system's two hardest problems: two writers on one state file
(→ [[M5-state-integrity]]) and a review gate that runs unattended (→ [[M6-review-gate-hardening]]).

## Tasks

- [[task-ci-image-and-build-infrastructure]]
- [[task-gitlab-ci-and-ci-scripts]]
- [[task-ci-state-machine-and-convergence]]
- [[task-data-repo-artifact-structure]]
- [[task-dashboard-three-views]]
- [[task-fix-state-log-run-log-jsonl]]
- [[task-fix-otel-cost-telemetry]]
- [[task-pipeline-story-dashboard]]
