#!/usr/bin/env python3
"""Pipeline orchestrator — process a strategy's epics through codegen.

Fetches child work items from Jira, classifies them by eligibility,
invokes Claude's /epic-codegen skill for each eligible epic, and
writes a structured JSON run log for dashboard consumption.

Usage:
    # Process one or more strategies
    python3 scripts/run_pipeline.py RHAISTRAT-1699 RHAISTRAT-1700

    # Dry run (show what would process, don't invoke Claude)
    python3 scripts/run_pipeline.py RHAISTRAT-1699 --dry-run

    # CI mode (use run-claude.sh wrapper)
    python3 scripts/run_pipeline.py RHAISTRAT-1699 --run-script ci-scripts/run-claude.sh

    # With codegen options
    python3 scripts/run_pipeline.py RHAISTRAT-1699 --max-iterations 5 --fork-owner dora-the-ai-coder
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from artifact_utils import find_epic_task, read_frontmatter_validated
from fetch_epic import fetch_strategy
from fetch_jira_epics import (
    DONE_STATUSES,
    build_dependency_dag,
    fetch_children,
    generate_epic_task_from_jira,
    generate_status_report,
    is_eligible,
    issue_to_epic_data,
)
from jira_utils import (
    add_comment,
    do_transition,
    get_transitions,
    markdown_to_adf,
    require_env,
)

PROCESSED = "processed"
SKIPPED = "skipped"
BLOCKED = "blocked"
FAILED = "failed"

PROCESSABLE_STATUSES = {"New", "To Do", "Open"}

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "config")


def transition_issue(server, user, token, issue_key, target_status):
    """Transition a Jira issue to the given status.

    Discovers available transitions and matches by name (case-insensitive).

    Returns:
        tuple: (success: bool, from_status: str) — from_status is the
        current status name before transition, or empty string on failure.
    """
    try:
        transitions = get_transitions(server, user, token, issue_key)
    except Exception as e:
        print(f"  Warning: failed to get transitions for {issue_key}: {e}",
              file=sys.stderr)
        return False, ""

    target_lower = target_status.lower()
    for t in transitions:
        to_name = t.get("to", {}).get("name", "")
        if to_name.lower() == target_lower:
            try:
                do_transition(server, user, token, issue_key, t["id"])
                print(f"  {issue_key}: transitioned to '{to_name}'")
                return True, to_name
            except Exception as e:
                print(f"  Warning: transition to '{to_name}' failed "
                      f"for {issue_key}: {e}", file=sys.stderr)
                return False, ""

    available = [t.get("to", {}).get("name", "?") for t in transitions]
    print(f"  Warning: no '{target_status}' transition for {issue_key} "
          f"(available: {available})", file=sys.stderr)
    return False, ""


def read_pr_url(epic_id, artifacts_dir):
    """Read the PR URL from an epic-task's frontmatter after codegen.

    Returns:
        str or None: the PR URL, or None if not found.
    """
    path = find_epic_task(artifacts_dir, epic_id)
    if not path:
        return None
    try:
        data, _ = read_frontmatter_validated(path, "epic-task")
        return data.get("pr_url")
    except Exception:
        return None


def link_pr_to_jira(server, user, token, issue_key, pr_url):
    """Post a comment on the Jira issue with the PR URL.

    Returns:
        bool: True on success, False on error.
    """
    comment_md = f"PR created by codegen pipeline: {pr_url}"
    body_adf = markdown_to_adf(comment_md)
    try:
        add_comment(server, user, token, issue_key, body_adf)
        print(f"  {issue_key}: linked PR {pr_url}")
        return True
    except Exception as e:
        print(f"  Warning: failed to link PR to {issue_key}: {e}",
              file=sys.stderr)
        return False


def load_pr_urls_from_logs(log_dir):
    """Scan previous run logs and collect known PR URLs per epic.

    Returns:
        dict: {epic_id: pr_url} — latest PR URL wins if an epic appears
        in multiple logs.
    """
    pr_urls = {}
    if not os.path.isdir(log_dir):
        return pr_urls
    for filename in sorted(os.listdir(log_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(log_dir, filename)
        try:
            with open(path, encoding="utf-8") as f:
                log = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for strategy in log.get("strategies", {}).values():
            for eid, epic_data in strategy.get("epics", {}).items():
                url = epic_data.get("pr_url")
                if url:
                    pr_urls[eid] = url
    return pr_urls


def check_pr_merged(pr_url):
    """Check if a GitHub PR is merged using the gh CLI.

    Returns:
        bool: True if merged, False otherwise (including errors).
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_url, "--json", "merged"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        return data.get("merged", False)
    except (subprocess.TimeoutExpired, FileNotFoundError,
            json.JSONDecodeError):
        return False


