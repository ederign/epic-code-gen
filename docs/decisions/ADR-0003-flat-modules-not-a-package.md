---
id: ADR-0003-flat-modules-not-a-package
title: Flat sys.path modules instead of an installable package
type: adr
status: accepted-under-review
repos: [epic-code-gen]
---

# ADR-0003: Flat `sys.path` modules instead of an installable package

## Status

**Accepted, under review.** Recorded retroactively on 2026-07-31 — this was never a deliberate
decision, it is the shape the code grew into. It is written down here because it is load-bearing and
because changing it now would touch every file.

## Context

`scripts/` holds 20 Python modules, 10.5k lines. They import each other as top-level modules:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import github_utils
```

`scripts/__init__.py` exists but is empty, and nothing anywhere imports `scripts.x`. All 18 test
files repeat the same `sys.path.insert` bootstrap, in two different spellings.

The scripts are invoked three ways — as CLIs from a skill prompt, as subprocesses from
`run_pipeline.py`, and as imports from each other and from tests. Only the third would benefit from
being a package.

## Decision

Keep the flat layout. Modules stay directly in `scripts/`, importable by bare name after a
`sys.path` insert. Do not introduce a `src/` layout or `pip install -e .` step.

The reason to keep it: the CI image clones this repo to `/tmp/claude-workdir` and runs
`python3 scripts/run_pipeline.py` directly. No install step, no editable-install path resolution, no
possibility of running against a stale installed copy. For a repo whose entry points are all scripts
invoked by prompt strings, that simplicity is worth real money.

## Consequences

### Positive

- `git clone && python3 scripts/x.py` works with zero setup. The Dockerfile needs no install step
  for this repo's own code.
- No stale-install class of bug, which matters when the same tree is cloned fresh per CI run.

### Negative

- The `sys.path.insert` preamble is duplicated ~38 times and is pure ceremony.
- No import-time namespacing, so module names are global. `state.py`, `frontmatter.py` are generic
  enough to collide with a real package.
- Tooling suffers: no `mypy` entry point, no editor go-to-definition without configuration, and
  `pytest` needs the bootstrap in every file rather than one `conftest.py`. There is no
  `conftest.py` at all.
- `scripts/__init__.py` is a vestigial 0-byte file implying a package that does not exist.

### Revisit when

Adding type checking, or the next time a name collision or an import cycle costs an hour. The
migration is mechanical but wide; it should be its own task, not a drive-by. Tracked in
`docs/tasks/pending/`.
