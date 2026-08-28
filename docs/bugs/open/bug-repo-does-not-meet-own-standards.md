---
id: bug-repo-does-not-meet-own-standards
title: This repo does not meet the standards it enforces on target repos
type: bug
status: open
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# Bug: This repo does not meet the standards it enforces on target repos

## Summary

The product exists to enforce lint, tests, and conventions on other repositories. Applied to itself it would score poorly on its own readiness assessment.

## Reproduction

1. Run `python3 scripts/repo_readiness.py .` against this repo.
2. Compare the result to the threshold of 8 the pipeline requires of targets.

## Expected

The repo meets the bar it sets, or the gap is deliberate and recorded.

## Actual

As of 2026-07-31: no CI at all (added by [[M7-engineering-process]]); **no linter or type checker** for 10.5k lines of Python; `make test` **always fails** because `test-integration` collects zero tests and pytest exits 5 ([[bug-make-test-fails-on-empty-integration-target]]); `jira_utils.py` (1,055 lines, including the whole Markdown↔ADF converter), `frontmatter.py`, `state.py`, and `parse_prototype.js` (699 lines) have **no tests**; six independent YAML parsers, three git wrappers, two HTTP clients, two slug extractors.

## Impact

High

## Evidence

This is a credibility problem as much as a quality one: the readiness score gates which repos are allowed to receive generated code, and the reviewers score lint conformance. `Dockerfile.ci` installs `markdownlint-cli` for target repos while nothing lints this repo's own Python.

Filed as one umbrella bug because the individual items are tracked as tasks in `docs/tasks/pending/` — this file exists so the aggregate is visible rather than spread across a dozen entries.

## Related Tasks

- [[task-fix-make-test-target]]
- [[task-add-lint-and-typecheck]]
- [[task-add-tests-for-untested-modules]]
- [[task-consolidate-yaml-parsers]]
- [[task-delete-dead-code]]
- [[M7-engineering-process]]
