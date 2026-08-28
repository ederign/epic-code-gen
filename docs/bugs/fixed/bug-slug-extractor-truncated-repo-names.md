---
id: bug-slug-extractor-truncated-repo-names
title: Duplicate slug extractor truncated repo names ending in . g i t
type: bug
status: fixed
commits: ["34b863a"]
repos: [epic-code-gen]
decisions: [ADR-0030, ADR-0035]
---

# Bug: Duplicate slug extractor truncated repo names ending in `.` `g` `i` `t`

## Summary

`clone_target.py` carried its own `_extract_slug()`, a near-copy of
`github_utils.extract_slug()`. The copy stripped the `.git` suffix with
`url.rstrip(".git")`.

`str.rstrip` takes a **character set**, not a suffix. It removes every trailing
character that appears in `{'.', 'g', 'i', 't'}`, so it does not stop once
`.git` is gone:

```
https://github.com/rh-forge/rh-forge-ui.git
  → strip 't' 'i' 'g' '.'   → rh-forge-ui     (correct so far)
  → strip 'i'               → rh-forge-u      (wrong; 'i' is in the set)
```

Every fork API call then addressed a repository that does not exist.

## Reproduction

```bash
python3 scripts/clone_target.py rh-forge/rh-forge-ui RHAI-760 --clean \
  --dest /tmp/tr --fork-owner ederign --gh-token-var RH_FORGE_GITHUB_TOKEN
```

## Expected

Clone, add a `fork` remote for `ederign/rh-forge-ui`, create `epic/RHAI-760`.

## Actual

```
HTTP 404: {"message":"Not Found", ... #get-a-repository}   ← GET /repos/ederign/rh-forge-u
HTTP 404: {"message":"Not Found", ... #create-a-fork}      ← POST /repos/rh-forge/rh-forge-u/forks
Error: HTTP Error 404: Not Found
```

`git clone` itself succeeded — the failure is entirely inside
`_setup_fork_remote()` → `github_utils.ensure_fork()`, which is why nothing in
the trace mentions git. GitHub answers 404 rather than 403 for a repository a
token cannot see, so the symptom reads exactly like a permissions problem: the
first hour of diagnosis went to the PAT (classic vs fine-grained, SSO
authorisation, org opt-in) and found nothing wrong with it.

## Impact

High, and latent since the extractor was duplicated. It fires only for repo
names whose last character is in `{'.', 'g', 'i', 't'}`, which no previous
target had — `odh-dashboard`, `kale`, `mlflow`, `codeflare-sdk` all end outside
the set. `rh-forge-ui` is the first target to end in `i`. Any future
`…-config`, `…-training` or `…-widget` target would have hit it too.

Compounding it: `setup_target_repo()` records a clone failure as terminal
`Failed`, so both epics of RHAISTRAT-2671 had to be reset by hand in the data
repo before they could retry — see [[bug-clone-fault-marks-epic-failed]].

## Fix

Deleted `clone_target._extract_slug` outright and pointed both call sites
(`_url_matches`, `_setup_fork_remote`) at `github_utils.extract_slug`, which
already used the correct `.removesuffix(".git")`. Deleting rather than patching
is the point: two copies of one function are what allowed the fix in
`github_utils` to never reach the copy that ran.

Regression coverage:

- `TestExtractSlug::test_repo_name_ending_in_git_suffix_chars` in
  `tests/test_github_utils.py` — the character-set case directly.
- `TestSetupForkRemote::test_repo_name_ending_in_i_is_not_truncated` in
  `tests/test_clone_target.py` — asserts the exact arguments reaching
  `ensure_fork` for `rh-forge-ui`, pinning the call site that actually broke.

The duplicated suite in `tests/test_clone_target.py` was removed along with the
function it covered.

## Related

- [[task-per-repo-github-identity]] — the change that first pointed a target at
  `rh-forge/rh-forge-ui` and exposed this.
- [[bug-clone-fault-marks-epic-failed]]
