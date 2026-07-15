#!/usr/bin/env python3
"""Fetch epic data from an HTML report and generate epic-task files.

Takes a Jira key (e.g., RHAISTRAT-1665-E001) as parameter. Current
implementation parses the epic creator HTML report. Also fetches the
parent strategy document from Jira and saves it alongside the epic-task.

Usage:
    # Extract a single epic (also fetches strategy from Jira)
    python3 scripts/fetch_epic.py RHAISTRAT-2027-E001 --report <path>

    # Extract all epics from a strategy
    python3 scripts/fetch_epic.py RHAISTRAT-2027 --report <path> --all-epics

    # List available strategies in a report
    python3 scripts/fetch_epic.py --report <path> --list

    # Skip strategy fetch (offline mode)
    python3 scripts/fetch_epic.py RHAISTRAT-2027-E001 --report <path> --no-strategy

    # Output to specific directory
    python3 scripts/fetch_epic.py RHAISTRAT-2027-E001 --report <path> \\
        --output-dir artifacts/epic-tasks
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from artifact_utils import write_frontmatter
from jira_utils import require_env, get_issue, download_attachment, adf_to_markdown


def parse_report(html_content):
    """Parse the HTML report into structured data.

    Returns:
        dict mapping epic_id -> epic_data dict with keys:
            epic_id, strategy_key, priority, ai_score, epic_type,
            component, team, dependencies, signals, body
    """
    strategies = _parse_strategies(html_content)
    epics = _parse_epics(html_content, strategies)
    bodies = _parse_epic_bodies(html_content)

    for epic_id, epic in epics.items():
        if epic_id in bodies:
            epic["body"] = bodies[epic_id]

    return epics


def _parse_strategies(html_content):
    """Extract strategy sections and their metadata."""
    strategies = {}
    pattern = re.compile(
        r'<div\s+class="strat-section"\s+id="(RHAISTRAT-\d+)">')
    for match in pattern.finditer(html_content):
        strat_key = match.group(1)
        strategies[strat_key] = {"key": strat_key}

    # Extract DAG dependencies per strategy
    dag_pattern = re.compile(
        r'id="(RHAISTRAT-\d+)".*?'
        r'<pre class="mermaid">\s*graph TD\s*(.*?)</pre>',
        re.DOTALL,
    )
    for match in dag_pattern.finditer(html_content):
        strat_key = match.group(1)
        dag_text = match.group(2)
        deps = _parse_dag_dependencies(dag_text, strat_key)
        if strat_key in strategies:
            strategies[strat_key]["dag_deps"] = deps

    return strategies


def _parse_dag_dependencies(dag_text, strat_key):
    """Parse mermaid DAG text into dependency mapping.

    Returns:
        dict mapping epic_id -> list of dependency epic_ids
    """
    deps = {}
    edge_pattern = re.compile(r'(E\d+)\s*-->\s*(E\d+)')
    for match in edge_pattern.finditer(dag_text):
        source = f"{strat_key}-{match.group(1)}"
        target = f"{strat_key}-{match.group(2)}"
        if target not in deps:
            deps[target] = []
        deps[target].append(source)
    return deps


def _parse_epics(html_content, strategies):
    """Extract epic cards from HTML."""
    epics = {}

    card_pattern = re.compile(
        r'<div\s+class="card"\s+id="(RHAISTRAT-\d+-E\d+)">'
        r'(.*?)</div>\s*(?=<div\s+class="card"|</div>\s*</div>)',
        re.DOTALL,
    )

    for match in card_pattern.finditer(html_content):
        epic_id = match.group(1)
        card_html = match.group(2)
        strategy_key = re.match(r'(RHAISTRAT-\d+)', epic_id).group(1)

        epic = {
            "epic_id": epic_id,
            "strategy_key": strategy_key,
            "priority": _extract_priority(card_html),
            "ai_score": _extract_ai_score(card_html),
            "epic_type": _extract_epic_type(card_html),
            "component": _extract_meta_field(card_html, "Component"),
            "team": _extract_meta_field(card_html, "Team"),
            "dependencies": _extract_dependencies(card_html, strategy_key),
            "signals": _extract_signals(card_html),
            "body": "",
        }

        # Merge DAG dependencies
        strat = strategies.get(strategy_key, {})
        dag_deps = strat.get("dag_deps", {})
        if epic_id in dag_deps:
            existing = set(epic["dependencies"] or [])
            existing.update(dag_deps[epic_id])
            epic["dependencies"] = sorted(existing)

        epics[epic_id] = epic

    return epics


def _extract_priority(html):
    """Extract priority badge (P0, P1, P2)."""
    match = re.search(r'badge-p\d">(P\d)</span>', html)
    return match.group(1) if match else None


def _extract_ai_score(html):
    """Extract AI implementability score from badge text."""
    match = re.search(
        r'badge-(?:high|medium|low)">[^<]*\(([+-]?\d+)\)</span>', html)
    if match:
        return int(match.group(1))
    return None


def _extract_epic_type(html):
    """Extract epic type badge (Implementation, Investigation, etc.)."""
    match = re.search(
        r'badge-(?:impl|docs|investigation|triage)">'
        r'([^<]+)</span>', html)
    return match.group(1).strip() if match else None


def _extract_meta_field(html, label):
    """Extract a value from the meta-grid by label."""
    pattern = re.compile(
        rf'<span class="meta-label">{re.escape(label)}:</span>'
        rf'\s*<span class="meta-value">([^<]+)</span>',
    )
    match = pattern.search(html)
    return match.group(1).strip() if match else None


def _extract_dependencies(html, strategy_key):
    """Extract dependency links from the epic card."""
    deps = []
    dep_pattern = re.compile(r'class="dep-chip"[^>]*>(E\d+)</a>')
    for match in dep_pattern.finditer(html):
        dep_id = f"{strategy_key}-{match.group(1)}"
        if dep_id not in deps:
            deps.append(dep_id)
    return deps if deps else None


def _extract_signals(html):
    """Extract AI implementability signals."""
    signals = {}
    signal_pattern = re.compile(
        r'<span class="signal-name">(\w+)</span>\s*([+-]?\d+)')
    for match in signal_pattern.finditer(html):
        signals[match.group(1)] = int(match.group(2))
    return signals if signals else None


def _parse_epic_bodies(html_content):
    """Parse the epicBodies JavaScript object from the report.

    The object is a JS dict of epic_id -> template literal string.
    """
    bodies = {}

    bodies_match = re.search(
        r'const epicBodies\s*=\s*\{(.*?)^\};',
        html_content, re.DOTALL | re.MULTILINE,
    )
    if not bodies_match:
        return bodies

    bodies_text = bodies_match.group(1)

    entry_pattern = re.compile(
        r'"(RHAISTRAT-\d+-E\d+)":\s*`((?:[^`\\]|\\.)*)`,?',
        re.DOTALL,
    )

    for match in entry_pattern.finditer(bodies_text):
        epic_id = match.group(1)
        body = match.group(2)
        body = body.replace(r'\`', '`')
        body = body.replace(r'\$', '$')
        body = body.replace(r'\\', '\\')
        bodies[epic_id] = body.strip()

    return bodies


def _estimate_effort(signals, body):
    """Estimate effort size from signals and body length."""
    if not signals:
        return None

    total_score = sum(signals.values())
    body_len = len(body) if body else 0

    if total_score >= 5 and body_len < 3000:
        return "S"
    elif total_score >= 3 or body_len < 5000:
        return "M"
    elif total_score >= 0:
        return "L"
    else:
        return "XL"


def generate_epic_task(epic, output_dir="artifacts/epic-tasks"):
    """Generate an epic-task markdown file from parsed epic data.

    Args:
        epic: dict from parse_report
        output_dir: directory to write the file

    Returns:
        Path to the generated file.
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{epic['epic_id']}.md")

    frontmatter = {
        "epic_id": epic["epic_id"],
        "title": _extract_title(epic),
        "strategy_key": epic["strategy_key"],
        "target_repo": "",
        "target_branch": "",
        "status": "Pending",
    }

    if epic.get("component"):
        frontmatter["components"] = [epic["component"]]
    if epic.get("dependencies"):
        frontmatter["dependencies"] = epic["dependencies"]
    if epic.get("signals"):
        effort = _estimate_effort(epic["signals"], epic.get("body", ""))
        if effort:
            frontmatter["effort_size"] = effort

    write_frontmatter(path, frontmatter, "epic-task")

    body_parts = []
    if epic.get("body"):
        body_parts.append(epic["body"])

    if epic.get("signals"):
        body_parts.append("\n\n### AI Implementability Signals\n")
        total = sum(epic["signals"].values())
        body_parts.append(f"\n**Total Score:** {total}\n")
        body_parts.append(
            "| Signal | Score |")
        body_parts.append(
            "|--------|-------|")
        for signal, score in epic["signals"].items():
            prefix = "+" if score > 0 else ""
            body_parts.append(
                f"| {signal} | {prefix}{score} |")

    if epic.get("team"):
        body_parts.append(f"\n\n### Team\n\n{epic['team']}")

    if epic.get("priority"):
        body_parts.append(
            f"\n\n### Priority\n\n{epic['priority']}")

    if epic.get("epic_type"):
        body_parts.append(
            f"\n\n### Type\n\n{epic['epic_type']}")

    body = "\n".join(body_parts) + "\n"

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    with open(path, "w", encoding="utf-8") as f:
        f.write(content + body)

    return path


