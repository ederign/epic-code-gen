#!/usr/bin/env python3
"""Fetch child work items from Jira and generate epic-task artifacts.

Given a parent strategy key (e.g., RHAISTRAT-1699), queries Jira for
child work items, builds a dependency DAG from "Blocks" issue links,
generates epic-task files using real Jira keys, and produces an HTML
status report.

Usage:
    # Fetch all children (fresh run: wipes artifacts first)
    python3 scripts/fetch_jira_epics.py RHAISTRAT-1699 --clean

    # Output as JSON (no files written)
    python3 scripts/fetch_jira_epics.py RHAISTRAT-1699 --json

    # Skip strategy fetch or report
    python3 scripts/fetch_jira_epics.py RHAISTRAT-1699 --no-strategy --no-report
"""

import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from artifact_utils import write_frontmatter
from fetch_epic import fetch_strategy
from jira_utils import adf_to_markdown, require_env, search_issues


_CHILD_FIELDS = [
    "summary", "description", "status", "priority",
    "issuelinks", "components",
]

DONE_STATUSES = {"Done", "Closed", "Resolved"}


def fetch_children(server, user, token, parent_key):
    """Fetch all child work items of a parent issue.

    Returns:
        list of Jira issue dicts.
    """
    jql = f"parent = {parent_key} ORDER BY key ASC"
    return search_issues(server, user, token, jql, fields=_CHILD_FIELDS)


def build_dependency_dag(issues):
    """Build dependency graph from Blocks issue links between siblings.

    For each issue, inspects issuelinks where type.name == "Blocks":
    - inwardIssue present → current issue is blocked by that issue
    - outwardIssue present → current issue blocks that issue

    Only tracks links between sibling issues (those in the input list).

    Returns:
        dict: {jira_key: {"dependencies": [...], "blocks": [...]}}
    """
    sibling_keys = {issue["key"] for issue in issues}
    dag = {issue["key"]: {"dependencies": [], "blocks": []} for issue in issues}

    for issue in issues:
        key = issue["key"]
        links = issue.get("fields", {}).get("issuelinks", [])
        for link in links:
            if link.get("type", {}).get("name") != "Blocks":
                continue

            inward = link.get("inwardIssue", {})
            outward = link.get("outwardIssue", {})

            if inward and inward.get("key") in sibling_keys:
                blocker_key = inward["key"]
                if blocker_key not in dag[key]["dependencies"]:
                    dag[key]["dependencies"].append(blocker_key)

            if outward and outward.get("key") in sibling_keys:
                blocked_key = outward["key"]
                if blocked_key not in dag[key]["blocks"]:
                    dag[key]["blocks"].append(blocked_key)

    return dag


def issue_to_epic_data(issue, parent_key, dag):
    """Convert a Jira issue to the epic-task data format.

    Returns:
        dict with keys matching the epic-task schema plus 'body'.
    """
    fields = issue.get("fields", {})
    key = issue["key"]
    deps = dag.get(key, {})

    description_adf = fields.get("description")
    body = adf_to_markdown(description_adf) if description_adf else ""

    components = [c.get("name", "") for c in fields.get("components", [])
                  if c.get("name")]

    dependencies = deps.get("dependencies", [])
    blocks = deps.get("blocks", [])

    return {
        "epic_id": key,
        "title": fields.get("summary", key),
        "strategy_key": parent_key,
        "target_repo": "",
        "target_branch": "main",
        "status": "Pending",
        "jira_status": fields.get("status", {}).get("name"),
        "components": components or None,
        "dependencies": sorted(dependencies) if dependencies else None,
        "blocks": sorted(blocks) if blocks else None,
        "body": body,
    }


