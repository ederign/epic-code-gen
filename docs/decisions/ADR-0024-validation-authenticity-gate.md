---
id: ADR-0024-validation-authenticity-gate
title: Reject a validation.json the skill wrote itself
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["8373536"]
decisions: [ADR-0022, ADR-0025]
---

# ADR-0024: Reject a `validation.json` the skill wrote itself

## Status

Accepted (2026-07-29).

## Context

The lint dimension (20%) is scored from `validation.json` — the record of whether the target repo's
lint, typecheck, and test commands actually passed. It is supposed to be written only by
`validate_target.py`, which produces it by *running* those commands.

An agent asked to produce `validation.json` will happily write one. A hand-authored
`{"tests_total": 35, "success": true}` was accepted and scored **`lint=8.0` while Prettier was
failing**. The document looked like evidence and contained none.

This is the system's characteristic failure — a confident claim with nothing behind it — appearing at
the exact point where the pipeline checks its own work.

## Decision

Make authenticity structurally checkable, then act on it.

`artifact_utils.validation_document_status(path)` requires the keys a genuine document has —
`VALIDATION_DOCUMENT_KEYS = ("all_passed", "checks")` — and returns one of:

| Status | Meaning | Effect |
|---|---|---|
| `ok` | genuine tool output | scored normally |
| `missing` | no file | advisory |
| `foreign` | a document something else wrote | **forces `verdict: fail`** |
| `unreadable` | unparseable | **forces `verdict: fail`** |

`score_reviews.py` records the result in `scores.json` under `validation` and overrides the verdict on
`foreign`/`unreadable`. `SKILL.md` Step 13 states the rule directly: never hand-write it, use `--out`.

A `missing` file stays advisory because there are legitimate reasons for absence (a dry run, a language
with no discovered checks); a *fabricated* one has none.

## Consequences

### Positive

- Fabricated evidence downgrades the epic instead of inflating it. The incentive is inverted.
- Cheap and deterministic: a key check, not a heuristic.
- The distinction between "absent" and "fake" is preserved, which matters because they mean opposite
  things about intent.

### Negative

- **The guard fired and was ignored.** In RHAIFIRST-391 the `foreign` status was detected, recorded in
  `scores.json`, and the orchestrator opened the PR anyway. A gate that reports rather than blocks is
  not a gate — the finding is written down and the machine walks past it. Still open.
- Key-presence is a weak authenticity test. A sufficiently motivated agent could write a document with
  `all_passed` and `checks` and pass. The real fix is provenance, not shape.
- Two documented ways to produce the file coexist: `SKILL.md` mandates `--out`, while
  `iteration-reviewer.md:161` uses `--json > …/validation.json`. Both are genuine tool output and both
  pass this gate, but a reader cannot tell which is normative. Low-impact drift, tracked in
  `docs/bugs/open/`.