def load_repo_mapping(path=None):
    """Load the keyword-to-repo mapping from JSON.

    Returns:
        dict: {repo: {"keywords": [...]}} or empty dict if file missing.
    """
    if path is None:
        path = os.path.join(_CONFIG_DIR, "repo_mapping.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_target_repo(epic_data, mapping, prompt_path=None):
    """Determine the target repo for an epic.

    First tries keyword matching against epic title + body.
    Falls back to LLM if no match or ambiguous.

    Returns:
        str: repo identifier or empty string.
    """
    if not mapping:
        return ""

    text = " ".join([
        epic_data.get("title", ""),
        epic_data.get("body", ""),
    ]).lower()

    matches = []
    for repo, config in mapping.items():
        keywords = config.get("keywords", [])
        if any(kw.lower() in text for kw in keywords):
            matches.append(repo)

    if len(matches) == 1:
        return matches[0]

    return resolve_repo_via_llm(epic_data, mapping, prompt_path)


def resolve_repo_via_llm(epic_data, mapping, prompt_path=None):
    """Ask Claude to determine the target repo.

    Returns:
        str: repo identifier or empty string.
    """
    if prompt_path is None:
        prompt_path = os.path.join(_CONFIG_DIR, "repo_resolve_prompt.md")
    if not os.path.isfile(prompt_path):
        print(f"  Warning: prompt template not found: {prompt_path}",
              file=sys.stderr)
        return ""

    with open(prompt_path, encoding="utf-8") as f:
        template = f.read()

    repos_text = "\n".join(
        f"- **{repo}**: keywords: {', '.join(cfg.get('keywords', []))}"
        for repo, cfg in mapping.items()
    )

    prompt = template.format(
        epic_title=epic_data.get("title", ""),
        epic_description=epic_data.get("body", "")[:2000],
        available_repos=repos_text,
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt,
             "--dangerously-skip-permissions",
             "--output-format", "text"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"  Warning: LLM repo resolution failed (exit {result.returncode})",
                  file=sys.stderr)
            return ""

        answer = result.stdout.strip()
        if answer == "NONE":
            return ""
        if answer in mapping:
            return answer
        print(f"  Warning: LLM returned unknown repo: {answer}",
              file=sys.stderr)
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Warning: LLM repo resolution error: {e}", file=sys.stderr)
        return ""


def clean_artifacts(output_dir):
    """Wipe epic-tasks and strategies directories for a fresh fetch.

    Preserves codegen-runs/ (audit trail).
    """
    for subdir in ["epic-tasks", "strategies"]:
        path = os.path.join(output_dir, subdir)
        if os.path.isdir(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)


def find_eligible(all_epics_by_key, completed_keys, handled_keys):
    """Return sorted list of epic keys eligible for codegen.

    Eligible: not in handled_keys, and all dependencies are in
    completed_keys (done in Jira or successfully processed).
    """
    eligible = []
    for key, epic in all_epics_by_key.items():
        if key in handled_keys:
            continue
        deps = epic.get("dependencies") or []
        if all(d in completed_keys for d in deps):
            eligible.append(key)
    return sorted(eligible)


def invoke_codegen(epic_id, args):
    """Shell out to Claude for codegen. Returns True on success."""
    skill_args = f"/epic-codegen {epic_id}"
    if args.max_iterations is not None:
        skill_args += f" --max-iterations {args.max_iterations}"
    if args.fork_owner:
        skill_args += f" --fork-owner {args.fork_owner}"

    if args.run_script:
        cmd = ["bash", args.run_script, skill_args]
    else:
        cmd = [
            "claude", "-p", skill_args,
            "--dangerously-skip-permissions",
            "--output-format", "text",
        ]

    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(args.log_dir, f"{epic_id}.log")

    print(f"--- Invoking codegen for {epic_id} ---")
    print(f"  Command: {' '.join(cmd)}")
    print(f"  Log: {log_path}")

    try:
        with open(log_path, "w", encoding="utf-8") as log_file:
            result = subprocess.run(
                cmd,
                cwd=os.getcwd(),
                timeout=args.timeout,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        if result.returncode == 0:
            print(f"  Result: SUCCESS")
            return True
        else:
            print(f"  Result: FAILED (exit code {result.returncode})",
                  file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print(f"  Result: TIMEOUT ({args.timeout}s)", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"  Result: COMMAND NOT FOUND ({cmd[0]})", file=sys.stderr)
        return False


def process_strategy(strategy_key, server, user, token, args):
    """Process one strategy: fetch epics, classify, run codegen on eligible.

    Returns:
        tuple: (epics_list, results_dict)
        results_dict has keys: processed, skipped, blocked, failed.
        Each value is a list of (epic_id, detail_str) tuples.
    """
    epic_tasks_dir = os.path.join(args.output_dir, "epic-tasks")
    strategies_dir = os.path.join(args.output_dir, "strategies")

    print(f"\n{'='*60}")
    print(f"Strategy: {strategy_key}")
    print(f"{'='*60}")

    print(f"Fetching children of {strategy_key}...")
    issues = fetch_children(server, user, token, strategy_key)
    if not issues:
        print(f"  No child work items found for {strategy_key}")
        return [], {PROCESSED: [], SKIPPED: [], BLOCKED: [], FAILED: []}, {}, {}

    print(f"  Found {len(issues)} child work items")

    dag = build_dependency_dag(issues)
    epics = [issue_to_epic_data(issue, strategy_key, dag) for issue in issues]

    mapping = load_repo_mapping()
    for epic in epics:
        repo = resolve_target_repo(epic, mapping)
        if repo:
            epic["target_repo"] = repo
            print(f"  {epic['epic_id']}: target_repo → {repo}")
        else:
            print(f"  {epic['epic_id']}: target_repo unresolved")

    all_epics_by_key = {e["epic_id"]: e for e in epics}

    for epic in epics:
        generate_epic_task_from_jira(epic, epic_tasks_dir)

    if not args.no_strategy:
        fetch_strategy(strategy_key, strategies_dir)

    results = {PROCESSED: [], SKIPPED: [], BLOCKED: [], FAILED: []}
    transitions_log = {}
    pr_urls = {}
    completed_keys = set()
    handled_keys = set()

    known_pr_urls = load_pr_urls_from_logs(args.log_dir)

    for key, epic in all_epics_by_key.items():
        status = epic.get("jira_status")
        if status in PROCESSABLE_STATUSES:
            continue

        if status in DONE_STATUSES:
            results[SKIPPED].append((key, "Already done in Jira"))
            completed_keys.add(key)
            print(f"  {key}: SKIP (already done)")
        elif status == "In Review" and not args.dry_run:
            pr_url = known_pr_urls.get(key)
            if pr_url and check_pr_merged(pr_url):
                ok, _ = transition_issue(
                    server, user, token, key, "Done")
                if ok:
                    completed_keys.add(key)
                    transitions_log[key] = [
                        {"to": "Done", "success": True}]
                    print(f"  {key}: RECONCILED (PR merged → Done)")
                else:
                    print(f"  {key}: PR merged but transition failed")
                results[SKIPPED].append(
                    (key, "PR merged, transitioned to Done"))
            else:
                results[SKIPPED].append((key, f"Active ({status})"))
                print(f"  {key}: SKIP (active: {status})")
        else:
            results[SKIPPED].append((key, f"Active ({status})"))
            print(f"  {key}: SKIP (active: {status})")
        handled_keys.add(key)

    eligible = find_eligible(all_epics_by_key, completed_keys, handled_keys)

    for epic_id in eligible:
        if args.dry_run:
            print(f"  {epic_id}: ELIGIBLE (dry-run, would process)")
            results[PROCESSED].append((epic_id, "dry-run"))
            handled_keys.add(epic_id)
            continue

        print(f"  {epic_id}: ELIGIBLE — starting codegen")
        epic_transitions = []

        ok, _ = transition_issue(
            server, user, token, epic_id, "In Progress")
        epic_transitions.append({
            "to": "In Progress", "success": ok})

        original_status = all_epics_by_key[epic_id].get("jira_status", "")

        success = invoke_codegen(epic_id, args)
        if success:
            results[PROCESSED].append((epic_id, "codegen completed"))
            ok, _ = transition_issue(
                server, user, token, epic_id, "In Review")
            epic_transitions.append({
                "to": "In Review", "success": ok})

            pr_url = read_pr_url(epic_id, args.output_dir)
            if pr_url:
                pr_urls[epic_id] = pr_url
                link_pr_to_jira(server, user, token, epic_id, pr_url)
        else:
            results[FAILED].append((epic_id, "codegen failed"))
            if original_status:
                ok, _ = transition_issue(
                    server, user, token, epic_id, original_status)
                epic_transitions.append({
                    "to": original_status, "success": ok})

        transitions_log[epic_id] = epic_transitions
        handled_keys.add(epic_id)

    for key in all_epics_by_key:
        if key not in handled_keys:
            epic = all_epics_by_key[key]
            deps = epic.get("dependencies") or []
            unmet = [d for d in deps if d not in completed_keys]
            reason = f"Blocked by {', '.join(unmet)}"
            results[BLOCKED].append((key, reason))
            print(f"  {key}: BLOCKED ({reason})")

    return epics, results, transitions_log, pr_urls


def build_run_log(all_results, start_time):
    """Build structured execution log for dashboard consumption.

    Args:
        all_results: dict of {strategy_key: (epics_list, results_dict, transitions_log, pr_urls)}
        start_time: datetime when the run started

    Returns:
        dict: the full run log structure
    """
    end_time = datetime.now(timezone.utc)
    run_id = start_time.strftime("%Y-%m-%dT%H-%M-%SZ")

    strategies = {}
    for strategy_key, (epics, results, transitions_log, pr_urls) in all_results.items():
        epics_by_key = {e["epic_id"]: e for e in epics}

        action_map = {}
        for action, entries in results.items():
            for epic_id, detail in entries:
                action_map[epic_id] = (action, detail)

        epics_log = {}
        for epic in epics:
            eid = epic["epic_id"]
            action, detail = action_map.get(eid, ("unknown", ""))
            result = None
            if action == PROCESSED:
                result = "success" if detail != "dry-run" else "dry-run"
            elif action == FAILED:
                result = "failure"

            epics_log[eid] = {
                "title": epic.get("title", ""),
                "jira_status": epic.get("jira_status", ""),
                "action": action,
                "result": result,
                "reason": detail,
                "dependencies": epic.get("dependencies") or [],
                "blocks": epic.get("blocks") or [],
                "transitions": transitions_log.get(eid, []),
                "pr_url": pr_urls.get(eid),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        strategies[strategy_key] = {
            "total_epics": len(epics),
            "summary": {
                action: len(entries)
                for action, entries in results.items()
            },
            "epics": epics_log,
        }

    return {
        "run_id": run_id,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "strategies": strategies,
    }


def write_run_log(run_log, output_dir="pipeline-runs"):
    """Write run log JSON to file.

    Returns:
        Path to the written file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{run_log['run_id']}.json"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, indent=2)
    return path


def print_summary(all_results):
    """Print a summary table to stdout."""
    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")

    total_p = total_s = total_b = total_f = 0
    for strategy_key, (epics, results, *_) in all_results.items():
        p = len(results[PROCESSED])
        s = len(results[SKIPPED])
        b = len(results[BLOCKED])
        f = len(results[FAILED])
        total_p += p
        total_s += s
        total_b += b
        total_f += f
        print(f"  {strategy_key}: "
              f"{p} processed, {s} skipped, {b} blocked, {f} failed")

    if len(all_results) > 1:
        print(f"  {'─'*40}")
        print(f"  TOTAL: "
              f"{total_p} processed, {total_s} skipped, "
              f"{total_b} blocked, {total_f} failed")
    print()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Orchestrate codegen pipeline for strategy epics")
    parser.add_argument("keys", nargs="+",
                        help="Strategy keys (e.g., RHAISTRAT-1699)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without invoking Claude")
    parser.add_argument("--run-script",
                        help="Path to run-claude.sh (CI mode)")
    parser.add_argument("--max-iterations", type=int, default=None,
                        help="Pass --max-iterations to epic-codegen")
    parser.add_argument("--fork-owner",
                        help="Pass --fork-owner to epic-codegen")
    parser.add_argument("--no-clean", action="store_true",
                        help="Don't wipe artifacts before fetch")
    parser.add_argument("--output-dir", default="artifacts",
                        help="Artifact output directory")
    parser.add_argument("--report-dir", default="epic-reports",
                        help="HTML report output directory")
    parser.add_argument("--log-dir", default="pipeline-runs",
                        help="Run log output directory")
    parser.add_argument("--timeout", type=int, default=3600,
                        help="Per-epic timeout in seconds (default: 3600)")
    parser.add_argument("--no-strategy", action="store_true",
                        help="Skip fetching strategy from Jira")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip generating HTML status report")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    start_time = datetime.now(timezone.utc)

    for key in args.keys:
        if not re.match(r'^[A-Z][A-Z0-9]+-\d+$', key):
            print(f"Error: invalid key format: {key}", file=sys.stderr)
            sys.exit(1)

    server, user, token = require_env()
    if not all([server, user, token]):
        print("Error: JIRA_SERVER, JIRA_USER, JIRA_TOKEN must be set",
              file=sys.stderr)
        sys.exit(1)

    if not args.no_clean:
        clean_artifacts(args.output_dir)

    all_results = {}
    for strategy_key in args.keys:
        epics, results, transitions_log, pr_urls = process_strategy(
            strategy_key, server, user, token, args)
        all_results[strategy_key] = (epics, results, transitions_log, pr_urls)

        if not args.no_report and epics:
            report_path = generate_status_report(
                epics, strategy_key, args.report_dir)
            print(f"  Report: {report_path}")

    run_log = build_run_log(all_results, start_time)
    log_path = write_run_log(run_log, args.log_dir)
    print(f"\nRun log: {log_path}")

    print_summary(all_results)

    has_failures = any(
        results[FAILED]
        for _, (_, results, *_) in all_results.items()
    )
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main())
