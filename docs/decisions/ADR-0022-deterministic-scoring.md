---
id: ADR-0022-deterministic-scoring
title: Reviewers classify severity; Python computes the score
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["a7326fe", "788f16f"]
decisions: [ADR-0021, ADR-0023, ADR-0026]
---

# ADR-0022: Reviewers classify severity; Python computes the score

## Status

Accepted (2026-07-09). **The pivotal decision of the project.**

## Context

Reviewers used to report a score directly: "architecture: 8.5". The scores were not defensible. The
same class of defect scored differently across dimensions and across runs, and — the observation that
forced the change — **a reviewer could write up a Critical finding and still award 8.5**, because the
number was a separate act of judgment from the analysis.

Since a weighted average of those numbers decided whether a PR was opened, the gate was resting on a
model's willingness to be harsh about its own colleague's output.

## Decision

Reviewers classify findings by severity. **Python computes the score.**

```
score = max(1, 10 − 5.0·Critical − 1.5·Important − 0.5·Minor)
```

Verified constants (`score_reviews.py:34-49`): `CRITICAL_WEIGHT 5.0`, `IMPORTANT_WEIGHT 1.5`,
`MINOR_WEIGHT 0.5`, `CRITICAL_CAP 5.0` ([ADR-0023]).

Dimension weights: architecture 0.30, tests 0.30, lint 0.20, intent 0.20.

Verdict thresholds: `pass` at ≥ 8.0 with no dimension below 6.0; `near-miss` at ≥ 7.0; else `fail`;
`incomplete` if a dimension is missing.

Findings are counted by parsing the review markdown — a `#### Critical` heading opens a section, and a
line matching `^\d+\.\s+\*\*` is one finding. The dimension name comes from the filename.

## Consequences

### Positive

- The score is reproducible. Re-running the scorer on the same reviews yields the same number, and
  anyone can recompute it by hand from the findings.
- A Critical cannot hide inside a passing score.
- It removes an entire category of self-assessment optimism from the gate — the model is asked "is this
  a Critical?", which it is good at, instead of "what number does this deserve?", which it is not.
- Score progressions became meaningful as evidence: 2.4 → 4.9 → 7.2 → 9.4 reflects findings closing.

### Negative

- **Severity classification is now the whole game.** The pressure moved rather than disappearing: a
  reviewer that calls a Critical "Important" moves the score 3.5 points. `24d8078` had to calibrate
  every reviewer, and `788f16f` add the cap, to keep classification honest.
- Finding count is a crude proxy for severity of impact. Five Minors (−2.5) outweigh one Important.
- The markdown parse is brittle and **fails open**: an unrecognized heading yields zero findings and
  therefore a perfect 10.0.
- `_ci_handle_review_pending` re-implements the pass rule instead of reading the computed `verdict`, so
  two copies exist and only one of them fails on a foreign `validation.json` ([ADR-0024]). Open bug.
- It does not prevent the gate being bypassed entirely — RHAIFIRST-391 opened a PR from a version that
  was never scored at all.
