#!/usr/bin/env python3
"""V2 Code Review Response orchestrator.

Reads PR review comments, triages them, invokes a fix agent,
validates, pushes, and replies to each comment on the PR.

Usage:
    python3 scripts/review_response.py <EPIC_ID> <PR_URL> \
        [--output-dir artifacts] [--target-repo .target-repo] \
        [--fork-owner dora-the-ai-coder] [--dry-run]
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from github_utils import (
    api_call_with_retry,
    get_pr_files,
    reply_to_review_comment,
    require_env,
)
from pr_lifecycle import (
    compute_diff_scope,
    filter_unprocessed_comments,
    get_pr_reviews,
    is_comment_in_scope,
    load_processed_comment_ids,
    parse_pr_url,
)


CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "review_config.json")


def load_review_config():
    """Load bot reviewer list and settings from config."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def triage_comments(comments, diff_scope, bot_reviewers):
    """Decide action for each comment: fix, skip_out_of_scope, or evaluate.

    Human reviewer comments in scope are always marked fix.
    Bot comments in scope are marked fix (default to fixing bots).
    Comments outside our diff are marked skip_out_of_scope.

    Returns list of dicts with original comment fields + "action" and "reason".
    """
    triaged = []
    for c in comments:
        user = c.get("user", "")
        is_bot = user in bot_reviewers
        in_scope = is_comment_in_scope(c, diff_scope)

        if not in_scope:
            action = "skip_out_of_scope"
            reason = "Comment targets pre-existing code outside this PR's changes"
        elif is_bot:
            action = "fix"
            reason = "Bot suggestion on our code — applying fix"
        else:
            action = "fix"
            reason = "Human reviewer request — must address"

        triaged.append({
            **c,
            "action": action,
            "reason": reason,
            "is_bot": is_bot,
        })
    return triaged


def write_review_feedback(triaged_comments, output_path):
    """Write raw review comments grouped by file."""
    lines = ["# PR Review Feedback (V2)\n"]

    by_file = {}
    for c in triaged_comments:
        by_file.setdefault(c["path"], []).append(c)

    for path in sorted(by_file.keys()):
        lines.append(f"## `{path}`\n")
        for c in sorted(by_file[path], key=lambda x: x.get("line") or 0):
            loc = f"line {c['line']}" if c.get("line") else "general"
            bot_tag = " [bot]" if c.get("is_bot") else ""
            lines.append(f"### {c['user']}{bot_tag} ({loc})\n")
            lines.append(f"{c['body']}\n")
            if c.get("diff_hunk"):
                lines.append("```diff")
                lines.append(c["diff_hunk"])
                lines.append("```\n")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def write_response_plan(triaged_comments, output_path):
    """Write triage decisions: what to fix, what to skip, and why."""
    lines = ["# Review Response Plan\n"]

    to_fix = [c for c in triaged_comments if c["action"] == "fix"]
    to_skip = [c for c in triaged_comments if c["action"] != "fix"]

    lines.append(f"**Total comments:** {len(triaged_comments)}")
    lines.append(f"**To fix:** {len(to_fix)}")
    lines.append(f"**To skip:** {len(to_skip)}\n")

    if to_fix:
        lines.append("## Fix\n")
        for c in to_fix:
            loc = f"line {c['line']}" if c.get("line") else "general"
            lines.append(f"- **{c['path']}** ({loc}) — {c['user']}")
            body_preview = c["body"][:200].replace("\n", " ")
            lines.append(f"  > {body_preview}")
            lines.append(f"  Action: {c['action']} — {c['reason']}\n")

    if to_skip:
        lines.append("## Skip\n")
        for c in to_skip:
            loc = f"line {c['line']}" if c.get("line") else "general"
            lines.append(f"- **{c['path']}** ({loc}) — {c['user']}")
            body_preview = c["body"][:200].replace("\n", " ")
            lines.append(f"  > {body_preview}")
            lines.append(f"  Action: {c['action']} — {c['reason']}\n")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def run_validation(target_repo):
    """Run lint/typecheck/tests on the target repo.

    Returns (passed: bool, result: dict).
    """
    validate_script = os.path.join(
        os.path.dirname(__file__), "validate_target.py")
    try:
        result = subprocess.run(
            [sys.executable, validate_script, target_repo, "--json"],
            capture_output=True, text=True, timeout=600,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout.strip())
            passed = all([
                data.get("lint_pass", True),
                data.get("typecheck_pass", True),
                data.get("tests_pass", True),
            ])
            return passed, data
        return result.returncode == 0, {"raw": result.stderr}
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return False, {"error": str(e)}


