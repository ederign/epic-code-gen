---
id: ADR-0012-run-orchestrator-directly-in-ci
title: Run the orchestrator directly in CI, not wrapped in Claude Code
type: adr
status: accepted
repos: [epic-code-gen-pipeline]
commits: ["fafa60d", "6e88f27", "268769b"]
decisions: [ADR-0010, ADR-0026]
---

# ADR-0012: Run the orchestrator directly in CI, not wrapped in Claude Code

## Status

Accepted (2026-07-14, on the second attempt).

## Context

The original CI design invoked Claude Code with a prompt telling it to run the pipeline — an outer
agent driving `run_pipeline.py`, which itself invokes inner Claude sessions per epic. Two agent layers.

That outer layer had no job. `run_pipeline.py` is deterministic Python; there is no decision for a
model to make about whether to call it. What the wrapper did contribute was: an extra 6-hour context
to blow, a place for the prompt to be reinterpreted, and an opaque failure mode when the outer agent
decided to do something else. `fa80793` tried to contain it by restricting the CI prompt to only run
the pipeline command — a prompt telling a model not to think.

An attempt to remove it (`db58afa`, 07-04) was reverted the same day (`6e88f27`) because it broke CI
log streaming — the logs appeared only at the end.

## Decision

`run-codegen.sh` invokes the orchestrator directly:

```bash
python3 scripts/run_pipeline.py ${strategy_keys} --ci \
    --data-repo "${data_repo}" --fork-owner dora-the-ai-coder \
    --timeout "${CODEGEN_TIMEOUT:-21600}" 2>&1
```

Claude is still invoked — once per epic, from inside `run_pipeline.py` via `ci-scripts/run-claude.sh`,
which is where a model is actually needed. The streaming problem was solved properly rather than by
keeping the wrapper: forced foreground execution (`268769b`), a progress-monitor subshell emitting a
heartbeat every 300s (`fa8f340`), and stderr captured as a CI artifact (`6ef9fcd`).

## Consequences

### Positive

- One less context window to exhaust, and one less place for an instruction to be reinterpreted.
- CI logs stream live, with a heartbeat, so a 6-hour job is observable rather than a black box.
- The exit code is the orchestrator's own, not laundered through an agent's interpretation of it.
- Consistent with [ADR-0026]: deterministic work belongs in Python.

### Negative

- Reverted once before it stuck; the first attempt traded a real problem (log streaming) for a
  cosmetic win and had to be backed out.
- `run-claude.sh` still needs exit-code laundering for the inner session: rc 143/141 plus
  `stream_rc == 42` is treated as success, because `stream-claude.py` signals completion by
  `SIGTERM`-ing its parent and exiting 42. That hack is intentional but genuinely surprising —
  documented in `docs/bugs/wontfix/`.
