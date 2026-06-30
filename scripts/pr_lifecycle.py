#!/usr/bin/env python3
"""PR lifecycle management for epic-code-gen CI pipeline.

Checks PR status, fetches review comments, and formats feedback
for the next codegen iteration. Uses github_utils for API access
(no gh CLI dependency).

Usage:
    python3 scripts/pr_lifecycle.py status <pr-url>
    python3 scripts/pr_lifecycle.py reviews <pr-url> [--output FILE]
"""

import argparse
import json
import os
import re
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from github_utils import (
    api_call_with_retry,
    extract_slug,
    require_env,
)


def parse_pr_url(pr_url):
    """Extract owner, repo, and PR number from a GitHub PR URL.

    Returns:
        tuple: (owner, repo, number) or raises ValueError.
    """
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        raise ValueError(f"Not a valid GitHub PR URL: {pr_url}")
    return match.group(1), match.group(2), int(match.group(3))


def get_pr_status(pr_url, token):
    """Check the current state of a pull request.

    Returns:
        dict: {
            "number": int,
            "state": "open" | "closed",
            "merged": bool,
            "mergeable": bool | None,
            "title": str,
            "draft": bool,
            "review_decision": str | None,
            "changed_files": int,
            "additions": int,
            "deletions": int,
            "reviews_pending": int,
            "reviews_approved": int,
            "reviews_changes_requested": int,
        }
    """
    owner, repo, number = parse_pr_url(pr_url)

    pr = api_call_with_retry(f"/repos/{owner}/{repo}/pulls/{number}", token)

    reviews = api_call_with_retry(
        f"/repos/{owner}/{repo}/pulls/{number}/reviews", token)

    review_counts = {"APPROVED": 0, "CHANGES_REQUESTED": 0, "PENDING": 0,
                     "COMMENTED": 0, "DISMISSED": 0}
    latest_by_user = {}
    for r in (reviews or []):
        user = r.get("user", {}).get("login", "")
        state = r.get("state", "")
        if user and state:
            latest_by_user[user] = state
    for state in latest_by_user.values():
        if state in review_counts:
            review_counts[state] += 1

    return {
        "number": pr["number"],
        "state": pr["state"],
        "merged": pr.get("merged", False),
        "mergeable": pr.get("mergeable"),
        "title": pr.get("title", ""),
        "draft": pr.get("draft", False),
        "review_decision": None,
        "changed_files": pr.get("changed_files", 0),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "reviews_pending": review_counts["PENDING"],
        "reviews_approved": review_counts["APPROVED"],
        "reviews_changes_requested": review_counts["CHANGES_REQUESTED"],
    }


def get_pr_reviews(pr_url, token):
    """Fetch all review comments on a pull request.

    Returns both top-level reviews and inline (file-level) comments.

    Returns:
        dict: {
            "reviews": [{user, state, body, submitted_at}],
            "comments": [{user, path, line, body, created_at, in_reply_to}],
        }
    """
    owner, repo, number = parse_pr_url(pr_url)

    raw_reviews = api_call_with_retry(
        f"/repos/{owner}/{repo}/pulls/{number}/reviews", token) or []

    reviews = []
    for r in raw_reviews:
        body = (r.get("body") or "").strip()
        state = r.get("state", "")
        if not body and state == "COMMENTED":
            continue
        reviews.append({
            "user": r.get("user", {}).get("login", ""),
            "state": state,
            "body": body,
            "submitted_at": r.get("submitted_at", ""),
        })

    raw_comments = api_call_with_retry(
        f"/repos/{owner}/{repo}/pulls/{number}/comments", token) or []

    comments = []
    for c in raw_comments:
        comments.append({
            "user": c.get("user", {}).get("login", ""),
            "path": c.get("path", ""),
            "line": c.get("original_line") or c.get("line"),
            "body": (c.get("body") or "").strip(),
            "created_at": c.get("created_at", ""),
            "in_reply_to": c.get("in_reply_to_id"),
        })

    return {"reviews": reviews, "comments": comments}


def format_review_feedback(reviews_data):
    """Format PR review data into structured feedback for the next iteration.

    Returns:
        str: Markdown-formatted review feedback.
    """
    lines = ["# PR Review Feedback\n"]

    change_requests = [r for r in reviews_data["reviews"]
                       if r["state"] == "CHANGES_REQUESTED"]
    if change_requests:
        lines.append("## Requested Changes\n")
        for r in change_requests:
            lines.append(f"**{r['user']}** ({r['submitted_at']}):")
            if r["body"]:
                lines.append(f"> {r['body']}\n")

    if reviews_data["comments"]:
        lines.append("## Inline Comments\n")
        by_file = {}
        for c in reviews_data["comments"]:
            if c["in_reply_to"]:
                continue
            by_file.setdefault(c["path"], []).append(c)

        for path in sorted(by_file.keys()):
            lines.append(f"### `{path}`\n")
            for c in sorted(by_file[path],
                            key=lambda x: x.get("line") or 0):
                loc = f"line {c['line']}" if c["line"] else "general"
                lines.append(f"- **{c['user']}** ({loc}): {c['body']}")
            lines.append("")

    approvals = [r for r in reviews_data["reviews"]
                 if r["state"] == "APPROVED"]
    if approvals:
        lines.append("## Approvals\n")
        for r in approvals:
            msg = f": {r['body']}" if r["body"] else ""
            lines.append(f"- {r['user']}{msg}")
        lines.append("")

    if not change_requests and not reviews_data["comments"]:
        lines.append("No actionable review feedback found.\n")

    return "\n".join(lines)


def derive_pr_state(status):
    """Map PR status to pipeline epic state.

    Returns:
        str: one of "PRCreated", "PRChangesRequested", "Done", "Ready"
    """
    if status["merged"]:
        return "Done"
    if status["state"] == "closed":
        return "Ready"
    if status["reviews_changes_requested"] > 0:
        return "PRChangesRequested"
    return "PRCreated"


def main():
    parser = argparse.ArgumentParser(
        description="PR lifecycle management for epic-code-gen")
    sub = parser.add_subparsers(dest="command")

    status_cmd = sub.add_parser("status", help="Check PR status")
    status_cmd.add_argument("pr_url", help="GitHub PR URL")
    status_cmd.add_argument("--token-var", default=None)

    reviews_cmd = sub.add_parser("reviews",
                                 help="Fetch PR review comments")
    reviews_cmd.add_argument("pr_url", help="GitHub PR URL")
    reviews_cmd.add_argument("--output", help="Write feedback to file")
    reviews_cmd.add_argument("--json", action="store_true",
                             help="Output raw JSON")
    reviews_cmd.add_argument("--token-var", default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    token = require_env(args.token_var)

    if args.command == "status":
        status = get_pr_status(args.pr_url, token)
        epic_state = derive_pr_state(status)
        status["epic_state"] = epic_state
        print(json.dumps(status, indent=2))

    elif args.command == "reviews":
        reviews_data = get_pr_reviews(args.pr_url, token)
        if args.json:
            print(json.dumps(reviews_data, indent=2))
        else:
            feedback = format_review_feedback(reviews_data)
            if args.output:
                with open(args.output, "w") as f:
                    f.write(feedback)
                print(f"Feedback written to {args.output}")
            else:
                print(feedback)


if __name__ == "__main__":
    main()
