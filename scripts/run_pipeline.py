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

    # CI mode with data repo (state machine, convergence across runs)
    python3 scripts/run_pipeline.py RHAISTRAT-1699 --ci --data-repo /path/to/data-repo

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

try:
    import yaml
except ImportError:
    yaml = None

PROCESSED = "processed"
SKIPPED = "skipped"
BLOCKED = "blocked"
FAILED = "failed"

PROCESSABLE_STATUSES = {"New", "To Do", "Open"}

CI_STATES = {
    "Pending", "Ready", "Generating", "ReviewPending",
    "PRCreated", "PRChangesRequested", "Done", "Blocked", "Failed",
}
CI_TERMINAL_STATES = {"Done", "Failed"}

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


TARGET_REPO_DIR = ".target-repo"


def setup_target_repo(epic, args):
    """Pre-setup target repo before Claude: clone, install deps, validate.

    Saves validation and readiness results to pre-setup.json so the
    epic-codegen skill can skip those steps and jump straight to
    spec generation.

    Returns:
        bool: True if setup succeeded, False on failure.
    """
    epic_id = epic["epic_id"]
    target_repo = epic.get("target_repo")
    if not target_repo:
        print(f"  {epic_id}: no target_repo set, skipping pre-setup")
        return False

    print(f"--- Pre-setup for {epic_id} ---")
    print(f"  Target repo: {target_repo}")

    # 1. Clone + branch
    clone_cmd = [
        sys.executable, os.path.join(_SCRIPT_DIR, "clone_target.py"),
        target_repo, epic_id, "--clean",
    ]
    if args.fork_owner:
        clone_cmd += ["--fork-owner", args.fork_owner,
                      "--gh-token-var", "EPIC_CODEGEN_GITHUB_TOKEN"]

    try:
        result = subprocess.run(
            clone_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  Clone failed: {result.stderr.strip()}", file=sys.stderr)
            return False
        print(f"  Cloned to {TARGET_REPO_DIR}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Clone error: {e}", file=sys.stderr)
        return False

    # 2. Validate (detect language + commands)
    validate_cmd = [
        sys.executable, os.path.join(_SCRIPT_DIR, "validate_target.py"),
        TARGET_REPO_DIR, "--json",
    ]
    try:
        result = subprocess.run(
            validate_cmd, capture_output=True, text=True, timeout=120)
        validation = json.loads(result.stdout) if result.stdout.strip() else {}
    except Exception:
        validation = {}

    language = validation.get("language")
    print(f"  Language: {language or 'unknown'}")

    # 3. Install deps based on language
    _install_deps(language)

    # 4. Readiness check
    readiness_cmd = [
        sys.executable, os.path.join(_SCRIPT_DIR, "repo_readiness.py"),
        TARGET_REPO_DIR,
    ]
    try:
        result = subprocess.run(
            readiness_cmd, capture_output=True, text=True, timeout=120)
        readiness_output = result.stdout.strip()
    except Exception:
        readiness_output = ""

    # 5. Save pre-setup.json
    pre_setup = {
        "validation": validation,
        "readiness_output": readiness_output,
        "language": language,
        "deps_installed": True,
    }
    run_dir = os.path.join(args.output_dir, "codegen-runs", epic_id)
    os.makedirs(run_dir, exist_ok=True)
    pre_setup_path = os.path.join(run_dir, "pre-setup.json")
    with open(pre_setup_path, "w") as f:
        json.dump(pre_setup, f, indent=2)
    print(f"  Pre-setup saved: {pre_setup_path}")
    return True


def _install_deps(language):
    """Install dependencies for the target repo based on detected language."""
    repo = TARGET_REPO_DIR

    if language in ("typescript", "javascript"):
        _install_node_deps(repo)
    elif language == "go":
        _run_cmd(["go", "mod", "download"], cwd=repo, label="go mod download")
    elif language == "python":
        pyproject = os.path.join(repo, "pyproject.toml")
        requirements = os.path.join(repo, "requirements.txt")
        if os.path.isfile(pyproject):
            _run_cmd([sys.executable, "-m", "pip", "install", "-e", "."],
                     cwd=repo, label="pip install -e .")
        elif os.path.isfile(requirements):
            _run_cmd([sys.executable, "-m", "pip", "install", "-r",
                      "requirements.txt"],
                     cwd=repo, label="pip install -r requirements.txt")


def _install_node_deps(repo):
    """Install Node.js dependencies, handling version requirements."""
    pkg_json = os.path.join(repo, "package.json")
    if not os.path.isfile(pkg_json):
        return

    required_major = None
    try:
        with open(pkg_json) as f:
            pkg = json.load(f)
        engines_node = pkg.get("engines", {}).get("node", "")
        match = re.search(r'>=\s*(\d+)', engines_node)
        if match:
            required_major = int(match.group(1))
    except Exception:
        pass

    nvmrc = os.path.join(repo, ".nvmrc")
    if not required_major and os.path.isfile(nvmrc):
        try:
            with open(nvmrc) as f:
                ver = f.read().strip().lstrip("v")
            required_major = int(ver.split(".")[0])
        except Exception:
            pass

    nvm_prefix = ""
    if required_major:
        current = _get_node_major()
        if current and current < required_major:
            nvm_sh = os.path.expanduser("~/.nvm/nvm.sh")
            if os.path.isfile(nvm_sh):
                nvm_prefix = (
                    f'source "{nvm_sh}" && nvm install {required_major} && '
                )
                print(f"  Node {current} < {required_major}, "
                      f"using nvm to install {required_major}")

    cmd = f"{nvm_prefix}npm install"
    _run_cmd(["bash", "-c", cmd], cwd=repo, label="npm install")


def _get_node_major():
    """Return the major version of the current node, or None."""
    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=10)
        ver = result.stdout.strip().lstrip("v")
        return int(ver.split(".")[0])
    except Exception:
        return None


