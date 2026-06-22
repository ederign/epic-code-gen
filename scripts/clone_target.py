#!/usr/bin/env python3
"""Clone a target repo and set up an epic branch for code generation.

Handles: fresh clone, fork remote (optional), epic branch creation.

Usage:
    python3 scripts/clone_target.py <repo-url> <epic-id> [--dest .target-repo]
    python3 scripts/clone_target.py <repo-url> <epic-id> --fork-owner ederign
    python3 scripts/clone_target.py <repo-url> <epic-id> --clean
"""

import argparse
import json
import os
import shutil
import subprocess
import sys


DEFAULT_DEST = ".target-repo"


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


def clone(repo_url, epic_id, dest=None, fork_owner=None, clean=False):
    """Clone a target repo and create an epic branch.

    Args:
        repo_url: upstream repo URL (https or git@)
        epic_id: epic identifier (e.g., RHAISTRAT-1749-E001)
        dest: clone destination (default: .target-repo)
        fork_owner: GitHub username for fork remote (optional)
        clean: if True, delete existing clone first

    Returns:
        dict with: dest, branch, upstream_url, fork_url, status
    """
    dest = dest or DEFAULT_DEST
    branch = f"epic/{epic_id}"

    result = {
        "dest": dest,
        "branch": branch,
        "upstream_url": repo_url,
        "fork_url": None,
        "status": "created",
    }

    if clean and os.path.exists(dest):
        shutil.rmtree(dest)

    if os.path.isdir(dest):
        existing_remotes, _, _ = _run_git(
            ["git", "remote", "-v"], cwd=dest, check=False)
        if repo_url in existing_remotes or _url_matches(repo_url, existing_remotes):
            result["status"] = "existing"
            _ensure_branch(dest, branch)
            if fork_owner:
                result["fork_url"] = _setup_fork_remote(dest, repo_url, fork_owner)
            return result
        raise ValueError(
            f"Directory {dest} exists but points to a different repo. "
            f"Use --clean to force a fresh clone."
        )

    _run_git(["git", "clone", repo_url, dest])

    _run_git(["git", "checkout", "-b", branch], cwd=dest)

    if fork_owner:
        result["fork_url"] = _setup_fork_remote(dest, repo_url, fork_owner)

    return result


def _url_matches(url, remote_output):
    """Check if url matches any remote URL (handles https vs git@ variants)."""
    slug = _extract_slug(url)
    if slug:
        return slug in remote_output
    return False


def _extract_slug(url):
    """Extract org/repo from a GitHub URL."""
    url = url.rstrip("/").rstrip(".git")
    if "github.com" in url:
        parts = url.split("github.com")[-1].strip("/:").split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return None


def _ensure_branch(dest, branch):
    """Create or switch to the epic branch."""
    stdout, _, rc = _run_git(
        ["git", "branch", "--list", branch], cwd=dest, check=False)
    if branch in stdout:
        _run_git(["git", "checkout", branch], cwd=dest)
    else:
        _run_git(["git", "checkout", "-b", branch], cwd=dest)


def _setup_fork_remote(dest, upstream_url, fork_owner):
    """Add fork remote pointing to the fork owner's copy.

    Returns the fork URL.
    """
    slug = _extract_slug(upstream_url)
    if not slug:
        return None

    repo_name = slug.split("/")[-1]
    fork_url = f"https://github.com/{fork_owner}/{repo_name}.git"

    existing, _, _ = _run_git(["git", "remote"], cwd=dest, check=False)
    if "fork" in existing.split("\n"):
        _run_git(["git", "remote", "set-url", "fork", fork_url], cwd=dest)
    else:
        _run_git(["git", "remote", "add", "fork", fork_url], cwd=dest)

    return fork_url


def main():
    parser = argparse.ArgumentParser(
        description="Clone target repo and create epic branch")
    parser.add_argument("repo_url", help="Upstream repo URL")
    parser.add_argument("epic_id", help="Epic ID (e.g., RHAISTRAT-1749-E001)")
    parser.add_argument("--dest", default=DEFAULT_DEST,
                        help=f"Clone destination (default: {DEFAULT_DEST})")
    parser.add_argument("--fork-owner", default=None,
                        help="GitHub username for fork remote")
    parser.add_argument("--clean", action="store_true",
                        help="Delete existing clone first")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    try:
        result = clone(
            args.repo_url,
            args.epic_id,
            dest=args.dest,
            fork_owner=args.fork_owner,
            clean=args.clean,
        )

        if args.json:
            json.dump(result, sys.stdout, indent=2)
            print()
        else:
            print(f"Cloned to: {result['dest']}")
            print(f"Branch: {result['branch']}")
            print(f"Status: {result['status']}")
            if result["fork_url"]:
                print(f"Fork remote: {result['fork_url']}")

        sys.exit(0)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
