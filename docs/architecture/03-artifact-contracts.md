---
id: 03-artifact-contracts
title: Artifact contracts — the exact shape of every file the pipeline passes
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
decisions: [ADR-0001, ADR-0002, ADR-0013, ADR-0014, ADR-0024]
---

# Artifact contracts

The pipeline's components communicate through files ([ADR-0001]). These are the contracts. Only the
first three are schema-validated; the rest are conventions enforced by whoever reads them.

## Schema-validated: `artifact_utils.SCHEMAS`

`scripts/artifact_utils.py:164`. Validated on read via `frontmatter.py read`.

### `epic-task` — `artifacts/epic-tasks/<EPIC_ID>.md`

| Field | Type | Req | Notes |
|---|---|---|---|
| `epic_id` | str | ✔ | `^[A-Z][A-Z0-9]+-\d+(-E\d+)?$` |
| `title` | str | ✔ | |
| `strategy_key` | str | ✔ | `^[A-Z][A-Z0-9]+-\d+$` |
| `target_repo` | str | ✔ | |
| `status` | str | ✔ | enum: `Pending, Ready, InProgress, Generated, Validated, Failed` |
| `target_branch` | str | | default `""` |
| `components`, `jira_labels`, `dependencies`, `blocks` | list | | `dependencies` = blocked-by |
| `effort_size` | str | | enum `S, M, L, XL` |
| `readiness_score`, `codegen_branch`, `pr_url`, `jira_status` | | | |

Note this `status` enum is a **fourth** vocabulary, distinct from `CI_STATES` and `CODEGEN_OUTCOMES`. It
describes the epic-task artifact, not the run.

### `codegen-run`

`epic_id` ✔, `status` (enum = `CI_STATES`), `codegen_outcome` (enum = `CODEGEN_OUTCOMES`), `iterations` ✔
(default 0), `max_iterations` ✔ (default 10), `started_at`, `completed_at`, `target_repo` ✔,
`target_branch`, `codegen_branch` ✔, `validation` (dict: `lint_pass`, `typecheck_pass`, `tests_pass`).

### `codegen-review` — **dead**

`epic_id`, `recommendation` (`approve|revise|reject`), `total_score`, `scores{lint, typecheck, tests,
intent_coverage, architecture}`.

Nothing in the pipeline has ever written one. Its `scores` keys (`typecheck`, `intent_coverage`) predate
the live dimensions. `find_codegen_review` and `rebuild_index` are dead with it. See `docs/bugs/open/`.

## `run-metadata.yaml` — the state file

**Not schema-validated.** Two writers, one file; always merge, never write ([ADR-0014]).

| Field | Owner |
|---|---|
| `status` | `run_pipeline.py` — `CI_STATES` only |
| `codegen_outcome` | the `/epic-codegen` skill — `CODEGEN_OUTCOMES` only |

`PIPELINE_OWNED_KEYS` (which the skill may never overwrite): `status`, `status_normalized_from`,
`current_version`, `max_iterations`, `pr_state`, `timestamps`, `scores`, `blocked_by`, `failure_reason`,
`tooling_missing`.

A real terminal file (`RHAISTRAT-2162/RHAI-74`):

```yaml
epic_id: RHAI-74
strategy_key: RHAISTRAT-2162
target_repo: ederign/kale
branch: epic/RHAI-74
base_sha: c2264752da1a7f4add3bf138b08fbbc982d901ea
status: Done
current_version: 7          # pipeline-owned; counts review-response cycles
max_iterations: 10
pr_state: merged
versions: 4                 # skill-owned; counts scored codegen iterations
final_version: 4
final_score: 9.4
verdict: pass
pr_url: https://github.com/ederign/kale/pull/11
fork_owner: dora-the-ai-coder
score_progression: {v1: 2.4, v2: 4.9, v3: 7.2, v4: 9.4}
dimension_scores: {architecture: 9.0, tests: 9.0, lint: 10.0, intent: 10.0}
files_changed: 8
lines_added: 1081
tests_count: 53
timestamps: {last_run: '2026-07-29T14:57:23.963082+00:00'}
```

### Known drift — four generations coexist in the data repo

| Generation | Distinctive shape |
|---|---|
| `RHAISTRAT-1749/RHOAIENG-72528` | nested `scores` with an **absolute** `reviews_dir`; no findings counts |
| `RHAISTRAT-1699/RHOAIENG-72103` | **flat** `scores{architecture, tests, lint, intent, weighted_average, verdict}` + a `features` block |
| `RHAISTRAT-1508/RHAI-64` | `iterations`, `final_version: v5` (**string**), `final_verdict`, `dimensions:` not `scores:` |
| `RHAISTRAT-1961/RHAI-68` | current: `readiness`, `codegen_outcome`, `scores_by_dimension` **and** nested `scores` |

Two names for one concept: `dimension_scores` (what production writes) vs `scores_by_dimension` (what
`SKILL.md`, `run_index.py`, and `frontmatter.py` reference). Three counters with no documented
relationship: `current_version`, `versions`, `final_version`. `RHAISTRAT-2352/RHAI-264` still carries the
pre-fix `status: completed`.

## `validation.json` — written only by `validate_target.py --out`

```
repo_path, language, marker,
commands: {lint|typecheck|test: <command string>},
checks: [ {name, command, passed, exit_code, output (≤5000 chars),
           unrunnable, missing_tool}, … ],
all_passed, unrunnable: [names], missing_tools: [executables], has_unrunnable
```