def _extract_title(epic):
    """Extract a clean title from the epic body or ID."""
    body = epic.get("body", "")
    if body:
        title_match = re.match(r'^##\s+(.+)', body)
        if title_match:
            return title_match.group(1).strip()

    return epic["epic_id"]


def fetch_strategy(strategy_key, output_dir="artifacts/strategies"):
    """Fetch a strategy document from Jira and save as markdown.

    Args:
        strategy_key: e.g., RHAISTRAT-1749
        output_dir: directory to write the file

    Returns:
        Path to the generated file, or None if Jira creds not set.
    """
    server, user, token = require_env()
    if not all([server, user, token]):
        print(f"Warning: JIRA_SERVER/JIRA_USER/JIRA_TOKEN not set, "
              f"skipping strategy fetch for {strategy_key}", file=sys.stderr)
        return None

    issue = get_issue(server, user, token, strategy_key,
                      fields=["summary", "description", "attachment"])

    summary = issue["fields"]["summary"]
    description_adf = issue["fields"].get("description")

    if not description_adf:
        print(f"Warning: no description found for {strategy_key}",
              file=sys.stderr)
        return None

    markdown = adf_to_markdown(description_adf)

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{strategy_key}.md")

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {summary}\n\n")
        f.write(markdown)

    # Download UX prototype attachments (HTML files) if UXD marker present
    _download_prototype_attachments(
        server, user, token, strategy_key, markdown,
        issue["fields"].get("attachment", []), output_dir,
    )

    return path


