---
id: 02-pipeline-state-machine
title: The CI state machine — nine states and every transition
type: plan
status: current
repos: [epic-code-gen]
decisions: [ADR-0009, ADR-0013, ADR-0015]
---

# The CI state machine

Until this document, the transition graph existed **only** as `if/elif` in
`scripts/run_pipeline.py:1127-1974`. Everything below is read from that code; line numbers are cited so
it can be re-verified when the code moves.

Each pipeline run takes **exactly one action per epic** ([ADR-0009]). Progress happens across runs.

## States

`CI_STATES` (`artifact_utils.py:31`) — the vocabulary of the `status` field in `run-metadata.yaml`,
owned solely by `run_pipeline.py` ([ADR-0013]):

| State | Meaning |
|---|---|
| `Pending` | Never processed. Freshly discovered from Jira. |
| `Ready` | Eligible to generate. Dependencies resolved. |
| `Generating` | Codegen in flight. **Transient** — only seen if a run died mid-generation. |
| `ReviewPending` | Code generated and scored; awaiting the PR decision. |
| `PRCreated` | PR is open upstream. Waiting on human/bot review. |
| `PRChangesRequested` | Review left actionable feedback. |
| `Done` | **Terminal.** PR merged. |
| `Blocked` | Waiting on a dependency epic. |
| `Failed` | **Terminal.** Unrecoverable without intervention. |

`CI_TERMINAL_STATES = {"Done", "Failed"}` (`run_pipeline.py:87`).

## Dispatch

`ci_process_epic()` (`:1127`) runs these guards **before** any state handler:

| Order | Guard | Result |
|---|---|---|
| 1 | `state is None` | `_init_epic_state()`, save, continue as `Pending` |
| 2 | `normalize_epic_state()` | maps foreign/legacy values onto `CI_STATES` ([ADR-0015]) |
| 3 | `not is_codegen_project(epic)` | `SKIPPED` — "Project not in codegen scope" |
| 4 | `has_skip_label(epic)` | `SKIPPED` — "Skipped (epic-code-gen-skip)" |
| 5 | `current in CI_TERMINAL_STATES` | `SKIPPED` — "Terminal state: …" |
| 6 | dispatch to `_ci_handle_<state>` | — |
| 7 | **unrecognised state** | `FAILED`, and the state file is **left untouched** |

Guard 7 is the RHAIFIRST-374 fix. The comment at `:1175-1181` is explicit about why the state is not
overwritten: *"we do not understand this document, and overwriting it would destroy the evidence a human
needs, so the run keeps failing until someone fixes it."* Previously this branch was a silent `SKIPPED`
that still exited 0, so an epic was skipped forever while CI reported success.

`Generating` deliberately routes to `_ci_handle_ready` (`:1163-1164`) — a run that died mid-generation
retries generation.

## Transitions

Every `return` in every handler. Action is one of `PROCESSED` / `SKIPPED` / `BLOCKED` / `FAILED`;
`FAILED` makes `main()` exit 1.

### `Pending` — `_ci_handle_pending` (`:1206`)

| → | Action | Condition | Line |
|---|---|---|---|
| `Blocked` | BLOCKED | unresolved dependencies | 1223 |
| `Ready` | PROCESSED | classified as ready | 1228 |

### `Ready` / `Generating` — `_ci_handle_ready` (`:1231`)

| → | Action | Condition | Line |
|---|---|---|---|
| `Ready` | PROCESSED | `--dry-run` | 1236 |
| `Failed` | FAILED | target repo setup failed | 1250 |
| **`Ready`** | **FAILED** | **toolchain preflight gap — no code generated** | 1266 |
| `ReviewPending` | PROCESSED | codegen completed | 1305 |
| `Failed` | FAILED | codegen failed | 1312 |

Line 1266 is the deliberate action/state disagreement: a missing tool is an environment fault, so state
stays `Ready` to retry once the image is fixed, but the action is `FAILED` so the run exits non-zero and
is visibly broken ([ADR-0025]). Consequence: it exits 1 on **every** run until someone rebuilds the
image — no backoff, no alert hook.

### `ReviewPending` — `_ci_handle_review_pending` (`:1315`)

| → | Action | Condition | Line |
|---|---|---|---|
| `ReviewPending` | SKIPPED | no scores yet | 1331 |
| `PRCreated` | PROCESSED | passed → PR opened | 1366 |
| `Failed` | FAILED | PR creation failed | 1373 |
| `PRCreated` | PROCESSED | **near-miss (≥7.0) → PR opened anyway** | 1391 |
| `Failed` | FAILED | iterations exhausted below near-miss | 1399 |
| **`Ready`** | PROCESSED | **failed but budget remains → iterate again** | 1404 |