def _run_cmd(cmd, cwd=None, label=None, timeout=600):
    """Run a command, log success/failure. Returns True on success."""
    label = label or " ".join(cmd)
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            print(f"  {label}: OK")
            return True
        else:
            print(f"  {label}: FAILED (exit {result.returncode})",
                  file=sys.stderr)
            return False
    except Exception as e:
        print(f"  {label}: ERROR ({e})", file=sys.stderr)
        return False


def _read_run_status(run_meta_path):
    """Read status field from run-metadata.yaml without a YAML library."""
    try:
        with open(run_meta_path) as f:
            for line in f:
                if line.startswith("status:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def invoke_codegen(epic_id, args):
    """Shell out to Claude for codegen. Returns True on success."""
    skill_args = f"/epic-codegen {epic_id}"
    if args.max_iterations is not None:
        skill_args += f" --max-iterations {args.max_iterations}"
    if args.fork_owner:
        skill_args += f" --fork-owner {args.fork_owner}"

    run_script = args.run_script or os.path.join(
        os.path.dirname(_SCRIPT_DIR), "ci-scripts", "run-claude.sh")
    cmd = ["bash", run_script, skill_args]

    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(args.log_dir, f"{epic_id}.log")

    print(f"--- Invoking codegen for {epic_id} ---")
    print(f"  Command: {' '.join(cmd)}")
    print(f"  Log: {log_path}")

    env = os.environ.copy()
    env["LOG_FILE"] = log_path

    try:
        result = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            timeout=args.timeout,
            env=env,
        )

        run_meta = os.path.join(
            args.output_dir, "codegen-runs", epic_id, "run-metadata.yaml")
        has_artifacts = os.path.exists(run_meta)

        if has_artifacts:
            status = _read_run_status(run_meta)
            if status == "completed":
                if result.returncode != 0:
                    print(f"  Note: exit code {result.returncode} but "
                          f"artifacts show completed — treating as success")
                print(f"  Result: SUCCESS")
                return True

        if result.returncode != 0:
            print(f"  Result: FAILED (exit code {result.returncode})",
                  file=sys.stderr)
            return False

        if not has_artifacts:
            print(f"  Result: FAILED (exit code 0 but no artifacts produced)",
                  file=sys.stderr)
            return False

        print(f"  Result: SUCCESS")
        return True
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
        elif status == "Review" and not args.dry_run:
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

        run_meta = os.path.join(
            args.output_dir, "codegen-runs", epic_id, "run-metadata.yaml")
        existing_status = _read_run_status(run_meta)
        if existing_status == "completed":
            print(f"  {epic_id}: REUSING existing completed run")
            results[PROCESSED].append((epic_id, "reused completed run"))
            epic_transitions = []
            ok, _ = transition_issue(
                server, user, token, epic_id, "Review")
            epic_transitions.append({
                "to": "Review", "success": ok})
            pr_url = read_pr_url(epic_id, args.output_dir)
            if pr_url:
                pr_urls[epic_id] = pr_url
                link_pr_to_jira(server, user, token, epic_id, pr_url)
            transitions_log[epic_id] = epic_transitions
            handled_keys.add(epic_id)
            continue

        print(f"  {epic_id}: ELIGIBLE — starting codegen")
        epic_transitions = []

        if not args.dry_run:
            setup_ok = setup_target_repo(
                all_epics_by_key[epic_id], args)
            if not setup_ok:
                results[FAILED].append(
                    (epic_id, "target repo setup failed"))
                handled_keys.add(epic_id)
                continue

        ok, _ = transition_issue(
            server, user, token, epic_id, "In Progress")
        epic_transitions.append({
            "to": "In Progress", "success": ok})

        original_status = all_epics_by_key[epic_id].get("jira_status", "")

        success = invoke_codegen(epic_id, args)
        if success:
            results[PROCESSED].append((epic_id, "codegen completed"))
            ok, _ = transition_issue(
                server, user, token, epic_id, "Review")
            epic_transitions.append({
                "to": "Review", "success": ok})

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