def save_pr_replies(replies, output_path, version):
    """Save or append to pr-replies.json."""
    existing = {"replies": []}
    if os.path.isfile(output_path):
        with open(output_path) as f:
            existing = json.load(f)

    for r in replies:
        r["version"] = version
    existing["replies"].extend(replies)

    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2)


def post_replies(triaged_comments, commit_sha, pr_url, token, dry_run=False):
    """Post replies to each comment on the PR.

    Returns list of reply records for pr-replies.json.
    """
    owner, repo, number = parse_pr_url(pr_url)
    replies = []

    for c in triaged_comments:
        comment_id = c.get("id")
        if not comment_id:
            continue

        if c["action"] == "fix":
            body = f"Fixed in {commit_sha[:8]}."
        elif c["action"] == "skip_out_of_scope":
            body = ("This comment targets pre-existing code outside the scope "
                    "of this PR's changes. Not modified.")
        elif c["action"] == "skip_bot_disagree":
            body = c.get("skip_reason", "We chose not to apply this suggestion.")
        else:
            body = f"Acknowledged. Action: {c['action']}."

        reply_record = {
            "comment_id": comment_id,
            "user": c.get("user", ""),
            "action": c["action"],
            "reply_body": body,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        if not dry_run:
            try:
                result = reply_to_review_comment(
                    owner, repo, number, comment_id, body, token)
                if result:
                    reply_record["reply_id"] = result.get("id")
            except Exception as e:
                print(f"  Warning: failed to reply to comment {comment_id}: "
                      f"{e}", file=sys.stderr)
                reply_record["error"] = str(e)

        replies.append(reply_record)

    return replies


def run_review_response(epic_id, pr_url, output_dir="artifacts",
                        target_repo=".target-repo", version=2,
                        dry_run=False, gh_token_var=None):
    """Execute the full V2 review response flow.

    Returns:
        dict: {success, comments_processed, fixes_applied, commit_sha, errors}
    """
    token = require_env(gh_token_var)
    config = load_review_config()
    bot_reviewers = set(config.get("bot_reviewers", []))
    our_user = config.get("our_user", "dora-the-ai-coder")
    max_retries = config.get("validation_retry_limit", 3)

    owner, repo, number = parse_pr_url(pr_url)

    # 1. Fetch and filter comments
    print(f"Fetching PR comments from {pr_url}...")
    reviews_data = get_pr_reviews(pr_url, token)
    all_comments = reviews_data["comments"]

    pr_replies_path = os.path.join(
        output_dir, "codegen-runs", epic_id, "pr-replies.json")
    processed_ids = load_processed_comment_ids(pr_replies_path)

    unprocessed = filter_unprocessed_comments(
        all_comments, processed_ids, our_user)

    if not unprocessed:
        print("No unprocessed comments found.")
        return {
            "success": True,
            "comments_processed": 0,
            "fixes_applied": 0,
            "commit_sha": None,
            "errors": [],
        }

    print(f"Found {len(unprocessed)} unprocessed comment(s).")

    # 2. Compute diff scope
    print("Computing diff scope...")
    pr_files = get_pr_files(owner, repo, number, token)
    diff_scope = compute_diff_scope(pr_files)
    print(f"  {len(diff_scope)} files in our diff scope.")

    # 3. Triage comments
    triaged = triage_comments(unprocessed, diff_scope, bot_reviewers)
    to_fix = [c for c in triaged if c["action"] == "fix"]
    to_skip = [c for c in triaged if c["action"] != "fix"]
    print(f"  {len(to_fix)} to fix, {len(to_skip)} to skip.")

    # 4. Write artifacts
    version_dir = os.path.join(
        output_dir, "codegen-runs", epic_id, f"v{version}")
    os.makedirs(version_dir, exist_ok=True)

    feedback_path = os.path.join(version_dir, "review-feedback.md")
    plan_path = os.path.join(version_dir, "review-response-plan.md")

    write_review_feedback(triaged, feedback_path)
    write_response_plan(triaged, plan_path)
    print(f"  Artifacts written to {version_dir}/")

    # 5. Record pre-fix state
    commit_sha = None
    errors = []

    if to_fix and not dry_run:
        # Get pre-fix SHA
        pre_fix_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=target_repo, capture_output=True, text=True)
        pre_fix_sha = pre_fix_result.stdout.strip()

        # 6. Invoke fix agent via Claude
        spec_path = os.path.join(
            output_dir, "codegen-runs", epic_id, "codegen-spec.md")

        print("Invoking fix agent...")
        fix_prompt = _build_fix_prompt(
            plan_path, feedback_path, spec_path, target_repo, version)

        fix_success = _invoke_claude(fix_prompt, target_repo)

        if not fix_success:
            errors.append("Fix agent failed")
            print("  Fix agent FAILED.", file=sys.stderr)
        else:
            # 7. Run validation with retry
            for attempt in range(1, max_retries + 1):
                print(f"  Validation attempt {attempt}/{max_retries}...")
                passed, val_result = run_validation(target_repo)

                val_path = os.path.join(version_dir, "validation.json")
                with open(val_path, "w") as f:
                    json.dump(val_result, f, indent=2)

                if passed:
                    print("  Validation PASSED.")
                    break

                if attempt < max_retries:
                    print("  Validation failed, retrying fix...")
                    retry_prompt = _build_validation_retry_prompt(
                        val_result, target_repo)
                    _invoke_claude(retry_prompt, target_repo)
            else:
                errors.append(
                    f"Validation failed after {max_retries} attempts")
                print(f"  Validation FAILED after {max_retries} retries.",
                      file=sys.stderr)

            # Get commit SHA
            post_fix_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=target_repo, capture_output=True, text=True)
            commit_sha = post_fix_result.stdout.strip()

            if commit_sha != pre_fix_sha:
                # Save incremental diff
                diff_result = subprocess.run(
                    ["git", "diff", f"{pre_fix_sha}..{commit_sha}"],
                    cwd=target_repo, capture_output=True, text=True)
                diff_path = os.path.join(version_dir, "diff.patch")
                with open(diff_path, "w") as f:
                    f.write(diff_result.stdout)

                # 8. Run sanity check
                print("Running sanity check...")
                _run_sanity_check(
                    plan_path, diff_path, feedback_path, version_dir,
                    target_repo)

                # 9. Push to fork
                if not errors:
                    print("Pushing to fork...")
                    push_result = subprocess.run(
                        ["git", "push", "fork", f"epic/{epic_id}"],
                        cwd=target_repo, capture_output=True, text=True,
                        timeout=120)
                    if push_result.returncode != 0:
                        errors.append(f"Push failed: {push_result.stderr}")
                        print(f"  Push FAILED: {push_result.stderr}",
                              file=sys.stderr)
                    else:
                        print("  Pushed successfully.")
            else:
                print("  No changes made by fix agent.")
                commit_sha = None

    # 10. Post replies
    print("Posting PR replies...")
    replies = post_replies(
        triaged, commit_sha or "no-change", pr_url, token, dry_run=dry_run)
    save_pr_replies(replies, pr_replies_path, version)
    print(f"  Posted {len(replies)} replies.")

    success = len(errors) == 0
    return {
        "success": success,
        "comments_processed": len(triaged),
        "fixes_applied": len(to_fix),
        "commit_sha": commit_sha,
        "errors": errors,
    }