The `→ Ready` edge at 1404 is the review loop's outer cycle, and the only backward edge in the graph.

> **Known defect:** this handler re-implements the pass rule (`avg >= 8.0 and dims_ok`, hard-coded 6.0
> floor, `:1348`) instead of reading the `verdict` `score_reviews.py` already computed. Two copies of the
> rule, and only the `score_reviews` copy fails on a foreign `validation.json` — so they can disagree.
> See `docs/bugs/open/`.

### `PRCreated` — `_ci_handle_pr_created` (`:1408`)

| → | Action | Condition | Line |
|---|---|---|---|
| `PRCreated` | SKIPPED | no PR URL / no GitHub token / no status change | 1413, 1424, 1457 |
| *derived* | PROCESSED | PR state changed | 1460 |
| `Done` | PROCESSED | **PR merged** | 1470 |
| `Ready` | PROCESSED | PR closed unmerged → regenerate | 1475 |
| *derived* | SKIPPED | other derived state | 1476 |
| `Done` | PROCESSED | PR merged, detected via `gh` fallback | 1486 |
| `PRCreated` | SKIPPED | PR still open | 1487 |

### `PRChangesRequested` — `_ci_handle_pr_changes` (`:1490`)

| → | Action | Condition | Line |
|---|---|---|---|
| `PRChangesRequested` | SKIPPED | dry-run / nothing actionable | 1495, 1515 |
| `PRChangesRequested` | PROCESSED | — | 1499 |
| `Failed` | FAILED | setup / review-response failure | 1510, 1531, 1633 |
| `PRCreated` | SKIPPED | rebase-only cycle, **no iteration consumed** | 1612 |
| `PRCreated` | PROCESSED | fixes applied and pushed | 1626 |

Line 1612 implements the [ADR-0031] rule: a cycle that rebases nothing and finds nothing actionable must
not consume an iteration, or an unaddressable review loops until the budget is gone.

### `Blocked` — `_ci_handle_blocked` (`:1687`)

| → | Action | Condition | Line |
|---|---|---|---|
| `Blocked` | BLOCKED | still blocked | 1703 |
| → `_ci_handle_ready` | *(inherited)* | deps resolved — **falls through in the same run** | 1706+ |

When dependencies resolve, the handler sets `Ready`, deletes `blocked_by`, and immediately delegates to
`_ci_handle_ready`, reporting `from: "Blocked"`. So an unblocked epic generates in the *same* pass rather
than waiting for the next one (`1045c53`).

> **Subtlety worth knowing:** the dependency check reads each dependency's **data-repo state** and
> requires `status == "Done"` (`:1694-1700`) — not its Jira status. Initial eligibility classification in
> `_ci_handle_pending` uses **Jira**. Two different authorities for "is this dependency finished",
> depending on which state you are in.

## Graph

```
                    ┌─────────┐
                    │ Pending │
                    └────┬────┘
              deps unmet │ │ ready
                  ┌──────┘ └──────┐
                  ▼               ▼
            ┌─────────┐     ┌──────────┐
            │ Blocked │────►│  Ready   │◄──────────┐
            └─────────┘ deps└────┬─────┘           │
             (falls through)     │                 │
                                 │ codegen         │ fail, budget left
                                 ▼                 │ (1404)
                        ┌────────────────┐         │
                        │ ReviewPending  │─────────┘
                        └───────┬────────┘
                    pass / near-miss │
                                 ▼
                        ┌────────────────┐   changes requested
                        │   PRCreated    │◄─────────────────┐
                        └───┬────────┬───┘                  │
                     merged │        │ review feedback      │
                            ▼        ▼                      │
                       ┌──────┐  ┌─────────────────────┐    │
                       │ Done │  │ PRChangesRequested  │────┘
                       └──────┘  └─────────────────────┘
                      (terminal)      fixes pushed

    Any state ──► Failed (terminal)   on unrecoverable error
    PRCreated ──► Ready               if PR closed unmerged (1475)
```

## Reading a run

`pipeline-runs/<run_id>.json` records `action`, `result`, `reason`, and `transitions` per epic;
`actions.json` records `{epic, from, to, version}` and feeds the dashboard's state-log view. In the data
repo, `<strategy>/run-log.jsonl` is the durable append-only history — 39 recorded passes to date.

Observed `to`-state distribution across those 39 passes: `Ready` 20, `PRCreated` 16, `Blocked` 10,
`Done` 4, `Failed` 3, `ReviewPending` 3, `Generating` 1. `PRChangesRequested` appears only as a `from`,
which is expected — it is entered by observing GitHub, not by a transition the pipeline records.
