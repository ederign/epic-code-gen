---
id: bug-clone-fault-marks-epic-failed
title: A clone or credential fault marks the epic terminally Failed
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0025]
---

# Bug: A clone or credential fault marks the epic terminally Failed

## Summary

`setup_target_repo()` treats any non-zero exit from `clone_target.py` as an
epic failure and writes `status: Failed`. `Failed` is in `CI_TERMINAL_STATES`,
so the epic is skipped on every subsequent run and only a hand-edit of
`run-metadata.yaml` in the data repo brings it back.

But a clone failure is an *environment* fault, not a property of the epic:
an expired or unauthorised token, a private repo, a transient GitHub 5xx, a
network blip. Nothing about the epic changed, and the next run — after the
variable is fixed — would succeed.

This is the same distinction [ADR-0025] draws for missing tools, where the
toolchain preflight deliberately leaves status at `Ready` so the epic retries
once the image is fixed. Clone faults were never brought into line with it.

## Reproduction

Point an epic at a private repo whose token is wrong or absent, then run the
pipeline twice.

## Expected

Run 1 flags the epic and generates nothing; status stays `Ready`. Run 2, after
the credential is corrected, picks it up and proceeds.

## Actual

Run 1 sets `status: Failed` with a `failure_reason`. Run 2 skips the epic
because `Failed` is terminal. The epic is stuck until someone edits the data
repo by hand.

Observed live on RHAISTRAT-2671: `RHAI-760` went `Ready → Failed` on a 404
caused by [[bug-slug-extractor-truncated-repo-names]], and had to be reset with
a manual commit to the data repo before the fix could even be tested.

## Impact

Medium. It does not corrupt anything, but it converts every transient
infrastructure fault into manual data-repo surgery, and it does so silently —
the dashboard shows a red epic that looks like a codegen failure.

## Proposed Fix

Classify the clone failure the way preflight already classifies a missing tool:

- Credential / not-found / network faults → leave `status: Ready`, record the
  reason, generate nothing. Retryable by construction.
- Genuinely epic-caused faults (a `target_repo` that is malformed or absent
  from `config/repo_mapping.json`) → `Failed`, since a re-run cannot help.

Worth extracting the retryable-vs-terminal judgement into one helper shared
with the preflight gate, rather than a second ad-hoc copy of the rule.

## Related

- [[bug-slug-extractor-truncated-repo-names]]
- [[task-toolchain-preflight]]
- [[task-per-repo-github-identity]]
