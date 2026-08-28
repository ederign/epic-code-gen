<!--
Every PR needs a ledger companion. See AGENTS.md §3.
If this PR genuinely needs none (typo, dep bump, docs-only), write:
    Ledger: none — <reason>
-->

## What

<!-- One or two sentences. What changed, and why it needed to change. -->

## Ledger

<!--
Link the task/bug/ADR file(s) this PR carries. At least one, or an explicit `none` with a reason.

- Task:     docs/tasks/done/<file>.md      (moved from current/ in this PR)
- Bug:      docs/bugs/fixed/<file>.md      (moved from open/ in this PR)
- Decision: docs/decisions/ADR-NNNN-<file>.md
-->

- Task:
- Bug:
- Decision:
- Jira: <!-- optional, opened on demand — see AGENTS.md §3 "Companion Jira". Omit or write "n/a". -->
        <!-- If you opened one, put this PR's ledger path in the Jira issue too. -->

<!--
The ledger file is required. The Jira issue is not — open one when the work needs to be visible
outside this repo, assigned, or linked to other Jira work. Don't file one just to fill this line.
-->


## Evidence

<!--
Required for anything moving to done/ or fixed/. Not prose — artifacts.
What proves this works? Test names, job URLs, before/after output, artifact paths.
"Tested manually" is not evidence.
-->

- [ ] `make test-unit` passes
- [ ] `make test` passes
- [ ] New logic has tests in this PR (or: N/A because …)
- [ ] Acceptance Criteria in the ledger file are checked off, with evidence recorded **in the file**

## Risk

<!--
What could this break, and how would we notice? Say "none" only if you mean it.
Call out anything touching: run-metadata.yaml writes, scoring, the CI state machine,
or the target-repo clone/PR path.
-->
