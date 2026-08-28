---
id: task-ci-image-and-build-infrastructure
title: CI image and build infrastructure
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-201
commits: ["356a192", "48ce5bc", "5b1d019"]
decisions: [ADR-0011]
---

# Task: CI image and build infrastructure

## Goal

A single container image with every target repo's toolchain plus Claude Code, published multi-arch to Quay.

## Context

Installing toolchains per run costs minutes, needs network, and fails in ways indistinguishable from a genuine check failure — a missing `uv` once scored `lint=5.0`.

## Acceptance Criteria

- [x] UBI9 base with Go, Node 22, Python 3.11, `uv`
- [x] Claude Code CLI plus the `obra/superpowers` plugin
- [x] `make ci-image` / `ci-image-push` build multi-arch (amd64 + arm64)
- [x] Build-time version verification of every runtime

## Files Likely Involved

- `Dockerfile.ci`
- `Makefile`

## Status

Done.

## Notes

Rust was added then dropped once no target needed it. Several layers exist to fix one specific bug each — unversioned `pip`/`python` symlinks, the pre-seeded trust file, three Playwright fixes. Published to a **personal** Quay namespace, which is a bus-factor risk: [[task-move-single-owner-deps-into-org]].