# ─── CI Mode: State Machine ─────────────────────────────────────────────────


def load_epic_state(data_repo, strategy_key, epic_id):
    """Read epic state from data repo's run-metadata.yaml.

    Returns:
        dict or None: parsed metadata, or None if no state file exists.
    """
    meta_path = os.path.join(data_repo, strategy_key, epic_id,
                             "run-metadata.yaml")
    if not os.path.isfile(meta_path):
        return None
    if yaml:
        with open(meta_path) as f:
            return yaml.safe_load(f) or {}
    return _read_metadata_simple(meta_path)


def _read_metadata_simple(path):
    """Fallback YAML reader for simple key: value files."""
    data = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ": " in line:
                key, val = line.split(": ", 1)
                val = val.strip().strip("'\"")
                if val.isdigit():
                    val = int(val)
                elif val in ("true", "True"):
                    val = True
                elif val in ("false", "False"):
                    val = False
                elif val in ("null", "None", "~"):
                    val = None
                data[key.strip()] = val
    return data


def save_epic_state(data_repo, strategy_key, epic_id, state):
    """Write epic state to data repo's run-metadata.yaml."""
    epic_dir = os.path.join(data_repo, strategy_key, epic_id)
    os.makedirs(epic_dir, exist_ok=True)
    meta_path = os.path.join(epic_dir, "run-metadata.yaml")

    state["epic_id"] = epic_id
    state["strategy_key"] = strategy_key

    if yaml:
        with open(meta_path, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False)
    else:
        with open(meta_path, "w") as f:
            for k, v in state.items():
                f.write(f"{k}: {v}\n")


def _copy_codegen_artifacts_to_data_repo(data_repo, strategy_key, epic_id,
                                         output_dir):
    """Copy codegen artifacts (specs, plans, diffs, reviews) to the data repo."""
    src = os.path.join(output_dir, "codegen-runs", epic_id)
    if not os.path.isdir(src):
        return
    dest = os.path.join(data_repo, strategy_key, epic_id)
    os.makedirs(dest, exist_ok=True)

    for name in ("codegen-spec.md", "codegen-plan.md",
                 "final-diff.patch", "best-diff.patch"):
        s = os.path.join(src, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dest, name))

    for entry in sorted(os.listdir(src)):
        v_src = os.path.join(src, entry)
        if os.path.isdir(v_src) and entry.startswith("v"):
            v_dest = os.path.join(dest, entry)
            os.makedirs(v_dest, exist_ok=True)
            for f in os.listdir(v_src):
                sf = os.path.join(v_src, f)
                if os.path.isfile(sf):
                    shutil.copy2(sf, os.path.join(v_dest, f))


