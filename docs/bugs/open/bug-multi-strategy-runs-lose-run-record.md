---
id: bug-multi-strategy-runs-lose-run-record
title: Multi-strategy runs lose the run record for all but the last strategy
type: bug
status: open
repos: [epic-code-gen-pipeline]
decisions: [ADR-0006, ADR-0010]
---

# Bug: Multi-strategy runs lose the run record for all but the last strategy

## Summary

`pipeline-post.sh` builds one `--strategy-key <k>` flag per key. Python's argparse abbreviation-matches that to the `nargs="+"` `--strategy-keys` option, and repeated occurrences **overwrite** rather than append — so `push_results` only ever loops over the last key.

## Reproduction

1. Trigger `codegen-run` with `STRATEGY_KEYS="RHAISTRAT-A RHAISTRAT-B"`.
2. Let the job complete so `after_script` runs `pipeline-post.sh`.
3. Inspect the data repo: only `RHAISTRAT-B` has a refreshed `strategy-summary.json`, a new `run-log.jsonl` entry, and an OTEL file.

## Expected

Every strategy processed in the run gets its state merged, its summary regenerated, its run log appended, and its telemetry persisted.

## Actual

Only the last key does. Verified empirically:

```python
p.add_argument("--strategy-keys", nargs="+", required=True)
p.parse_args(["--strategy-key","A","--strategy-key","B"]).strategy_keys
# → ['B']
```

## Impact

High

## Evidence

`ci-scripts/pipeline-post.sh:38-41` builds the flags:

```bash
IFS=' ' read -ra keys <<< "$strategy_keys"
key_args=""
for key in "${keys[@]}"; do
    key_args="$key_args --strategy-key $key"
```

`ci-scripts/push-results.py:444` declares `--strategy-keys` with `nargs="+"`.

**Blast radius is narrower than it first appears, and worth stating precisely.** Codegen artifacts still land, because `run_pipeline.py` writes state live during the run and `commit_and_push` does `git add -A`, which sweeps up everything on disk. What is lost for every strategy except the last is the work inside the per-key loop: the `merge_state_file()` call (so the skill's own fields never reach the data repo), the `strategy-summary.json` regeneration, the `run-log.jsonl` append, and the OTEL file copy.

Net effect: the durable run record and the dashboard feed silently lose all but one strategy per pass. The State Log and Cost views are missing entries nobody has noticed, because the job exits 0.

## Related Tasks

- [[task-gitlab-ci-and-ci-scripts]]
- Fix is one character — pass `--strategy-keys` once with all keys — plus a test
- Illustrates the [ADR-0010] trade-off: a shell script assembling flags for an argparse it cannot see, in the repo with almost no test coverage
