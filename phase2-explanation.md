# Phase 2: Manual POC — Explanation

## What Was Built

Phase 2 proved the spec-to-code-to-validate mapping works end-to-end by manually generating code for RHAISTRAT-1749-E001: "Expose ModelConfig on Prompt and PromptVersion structs in MLflow Go SDK."

### Pivot from RHAISTRAT-1665

Originally targeted RHAISTRAT-1665 (text search on RHOAI Resources page). Pre-implementation exploration discovered the feature already exists in odh-dashboard (`LearningCenterToolbar.tsx` has `SearchInput`, `matchesSearch()`, and `keyword` URL param). Pivoted to RHAISTRAT-1749-E001. This validated Fullsend's principle: "Generation is the solved part — invest in review and intent verification."

### Bug Fix: Escaped Backtick Parsing

The `fetch_epic.py` body parser used `(.*?)` regex which terminated at escaped backticks (`\``) inside JS template literals, truncating epic body content. Fixed with `(?:[^`\\]|\\.)*)` to properly skip escaped characters. Added test for escaped backtick preservation. This bug would have silently truncated every epic body containing inline code formatting — a critical fix for the pipeline.

### Target Epic

**RHAISTRAT-1749-E001**: Add `ModelConfig` field to `Prompt` struct and populate it in `ListPrompts()` and `ListPromptVersions()` responses. The SDK already parsed `_mlflow_prompt_model_config` tags for `LoadPrompt()` but discarded the data in list operations.

- Repo: `opendatahub-io/mlflow-go` (Go 1.24)
- Readiness: 9/12 (Pass)
- AI Score: 5/9
- Effort: S (~10 lines of actual code change)
- Dependencies: None
- Iterations needed: 1 (zero fix iterations)

### Changes Made (in mlflow-go)

**`prompt.go`**: Added `ModelConfig *PromptModelConfig` field to `Prompt` struct.

**`client.go`**: Two function modifications:
1. `registeredModelToPrompt()`: Parse `tagModelConfig` from `rm.LatestVersions[0].Tags`, populate `p.ModelConfig`
2. `modelVersionToPromptVersionWithoutTemplate()`: Parse `tagModelConfig` instead of stripping it as internal tag

**`client_test.go`**: Two new tests:
1. `TestListPrompts_ModelConfig` — verifies ModelConfig populated from latest version tags, nil when missing
2. `TestListPromptVersions_ModelConfig` — verifies ModelConfig on versions, tag not leaked to user Tags

### Validation

- `go build ./...` — compiles clean
- `make lint` — 0 issues (golangci-lint)
- `make vet` — clean
- `make test/unit` — all tests pass (including 2 new)

### Artifacts Produced

```
artifacts/
  epic-tasks/RHAISTRAT-1749-E001.md        # Epic-task with frontmatter (status=Generated)
  codegen-runs/RHAISTRAT-1749-E001/
    readiness-assessment.md                 # 9/12, passes threshold
    codegen-spec.md                         # Spec-first document: 3 changes, AC mapping
    run-metadata.yaml                       # Iteration count, validation status
    final-diff.patch                        # The actual diff
```

## Lessons Learned

### What Worked Well

1. **Exact file paths and line numbers in the epic spec were invaluable.** The strategy identified `registeredModelToPrompt()` at `client.go:231-268` and `modelVersionToPromptVersionWithoutTemplate()` at ~line 211. This precision meant zero time spent on codebase exploration for locating the change points.

2. **Pattern replication is the sweet spot for AI code generation.** The existing `modelVersionToPromptVersion()` function already had the exact ModelConfig parsing pattern (lines 170-175). The change was literally "copy this 5-line block and adapt to 2 other functions." This is Superpowers' "reference-based adaptation" in its purest form.

3. **Repo readiness assessment predicted difficulty accurately.** 9/12 score with CLAUDE.md, linter, CI, tests — the repo was ready for code generation. The high score correlated with zero iteration failures.

4. **Spec-first approach (codegen-spec.md) prevented scope creep.** Writing the spec before touching code forced clarity on exactly what to change and why. The spec served as both prompt and audit trail.

5. **Single-iteration success on the first try.** The combination of precise spec + existing pattern + well-tested repo = zero fix iterations needed. The codegen loop's value is insurance, not the expected path for well-specified epics.

### What Needs Improvement

1. **Body parsing was silently broken.** The escaped backtick bug truncated ALL epic bodies containing inline code. If we hadn't manually inspected the generated file, we'd have passed truncated specs to the codegen agent. Lesson: always validate parsed content length against source.

2. **`target_repo` is not in structured metadata.** It lives in the body prose as "the repo `opendatahub-io/mlflow-go`". The epic-task generator leaves it blank, requiring manual `frontmatter.py set`. The codegen skill will need to extract this from component metadata or body heuristics.

3. **`effort_size` estimation was wrong.** The parser estimated "M" but the change was clearly "S" (~10 lines). The heuristic uses AI signal score + body length, but body length reflects spec verbosity, not implementation complexity. Needs calibration.

4. **No integration test was written.** The codegen spec mapped AC to unit tests only. For a real PR, integration tests against a running MLflow server would strengthen confidence. The mlflow-go repo has integration test infrastructure (`test/integration/`) but it requires `make dev/up` to start a local MLflow instance.

### Implications for Phase 3 (Skill Automation)

1. **Pattern discovery is critical.** The skill needs to find reference implementations automatically. For this epic, `grep -n tagModelConfig` would have found both the constant definition and the existing parsing pattern in 2 seconds.

2. **Codegen spec should be a template.** The structure is repeatable: files to modify, reference patterns, AC→test mapping, constraints. A `codegen_spec.py` script can generate the skeleton.

3. **Validation sequence is clear.** For Go: `go build → make lint → make vet → make test/unit`. The skill can detect language from `go.mod` or `package.json` and select the right validation pipeline.

4. **Iteration budget of 10 is generous for S-effort epics.** Consider scaling budget by effort_size: S=5, M=10, L=15, XL=20.

## Commits (in epic-code-gen repo)

1. `d0a29e8 fix: handle escaped backticks in epic body template literals`
2. (artifacts in gitignored directories — readiness assessment, codegen spec, run metadata)

## Commits (in mlflow-go repo)

1. `78ccdec feat: expose ModelConfig on Prompt and PromptVersion list operations`
