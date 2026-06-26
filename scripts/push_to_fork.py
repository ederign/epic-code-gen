#!/usr/bin/env python3
"""Push an epic branch to the fork remote.

Expects the fork remote to already be configured by clone_target.py
(with token embedded in URL if auth is needed).

Usage:
    python3 scripts/push_to_fork.py <repo-path> <branch>
    python3 scripts/push_to_fork.py .target-repo epic/RHAISTRAT-1749-E001 --force
"""

import argparse
import json
import subprocess
import sys


def _run_git(args, cwd=None, check=True):
    """Run a git command and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, args,
            output=result.stdout, stderr=result.stderr,
        )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def push(repo_path, branch, force=False):
    """Push branch to fork remote.

    Args:
        repo_path: path to the cloned repo
        branch: branch name to push
        force: if True, force push

    Returns:
        dict with: pushed, branch, remote
    """
    remotes, _, _ = _run_git(["git", "remote"], cwd=repo_path)
    if "fork" not in remotes.split("\n"):
        raise ValueError(
            f"No 'fork' remote in {repo_path}. "
            f"Run clone_target.py with --fork-owner first."
        )

    current, _, _ = _run_git(
        ["git", "branch", "--show-current"], cwd=repo_path)
    if current != branch:
        _run_git(["git", "checkout", branch], cwd=repo_path)

    cmd = ["git", "push", "fork", branch]
    if force:
        cmd.insert(2, "--force")

    _run_git(cmd, cwd=repo_path)

    return {
        "pushed": True,
        "branch": branch,
        "remote": "fork",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Push epic branch to fork remote")
    parser.add_argument("repo_path", help="Path to cloned repo")
    parser.add_argument("branch", help="Branch name to push")
    parser.add_argument("--force", action="store_true",
                        help="Force push")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    try:
        result = push(args.repo_path, args.branch, force=args.force)

        if args.json:
            json.dump(result, sys.stdout, indent=2)
            print()
        else:
            print(f"Pushed {result['branch']} to {result['remote']}")

        sys.exit(0)
    except (subprocess.CalledProcessError, ValueError) as e:
        if args.json:
            json.dump({"pushed": False, "error": str(e)}, sys.stdout, indent=2)
            print()
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
