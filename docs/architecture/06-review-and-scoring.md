---
id: 06-review-and-scoring
title: Review and scoring — how a diff becomes a number
type: plan
status: current
repos: [epic-code-gen]
decisions: [ADR-0022, ADR-0023, ADR-0024, ADR-0026, ADR-0028]
---

# Review and scoring

## The rule

**Reviewers classify findings by severity. Python computes the score.** No model ever chooses a number
([ADR-0022]).

```
dimension_score = max(1, 10 − 5.0·Critical − 1.5·Important − 0.5·Minor)
if any Critical:  dimension_score = min(dimension_score, 5.0)      # ADR-0023
weighted_average = Σ (dimension_score × weight)
```

Constants, all in `score_reviews.py:34-49`:

| Constant | Value |
|---|---|
| architecture / tests / lint / intent weights | 0.30 / 0.30 / 0.20 / 0.20 |
| `CRITICAL_WEIGHT` / `IMPORTANT_WEIGHT` / `MINOR_WEIGHT` | 5.0 / 1.5 / 0.5 |
| `CRITICAL_CAP` | 5.0 |
| `PASS_THRESHOLD` | 8.0 |
| `NEAR_MISS_THRESHOLD` | 7.0 |
| `MIN_DIMENSION_SCORE` | 6.0 |
| `HARD_FLOOR` | 5.0 |

## Verdicts

| Verdict | Condition |
|---|---|
| `pass` | `weighted_average ≥ 8.0` **and** no dimension `< 6.0` |
| `near-miss` | `≥ 7.0` (opens a PR anyway on exhaustion — [ADR-0033]) |
| `fail` | below that |
| `incomplete` | a dimension is missing |

Because `CRITICAL_CAP` (5.0) is below `MIN_DIMENSION_SCORE` (6.0), **one Critical anywhere makes a pass
arithmetically impossible.** Not unlikely — impossible. That interaction is the real force of
[ADR-0023].

## The loop

Driven by `review_cycle.py`, not by prose ([ADR-0026]). It owns the `REVIEWERS` table — six reviewers,
four scored.

```
1. review_cycle.py prompts          → emit 6 dispatch prompts
2. dispatch 6 agents in parallel    (no agentType — ADR-0027)
3. review_cycle.py wait             → block until review files land
4. review_cycle.py verify           → files well-formed and non-empty
5. review_cycle.py score            → score_reviews.py → scores.json
6. verdict?
     pass       → save final diff, hand to PR creation
     fail       → review_cycle.py triage-prompt → iteration-reviewer
                    → fix agent → new version → back to 1
     exhausted  → near-miss (≥7.0) ? open PR anyway : report best version
```

`SKILL.md` states the hard rule: **never write review files yourself.** `5e26193` added an anti-fallback
guardrail; if dispatch fails, fail — do not improvise.

## How findings are counted

Regex over markdown, in `_extract_findings`:

- A heading matching `^#{1,4}\s+(critical|important|minor)$` (case-insensitive) opens a section.
- A finding is any line matching `^\d+\.\s+\*\*`.
- The dimension name comes from the filename: `^review-(\w+)\.md$`.

> **This fails open.** An unrecognized heading spelling yields **zero findings**, which computes to
> **10.0**. A prompt-drift regression looks exactly like flawless code. There is no test asserting that a
> known-Critical review file scores 5.0.

## The authenticity gate

The lint dimension is scored from `validation.json`, which must be genuine tool output ([ADR-0024]).
`validation_document_status()` requires `all_passed` and `checks`:

| Status | Effect on verdict |
|---|---|
| `ok` | scored normally |
| `missing` | advisory |
| `foreign` | **forced `fail`** |
| `unreadable` | **forced `fail`** |

Recorded in `scores.json` under `validation`. It exists because a hand-written
`{"tests_total": 35, "success": true}` once scored `lint=8.0` while Prettier was failing.

## Two known gaps

1. **The gate can be walked past.** In RHAIFIRST-391 `foreign` was detected, recorded, and ignored; the PR
   opened from a version that was never reviewed. A gate that reports rather than blocks is not a gate.
2. **The pass rule exists twice.** `_ci_handle_review_pending` (`run_pipeline.py:1348`) re-derives
   `avg >= 8.0 and dims_ok` with a hard-coded 6.0 floor instead of reading the `verdict`
   `score_reviews.py` computed. Only the `score_reviews` copy fails on a foreign `validation.json`, so the
   two can disagree.

Both in [`../bugs/open/`](../bugs/open/).

## Evidence that it works

Score progressions from the data repo, which are only meaningful *because* the number is computed rather
than chosen:

| Epic | Progression | Outcome |
|---|---|---|
| RHAI-74 | 2.4 → 4.9 → 7.2 → 9.4 | Done, merged |
| RHAI-64 | 2.6 → 2.65 → 6.1 → 6.7 → 8.2 | PRCreated |
| RHOAIENG-72103 | → 8.15 over 5 versions | Done (first UX-AC epic) |

Passing scores cluster 7.9–9.4. The v1 → v2 jump is consistently the largest, which is what motivated
spec-first generation ([ADR-0016]) — most of the early climb was recoverable design error.