def generate_epic_task_from_jira(epic_data, output_dir="artifacts/epic-tasks"):
    """Generate an epic-task markdown file from Jira issue data.

    Returns:
        Path to the generated file.
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{epic_data['epic_id']}.md")

    frontmatter = {k: v for k, v in epic_data.items() if k != "body"}
    write_frontmatter(path, frontmatter, "epic-task")

    body = epic_data.get("body", "")
    if body:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content + body)

    return path


def is_eligible(epic_data, all_epics_by_key):
    """Determine if an epic is eligible for codegen.

    Eligible means: not done AND all dependencies are done.

    Returns:
        (eligible: bool, reason: str)
    """
    jira_status = epic_data.get("jira_status", "")
    if jira_status in DONE_STATUSES:
        return False, "Already done"

    dependencies = epic_data.get("dependencies") or []
    unresolved = []
    for dep_key in dependencies:
        dep = all_epics_by_key.get(dep_key)
        if dep and dep.get("jira_status") not in DONE_STATUSES:
            unresolved.append(dep_key)

    if unresolved:
        return False, f"Blocked by {', '.join(unresolved)}"

    return True, "Ready"


def generate_status_report(epics, parent_key, output_dir="epic-reports"):
    """Generate an HTML status report for the fetched epics.

    Returns:
        Path to the generated report file.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    filename = f"{timestamp}-{parent_key}-status.html"
    path = os.path.join(output_dir, filename)

    epics_by_key = {e["epic_id"]: e for e in epics}

    status_counts = {}
    eligible_count = 0
    blocked_count = 0
    done_count = 0

    rows = []
    for epic in epics:
        jira_status = epic.get("jira_status", "Unknown")
        status_counts[jira_status] = status_counts.get(jira_status, 0) + 1

        eligible, reason = is_eligible(epic, epics_by_key)
        if eligible:
            eligible_count += 1
        elif jira_status in DONE_STATUSES:
            done_count += 1
        else:
            blocked_count += 1

        rows.append({
            "key": epic["epic_id"],
            "title": epic["title"],
            "jira_status": jira_status,
            "dependencies": epic.get("dependencies") or [],
            "blocks": epic.get("blocks") or [],
            "eligible": eligible,
            "reason": reason,
        })

    html_content = _render_report_html(
        parent_key, timestamp, rows, status_counts,
        len(epics), eligible_count, blocked_count, done_count,
        epics,
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return path


def _render_report_html(parent_key, timestamp, rows, status_counts,
                        total, eligible, blocked, done, epics):
    """Render the full HTML report string."""
    jira_base = os.environ.get("JIRA_SERVER", "https://redhat.atlassian.net")
    jira_base = jira_base.rstrip("/")

    # Summary cards
    status_cards = ""
    for status, count in sorted(status_counts.items()):
        status_cards += (
            f'<div class="stat-card">'
            f'<div class="stat-value">{count}</div>'
            f'<div class="stat-label">{_h(status)}</div></div>\n'
        )

    # Mermaid DAG (use underscores for node IDs — mermaid rejects hyphens)
    mermaid_lines = [
        "graph TD",
        "    classDef done fill:#198754,stroke:#198754,color:#fff",
        "    classDef blocked fill:#dc3545,stroke:#dc3545,color:#fff",
        "    classDef eligible fill:#0d6efd,stroke:#0d6efd,color:#fff",
    ]
    for epic in epics:
        key = epic["epic_id"]
        node_id = _mermaid_id(key)
        jira_status = epic.get("jira_status", "")
        if jira_status in DONE_STATUSES:
            style = "done"
        elif any(d for d in (epic.get("dependencies") or [])
                 if d in {e["epic_id"] for e in epics
                          if e.get("jira_status") not in DONE_STATUSES}):
            style = "blocked"
        else:
            style = "eligible"
        short = key.split("-")[-1]
        label = _truncate(epic["title"], 40).replace('"', "'")
        mermaid_lines.append(
            f'    {node_id}["{short}: {label}"]:::{style}')

    for epic in epics:
        for dep in epic.get("dependencies") or []:
            mermaid_lines.append(
                f"    {_mermaid_id(dep)} --> {_mermaid_id(epic['epic_id'])}")

    mermaid_text = "\n".join(mermaid_lines)

    # Table rows
    table_rows = ""
    for row in rows:
        deps_chips = " ".join(
            f'<a class="dep-chip" href="{jira_base}/browse/{_h(d)}">{_h(d)}</a>'
            for d in row["dependencies"]
        ) or "&mdash;"
        blocks_chips = " ".join(
            f'<a class="dep-chip" href="{jira_base}/browse/{_h(b)}">{_h(b)}</a>'
            for b in row["blocks"]
        ) or "&mdash;"

        if row["eligible"]:
            eligible_badge = '<span class="badge badge-high">Eligible</span>'
        elif row["jira_status"] in DONE_STATUSES:
            eligible_badge = '<span class="badge badge-impl">Done</span>'
        else:
            eligible_badge = (
                f'<span class="badge badge-low">Blocked</span>'
                f' <span class="reason">{_h(row["reason"])}</span>'
            )

        status_class = _status_badge_class(row["jira_status"])
        table_rows += f"""<tr>
  <td><a class="strat-link" href="{jira_base}/browse/{_h(row['key'])}">{_h(row['key'])}</a></td>
  <td>{_h(row['title'])}</td>
  <td><span class="badge {status_class}">{_h(row['jira_status'])}</span></td>
  <td><div class="deps-list">{deps_chips}</div></td>
  <td><div class="deps-list">{blocks_chips}</div></td>
  <td>{eligible_badge}</td>
</tr>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Strategy Status &mdash; {_h(parent_key)}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js"></script>
<style>
  :root {{
    --bg: #f8f9fa; --card-bg: #ffffff; --border: #dee2e6; --text: #212529;
    --muted: #6c757d; --accent: #0d6efd;
    --high: #198754; --medium: #fd7e14; --low: #dc3545;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.6;
         padding: 2rem; max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.75rem; margin-bottom: 0.25rem; }}
  h2 {{ font-size: 1.35rem; margin-bottom: 1rem; color: var(--text);
       border-bottom: 2px solid var(--accent); padding-bottom: 0.4rem; }}
  .subtitle {{ color: var(--muted); margin-bottom: 1.5rem; font-size: 0.95rem; }}
  .summary-row {{ display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }}
  .stat-card {{ background: var(--card-bg); border: 1px solid var(--border);
               border-radius: 8px; padding: 1rem 1.25rem; text-align: center; min-width: 120px; }}
  .stat-value {{ font-size: 1.75rem; font-weight: 700; }}
  .stat-label {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat-card.highlight {{ border-color: var(--accent); }}
  .card {{ background: var(--card-bg); border: 1px solid var(--border);
          border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
  .dag-container {{ text-align: center; padding: 1rem 0; margin-bottom: 1rem; }}
  .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
           font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }}
  .badge-high {{ background: var(--high); color: white; }}
  .badge-medium {{ background: var(--medium); color: white; }}
  .badge-low {{ background: var(--low); color: white; }}
  .badge-impl {{ background: #e9ecef; color: #495057; }}
  .badge-info {{ background: #cfe2ff; color: #084298; }}
  .badge-muted {{ background: #e9ecef; color: var(--muted); }}
  .deps-list {{ display: flex; gap: 0.4rem; flex-wrap: wrap; }}
  .dep-chip {{ font-family: 'SF Mono', SFMono-Regular, Consolas, monospace;
              font-size: 0.75rem; padding: 0.15rem 0.5rem; background: #e9ecef;
              border-radius: 4px; color: #495057; text-decoration: none; }}
  .dep-chip:hover {{ background: #dee2e6; }}
  .strat-link {{ color: var(--accent); text-decoration: none; font-weight: 600;
                font-family: 'SF Mono', SFMono-Regular, Consolas, monospace; font-size: 0.85rem; }}
  .strat-link:hover {{ text-decoration: underline; }}
  .summary-table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; font-size: 0.9rem; }}
  .summary-table th {{ background: #e9ecef; font-weight: 600; padding: 0.5rem 0.75rem;
                      text-align: left; border-bottom: 2px solid var(--border);
                      font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.03em; }}
  .summary-table td {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid #f1f3f5; }}
  .summary-table tr:hover {{ background: #f8f9fa; }}
  .reason {{ font-size: 0.75rem; color: var(--muted); }}
</style>
</head>
<body>

<h1>Strategy Status: <a class="strat-link" href="{jira_base}/browse/{_h(parent_key)}"
   style="font-size:inherit">{_h(parent_key)}</a></h1>
<p class="subtitle">Generated {_h(timestamp.replace('T', ' ').replace('Z', ' UTC'))}</p>

<div class="summary-row">
  <div class="stat-card"><div class="stat-value">{total}</div><div class="stat-label">Total</div></div>
  <div class="stat-card highlight"><div class="stat-value" style="color:var(--high)">{eligible}</div><div class="stat-label">Eligible</div></div>
  <div class="stat-card"><div class="stat-value" style="color:var(--low)">{blocked}</div><div class="stat-label">Blocked</div></div>
  <div class="stat-card"><div class="stat-value" style="color:var(--muted)">{done}</div><div class="stat-label">Done</div></div>
  {status_cards}
</div>

<div class="card">
  <h2>Dependency Graph</h2>
  <div class="dag-container">
    <pre class="mermaid">
{mermaid_text}
    </pre>
  </div>
</div>

<div class="card">
  <h2>Epic Tasks</h2>
  <table class="summary-table">
    <thead>
      <tr><th>Key</th><th>Title</th><th>Jira Status</th><th>Blocked By</th><th>Blocks</th><th>Eligibility</th></tr>
    </thead>
    <tbody>
{table_rows}
    </tbody>
  </table>
</div>

<script>
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'base',
    themeVariables: {{
      fontSize: '14px',
    }},
    flowchart: {{ curve: 'basis' }}
  }});
</script>
</body>
</html>
"""


def _mermaid_id(jira_key):
    """Convert a Jira key to a valid mermaid node ID."""
    return jira_key.replace("-", "_")


def _h(text):
    """HTML-escape a string."""
    return html.escape(str(text)) if text else ""


def _truncate(text, max_len):
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _status_badge_class(status):
    """Map Jira status to a badge CSS class."""
    if status in DONE_STATUSES:
        return "badge-impl"
    if status in ("In Progress", "In Review"):
        return "badge-info"
    if status in ("To Do", "New", "Open"):
        return "badge-muted"
    return "badge-muted"


def main():
    parser = argparse.ArgumentParser(
        description="Fetch child work items from Jira and generate "
                    "epic-task artifacts")
    parser.add_argument("key",
                        help="Parent strategy key (e.g., RHAISTRAT-1699)")
    parser.add_argument("--output-dir", default="artifacts/epic-tasks",
                        help="Output directory for epic-task files")
    parser.add_argument("--strategies-dir", default="artifacts/strategies",
                        help="Output directory for strategy files")
    parser.add_argument("--report-dir", default="epic-reports",
                        help="Output directory for HTML reports")
    parser.add_argument("--clean", action="store_true",
                        help="Wipe artifacts before fetching")
    parser.add_argument("--json", action="store_true",
                        help="Output parsed data as JSON (no files written)")
    parser.add_argument("--no-strategy", action="store_true",
                        help="Skip fetching strategy from Jira")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip generating HTML status report")
    args = parser.parse_args()

    if not re.match(r'^[A-Z][A-Z0-9]+-\d+$', args.key):
        print(f"Error: invalid key format: {args.key}", file=sys.stderr)
        sys.exit(1)

    server, user, token = require_env()
    if not all([server, user, token]):
        print("Error: JIRA_SERVER, JIRA_USER, JIRA_TOKEN must be set",
              file=sys.stderr)
        sys.exit(1)

    if args.clean:
        for d in [args.output_dir, args.strategies_dir]:
            if os.path.isdir(d):
                shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)

    print(f"Fetching children of {args.key}...", file=sys.stderr)
    issues = fetch_children(server, user, token, args.key)
    if not issues:
        print(f"No child work items found for {args.key}", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(issues)} child work items", file=sys.stderr)

    dag = build_dependency_dag(issues)
    epics = [issue_to_epic_data(issue, args.key, dag) for issue in issues]

    if args.json:
        json.dump(epics, sys.stdout, indent=2)
        print()
        return

    for epic in epics:
        path = generate_epic_task_from_jira(epic, args.output_dir)
        deps = epic.get("dependencies") or []
        blocks = epic.get("blocks") or []
        dep_str = f" (blocked by: {', '.join(deps)})" if deps else ""
        blk_str = f" (blocks: {', '.join(blocks)})" if blocks else ""
        print(f"  {epic['epic_id']}: {epic['title']}{dep_str}{blk_str}")

    if not args.no_strategy:
        strat_path = fetch_strategy(args.key, args.strategies_dir)
        if strat_path:
            print(f"Strategy: {strat_path}")

    if not args.no_report:
        report_path = generate_status_report(
            epics, args.key, args.report_dir)
        print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