def ci_process_epic(epic, state, args, server, user, token):
    """State machine: decide action based on epic's current CI state.

    Args:
        epic: epic data dict from Jira
        state: current state from data repo (or None for new epics)
        args: parsed CLI args
        server, user, token: Jira credentials

    Returns:
        tuple: (action, from_state, to_state, detail)
    """
    epic_id = epic["epic_id"]

    if state is None:
        state = _init_epic_state(epic)
        save_epic_state(args.data_repo, epic["strategy_key"], epic_id, state)

    current = state.get("status", "Pending")

    if current in CI_TERMINAL_STATES:
        return SKIPPED, current, current, f"Terminal state: {current}"

    if current == "Pending":
        return _ci_handle_pending(epic, state, args, server, user, token)
    elif current == "Ready":
        return _ci_handle_ready(epic, state, args, server, user, token)
    elif current == "Generating":
        return _ci_handle_ready(epic, state, args, server, user, token)
    elif current == "ReviewPending":
        return _ci_handle_review_pending(epic, state, args,
                                         server, user, token)
    elif current == "PRCreated":
        return _ci_handle_pr_created(epic, state, args, server, user, token)
    elif current == "PRChangesRequested":
        return _ci_handle_pr_changes(epic, state, args, server, user, token)
    elif current == "Blocked":
        return _ci_handle_blocked(epic, state, args, server, user, token)
    else:
        return SKIPPED, current, current, f"Unknown state: {current}"


