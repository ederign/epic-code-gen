#!/usr/bin/env python3
"""Check that an epic's dependencies are finished in Jira.

Usage:
    python3 scripts/check_dependencies.py <EPIC_ID> [--epic-tasks DIR] [--json]

Exit 0 when every dependency is done, 1 when any is not — including one whose
epic-task file is missing, since an unverifiable dependency is not a met one.

Reads `jira_status`, never `status`. Epic-task files are regenerated from Jira
on every run with `status: Pending` hardcoded (`fetch_jira_epics.py`), so that
field carries no information about whether the work finished. The gate this
replaced looked for `status=Validated`, which nothing in the repo writes.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from artifact_utils import read_frontmatter  # noqa: E402
from fetch_jira_epics import DONE_STATUSES  # noqa: E402

DEFAULT_EPIC_TASKS_DIR = "artifacts/epic-tasks"


def check_dependencies(epic_id, epic_tasks_dir=DEFAULT_EPIC_TASKS_DIR):
    """Resolve each dependency of epic_id to a done/not-done verdict.

    Returns:
        dict: {epic_id, dependencies: [{epic_id, jira_status, done, reason}],
               all_done}
    """
    path = os.path.join(epic_tasks_dir, f"{epic_id}.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Epic task not found: {path}")

    results = []
    for dep_id in read_frontmatter(path)[0].get("dependencies") or []:
        dep_path = os.path.join(epic_tasks_dir, f"{dep_id}.md")
        if not os.path.isfile(dep_path):
            results.append({
                "epic_id": dep_id,
                "jira_status": None,
                "done": False,
                "reason": f"no epic-task file at {dep_path}",
            })
            continue

        jira_status = read_frontmatter(dep_path)[0].get("jira_status")
        done = jira_status in DONE_STATUSES
        results.append({
            "epic_id": dep_id,
            "jira_status": jira_status,
            "done": done,
            "reason": "done in Jira" if done
                      else f"jira_status={jira_status!r}, "
                           f"not one of {sorted(DONE_STATUSES)}",
        })

    return {
        "epic_id": epic_id,
        "dependencies": results,
        "all_done": all(r["done"] for r in results),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check that an epic's dependencies are done in Jira")
    parser.add_argument("epic_id")
    parser.add_argument("--epic-tasks", default=DEFAULT_EPIC_TASKS_DIR,
                        help="Directory of epic-task files")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = check_dependencies(args.epic_id, args.epic_tasks)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    elif not result["dependencies"]:
        print(f"{args.epic_id}: no dependencies")
    else:
        for dep in result["dependencies"]:
            mark = "OK" if dep["done"] else "BLOCKED"
            print(f"  {mark}: {dep['epic_id']} — {dep['reason']}")

    if result["all_done"]:
        return 0

    blocked = ", ".join(d["epic_id"] for d in result["dependencies"]
                        if not d["done"])
    print(f"{args.epic_id} is blocked by: {blocked}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