def _download_prototype_attachments(server, user, token, strategy_key,
                                    strategy_text, attachments, output_dir):
    """Download HTML prototype attachments when UXD support is required.

    Only downloads if the strategy body contains a UXD marker referencing
    an HTML filename, AND that filename is found among the issue attachments.
    """
    if not attachments:
        return

    # Check for UXD marker in strategy text
    uxd_required = bool(re.search(
        r'UXD\s+Support\s*[:\-|]?\s*(?:is\s+)?(Required|Yes)',
        strategy_text, re.IGNORECASE,
    ))
    if not uxd_required:
        return

    # Find referenced HTML filename in strategy text
    html_ref = re.search(
        r'(?:file|attached|prototype)[:\s]+\S*?([a-zA-Z0-9_-]+\.html?)\b',
        strategy_text, re.IGNORECASE,
    )

    proto_dir = os.path.join(output_dir, "prototypes", strategy_key)

    if html_ref:
        target_name = html_ref.group(1)
        matching = [a for a in attachments
                    if a.get("filename", "").lower() == target_name.lower()]
        if matching:
            os.makedirs(proto_dir, exist_ok=True)
            dest = os.path.join(proto_dir, matching[0]["filename"])
            if not os.path.exists(dest):
                print(f"  Downloading prototype: {matching[0]['filename']}")
                download_attachment(
                    server, user, token,
                    matching[0]["content"], dest,
                )
            return

    # Fallback: download any HTML attachments if UXD is required
    html_attachments = [a for a in attachments
                        if a.get("filename", "").lower().endswith((".html", ".htm"))]
    if html_attachments:
        os.makedirs(proto_dir, exist_ok=True)
        for att in html_attachments:
            dest = os.path.join(proto_dir, att["filename"])
            if not os.path.exists(dest):
                print(f"  Downloading prototype: {att['filename']}")
                download_attachment(
                    server, user, token, att["content"], dest,
                )
    elif uxd_required:
        print(f"Warning: UXD Support marked Required for {strategy_key} "
              f"but no HTML prototype attachment found", file=sys.stderr)


