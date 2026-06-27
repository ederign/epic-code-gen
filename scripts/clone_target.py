#!/usr/bin/env python3
"""Clone a target repo and set up an epic branch for code generation.

Handles: fresh clone, fork remote (optional), epic branch creation.
Supports token-based auth for CI environments (no gh CLI needed).

Usage:
    python3 scripts/clone_target.py <repo-url> <epic-id> [--dest .target-repo]
    python3 scripts/clone_target.py <repo-url> <epic-id> --fork-owner ederign
    python3 scripts/clone_target.py <repo-url> <epic-id> --fork-owner ederign --gh-token-var EPIC_CODEGEN_GITHUB_TOKEN
    python3 scripts/clone_target.py <repo-url> <epic-id> --clean
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

import github_utils

DEFAULT_DEST = ".target-repo"
DEFAULT_FORK_OWNER = "dora-the-ai-coder"


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


def clone(repo_url, epic_id, dest=None, fork_owner=None, clean=False,
          gh_token_var=None):
    """Clone a target repo and create an epic branch.

    Args:
        repo_url: upstream repo URL (https or git@)
        epic_id: epic identifier (e.g., RHAISTRAT-1749-E001)
        dest: clone destination (default: .target-repo)
        fork_owner: GitHub username for fork remote (optional)
        clean: if True, delete existing clone first
        gh_token_var: env var name for GitHub token (enables auth clone + fork creation)

    Returns:
        dict with: dest, branch, upstream_url, fork_url, fork_created, status
    """
    dest = dest or DEFAULT_DEST
    branch = f"epic/{epic_id}"

    token = None
    if fork_owner and not gh_token_var:
        gh_token_var = github_utils.DEFAULT_TOKEN_VAR
    if gh_token_var:
        token = github_utils.require_env(gh_token_var)

    result = {
        "dest": dest,
        "branch": branch,
        "upstream_url": repo_url,
        "fork_url": None,
        "fork_created": False,
        "status": "created",
    }

    if clean and os.path.exists(dest):
        shutil.rmtree(dest)

    if os.path.isdir(dest):
        existing_remotes, _, _ = _run_git(
            ["git", "remote", "-v"], cwd=dest, check=False)
        if repo_url in existing_remotes or _url_matches(repo_url, existing_remotes):
            result["status"] = "existing"
            if fork_owner:
                fork_result = _setup_fork_remote(
                    dest, repo_url, fork_owner, token)
                result["fork_url"] = fork_result["fork_url"]
                result["fork_created"] = fork_result["fork_created"]
            slug = github_utils.extract_slug(repo_url)
            repo_name = slug.split("/")[1] if slug else None
            _sync_with_upstream(dest, fork_owner, repo_name, token)
            _ensure_branch(dest, branch)
            return result
        raise ValueError(
            f"Directory {dest} exists but points to a different repo. "
            f"Use --clean to force a fresh clone."
        )

    if ("://" not in repo_url and "@" not in repo_url
            and not repo_url.startswith("/") and repo_url.count("/") == 1):
        repo_url = f"https://github.com/{repo_url}.git"

    clone_url = repo_url
    slug = github_utils.extract_slug(repo_url)
    if token and slug:
        clone_url = github_utils.authenticated_url(slug, token)

    _run_git(["git", "clone", clone_url, dest])

    if token:
        _configure_git_identity(dest, token)

    if fork_owner:
        fork_result = _setup_fork_remote(dest, repo_url, fork_owner, token)
        result["fork_url"] = fork_result["fork_url"]
        result["fork_created"] = fork_result["fork_created"]

    repo_name = slug.split("/")[1] if slug else None
    _sync_with_upstream(dest, fork_owner, repo_name, token)

    _run_git(["git", "checkout", "-b", branch], cwd=dest)

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


def _configure_git_identity(dest, token):
    """Set git user.name and user.email from the GitHub token owner."""
    user = github_utils.get_authenticated_user(token)
    login = user["login"]
    email = user.get("email") or f"{login}@users.noreply.github.com"
    _run_git(["git", "config", "user.name", login], cwd=dest)
    _run_git(["git", "config", "user.email", email], cwd=dest)


def _default_branch(dest):
    """Detect the default branch name (main or master)."""
    stdout, _, _ = _run_git(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=dest, check=False)
    if stdout:
        return stdout.split("/")[-1]
    for candidate in ("main", "master"):
        _, _, rc = _run_git(
            ["git", "rev-parse", "--verify", f"origin/{candidate}"],
            cwd=dest, check=False)
        if rc == 0:
            return candidate
    return "main"


def _sync_with_upstream(dest, fork_owner=None, repo_name=None, token=None):
    """Fetch upstream and sync fork if applicable.

    For fork repos, also syncs via GitHub API so the fork's default
    branch matches upstream before we fetch.
    """
    if fork_owner and repo_name and token:
        default = _default_branch(dest)
        try:
            github_utils.sync_fork(fork_owner, repo_name, token, default)
        except Exception:
            pass

    _run_git(["git", "fetch", "--all", "--prune"], cwd=dest)


def _has_remote(dest, name="origin"):
    """Check if a remote exists."""
    stdout, _, _ = _run_git(["git", "remote"], cwd=dest, check=False)
    return name in stdout.split("\n")


def _ensure_branch(dest, branch):
    """Create or switch to the epic branch, based on latest upstream."""
    stdout, _, rc = _run_git(
        ["git", "branch", "--list", branch], cwd=dest, check=False)
    if branch in stdout:
        _run_git(["git", "checkout", branch], cwd=dest)
        if _has_remote(dest):
            default = _default_branch(dest)
            _run_git(
                ["git", "reset", "--hard", f"origin/{default}"], cwd=dest)
    else:
        if _has_remote(dest):
            default = _default_branch(dest)
            _run_git(["git", "checkout", f"origin/{default}"], cwd=dest)
        _run_git(["git", "checkout", "-b", branch], cwd=dest)


def _setup_fork_remote(dest, upstream_url, fork_owner, token=None):
    """Add fork remote pointing to the fork owner's copy.

    If token is provided:
    - Creates the fork via GitHub API if it doesn't exist
    - Uses authenticated URL for push access

    Returns dict with: fork_url (display URL), fork_created.
    """
    slug = _extract_slug(upstream_url)
    if not slug:
        return {"fork_url": None, "fork_created": False}

    upstream_owner, repo_name = slug.split("/")
    fork_created = False

    if token:
        _, fork_created = github_utils.ensure_fork(
            upstream_owner, repo_name, fork_owner, token)
        fork_slug = f"{fork_owner}/{repo_name}"
        git_url = github_utils.authenticated_url(fork_slug, token)
    else:
        git_url = f"https://github.com/{fork_owner}/{repo_name}.git"

    display_url = github_utils.sanitized_url(f"{fork_owner}/{repo_name}")

    existing, _, _ = _run_git(["git", "remote"], cwd=dest, check=False)
    if "fork" in existing.split("\n"):
        _run_git(["git", "remote", "set-url", "fork", git_url], cwd=dest)
    else:
        _run_git(["git", "remote", "add", "fork", git_url], cwd=dest)

    return {"fork_url": display_url, "fork_created": fork_created}


def main():
    parser = argparse.ArgumentParser(
        description="Clone target repo and create epic branch")
    parser.add_argument("repo_url", help="Upstream repo URL")
    parser.add_argument("epic_id", help="Epic ID (e.g., RHAISTRAT-1749-E001)")
    parser.add_argument("--dest", default=DEFAULT_DEST,
                        help=f"Clone destination (default: {DEFAULT_DEST})")
    parser.add_argument("--fork-owner", default=None,
                        help=f"GitHub username for fork remote (default: {DEFAULT_FORK_OWNER})")
    parser.add_argument("--gh-token-var", default=None,
                        help="Env var name for GitHub token (default: EPIC_CODEGEN_GITHUB_TOKEN)")
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
            gh_token_var=args.gh_token_var,
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
            if result["fork_created"]:
                print("Fork: newly created")

        sys.exit(0)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError,
            EnvironmentError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
