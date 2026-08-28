---
id: ADR-0002-frontmatter-as-metadata-contract
title: YAML frontmatter as the metadata contract
type: adr
status: accepted
repos: [epic-code-gen]
commits: ["ae79932"]
decisions: [ADR-0001]
---

# ADR-0002: YAML frontmatter as the metadata contract

## Status

Accepted (2026-06-22).

## Context

Artifacts are markdown files agents read as prose ([ADR-0001]), but the pipeline also needs
structured fields from them — which epic, which target repo, what status, which dependencies.
Parsing prose for these is unreliable; keeping a parallel index invites drift.

## Decision

Every task and review artifact carries YAML frontmatter, and **schemas live in exactly one module**:
`scripts/artifact_utils.py` defines `SCHEMAS` for `epic-task`, `codegen-run`, and `codegen-review`,
with types, required flags, enums, and defaults.

Skills never parse YAML. They shell out to `scripts/frontmatter.py`:

```bash
python3 scripts/frontmatter.py schema epic-task
python3 scripts/frontmatter.py read <path>          # validated JSON
python3 scripts/frontmatter.py set <path> field=value
python3 scripts/frontmatter.py merge-run-metadata <path> field=value
```

Validation happens on read, so a malformed artifact fails at the boundary rather than three steps
later.

## Consequences

### Positive

- One place to change a field. `CI_STATES` and `CODEGEN_OUTCOMES` being defined here is what made
  the RHAIFIRST-374 fix a small change rather than a hunt ([ADR-0013]).
- Human-readable and machine-readable in the same file; no sidecar to keep in sync.
- The CLI boundary means a skill's prompt cannot invent a field name that silently does nothing —
  `set` rejects unknown fields against the schema.

### Negative

- `run-metadata.yaml` is **not** schema-validated in practice. `merge_run_metadata` enforces only
  two rules (reject `status=`, reject an out-of-vocabulary `codegen_outcome`); every other field is
  free-form and type-inferred. Four schema generations now coexist in the data repo, including
  `dimension_scores` vs `scores_by_dimension` for one concept.
- The `codegen-review` schema was designed and never used. Its `scores` keys (`typecheck`,
  `intent_coverage`) predate the real dimensions. Dead, tracked in `docs/bugs/open/`.
- Shelling out per field write is slow and chatty in a skill that sets many fields.