def list_strategies(html_content):
    """List all strategies in the report with their epic counts.

    Returns:
        list of dicts with keys: key, epic_count
    """
    results = []
    epics = parse_report(html_content)

    strat_counts = {}
    for epic_id, epic in epics.items():
        strat = epic["strategy_key"]
        if strat not in strat_counts:
            strat_counts[strat] = 0
        strat_counts[strat] += 1

    for strat, count in sorted(strat_counts.items()):
        results.append({"key": strat, "epic_count": count})

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Fetch epic data from HTML report")
    parser.add_argument("key", nargs="?",
                        help="Epic ID (RHAISTRAT-NNNN-ENNN) or "
                             "strategy key (RHAISTRAT-NNNN)")
    parser.add_argument("--report", required=True,
                        help="Path to the HTML report file")
    parser.add_argument("--output-dir", default="artifacts/epic-tasks",
                        help="Output directory for epic-task files")
    parser.add_argument("--all-epics", action="store_true",
                        help="Extract all epics from the strategy")
    parser.add_argument("--list", action="store_true",
                        help="List available strategies in the report")
    parser.add_argument("--json", action="store_true",
                        help="Output parsed data as JSON (no files written)")
    parser.add_argument("--no-strategy", action="store_true",
                        help="Skip fetching strategy from Jira")
    parser.add_argument("--strategies-dir", default="artifacts/strategies",
                        help="Output directory for strategy files")
    args = parser.parse_args()

    if not os.path.isfile(args.report):
        print(f"Error: report not found: {args.report}", file=sys.stderr)
        sys.exit(1)

    with open(args.report, encoding="utf-8") as f:
        html_content = f.read()

    if args.list:
        strategies = list_strategies(html_content)
        for s in strategies:
            print(f"{s['key']}  ({s['epic_count']} epics)")
        return

    if not args.key:
        print("Error: provide an epic ID or strategy key", file=sys.stderr)
        sys.exit(1)

    epics = parse_report(html_content)

    if re.match(r'^RHAISTRAT-\d+-E\d+$', args.key):
        # Single epic
        if args.key not in epics:
            print(f"Error: epic {args.key} not found in report",
                  file=sys.stderr)
            sys.exit(1)

        epic = epics[args.key]
        if args.json:
            json.dump(epic, sys.stdout, indent=2)
            print()
        else:
            path = generate_epic_task(epic, args.output_dir)
            print(f"Generated: {path}")
            if not args.no_strategy:
                strat_path = fetch_strategy(epic["strategy_key"],
                                            args.strategies_dir)
                if strat_path:
                    print(f"Strategy: {strat_path}")

    elif re.match(r'^RHAISTRAT-\d+$', args.key):
        # All epics from a strategy
        matching = {k: v for k, v in epics.items()
                    if v["strategy_key"] == args.key}
        if not matching:
            print(f"Error: no epics found for {args.key}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            json.dump(matching, sys.stdout, indent=2)
            print()
        else:
            for epic_id in sorted(matching):
                path = generate_epic_task(matching[epic_id], args.output_dir)
                print(f"Generated: {path}")
            if not args.no_strategy:
                strat_path = fetch_strategy(args.key, args.strategies_dir)
                if strat_path:
                    print(f"Strategy: {strat_path}")
    else:
        print(f"Error: invalid key format: {args.key}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