`all_passed = all checks passed AND len(checks) > 0 AND no unrunnable`. **Consumers must read
`all_passed`, never per-check keys.**

**Authenticity gate** ([ADR-0024]): `VALIDATION_DOCUMENT_KEYS = ("all_passed", "checks")`.
`validation_document_status()` → `ok` | `missing` | `foreign` | `unreadable`; `foreign`/`unreadable`
force `verdict: fail`.

`--preflight` returns a **different** shape: `{language, required, found: {tool: path|null}, missing,
ok}`. Exit 2 = missing tool; exit 1 = failing check.

## `scores.json` — written by `review_cycle.py score`

```
{
  "reviews_dir": str,
  "dimensions": { "<dim>": { "score": float, "weight": float, "weighted": float,
                             "file": str,
                             "findings": {"critical": int, "important": int, "minor": int} } },
  "weighted_average": float,
  "verdict": "pass" | "near-miss" | "fail" | "incomplete",
  "missing": [dim], "errors": [str],
  "validation": {"status": "ok"|"missing"|"foreign"|"unreadable", "detail": str|null}
}
```

Constants (`score_reviews.py:34-49`): weights architecture .30 / tests .30 / lint .20 / intent .20;
`CRITICAL_WEIGHT 5.0`, `IMPORTANT_WEIGHT 1.5`, `MINOR_WEIGHT 0.5`, `CRITICAL_CAP 5.0`;
`PASS_THRESHOLD 8.0`, `NEAR_MISS_THRESHOLD 7.0`, `MIN_DIMENSION_SCORE 6.0`, `HARD_FLOOR 5.0`.

**Findings are parsed by regex over markdown**: a heading matching
`^#{1,4}\s+(critical|important|minor)$` opens a section; a finding is a line matching `^\d+\.\s+\*\*`.
Dimension name comes from the filename via `^review-(\w+)\.md$`. This **fails open** — an unrecognized
heading yields zero findings and therefore 10.0.

## Review files — `review-<dimension>.md`

Written by reviewer agents ([ADR-0021]). Required: findings grouped under `#### Critical` /
`#### Important` / `#### Minor`, each numbered `N. **Title**`. **No score in the output.**

Per-dimension extras: architecture → `### Convention Compliance`, `### Integration Assessment`;
tests → `### AC Coverage` table, `### Edge Cases`; lint → `### Validation Results` table;
intent → `### AC-to-Diff Mapping`, `### Pass Criteria Verification`, `### Scope Fidelity`,
`### UX Acceptance Criteria Verification`, `### Scope Creep Check`.

Unscored ([ADR-0028]): `review-wiring.md` (`### Wiring Traces` table), `review-interactions.md`.

## Smaller contracts

| File | Shape |
|---|---|
| `pre-setup.json` | `{validation: <full validate dict>, readiness_output: <markdown **string**>, language, deps_installed}` |
| `pr-replies.json` | processed review-comment IDs per version |
| `tmp/epic-codegen-<EPIC>.json` | despite `.json`, `state.py`'s `key: value` **line format** |
| `tmp/accepted-findings-<EPIC>.json` | real JSON: `[{finding, dimension, accepted_in, reason}]` |
| `index.json` | `{runs: [<full run-metadata dict>], total, summary: {<outcome>: count}}` |
| `pipeline-runs/<run_id>.json` | `{run_id, start_time, end_time, strategies: {<KEY>: {total_epics, summary{processed,skipped,blocked,failed}, epics: {<EPIC>: {title, jira_status, action, result, reason, dependencies, blocks, transitions, pr_url, timestamp}}}}}` |
| `pipeline-runs/actions.json` | `{epic, from, to, version}` per transition — input to `push-results.py` |
| `config/review_config.json` | `{bot_reviewers[], our_user, max_review_iterations: 5, validation_retry_limit: 3}` |
| `config/repo_mapping.json` | `{"<owner/repo>": {"keywords": [...]}}` |

## Data-repo aggregates

Regenerated by `push-results.py` on every push; consumed by the dashboard.

- `<strategy>/strategy-summary.json` — `{strategy_key, generated_at, stats{total, done, in_progress,
  blocked, failed}, epics[{epic_id, status, current_version, pr_url, pr_state, scores, target_repo}]}`.
  `in_progress` is derived as `total − done − failed − blocked`.
- `summary.json` (top level) — `{generated_at, stats{strategies, total_epics, total_done,
  completion_rate}, strategies[…]}`.
- `<strategy>/run-log.jsonl` — append-only, one line per pass: `{timestamp, strategy, epics_processed,
  epics_skipped, epics_blocked, actions[], otel_cost_usd?}`.

> **Two live data-quality defects in these aggregates**, both tracked in `docs/bugs/open/`:
> `summary.json` reports 7 strategies but double-counts `RHAISTRAT-1699`, because the manual archive
> directory `RHAISTRAT-1699-before-ux-ac/` declares the same `strategy_key` inside its summary. And
> `scores` is `null` for every epic whose metadata uses `dimension_scores`/`dimensions`/
> `scores_by_dimension` instead of a nested `scores` block — including RHAI-74, which shows
> `scores: null` beside `final_score: 9.4`.

There is **no `index.json` in the data repo**; `run_index.py` writes it into `artifacts/codegen-runs/`.