def _init_epic_state(epic):
    """Create initial state for a new epic."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "epic_id": epic["epic_id"],
        "strategy_key": epic.get("strategy_key", ""),
        "status": "Pending",
        "target_repo": epic.get("target_repo", ""),
        "target_branch": "main",
        "current_version": 0,
        "max_iterations": 3,
        "timestamps": {"created": now},
    }


def _ci_handle_pending(epic, state, args, server, user, token):
    """Classify: check eligibility, move to Ready or Blocked."""
    epic_id = epic["epic_id"]
    deps = epic.get("dependencies") or []

    if deps:
        unmet = []
        for dep in deps:
            dep_state = load_epic_state(
                args.data_repo, epic["strategy_key"], dep)
            if not dep_state or dep_state.get("status") != "Done":
                unmet.append(dep)
        if unmet:
            state["status"] = "Blocked"
            state["blocked_by"] = unmet
            save_epic_state(
                args.data_repo, epic["strategy_key"], epic_id, state)
            return BLOCKED, "Pending", "Blocked", \
                f"Blocked by {', '.join(unmet)}"

    state["status"] = "Ready"
    save_epic_state(args.data_repo, epic["strategy_key"], epic_id, state)
    return PROCESSED, "Pending", "Ready", "Classified as ready"


def _ci_handle_ready(epic, state, args, server, user, token):
    """Run codegen for this epic."""
    epic_id = epic["epic_id"]

    if args.dry_run:
        return PROCESSED, "Ready", "Ready", "dry-run"

    setup_ok = setup_target_repo(epic, args)
    if not setup_ok:
        state["status"] = "Failed"
        state["failure_reason"] = "target repo setup failed"
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return FAILED, "Ready", "Failed", "target repo setup failed"

    transition_issue(server, user, token, epic_id, "In Progress")

    state["status"] = "Generating"
    state["current_version"] = state.get("current_version", 0) + 1
    state.setdefault("timestamps", {})["last_run"] = \
        datetime.now(timezone.utc).isoformat()
    save_epic_state(args.data_repo, epic["strategy_key"], epic_id, state)

    success = invoke_codegen(epic_id, args)
    _copy_codegen_artifacts_to_data_repo(
        args.data_repo, epic["strategy_key"], epic_id, args.output_dir)
    if success:
        state["status"] = "ReviewPending"
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return PROCESSED, "Ready", "ReviewPending", \
            f"Codegen v{state['current_version']} completed"
    else:
        state["status"] = "Failed"
        state["failure_reason"] = "codegen failed"
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return FAILED, "Ready", "Failed", "codegen failed"


def _ci_handle_review_pending(epic, state, args, server, user, token):
    """Score the review and decide: create PR or iterate."""
    epic_id = epic["epic_id"]
    version = state.get("current_version", 1)

    scores_path = os.path.join(
        args.output_dir, "codegen-runs", epic_id,
        f"v{version}", "scores.json")

    if not os.path.isfile(scores_path):
        return SKIPPED, "ReviewPending", "ReviewPending", \
            "Waiting for review scores"

    with open(scores_path) as f:
        scores = json.load(f)

    _copy_codegen_artifacts_to_data_repo(
        args.data_repo, epic["strategy_key"], epic_id, args.output_dir)

    state["scores"] = scores
    avg = scores.get("weighted_average", 0)
    dims = scores.get("dimensions", {})
    dims_ok = all(dims.get(d, {}).get("score", 0) >= 6.0
                  for d in ("architecture", "tests", "lint", "intent"))

    if avg >= 8.0 and dims_ok:
        pr_url = _create_pr_for_epic(epic, state, args)
        if pr_url:
            state["status"] = "PRCreated"
            state["pr_url"] = pr_url
            state["pr_state"] = "open"
            state.setdefault("timestamps", {})["pr_created"] = \
                datetime.now(timezone.utc).isoformat()
            save_epic_state(
                args.data_repo, epic["strategy_key"], epic_id, state)

            transition_issue(server, user, token, epic_id, "Review")
            link_pr_to_jira(server, user, token, epic_id, pr_url)
            return PROCESSED, "ReviewPending", "PRCreated", \
                f"PR created (avg={avg:.1f})"

        state["status"] = "Failed"
        state["failure_reason"] = "PR creation failed"
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return FAILED, "ReviewPending", "Failed", "PR creation failed"

    max_iter = state.get("max_iterations", 3)
    if version >= max_iter:
        state["status"] = "Failed"
        state["failure_reason"] = \
            f"Exhausted {max_iter} iterations (avg={avg:.1f})"
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return FAILED, "ReviewPending", "Failed", \
            f"Exhausted {max_iter} iterations"

    state["status"] = "Ready"
    save_epic_state(args.data_repo, epic["strategy_key"], epic_id, state)
    return PROCESSED, "ReviewPending", "Ready", \
        f"Score too low (avg={avg:.1f}), will retry v{version + 1}"


def _ci_handle_pr_created(epic, state, args, server, user, token):
    """Check PR status on GitHub."""
    epic_id = epic["epic_id"]
    pr_url = state.get("pr_url")
    if not pr_url:
        return SKIPPED, "PRCreated", "PRCreated", "No PR URL"

    try:
        from pr_lifecycle import get_pr_status, derive_pr_state
        gh_token = os.environ.get("EPIC_CODEGEN_GITHUB_TOKEN", "")
        if not gh_token:
            return SKIPPED, "PRCreated", "PRCreated", "No GitHub token"

        status = get_pr_status(pr_url, gh_token)
        new_state = derive_pr_state(status)

        if new_state == state.get("status"):
            return SKIPPED, "PRCreated", "PRCreated", "No status change"

        state["status"] = new_state
        state["pr_state"] = "merged" if status["merged"] else status["state"]
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)

        if new_state == "Done":
            transition_issue(server, user, token, epic_id, "Done")
            return PROCESSED, "PRCreated", "Done", "PR merged"
        elif new_state == "PRChangesRequested":
            return PROCESSED, "PRCreated", "PRChangesRequested", \
                "Review changes requested"
        elif new_state == "Ready":
            return PROCESSED, "PRCreated", "Ready", "PR closed, will retry"
        return SKIPPED, "PRCreated", new_state, f"State → {new_state}"

    except ImportError:
        merged = check_pr_merged(pr_url)
        if merged:
            state["status"] = "Done"
            state["pr_state"] = "merged"
            save_epic_state(
                args.data_repo, epic["strategy_key"], epic_id, state)
            transition_issue(server, user, token, epic_id, "Done")
            return PROCESSED, "PRCreated", "Done", "PR merged (gh fallback)"
        return SKIPPED, "PRCreated", "PRCreated", "PR still open"


def _ci_handle_pr_changes(epic, state, args, server, user, token):
    """Pull review comments and prepare the next iteration."""
    epic_id = epic["epic_id"]
    pr_url = state.get("pr_url")
    if not pr_url:
        return SKIPPED, "PRChangesRequested", "PRChangesRequested", \
            "No PR URL"

    max_iter = state.get("max_iterations", 3)
    version = state.get("current_version", 1)
    if version >= max_iter:
        state["status"] = "Failed"
        state["failure_reason"] = \
            f"Exhausted {max_iter} iterations with PR feedback"
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return FAILED, "PRChangesRequested", "Failed", \
            f"Exhausted {max_iter} iterations"

    try:
        from pr_lifecycle import get_pr_reviews, format_review_feedback
        gh_token = os.environ.get("EPIC_CODEGEN_GITHUB_TOKEN", "")
        if not gh_token:
            return SKIPPED, "PRChangesRequested", "PRChangesRequested", \
                "No GitHub token for review fetch"

        reviews_data = get_pr_reviews(pr_url, gh_token)
        feedback = format_review_feedback(reviews_data)

        next_version = version + 1
        revision_dir = os.path.join(
            args.output_dir, "codegen-runs", epic_id, f"v{next_version}")
        os.makedirs(revision_dir, exist_ok=True)
        with open(os.path.join(revision_dir, "revision-notes.md"), "w") as f:
            f.write(feedback)

        _copy_codegen_artifacts_to_data_repo(
            args.data_repo, epic["strategy_key"], epic_id, args.output_dir)

        state["status"] = "Ready"
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return PROCESSED, "PRChangesRequested", "Ready", \
            f"Review feedback saved, will retry v{next_version}"

    except ImportError:
        return SKIPPED, "PRChangesRequested", "PRChangesRequested", \
            "pr_lifecycle not available"


def _ci_handle_blocked(epic, state, args, server, user, token):
    """Check if blocking dependencies are now done."""
    epic_id = epic["epic_id"]
    blocked_by = state.get("blocked_by") or epic.get("dependencies") or []

    still_blocked = []
    for dep in blocked_by:
        dep_state = load_epic_state(
            args.data_repo, epic["strategy_key"], dep)
        if not dep_state or dep_state.get("status") != "Done":
            still_blocked.append(dep)

    if still_blocked:
        state["blocked_by"] = still_blocked
        save_epic_state(
            args.data_repo, epic["strategy_key"], epic_id, state)
        return BLOCKED, "Blocked", "Blocked", \
            f"Still blocked by {', '.join(still_blocked)}"

    state["status"] = "Ready"
    if "blocked_by" in state:
        del state["blocked_by"]
    save_epic_state(args.data_repo, epic["strategy_key"], epic_id, state)
    return PROCESSED, "Blocked", "Ready", "Dependencies resolved"


def _create_pr_for_epic(epic, state, args):
    """Create a PR from fork to upstream for the epic's changes.

    Returns:
        str or None: PR URL, or None on failure.
    """
    epic_id = epic["epic_id"]
    target_repo = epic.get("target_repo", "")
    if not target_repo:
        print(f"  {epic_id}: no target_repo, skipping PR creation",
              file=sys.stderr)
        return None

    pr_url = read_pr_url(epic_id, args.output_dir)
    if pr_url:
        return pr_url

    try:
        from create_pr import create_pr
        from push_to_fork import push_to_fork

        branch = f"epic/{epic_id}"
        push_ok = push_to_fork(TARGET_REPO_DIR, branch)
        if not push_ok:
            print(f"  {epic_id}: push to fork failed", file=sys.stderr)
            return None

        slug = target_repo.split("/")
        if len(slug) != 2:
            return None

        pr = create_pr(
            upstream=target_repo,
            fork_owner=args.fork_owner,
            branch=branch,
            title=f"{epic_id}: {epic.get('title', 'Code generation')}",
            body=f"Generated by epic-code-gen pipeline.\n\n"
                 f"Strategy: {epic.get('strategy_key', '')}\n"
                 f"Epic: {epic_id}",
        )
        return pr.get("html_url")
    except (ImportError, Exception) as e:
        print(f"  {epic_id}: PR creation error: {e}", file=sys.stderr)
        return None


def process_strategy_ci(strategy_key, server, user, token, args):
    """CI-mode: process one strategy with state machine convergence.

    Returns:
        tuple: (epics_list, results_dict, actions_log)
    """
    print(f"\n{'='*60}")
    print(f"Strategy: {strategy_key} (CI mode)")
    print(f"{'='*60}")

    print(f"Fetching children of {strategy_key}...")
    issues = fetch_children(server, user, token, strategy_key)
    if not issues:
        print(f"  No child work items found for {strategy_key}")
        return [], {PROCESSED: [], SKIPPED: [], BLOCKED: [], FAILED: []}, []

    print(f"  Found {len(issues)} child work items")

    dag = build_dependency_dag(issues)
    epics = [issue_to_epic_data(issue, strategy_key, dag) for issue in issues]

    mapping = load_repo_mapping()
    for epic in epics:
        repo = resolve_target_repo(epic, mapping)
        if repo:
            epic["target_repo"] = repo

    results = {PROCESSED: [], SKIPPED: [], BLOCKED: [], FAILED: []}
    actions_log = []

    for epic in epics:
        epic_id = epic["epic_id"]
        state = load_epic_state(args.data_repo, strategy_key, epic_id)

        action, from_state, to_state, detail = ci_process_epic(
            epic, state, args, server, user, token)

        results[action].append((epic_id, detail))
        print(f"  {epic_id}: {from_state} → {to_state} ({detail})")

        if from_state != to_state:
            actions_log.append({
                "epic": epic_id,
                "from": from_state,
                "to": to_state,
                "version": (state or {}).get("current_version"),
            })

    return epics, results, actions_log


# ─── CLI ─────────────────────────────────────────────────────────────────────


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
    parser.add_argument("--fork-owner", default="dora-the-ai-coder",
                        help="Pass --fork-owner to epic-codegen "
                             "(default: dora-the-ai-coder)")
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
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: use data repo for state persistence")
    parser.add_argument("--data-repo",
                        help="Path to cloned data repo (required with --ci)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    start_time = datetime.now(timezone.utc)

    for key in args.keys:
        if not re.match(r'^[A-Z][A-Z0-9]+-\d+$', key):
            print(f"Error: invalid key format: {key}", file=sys.stderr)
            sys.exit(1)

    if args.ci and not args.data_repo:
        print("Error: --data-repo is required with --ci", file=sys.stderr)
        sys.exit(1)

    server, user, token = require_env()
    if not all([server, user, token]):
        print("Error: JIRA_SERVER, JIRA_USER, JIRA_TOKEN must be set",
              file=sys.stderr)
        sys.exit(1)

    if not args.no_clean and not args.ci:
        clean_artifacts(args.output_dir)

    all_results = {}
    all_actions = {}

    for strategy_key in args.keys:
        if args.ci:
            epics, results, actions_log = process_strategy_ci(
                strategy_key, server, user, token, args)
            all_results[strategy_key] = (epics, results, {}, {})
            all_actions[strategy_key] = actions_log
        else:
            epics, results, transitions_log, pr_urls = process_strategy(
                strategy_key, server, user, token, args)
            all_results[strategy_key] = (
                epics, results, transitions_log, pr_urls)

            if not args.no_report and epics:
                codegen_runs_dir = os.path.join(
                    args.output_dir, "codegen-runs")
                report_path = generate_status_report(
                    epics, strategy_key, args.report_dir,
                    codegen_runs_dir=codegen_runs_dir, pr_urls=pr_urls)
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