def _build_fix_prompt(plan_path, feedback_path, spec_path, target_repo,
                      version):
    """Build the prompt for the fix agent."""
    return (
        f"You are applying review fixes for version {version}.\n\n"
        f"PLAN_FILE = {os.path.abspath(plan_path)}\n"
        f"FEEDBACK_FILE = {os.path.abspath(feedback_path)}\n"
        f"SPEC_FILE = {os.path.abspath(spec_path)}\n"
        f"TARGET_REPO = {os.path.abspath(target_repo)}\n\n"
        "Read the response plan. For each item marked 'fix', apply the "
        "requested change in the target repo. Commit once at the end with "
        f"message: 'fix: address PR review feedback (v{version})'\n"
        "Sign off with --signoff."
    )


def _build_validation_retry_prompt(val_result, target_repo):
    """Build prompt for validation retry."""
    return (
        "Validation failed after your fixes. Here are the errors:\n\n"
        f"```json\n{json.dumps(val_result, indent=2)}\n```\n\n"
        f"Fix the issues in {os.path.abspath(target_repo)} and commit "
        "the fixes. Sign off with --signoff."
    )


def _invoke_claude(prompt, cwd):
    """Invoke Claude as a subprocess. Returns True on success."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions",
             "--output-format", "text"],
            capture_output=True, text=True, cwd=cwd, timeout=900,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Claude invocation error: {e}", file=sys.stderr)
        return False


def _run_sanity_check(plan_path, diff_path, feedback_path, version_dir, cwd):
    """Run the sanity-check agent."""
    sanity_path = os.path.join(version_dir, "sanity-check.md")
    prompt = (
        "You are performing a sanity check on review fixes.\n\n"
        f"PLAN_FILE = {os.path.abspath(plan_path)}\n"
        f"DIFF_FILE = {os.path.abspath(diff_path)}\n"
        f"FEEDBACK_FILE = {os.path.abspath(feedback_path)}\n"
        f"SANITY_CHECK_FILE = {os.path.abspath(sanity_path)}\n\n"
        "Verify each fix in the plan has a corresponding change in the diff. "
        "Flag any unplanned changes. Write results to SANITY_CHECK_FILE."
    )
    try:
        subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions",
             "--output-format", "text"],
            capture_output=True, text=True, cwd=cwd, timeout=300,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Sanity check error: {e}", file=sys.stderr)
        with open(sanity_path, "w") as f:
            f.write(f"## Sanity Check Results\n\nError: {e}\n")


def main():
    parser = argparse.ArgumentParser(
        description="V2 Code Review Response orchestrator")
    parser.add_argument("epic_id", help="Epic ID (e.g., RHOAIENG-72528)")
    parser.add_argument("pr_url", help="GitHub PR URL")
    parser.add_argument("--output-dir", default="artifacts",
                        help="Artifacts directory (default: artifacts)")
    parser.add_argument("--target-repo", default=".target-repo",
                        help="Target repo path (default: .target-repo)")
    parser.add_argument("--version", type=int, default=2,
                        help="Version number for this iteration (default: 2)")
    parser.add_argument("--fork-owner", default=None,
                        help="Fork owner for push")
    parser.add_argument("--gh-token-var", default=None,
                        help="Env var for GitHub token")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip push and PR replies")
    parser.add_argument("--json", action="store_true",
                        help="Output result as JSON")
    args = parser.parse_args()

    try:
        result = run_review_response(
            args.epic_id,
            args.pr_url,
            output_dir=args.output_dir,
            target_repo=args.target_repo,
            version=args.version,
            dry_run=args.dry_run,
            gh_token_var=args.gh_token_var,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            status = "SUCCESS" if result["success"] else "FAILED"
            print(f"\n{'='*50}")
            print(f"Review Response: {status}")
            print(f"Comments processed: {result['comments_processed']}")
            print(f"Fixes applied: {result['fixes_applied']}")
            if result["commit_sha"]:
                print(f"Commit: {result['commit_sha'][:8]}")
            if result["errors"]:
                print(f"Errors: {', '.join(result['errors'])}")

        sys.exit(0 if result["success"] else 1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
