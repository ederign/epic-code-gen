"""GitHub REST API utilities for fork management and push authentication.

No gh CLI dependency — pure Python + git CLI. Designed for GitLab CI
environments where gh is unavailable.

Environment variables:
    EPIC_CODEGEN_GITHUB_TOKEN  GitHub personal access token (or fine-grained token)
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

ssl_ctx = ssl.create_default_context()
try:
    import certifi
    ssl_ctx.load_verify_locations(certifi.where())
except (ImportError, OSError):
    pass


API_BASE = "https://api.github.com"
DEFAULT_TOKEN_VAR = "EPIC_CODEGEN_GITHUB_TOKEN"
FORK_POLL_INTERVAL = 2
FORK_POLL_MAX_WAIT = 120


# ─── HTTP Layer ───────────────────────────────────────────────────────────────

def make_request(url, token, body=None, method=None):
    """HTTP request with Bearer token auth. Returns parsed JSON or None."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as resp:
        if resp.status == 204:
            return None
        resp_body = resp.read()
        if not resp_body:
            return None
        return json.loads(resp_body)


def api_call(path, token, body=None, method=None):
    """Build full GitHub API URL and call make_request."""
    url = f"{API_BASE}{path}"
    return make_request(url, token, body, method)


def api_call_with_retry(path, token, body=None, method=None, max_retries=3):
    """Wrap api_call with retry on transient errors."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return api_call(path, token, body, method)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 1))
                wait = max(retry_after, 1)
                print(f"  Rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                last_error = e
                continue
            if e.code in (502, 503, 504):
                wait = 4 ** attempt
                print(f"  HTTP {e.code}, retrying in {wait}s...",
                      file=sys.stderr)
                time.sleep(wait)
                last_error = e
                continue
            error_body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {error_body}", file=sys.stderr)
            e.error_body = error_body
            raise
        except urllib.error.URLError as e:
            wait = 4 ** attempt
            print(f"  Network error: {e.reason}, retrying in {wait}s...",
                  file=sys.stderr)
            time.sleep(wait)
            last_error = e
    raise last_error


def api_call_paginated(path, token, per_page=100):
    """Fetch all pages of a paginated GitHub API endpoint.

    Returns combined list of all items across all pages.
    """
    all_items = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        paged_path = f"{path}{separator}per_page={per_page}&page={page}"
        items = api_call_with_retry(paged_path, token) or []
        if not items:
            break
        all_items.extend(items)
        if len(items) < per_page:
            break
        page += 1
    return all_items


# ─── Env ──────────────────────────────────────────────────────────────────────

def require_env(token_var=None):
    """Read GitHub token from the named env var. Returns token string."""
    var = token_var or DEFAULT_TOKEN_VAR
    token = os.environ.get(var)
    if not token:
        raise EnvironmentError(
            f"Environment variable {var} is not set. "
            f"Set it to a GitHub personal access token with repo scope."
        )
    return token


# ─── URL Helpers ──────────────────────────────────────────────────────────────

def extract_slug(url):
    """Extract owner/repo from a GitHub URL. Returns None for non-GitHub URLs."""
    url = url.rstrip("/").removesuffix(".git")
    if "github.com" not in url:
        return None
    parts = url.split("github.com")[-1].strip("/:").split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def authenticated_url(slug, token):
    """Build HTTPS URL with embedded token for git clone/push."""
    return f"https://x-access-token:{token}@github.com/{slug}.git"


def sanitized_url(slug):
    """Build HTTPS URL without token (for display/logging)."""
    return f"https://github.com/{slug}.git"


# ─── Repository Operations ───────────────────────────────────────────────────

def get_repo(owner, repo, token):
    """Check if a repo exists. Returns repo dict or None (404)."""
    try:
        return api_call_with_retry(f"/repos/{owner}/{repo}", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def get_authenticated_user(token):
    """Get the username of the authenticated token owner."""
    return api_call_with_retry("/user", token)


def fork_repo(upstream_owner, upstream_repo, token, org=None):
    """Fork a repo. Creates fork under the authenticated user (or org).

    GitHub forks are async — polls until the fork is ready.

    Returns the fork's full_name (owner/repo).
    """
    body = {}
    if org:
        body["organization"] = org

    result = api_call_with_retry(
        f"/repos/{upstream_owner}/{upstream_repo}/forks",
        token, body=body, method="POST",
    )

    fork_owner = result["owner"]["login"]
    fork_repo_name = result["name"]

    elapsed = 0
    while elapsed < FORK_POLL_MAX_WAIT:
        repo = get_repo(fork_owner, fork_repo_name, token)
        if repo and not repo.get("fork") is False:
            return f"{fork_owner}/{fork_repo_name}"
        time.sleep(FORK_POLL_INTERVAL)
        elapsed += FORK_POLL_INTERVAL

    return f"{fork_owner}/{fork_repo_name}"


def ensure_fork(upstream_owner, upstream_repo, fork_owner, token):
    """Ensure a fork exists for fork_owner. Creates one if needed.

    Returns (fork_slug, created) where created is True if newly forked.
    """
    existing = get_repo(fork_owner, upstream_repo, token)
    if existing and existing.get("fork"):
        return f"{fork_owner}/{upstream_repo}", False

    slug = fork_repo(upstream_owner, upstream_repo, token)
    return slug, True


def sync_fork(fork_owner, repo, token, branch="main"):
    """Sync a fork's branch with its upstream parent via GitHub API.

    Uses POST /repos/{owner}/{repo}/merge-upstream.
    Returns True if updated, False if already up-to-date.
    """
    result = api_call(
        f"/repos/{fork_owner}/{repo}/merge-upstream",
        token, body={"branch": branch}, method="POST",
    )
    return result.get("merge_type") != "none"


def get_pr_template(owner, repo, token):
    """Fetch PR template from target repo. Returns content string or None."""
    import base64
    candidates = [
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/pull_request_template.md",
        "PULL_REQUEST_TEMPLATE.md",
        "docs/pull_request_template.md",
    ]
    for path in candidates:
        try:
            result = api_call(
                f"/repos/{owner}/{repo}/contents/{path}", token)
            if result and result.get("content"):
                return base64.b64decode(result["content"]).decode("utf-8")
        except urllib.error.HTTPError:
            continue
    return None


def create_pull_request(upstream_owner, upstream_repo, head_owner, branch,
                        base, title, body, token):
    """Create a pull request from fork branch to upstream base.

    Args:
        upstream_owner: upstream repo owner
        upstream_repo: upstream repo name
        head_owner: fork owner (for cross-repo PR: "head_owner:branch")
        branch: branch name in the fork
        base: target branch in upstream (e.g., "main")
        title: PR title
        body: PR body (markdown)
        token: GitHub token

    Returns PR dict from GitHub API.
    """
    pr_body = {
        "title": title,
        "body": body,
        "head": f"{head_owner}:{branch}",
        "base": base,
    }
    return api_call_with_retry(
        f"/repos/{upstream_owner}/{upstream_repo}/pulls",
        token, body=pr_body, method="POST",
    )


# ─── PR Review Operations ────────────────────────────────────────────────────

def get_pr_files(owner, repo, pull_number, token):
    """Fetch the list of files changed in a PR.

    Returns list of {filename, status, additions, deletions, patch} dicts.
    """
    return api_call_paginated(
        f"/repos/{owner}/{repo}/pulls/{pull_number}/files", token,
    )


def reply_to_review_comment(owner, repo, pull_number, comment_id, body, token):
    """Post a threaded reply to a PR review comment.

    Returns the created comment dict, or None on error.
    """
    return api_call_with_retry(
        f"/repos/{owner}/{repo}/pulls/{pull_number}/comments",
        token,
        body={"body": body, "in_reply_to": comment_id},
        method="POST",
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    """CLI entry point for quick checks."""
    import argparse

    parser = argparse.ArgumentParser(description="GitHub API utilities")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check-token", help="Verify token works")
    check.add_argument("--token-var", default=DEFAULT_TOKEN_VAR)

    repo = sub.add_parser("check-repo", help="Check if a repo exists")
    repo.add_argument("owner")
    repo.add_argument("repo")
    repo.add_argument("--token-var", default=DEFAULT_TOKEN_VAR)

    fork = sub.add_parser("ensure-fork", help="Ensure fork exists")
    fork.add_argument("upstream", help="owner/repo")
    fork.add_argument("--fork-owner", help="Fork under this user (default: token owner)")
    fork.add_argument("--token-var", default=DEFAULT_TOKEN_VAR)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        token = require_env(args.token_var)

        if args.command == "check-token":
            user = get_authenticated_user(token)
            print(f"Authenticated as: {user['login']}")

        elif args.command == "check-repo":
            result = get_repo(args.owner, args.repo, token)
            if result:
                print(f"Exists: {result['full_name']} (fork={result.get('fork', False)})")
            else:
                print("Not found")
                sys.exit(1)

        elif args.command == "ensure-fork":
            parts = args.upstream.split("/")
            if len(parts) != 2:
                print("upstream must be owner/repo", file=sys.stderr)
                sys.exit(1)
            up_owner, up_repo = parts
            fork_owner = args.fork_owner
            if not fork_owner:
                user = get_authenticated_user(token)
                fork_owner = user["login"]
            slug, created = ensure_fork(up_owner, up_repo, fork_owner, token)
            status = "created" if created else "exists"
            print(json.dumps({"fork": slug, "status": status}, indent=2))

    except (EnvironmentError, urllib.error.HTTPError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
