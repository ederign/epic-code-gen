---
id: ADR-0028-unscored-verifiers
title: Unscored verifiers inform triage but never score
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["5e19a14", "d0f2a2d"]
decisions: [ADR-0022]
---

# ADR-0028: Unscored verifiers inform triage but never score

## Status

Accepted (2026-07-09 wiring, 2026-07-11 interactions).

## Context

The four scored dimensions are structural: does the code match conventions, is it tested, does it lint,
does it match the epic. Code can satisfy all four and still not work.

Two specific gaps. **Wiring**: a handler exists, a test covers it, and nothing calls it — every link
present except one. **Interactions**: the form renders, the callback is registered, and a race or a
missing `switch` branch means the flow breaks at runtime. Neither is visible to a reviewer reading a
diff for conventions.

Adding these as scored dimensions was rejected. Their findings are binary rather than graded — wiring is
either connected or it isn't, so a "Minor wiring finding" is close to meaningless — and folding them into
the weighted average would require re-deriving weights that had just been calibrated.

## Decision

Two additional agents, dispatched in parallel with the four reviewers, **not scored**:

| Agent | Traces | Output |
|---|---|---|
| `wiring-verifier` | trigger → chain → outcome, per AC | `### Wiring Traces` table + findings |
| `interaction-verifier` | user interactions, enum/branch completeness | traces + findings |

`review_cycle.py`'s `REVIEWERS` table holds six entries, four flagged as scored. The verifiers' findings
go to the `iteration-reviewer` as triage input, where they can motivate a fix without moving a number.
`wiring-verifier.md` notes "Minor: none expected — wiring is binary."

## Consequences

### Positive

- Catches a defect class the structural reviewers provably miss, without disturbing calibrated weights.
- Keeps the score interpretable: four dimensions, published weights, reproducible arithmetic.
- Present for 20 and 19 epic-versions respectively in the data repo, so they are actually running.

### Negative

- **Advisory findings can be ignored, and advisory signals in this system have a track record of being
  ignored** — the same shape as the `validation.json` gate that fired and was walked past
  ([ADR-0024]). A broken wiring trace costs nothing automatically.
- `review_cycle.py wait` returns when the four *scored* files land, so the verifiers may still be
  running when triage reads their files. Triage cannot distinguish "clean" from "never finished". Open
  bug.
- Two more parallel agents per version, on the critical path, for output that does not gate.
- Absent from `README.md` and `CLAUDE.md`; `interaction-verifier` is documented nowhere outside its own
  definition.
