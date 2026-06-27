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


def generate_status_report(epics, parent_key, output_dir="epic-reports",
                           codegen_runs_dir=None, pr_urls=None):
    """Generate an HTML status report for the fetched epics.

    Returns:
        Path to the generated report file.
    """
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    filename = f"{timestamp}-{parent_key}-status.html"
    path = os.path.join(output_dir, filename)

    epics_by_key = {e["epic_id"]: e for e in epics}
    pr_urls = pr_urls or {}

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
        epics, codegen_runs_dir, pr_urls,
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return path


def _render_report_html(parent_key, timestamp, rows, status_counts,
                        total, eligible, blocked, done, epics,
                        codegen_runs_dir=None, pr_urls=None):
    """Render the full HTML report string."""
    jira_base = os.environ.get("JIRA_SERVER", "https://redhat.atlassian.net")
    jira_base = jira_base.rstrip("/")
    pr_urls = pr_urls or {}

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

    # Table rows with detail panels
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

        artifacts = _load_epic_artifacts(row["key"], codegen_runs_dir)
        has_detail = artifacts is not None
        cursor = ' class="clickable-row"' if has_detail else ""
        expand = (' <span class="expand-icon">&#9654;</span>'
                  if has_detail else "")

        status_class = _status_badge_class(row["jira_status"])
        table_rows += f"""<tr{cursor} onclick="toggleDetail(this)">
  <td><a class="strat-link" href="{jira_base}/browse/{_h(row['key'])}">{_h(row['key'])}</a>{expand}</td>
  <td>{_h(row['title'])}</td>
  <td><span class="badge {status_class}">{_h(row['jira_status'])}</span></td>
  <td><div class="deps-list">{deps_chips}</div></td>
  <td><div class="deps-list">{blocks_chips}</div></td>
  <td>{eligible_badge}</td>
</tr>
"""
        table_rows += _render_epic_detail(
            row["key"], artifacts, pr_urls.get(row["key"]))

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

  /* Detail panels */
  .clickable-row {{ cursor: pointer; }}
  .clickable-row:hover {{ background: #e8f0fe !important; }}
  .expand-icon {{ font-size: 0.7rem; color: var(--muted); margin-left: 0.3rem; }}
  .detail-row td {{ padding: 0 !important; border: none !important; }}
  .detail-panel {{ background: #f8f9fb; border: 1px solid var(--border);
                  border-radius: 0 0 8px 8px; padding: 1.25rem; margin: 0 0.5rem 0.75rem; }}
  .detail-header {{ display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;
                   margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border); }}
  .detail-score {{ font-size: 1.5rem; font-weight: 700; }}
  .detail-meta {{ font-size: 0.85rem; color: var(--muted); }}
  .pr-link {{ color: var(--accent); font-weight: 600; text-decoration: none;
             padding: 0.2rem 0.6rem; border: 1px solid var(--accent); border-radius: 4px; }}
  .pr-link:hover {{ background: var(--accent); color: white; }}
  .muted {{ color: var(--muted); font-style: italic; }}

  /* CSS-only tabs */
  .tabs {{ position: relative; }}
  .tabs input[type="radio"] {{ display: none; }}
  .tabs label {{ display: inline-block; padding: 0.4rem 1rem; cursor: pointer;
                font-size: 0.85rem; font-weight: 600; color: var(--muted);
                border-bottom: 2px solid transparent; margin-bottom: -1px; }}
  .tabs input:checked + label {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .tab-panel {{ display: none; padding: 1rem 0; }}
  .tabs input:nth-of-type(1):checked ~ .tab-panel:nth-of-type(1),
  .tabs input:nth-of-type(2):checked ~ .tab-panel:nth-of-type(2),
  .tabs input:nth-of-type(3):checked ~ .tab-panel:nth-of-type(3),
  .tabs input:nth-of-type(4):checked ~ .tab-panel:nth-of-type(4),
  .tabs input:nth-of-type(5):checked ~ .tab-panel:nth-of-type(5) {{ display: block; }}

  /* Score bars */
  .score-row {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }}
  .score-dim {{ width: 90px; font-size: 0.8rem; font-weight: 600; text-transform: capitalize; }}
  .score-weight {{ width: 35px; font-size: 0.75rem; color: var(--muted); text-align: right; }}
  .score-track {{ flex: 1; height: 18px; background: #e9ecef; border-radius: 4px; overflow: hidden; }}
  .score-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
  .score-val {{ width: 45px; font-size: 0.8rem; font-weight: 600; text-align: right; }}

  /* Plan tasks */
  .task-block {{ margin-bottom: 0.5rem; }}
  .task-block summary {{ cursor: pointer; padding: 0.4rem; border-radius: 4px; }}
  .task-block summary:hover {{ background: #e9ecef; }}
  .task-files {{ margin-left: 0.5rem; }}
  .file-path {{ font-size: 0.75rem; background: #e9ecef; padding: 0.1rem 0.4rem; border-radius: 3px; }}
  .task-steps {{ padding: 0.5rem 0 0.5rem 1.5rem; }}
  .step-item {{ display: flex; gap: 0.4rem; font-size: 0.85rem; line-height: 1.8; }}
  .step-check {{ font-size: 1rem; }}

  /* Diff */
  .diff-file {{ margin-bottom: 0.5rem; }}
  .diff-file summary {{ cursor: pointer; padding: 0.3rem 0.5rem; border-radius: 4px;
                        font-size: 0.85rem; }}
  .diff-file summary:hover {{ background: #e9ecef; }}
  .diff-stat-add {{ color: var(--high); font-weight: 600; margin-left: 0.5rem; font-size: 0.8rem; }}
  .diff-stat-del {{ color: var(--low); font-weight: 600; margin-left: 0.3rem; font-size: 0.8rem; }}
  .diff-content {{ font-size: 0.78rem; line-height: 1.5; overflow-x: auto;
                  max-height: 500px; overflow-y: auto; padding: 0.5rem;
                  background: white; border: 1px solid var(--border); border-radius: 4px; }}
  .diff-add {{ color: #1a7f37; background: #dafbe1; }}
  .diff-del {{ color: #cf222e; background: #ffebe9; }}
  .diff-hunk {{ color: #8250df; background: #f5f0ff; font-weight: 600; }}

  /* Reviews */
  .review-block {{ margin-bottom: 0.5rem; }}
  .review-block summary {{ cursor: pointer; padding: 0.4rem; border-radius: 4px; }}
  .review-block summary:hover {{ background: #e9ecef; }}
  .review-body {{ padding: 0.5rem 1rem; font-size: 0.85rem; }}
  .review-body h4,.review-body h5,.review-body h6 {{ margin: 0.75rem 0 0.25rem; }}
  .review-body p {{ margin-bottom: 0.4rem; }}
  .review-body li {{ margin-left: 1.5rem; margin-bottom: 0.2rem; }}

  /* Validation */
  .val-check {{ margin-bottom: 0.5rem; }}
  .val-check summary {{ cursor: pointer; padding: 0.3rem 0.5rem; border-radius: 4px; }}
  .val-check summary:hover {{ background: #e9ecef; }}
  .val-output {{ font-size: 0.75rem; max-height: 300px; overflow: auto;
                background: #1e1e1e; color: #d4d4d4; padding: 0.75rem;
                border-radius: 4px; white-space: pre-wrap; word-break: break-all; }}
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
    themeVariables: {{ fontSize: '14px' }},
    flowchart: {{ curve: 'basis' }}
  }});
  function toggleDetail(row) {{
    if (event.target.closest('a')) return;
    var detail = row.nextElementSibling;
    if (detail && detail.classList.contains('detail-row')) {{
      var icon = row.querySelector('.expand-icon');
      if (detail.style.display === 'none') {{
        detail.style.display = '';
        if (icon) icon.innerHTML = '&#9660;';
      }} else {{
        detail.style.display = 'none';
        if (icon) icon.innerHTML = '&#9654;';
      }}
    }}
  }}
</script>
</body>
</html>
"""


def _load_epic_artifacts(epic_id, codegen_runs_dir):
    """Load codegen artifacts for an epic if they exist.

    Returns dict with available data (all keys optional):
        metadata, scores, plan_md, reviews (dict), diff, validation, pr_url
    """
    if not codegen_runs_dir:
        return None
    epic_dir = os.path.join(codegen_runs_dir, epic_id)
    if not os.path.isdir(epic_dir):
        return None

    result = {}

    meta_path = os.path.join(epic_dir, "run-metadata.yaml")
    if os.path.isfile(meta_path):
        result["metadata"] = _parse_simple_yaml(meta_path)

    plan_path = os.path.join(epic_dir, "codegen-plan.md")
    if os.path.isfile(plan_path):
        with open(plan_path, "r", encoding="utf-8") as f:
            result["plan_md"] = f.read()

    diff_path = os.path.join(epic_dir, "final-diff.patch")
    if not os.path.isfile(diff_path):
        diff_path = os.path.join(epic_dir, "v1", "diff.patch")
    if os.path.isfile(diff_path):
        with open(diff_path, "r", encoding="utf-8") as f:
            result["diff"] = f.read()

    versions = sorted(
        d for d in os.listdir(epic_dir)
        if d.startswith("v") and os.path.isdir(os.path.join(epic_dir, d)))
    if versions:
        latest_v = os.path.join(epic_dir, versions[-1])
        scores_path = os.path.join(latest_v, "scores.json")
        if os.path.isfile(scores_path):
            with open(scores_path, "r", encoding="utf-8") as f:
                result["scores"] = json.load(f)

        reviews = {}
        for fname in os.listdir(latest_v):
            if fname.startswith("review-") and fname.endswith(".md"):
                dim = fname[7:-3]
                with open(os.path.join(latest_v, fname),
                          "r", encoding="utf-8") as f:
                    reviews[dim] = f.read()
        if reviews:
            result["reviews"] = reviews

        val_path = os.path.join(latest_v, "validation.json")
        if os.path.isfile(val_path):
            with open(val_path, "r", encoding="utf-8") as f:
                result["validation"] = json.load(f)

    return result if result else None


def _parse_simple_yaml(path):
    """Parse a simple flat YAML file (no nested structures beyond one level)."""
    data = {}
    current_key = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("  ") and current_key:
                sub_key, _, sub_val = line.strip().partition(":")
                sub_val = sub_val.strip().strip('"')
                if current_key not in data or not isinstance(
                        data[current_key], dict):
                    data[current_key] = {}
                try:
                    sub_val = float(sub_val)
                    if sub_val == int(sub_val):
                        sub_val = int(sub_val)
                except (ValueError, TypeError):
                    pass
                data[current_key][sub_key] = sub_val
            else:
                key, _, val = line.partition(":")
                val = val.strip().strip('"')
                if val == "":
                    current_key = key
                    continue
                current_key = None
                try:
                    val = float(val)
                    if val == int(val):
                        val = int(val)
                except (ValueError, TypeError):
                    pass
                data[key] = val
    return data


def _render_score_bars(scores):
    """Render score dimension bars as HTML."""
    if not scores or "dimensions" not in scores:
        return ""
    dims = scores["dimensions"]
    bars = ""
    for dim in ["architecture", "tests", "lint", "intent"]:
        d = dims.get(dim, {})
        score = d.get("score", 0)
        weight = d.get("weight", 0)
        pct = score * 10
        color = "#198754" if score >= 8 else "#fd7e14" if score >= 6 else "#dc3545"
        bars += (
            f'<div class="score-row">'
            f'<span class="score-dim">{_h(dim)}</span>'
            f'<span class="score-weight">{int(weight*100)}%</span>'
            f'<div class="score-track">'
            f'<div class="score-fill" style="width:{pct}%;background:{color}"></div>'
            f'</div>'
            f'<span class="score-val">{score:.0f}/10</span>'
            f'</div>\n'
        )
    return bars


def _render_plan_html(plan_md):
    """Parse codegen plan markdown into an HTML task list."""
    if not plan_md:
        return '<p class="muted">No plan available</p>'
    tasks = []
    current_task = None
    for line in plan_md.split("\n"):
        if line.startswith("### Task "):
            if current_task:
                tasks.append(current_task)
            current_task = {"title": line[4:].strip(), "steps": [], "files": []}
        elif current_task and line.startswith("- [ ] "):
            current_task["steps"].append(("pending", line[6:].strip()))
        elif current_task and line.startswith("- [x] "):
            current_task["steps"].append(("done", line[6:].strip()))
        elif (current_task and line.startswith("- ")
              and any(k in line.lower() for k in
                      ["create:", "modify:", "test:"])):
            current_task["files"].append(line[2:].strip())
    if current_task:
        tasks.append(current_task)

    if not tasks:
        return '<p class="muted">No tasks found in plan</p>'

    out = ""
    for t in tasks:
        files_html = "".join(
            f'<code class="file-path">{_h(f)}</code> '
            for f in t["files"])
        steps_html = ""
        for status, text in t["steps"]:
            icon = "&#9745;" if status == "done" else "&#9744;"
            steps_html += (
                f'<div class="step-item">'
                f'<span class="step-check">{icon}</span>'
                f'<span>{_h(text)}</span></div>\n')
        out += (
            f'<details class="task-block">'
            f'<summary><strong>{_h(t["title"])}</strong>'
            f'<span class="task-files">{files_html}</span></summary>'
            f'<div class="task-steps">{steps_html}</div>'
            f'</details>\n')
    return out


def _render_diff_html(diff_text):
    """Render unified diff with per-file collapsible sections."""
    if not diff_text:
        return '<p class="muted">No diff available</p>'
    files = []
    current = None
    for line in diff_text.split("\n"):
        if line.startswith("diff --git"):
            if current:
                files.append(current)
            parts = line.split(" b/")
            fname = parts[-1] if len(parts) > 1 else line
            current = {"name": fname, "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current:
        files.append(current)

    if not files:
        return '<p class="muted">Empty diff</p>'

    out = ""
    for f in files:
        adds = sum(1 for l in f["lines"] if l.startswith("+")
                   and not l.startswith("+++"))
        dels = sum(1 for l in f["lines"] if l.startswith("-")
                   and not l.startswith("---"))
        stat = (f'<span class="diff-stat-add">+{adds}</span>'
                f'<span class="diff-stat-del">-{dels}</span>')
        lines_html = ""
        for line in f["lines"]:
            cls = ""
            if line.startswith("+") and not line.startswith("+++"):
                cls = "diff-add"
            elif line.startswith("-") and not line.startswith("---"):
                cls = "diff-del"
            elif line.startswith("@@"):
                cls = "diff-hunk"
            lines_html += f'<div class="{cls}">{_h(line)}</div>'
        out += (
            f'<details class="diff-file">'
            f'<summary><code>{_h(f["name"])}</code> {stat}</summary>'
            f'<pre class="diff-content">{lines_html}</pre>'
            f'</details>\n')
    return out


def _render_reviews_html(reviews, scores):
    """Render review sections with scores."""
    if not reviews:
        return '<p class="muted">No reviews available</p>'
    out = ""
    for dim in ["architecture", "tests", "lint", "intent"]:
        content = reviews.get(dim)
        if not content:
            continue
        score = ""
        if scores and "dimensions" in scores:
            s = scores["dimensions"].get(dim, {}).get("score", "?")
            score = f' <span class="badge badge-high">{s}/10</span>'

        body = content.split("---")[-1] if "---" in content else content
        body_html = ""
        for line in body.split("\n"):
            if line.startswith("# "):
                body_html += f"<h4>{_h(line[2:])}</h4>\n"
            elif line.startswith("## "):
                body_html += f"<h5>{_h(line[3:])}</h5>\n"
            elif line.startswith("### "):
                body_html += f"<h6>{_h(line[4:])}</h6>\n"
            elif line.startswith("- "):
                body_html += f"<li>{_h(line[2:])}</li>\n"
            elif line.startswith("```"):
                continue
            elif line.strip():
                body_html += f"<p>{_h(line)}</p>\n"

        out += (
            f'<details class="review-block">'
            f'<summary><strong>{_h(dim.title())}</strong>{score}</summary>'
            f'<div class="review-body">{body_html}</div>'
            f'</details>\n')
    return out


def _render_validation_html(validation):
    """Render validation check results."""
    if not validation:
        return '<p class="muted">No validation data</p>'
    lang = validation.get("language", "unknown")
    checks = validation.get("checks", [])
    out = f'<p><strong>Language:</strong> {_h(lang)}</p>'
    for check in checks:
        name = check.get("name", check.get("command", "?"))
        passed = check.get("passed", False)
        badge_cls = "badge-high" if passed else "badge-low"
        label = "PASS" if passed else "FAIL"
        output = check.get("output", "")
        if len(output) > 2000:
            output = output[:2000] + "\n... (truncated)"
        out += (
            f'<details class="val-check">'
            f'<summary><code>{_h(name)}</code> '
            f'<span class="badge {badge_cls}">{label}</span></summary>'
            f'<pre class="val-output">{_h(output)}</pre>'
            f'</details>\n')
    return out


def _render_epic_detail(epic_id, artifacts, pr_url=None):
    """Render the full detail panel for an epic."""
    if not artifacts:
        return (
            '<tr class="detail-row" style="display:none">'
            '<td colspan="6"><div class="detail-panel">'
            '<p class="muted">No codegen run data available</p>'
            '</div></td></tr>')

    meta = artifacts.get("metadata", {})
    scores = artifacts.get("scores")
    status = meta.get("status", "unknown")
    final_score = meta.get("final_score", "—")
    lang = meta.get("language", "—")
    versions = meta.get("versions", "—")
    started = meta.get("started_at", "")
    completed = meta.get("completed_at", "")
    verdict = scores.get("verdict", "—") if scores else "—"

    duration = ""
    if started and completed:
        try:
            from datetime import datetime as _dt
            t0 = _dt.fromisoformat(started.replace("Z", "+00:00"))
            t1 = _dt.fromisoformat(completed.replace("Z", "+00:00"))
            mins = int((t1 - t0).total_seconds() / 60)
            duration = f"{mins}m"
        except Exception:
            pass

    status_cls = ("badge-high" if status == "completed"
                  else "badge-low" if status in ("failed", "error")
                  else "badge-medium")
    verdict_cls = ("badge-high" if verdict == "pass"
                   else "badge-low" if verdict == "fail"
                   else "badge-medium")

    header = (
        f'<div class="detail-header">'
        f'<span class="badge {status_cls}">{_h(status)}</span> '
        f'<span class="detail-score">{final_score}/10</span> '
        f'<span class="badge {verdict_cls}">{_h(verdict)}</span> '
        f'<span class="detail-meta">{_h(lang)} &bull; '
        f'v{versions} &bull; {duration}</span>')
    if pr_url:
        header += (f' <a href="{_h(pr_url)}" class="pr-link" '
                   f'target="_blank">View PR</a>')
    header += '</div>'

    uid = epic_id.replace("-", "_")
    score_bars = _render_score_bars(scores)
    plan_html = _render_plan_html(artifacts.get("plan_md"))
    reviews_html = _render_reviews_html(
        artifacts.get("reviews"), scores)
    diff_html = _render_diff_html(artifacts.get("diff"))
    val_html = _render_validation_html(artifacts.get("validation"))

    tabs = f"""
<div class="tabs">
  <input type="radio" name="tab_{uid}" id="tab_{uid}_overview" checked>
  <label for="tab_{uid}_overview">Overview</label>
  <input type="radio" name="tab_{uid}" id="tab_{uid}_plan">
  <label for="tab_{uid}_plan">Plan</label>
  <input type="radio" name="tab_{uid}" id="tab_{uid}_reviews">
  <label for="tab_{uid}_reviews">Reviews</label>
  <input type="radio" name="tab_{uid}" id="tab_{uid}_diff">
  <label for="tab_{uid}_diff">Diff</label>
  <input type="radio" name="tab_{uid}" id="tab_{uid}_validation">
  <label for="tab_{uid}_validation">Validation</label>

  <div class="tab-panel">{score_bars}</div>
  <div class="tab-panel">{plan_html}</div>
  <div class="tab-panel">{reviews_html}</div>
  <div class="tab-panel">{diff_html}</div>
  <div class="tab-panel">{val_html}</div>
</div>"""

    return (
        f'<tr class="detail-row" style="display:none">'
        f'<td colspan="6"><div class="detail-panel">'
        f'{header}{tabs}'
        f'</div></td></tr>')


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
