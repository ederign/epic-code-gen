---
id: ADR-0011-fat-container-image
title: Fat container image over runtime installs
type: adr
status: accepted
repos: [epic-code-gen]
jira: RHAIFIRST-201
commits: ["356a192", "5b1d019", "e7c9dac", "72817df"]
---

# ADR-0011: Fat container image over runtime installs

## Status

Accepted (2026-06-30).

## Context

Codegen runs against arbitrary target repos in arbitrary languages. To validate a repo the container
needs that repo's toolchain: Go for `mlflow-go`, Node 22 for `odh-dashboard`, `uv` for `kale`,
`ruff`, `markdownlint`. Installing per run costs minutes per job, needs network, and fails
mid-pipeline in ways indistinguishable from a genuine check failure.

The specific failure mode that motivated this: a missing `uv` made `make lint` exit 127, GNU make
reported `Error 127`, and the reviewer scored it `lint=5.0` — an environment fault recorded as bad
code ([ADR-0025]).

## Decision

Bake everything into `Dockerfile.ci` (UBI9 base), published multi-arch to
`quay.io/ederignatowicz/epic-code-gen-ci`. Contents, and the reason each exists:

| Layer | Why |
|---|---|
| Python 3.11 + `pip`/`python` **unversioned symlinks** | a target Makefile may call `pip`, which would otherwise exit 127 |
| Go 1.24.4 | `mlflow-go` |
| Node 22 + yarn + `markdownlint-cli` | `odh-dashboard` needs `engines.node >= 22`; markdownlint for `pipelines-components` |
| `uv` | `kale`'s Makefile drives `uv run ruff` / `uv run pytest` |
| Playwright + chromium + X/GTK libs | `parse_prototype.js` UX prototype parsing ([ADR-0020]) |
| Claude Code CLI + `obra/superpowers` plugin | the engine and its SDD skill |
| pre-seeded `~/.claude.json` trusting `/tmp/claude-workdir` | without it Claude Code won't load `.claude/settings.json` from the clone |

Rust was added and later dropped (`5b1d019`) once no target needed it. `uv` is verified with
`test -x` rather than `uv --version`, because executing the freshly installed amd64 binary segfaults
under qemu when cross-building from arm64 (`e7c9dac`).

## Consequences

### Positive

- No per-run install latency, no network dependency mid-run, no partial-toolchain failures.
- The toolchain is versioned and reproducible: an image tag pins every target repo's tooling.
- `--preflight` can assert the toolchain is present *before* generating anything ([ADR-0025]).

### Negative

- 3–5 GB image. Slow to build, slow to pull on a cold runner.
- **The image is coupled to the set of target repos.** Onboarding a repo with a new toolchain is an
  image change, a rebuild, and a push — not a config change. `72817df` (markdownlint) and
  `370a6a6` (mlflow mapping) are both this.
- Playwright cost three separate fix commits to work headless as non-root (`210c464`, `5571f31`,
  `0346470`).
- Published to a **personal Quay namespace** in the critical path. Tracked in `docs/tasks/pending/`.
