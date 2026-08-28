---
id: bug-validation-runs-before-deps-installed
title: setup_target_repo validates the repo before installing its dependencies
type: bug
status: open
repos: [epic-code-gen]
---

# Bug: setup_target_repo validates the repo before installing its dependencies

## Summary

`setup_target_repo` runs validation at step 2 and installs dependencies at step 3, then stores the step-2 result in `pre-setup.json` — which the skill reads to skip its own validation.

## Reproduction

1. Read `run_pipeline.py:401-435`: step 2 `validate_target.py --json`, step 3 `_install_deps`, step 4 readiness.
2. Read SKILL.md Step 4, which reads `pre-setup.json` and skips its own validation.

## Expected

Validation runs against a tree whose dependencies are installed.

## Actual

The `validation` object in `pre-setup.json` records lint/test results from an un-installed tree, where checks may fail or be unrunnable for reasons that no longer hold.

## Impact

Medium

## Evidence

**Currently harmless** — the skill uses `pre-setup.json` only for language detection, not for the validation verdict. But the field is present, documented as validation output, and an obvious thing for a future change to start trusting. Filed now precisely because it is latent rather than active.

## Related Tasks

- [[task-target-validation-and-language-detection]]
- Fix: reorder to install-then-validate, or drop `validation` from `pre-setup.json`
