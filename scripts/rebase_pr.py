#!/usr/bin/env python3
"""Rebase an epic branch onto its upstream base, resolving conflicts.

The pipeline runs this before addressing review comments on every cycle, so
fixes are always authored against current upstream code and the PR never
sits in a CONFLICTING state waiting on a human.

A rebase rewrites history, so pushing the result requires --force-with-lease.
Use push_rebased_branch() rather than a plain push.

Usage:
    python3 scripts/rebase_pr.py <repo-path> <branch> \
        [--base main] [--remote origin] [--push-remote fork] \
        [--no-resolve] [--json]
"""

import argparse
import json
import os
import subprocess
import sys

# A rebase stops once per conflicting commit. Bound the resolve loop so a
# pathological history can't spin forever.
MAX_CONFLICT_ROUNDS = 10

CONFLICT_AGENT_TIMEOUT = 900


def _git(args, cwd, check=False, env=None):
    """Run a git command. Returns (stdout, stderr, returncode)."""
    full_env = None
    if env:
        full_env = {**os.environ, **env}
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True,
        env=full_env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip(), result.stderr.strip(), result.returncode


# Rebase needs a non-interactive editor or it blocks forever waiting on a
# commit message / todo list.
_NONINTERACTIVE = {
    "GIT_EDITOR": "true",
    "GIT_SEQUENCE_EDITOR": "true",
}


def detect_base_branch(target_repo, remote="origin"):
    """Detect the upstream default branch (main, master, ...)."""
    stdout, _, rc = _git(
        ["symbolic-ref", f"refs/remotes/{remote}/HEAD"], cwd=target_repo)
    if rc == 0 and stdout:
        return stdout.split("/")[-1]
    for candidate in ("main", "master"):
        _, _, rc = _git(
            ["rev-parse", "--verify", f"{remote}/{candidate}"],
            cwd=target_repo)
        if rc == 0:
            return candidate
    return "main"


def rebase_in_progress(target_repo):
    """Check whether a rebase is currently stopped mid-flight."""
    for path in ("rebase-merge", "rebase-apply"):
        stdout, _, rc = _git(["rev-parse", "--git-path", path],
                             cwd=target_repo)
        if rc == 0 and stdout:
            candidate = stdout
            if not os.path.isabs(candidate):
                candidate = os.path.join(target_repo, candidate)
            if os.path.exists(candidate):
                return True
    return False


def conflicted_files(target_repo):
    """List paths with unresolved merge conflicts."""
    stdout, _, rc = _git(
        ["diff", "--name-only", "--diff-filter=U"], cwd=target_repo)
    if rc != 0 or not stdout:
        return []
    return [line for line in stdout.split("\n") if line]


def rebase_onto_base(target_repo, branch, base_branch=None, remote="origin",
                     resolver=None, fetch=True):
    """Rebase `branch` onto `remote/base_branch`, resolving conflicts.

    Args:
        target_repo: path to the checked-out target repo.
        branch: epic branch name (e.g. "epic/RHAI-74").
        base_branch: base to rebase onto; auto-detected when None.
        remote: remote holding the base branch (upstream, normally "origin").
        resolver: callable(conflicts, target_repo) -> bool, invoked per
            conflict round. None means don't attempt resolution — a
            conflicting rebase is aborted and reported instead.
        fetch: fetch `remote` before rebasing.

    Returns:
        dict describing the outcome. `rebased` is True only when the branch
        head actually moved, which is the signal that a force-push is needed.
    """
    result = {
        "branch": branch,
        "base": None,
        "base_sha": None,
        "old_head": None,
        "new_head": None,
        "already_current": False,
        "rebased": False,
        "conflict_rounds": 0,
        "conflicted_files": [],
        "aborted": False,
        "error": None,
    }

    _, _, rc = _git(["rev-parse", "--git-dir"], cwd=target_repo)
    if rc != 0:
        result["error"] = f"{target_repo} is not a git repository"
        return result

    # Never rebase on top of a half-finished one from a previous crashed run.
    if rebase_in_progress(target_repo):
        _git(["rebase", "--abort"], cwd=target_repo, env=_NONINTERACTIVE)

    if fetch:
        _, err, rc = _git(["fetch", remote, "--prune"], cwd=target_repo)
        if rc != 0:
            result["error"] = f"fetch {remote} failed: {err}"
            return result

    base = base_branch or detect_base_branch(target_repo, remote)
    result["base"] = base
    base_ref = f"{remote}/{base}"

    base_sha, _, rc = _git(["rev-parse", base_ref], cwd=target_repo)
    if rc != 0:
        result["error"] = f"base ref {base_ref} not found"
        return result
    result["base_sha"] = base_sha

    old_head, _, rc = _git(["rev-parse", "HEAD"], cwd=target_repo)
    if rc != 0:
        result["error"] = "cannot resolve HEAD"
        return result
    result["old_head"] = old_head
    result["new_head"] = old_head

    # Already contains the base tip: nothing to replay.
    _, _, rc = _git(["merge-base", "--is-ancestor", base_sha, "HEAD"],
                    cwd=target_repo)
    if rc == 0:
        result["already_current"] = True
        return result

    _, err, rc = _git(["rebase", base_ref], cwd=target_repo,
                      env=_NONINTERACTIVE)

    while rc != 0 and rebase_in_progress(target_repo):
        if result["conflict_rounds"] >= MAX_CONFLICT_ROUNDS:
            result["error"] = (
                f"exceeded {MAX_CONFLICT_ROUNDS} conflict rounds")
            break

        conflicts = conflicted_files(target_repo)
        result["conflict_rounds"] += 1
        for path in conflicts:
            if path not in result["conflicted_files"]:
                result["conflicted_files"].append(path)

        if not conflicts:
            # Stopped without conflicts — usually a commit that became empty
            # because upstream already carries the same change.
            _, err, rc = _git(["rebase", "--skip"], cwd=target_repo,
                              env=_NONINTERACTIVE)
            continue

        if resolver is None:
            result["error"] = (
                f"conflicts in {', '.join(conflicts)} and no resolver")
            break

        if not resolver(conflicts, target_repo):
            result["error"] = f"resolver failed on {', '.join(conflicts)}"
            break

        _git(["add", "-A"], cwd=target_repo)

        # If resolution left nothing staged the commit is empty; skip it.
        _, _, diff_rc = _git(["diff", "--cached", "--quiet"], cwd=target_repo)
        if diff_rc == 0:
            _, err, rc = _git(["rebase", "--skip"], cwd=target_repo,
                              env=_NONINTERACTIVE)
        else:
            _, err, rc = _git(["rebase", "--continue"], cwd=target_repo,
                              env=_NONINTERACTIVE)

    if rebase_in_progress(target_repo) or (rc != 0 and not result["error"]):
        if not result["error"]:
            result["error"] = f"rebase failed: {err}"

    if rebase_in_progress(target_repo):
        _git(["rebase", "--abort"], cwd=target_repo, env=_NONINTERACTIVE)
        result["aborted"] = True
        result["new_head"] = old_head
        return result

    if result["error"]:
        return result

    new_head, _, _ = _git(["rev-parse", "HEAD"], cwd=target_repo)
    result["new_head"] = new_head
    result["rebased"] = new_head != old_head
    return result


