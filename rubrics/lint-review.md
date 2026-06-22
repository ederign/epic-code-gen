# Lint Review Rubric

**Dimension:** lint
**Weight:** 20%
**Model:** sonnet

You are reviewing code quality: whether the generated code passes lint,
typecheck, and build, and whether it follows clean code practices.

## Inputs

Read these files (do not ask for them inline):

1. **Diff file:** `DIFF_FILE` — the code changes under review
2. **Spec file:** `SPEC_FILE` — the codegen spec
3. **Validation output:** `VALIDATION_FILE` — output from validate_target.py

## Your Review Should Contain

1. **Validation results:** read the validation output file and report lint,
   typecheck, and test pass/fail status. Any validation failure is Critical.
2. **Code style consistency:** does the new code match the style of surrounding
   code in the diff context lines? Check indentation, naming conventions,
   import ordering, comment style.
3. **Error handling:** are errors handled properly? No swallowed errors. No
   bare `catch` blocks. Error messages are descriptive.
4. **Type safety:** are types used correctly? No `any` in TypeScript, no
   unchecked type assertions, no implicit conversions that lose precision.
5. **Dead code:** does the diff introduce unreachable code, unused imports,
   unused variables, or commented-out code?

## Scoring Guide

| Score | Criteria |
|-------|----------|
| 9-10 | All lint/typecheck/build pass. Code is clean, consistent, well-structured. No dead code. |
| 7-8 | Lint passes. Minor style inconsistencies. Trivial dead code (one unused import). |
| 5-6 | Lint passes with warnings. Some style issues. Error handling exists but weak. |
| 3-4 | Lint or typecheck fails. Multiple style violations. Errors swallowed or poorly handled. |
| 1-2 | Build fails. Major quality issues throughout. |

## Calibration

| Severity | Examples |
|----------|----------|
| Critical | Lint fails; typecheck fails; build fails; error swallowed that could cause data loss |
| Important | Unused import; inconsistent naming vs surrounding code; bare catch block; `any` type |
| Minor | Slightly different indent style; comment capitalization; import order preference |

## Rules

- Do not re-run lint, typecheck, or build. Read the validation output file.
- Do not mutate the working tree, index, or HEAD.
- Do not read files outside the diff unless checking a concrete named risk.
- Cite file:line for every finding.
- If the validation output file is missing, report that as Critical and score
  based on code-reading alone.

## Output Format

```
### Validation Results

| Check | Status | Notes |
|-------|--------|-------|
| lint | pass/fail | |
| typecheck | pass/fail | |
| test | pass/fail | |

### Code Quality Findings

#### Critical
#### Important
#### Minor

### Score

---
score: N
---

**Reasoning:** [1-2 sentences]
```
