---
id: ADR-0023-critical-caps-the-dimension
title: A Critical finding caps its dimension at 5
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["788f16f"]
decisions: [ADR-0022]
---

# ADR-0023: A Critical finding caps its dimension at 5

## Status

Accepted (2026-07-09).

## Context

With scores computed from findings ([ADR-0022]), a single Critical costs 5.0 — so a dimension with one
Critical and no other findings scores 5.0. But the arithmetic alone permits an awkward case: because
weights differ, one Critical in the lint dimension (20%) moves the weighted average by only 1.0, so an
epic with a Critical could still land near the 8.0 pass line if everything else was clean.

A Critical means "this is broken". It should not be arithmetically survivable.

## Decision

`CRITICAL_CAP = 5.0`. Any dimension containing at least one Critical finding is capped at 5, regardless
of what the subtraction produced.

Because `MIN_DIMENSION_SCORE` is 6.0 and a `pass` requires no dimension below 6.0, this makes the
consequence categorical: **one Critical anywhere means the epic cannot pass.** Not "is unlikely to" —
cannot.

The cap is also stated in every reviewer's own definition, so the reviewer knows what classifying a
finding as Critical will do.

## Consequences

### Positive

- Turns "Critical" into a real veto rather than a large penalty. The gate can be reasoned about
  categorically.
- Interacts correctly with the 6.0 floor: the two rules together mean a Critical is unappealable,
  without needing a special case in the verdict logic.
- Removes the incentive to be arithmetically clever about which dimension a Critical lands in.

### Negative

- Puts the entire weight of the gate on one classification boundary. The difference between
  "Critical" and "Important" is now the difference between cannot-pass and −1.5, decided by a model
  reading a diff.
- Creates pressure to under-classify. Whether reviewers actually feel it is unmeasured — there is no
  calibration test asserting that a known-Critical defect is classified Critical.
- **RHAIFIRST-392 is this rule misfiring.** RHAI-68's lint dimension carried exactly one Critical, and
  that Critical was `opendatahub-io/pipelines-components`' own pre-existing `make lint` failure —
  three unparseable notebook templates the epic never touched, reproduced on a pristine checkout. It
  capped lint at 4.5 and dragged 9.5/7.5/9.5 down to a 7.9 `fail`. The cap is correct; attributing an
  upstream failure to the epic is not.