def push_rebased_branch(target_repo, branch, remote="fork"):
    """Force-push a rebased branch, refusing to clobber unseen commits.

    Returns:
        dict: {pushed, error}
    """
    # --force-with-lease needs a remote-tracking ref to compare against.
    _git(["fetch", remote, branch], cwd=target_repo)

    _, err, rc = _git(
        ["push", "--force-with-lease", remote, f"HEAD:refs/heads/{branch}"],
        cwd=target_repo)
    if rc != 0:
        return {"pushed": False, "error": err}
    return {"pushed": True, "error": None}


def claude_conflict_resolver(conflicts, target_repo):
    """Default resolver: hand the conflicted files to Claude.

    Resolves working-tree conflicts only — it must not run git rebase
    commands itself, since rebase_onto_base() drives the sequence.
    """
    file_list = "\n".join(f"  - {p}" for p in conflicts)
    prompt = (
        "You are resolving git rebase conflicts in "
        f"{os.path.abspath(target_repo)}.\n\n"
        f"Conflicted files:\n{file_list}\n\n"
        "For each file, remove the conflict markers (<<<<<<<, =======, "
        ">>>>>>>) and produce the correct merged content. Keep BOTH sides' "
        "intent: upstream changes must survive, and so must this branch's "
        "feature work. Do not discard either side wholesale, and do not "
        "revert unrelated upstream changes.\n\n"
        "Do NOT run any git command — no add, commit, rebase, continue, or "
        "abort. Edit the files only; the caller stages and continues the "
        "rebase for you."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions",
             "--output-format", "text"],
            capture_output=True, text=True, cwd=target_repo,
            timeout=CONFLICT_AGENT_TIMEOUT,
        )
        if result.returncode != 0:
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Conflict resolver error: {e}", file=sys.stderr)
        return False

    # Markers left behind mean the resolution is not usable.
    for path in conflicts:
        full = os.path.join(target_repo, path)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, errors="replace") as f:
                content = f.read()
        except OSError:
            return False
        if "<<<<<<<" in content or ">>>>>>>" in content:
            print(f"  Conflict markers remain in {path}", file=sys.stderr)
            return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Rebase an epic branch onto its upstream base")
    parser.add_argument("repo_path", help="Path to the target repo")
    parser.add_argument("branch", help="Epic branch name")
    parser.add_argument("--base", default=None,
                        help="Base branch (default: auto-detect)")
    parser.add_argument("--remote", default="origin",
                        help="Remote holding the base (default: origin)")
    parser.add_argument("--push-remote", default=None,
                        help="Force-push the result to this remote")
    parser.add_argument("--no-resolve", action="store_true",
                        help="Abort on conflicts instead of resolving them")
    parser.add_argument("--no-fetch", action="store_true",
                        help="Skip fetching the remote first")
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON")
    args = parser.parse_args()

    resolver = None if args.no_resolve else claude_conflict_resolver
    result = rebase_onto_base(
        args.repo_path, args.branch, base_branch=args.base,
        remote=args.remote, resolver=resolver, fetch=not args.no_fetch,
    )

    if args.push_remote and result["rebased"] and not result["error"]:
        push = push_rebased_branch(
            args.repo_path, args.branch, remote=args.push_remote)
        result["pushed"] = push["pushed"]
        if push["error"]:
            result["error"] = f"push failed: {push['error']}"

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["error"]:
            print(f"Rebase FAILED: {result['error']}")
        elif result["already_current"]:
            print(f"Already current with {args.remote}/{result['base']}")
        elif result["rebased"]:
            rounds = result["conflict_rounds"]
            suffix = f" ({rounds} conflict round(s))" if rounds else ""
            print(f"Rebased onto {args.remote}/{result['base']}{suffix}")
        else:
            print("Nothing to rebase")

    sys.exit(1 if result["error"] else 0)


if __name__ == "__main__":
    main()
