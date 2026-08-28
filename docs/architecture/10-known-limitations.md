---
id: 10-known-limitations
title: Known limitations
type: plan
status: current
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
---

# Known limitations

What this system does not do well, stated plainly. Individual defects live in
[`../bugs/open/`](../bugs/open/); this is the structural view.

## 1. It reports success it hasn't earned

The defining failure mode. Five of the twelve epics under RHAIFIRST-168 are bug reports and **all five
describe a silent success**:

| Issue | What was reported | What happened |
|---|---|---|
| 374 | job exit 0, "2 skipped" | strategy deadlocked; two merge-quality PRs stranded |
| 375 | review answered | `CHANGES_REQUESTED` bodies dropped entirely |
| 391 | `codegen_outcome: completed`, PR opened | PR came from a version never reviewed or scored |
| 392 | `lint: 4.5`, epic failed | the repo's own `main` was red; epic never touched those files |
| — (`d807dca`) | generic failure | the real fix-agent error was swallowed |

This is structural, not incidental: a system that reviews its own output will rate that output as good
unless something outside the model's judgment says otherwise. Every hardening fix has been the same move —
take a decision away from the model ([ADR-0022], [ADR-0026]), or make the failure loud ([ADR-0015]).

**Still true today:** advisory signals get ignored. In RHAIFIRST-391 the `validation.json` provenance guard
fired, was recorded in `scores.json`, and the orchestrator opened the PR anyway. Writing a finding down is
not the same as blocking on it.

## 2. Manual intervention is routine, not exceptional

**39 of the data repo's 104 commits are humans repairing state.** Their subjects read as an incident log:
`Unwedge RHAI-74/RHAI-76 from invalid 'completed' state`, `Restore RHAI-75 to PRCreated after a clobbered
state file`, `Fix RHOAIENG-72532 target_branch: master (not main)`, and ~12 × `Clean RHOAIENG-72103 for
re-run with <fix>`.

This is the direct cost of git-as-database ([ADR-0008]): every recovery is a hand-edited YAML commit. The
merge guard ([ADR-0014]) removed the largest cause, but the recovery mechanism is unchanged.

## 3. No concurrency protection

`codegen-run` has **no `resource_group`**. Two concurrent manual triggers race on the data repo, mitigated
only by push-retry-with-rebase (3 attempts, `-X theirs`). `FOREDER.md` identified this in June as the
prerequisite for moving off a manual trigger; it is still unaddressed, which is the real reason the
pipeline is still manually triggered.

## 4. The review gate is bypassable

Scoring is deterministic ([ADR-0022]) and the loop is Python ([ADR-0026]), but the skill still has to
*call* the loop. The anti-fallback rule ("never write review files yourself") is a prompt instruction, not
a mechanism, and reviewers hold `Write` by necessity ([ADR-0027]). RHAIFIRST-391 is that gap being
exercised.

## 5. Baseline repo health is not separated from epic quality

A target repo whose `make lint` is red on `main` fails every epic generated against it. Worse, GNU make
stops at the first failing prerequisite, so an early baseline failure **conceals** genuine findings that
would have run after it. RHAIFIRST-392, open. The `unrunnable` ≠ `failed` distinction ([ADR-0025]) covers
checks that *couldn't run*, not checks that fail for reasons the epic didn't cause.

## 6. Growth is unbounded

The data repo is 33 MB for 24 epics, **13.7 MB of it three OTEL files** (one is 9.8 MB). Versions
accumulate and are never deleted, by design. No pruning strategy exists — predicted in `FOREDER.md`.

## 7. Single-owner dependencies in the critical path

The brains repo is on personal GitHub (`github.com/ederign/epic-code-gen`) and the CI image on personal
Quay (`quay.io/ederignatowicz/`), while the other three repos are under
`gitlab.com/redhat/rhel-ai/agentic-ci/`. Two bus-factor-one dependencies for a pipeline being positioned
for production rollout.

## 8. This repo does not meet its own standards

The product's value proposition is enforcing lint, tests, and conventions on other repos. On itself, as of
2026-07-31:

- **No CI** at all until this ledger added one, and **no linter or type checker** for 10.5k Python lines.
- `jira_utils.py` — 1,055 lines including the whole Markdown↔ADF converter — has **zero tests**. So do
  `frontmatter.py`, `state.py`, and `parse_prototype.js` (699 lines, no JS test runner configured).
- `make test` **always fails** — `test-integration` collects zero tests and pytest exits 5.
- Six independent YAML parsers, three git wrappers, two HTTP clients, two slug extractors.
- `rubrics/` is 424 lines of dead, contradictory calibration still in the tree.
- `README.md` claims 186 tests (actual: 703), 3 iterations (actual: 10), and documented a script that did
  not exist.
- `.claude/settings.json`'s allowlist omits scripts the skill actually runs — masked in CI by
  `--dangerously-skip-permissions`, prompts interactively.

## 9. Cost is high and unbudgeted per epic

Everything runs on opus with no per-agent downgrades ([ADR-0029]) — deliberate, because cheaper reviewers
produced *higher* scores. ~$80 across 39 passes. Up to 10 codegen iterations plus 5 review-response
cycles, each dispatching 6+ agents, with no early-abandon on a flat score progression.

## 10. Reviewer calibration is unverified

Scores are computed from severity classifications ([ADR-0022]), so classification is now the whole game —
a Critical mislabelled Important moves a dimension 3.5 points. There is **no calibration test** asserting
that a known-Critical defect is classified Critical. Finding parsing also **fails open**: an unrecognized
markdown heading yields zero findings and therefore 10.0.
