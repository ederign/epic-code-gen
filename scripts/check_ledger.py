#!/usr/bin/env python3
"""Validate the work ledger under docs/ and enforce the PR companion rule.

Two modes:

    check_ledger.py --all
        Validate every ledger file: frontmatter parses, `status` agrees with the
        directory the file sits in, done/fixed files carry evidence, ids match
        filenames, and cross-references resolve. Exits 1 on any error.

    check_ledger.py --diff <base>..<head> [--body FILE]
        The PR companion check. If the diff touches code but no ledger file,
        report it. Advisory by default (exit 0); --strict makes it exit 1.
        Honours `Ledger: none — <reason>` in the PR body.

See AGENTS.md for the rule this enforces. Frontmatter is read with
artifact_utils.read_frontmatter rather than a new parser — this repo already has
six too many.
"""

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from artifact_utils import read_frontmatter  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO_ROOT, "docs")

# Directory → the status value a file in it must declare.
DIR_STATUS = {
    "tasks/pending": "pending",
    "tasks/current": "current",
    "tasks/blocked": "blocked",
    "tasks/done": "done",
    "bugs/open": "open",
    "bugs/fixed": "fixed",
    "bugs/wontfix": "wontfix",
}

# Files whose status is free-form (ADRs, architecture, plans, milestones).
FREE_STATUS_DIRS = ("decisions", "architecture", "plans", "milestones", "notes")

# Statuses that must carry evidence of what closed them.
EVIDENCE_REQUIRED = ("done", "fixed")

REQUIRED_FIELDS = ("id", "title", "type", "status", "repos")
VALID_TYPES = ("task", "bug", "adr", "milestone", "plan")
VALID_REPOS = ("epic-code-gen", "epic-code-gen-pipeline",
               "epic-code-gen-pipeline-data", "epic-code-gen-dashboard")

# A code change wants a ledger companion.
CODE_PREFIXES = ("scripts/", ".claude/", "ci-scripts/", "rubrics/")
CODE_SUFFIXES = (".py", ".js", ".sh", ".md", ".json", ".yml", ".yaml")
LEDGER_PREFIXES = ("docs/tasks/", "docs/bugs/", "docs/decisions/")

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
ADR_REF_RE = re.compile(r"\[?(ADR-\d{4})\]?")
LEDGER_NONE_RE = re.compile(r"^\s*Ledger:\s*none\b", re.IGNORECASE | re.MULTILINE)


# ── helpers ─────────────────────────────────────────────────────────────────

def ledger_files(docs=DOCS, repo_root=REPO_ROOT):
    """Every .md file under docs/, relative to repo_root.

    repo_root must be the root the caller will rejoin these against — passing a
    docs/ from outside REPO_ROOT with the default root yields unusable paths.
    """
    out = []
    for root, _dirs, files in os.walk(docs):
        for f in sorted(files):
            if f.endswith(".md"):
                out.append(os.path.relpath(os.path.join(root, f), repo_root))
    return sorted(out)


def _rel_docs(rel, docs_name="docs"):
    """docs-relative directory of a repo-relative path, with / separators."""
    d = os.path.dirname(os.path.relpath(rel, docs_name))
    return d.replace(os.sep, "/")


def _expected_status(rel_dir):
    for prefix, status in DIR_STATUS.items():
        if rel_dir == prefix:
            return status
    return None


def _as_list(value):
    """Frontmatter lists arrive as list or as a bare scalar."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ── --all ───────────────────────────────────────────────────────────────────

def check_all(docs=DOCS, repo_root=REPO_ROOT):
    """Validate every ledger file. Returns a list of error strings."""
    errors = []
    files = ledger_files(docs, repo_root)
    if not files:
        return [f"no ledger files found under {docs}"]
    # docs/ may be named anything when called from a test tmp tree.
    docs_name = os.path.relpath(docs, repo_root)

    known_ids = set()
    for rel in files:
        data, _ = read_frontmatter(os.path.join(repo_root, rel))
        if data.get("id"):
            known_ids.add(str(data["id"]))

    known_adrs = {
        m.group(1)
        for rel in files
        for m in [ADR_REF_RE.match(os.path.basename(rel))] if m
    }

    # Root docs aren't ledger entries, but they link into docs/ heavily and a
    # broken link there is the most visible kind.
    for root_doc in ("PLAN.md", "AGENTS.md"):
        root_path = os.path.join(repo_root, root_doc)
        if os.path.exists(root_path):
            _, root_body = read_frontmatter(root_path)
            errors.extend(
                _check_links(root_doc, root_path, root_body, known_ids, known_adrs))

    for rel in files:
        path = os.path.join(repo_root, rel)
        rel_dir = _rel_docs(rel, docs_name)
        stem = os.path.basename(rel)[: -len(".md")]

        try:
            data, body = read_frontmatter(path)
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{rel}: frontmatter does not parse: {e}")
            continue

        # README.md files are index pages, not ledger entries. Their links are
        # still checked below; their frontmatter is not required.
        if os.path.basename(rel) == "README.md":
            errors.extend(_check_links(rel, path, body, known_ids, known_adrs))
            continue

        if not data:
            errors.append(f"{rel}: no frontmatter")
            continue

        for field in REQUIRED_FIELDS:
            if not data.get(field):
                errors.append(f"{rel}: missing required field `{field}`")

        if data.get("id") and str(data["id"]) != stem:
            errors.append(
                f"{rel}: id `{data['id']}` does not match filename `{stem}`")

        if data.get("type") and data["type"] not in VALID_TYPES:
            errors.append(
                f"{rel}: type `{data['type']}` not one of {', '.join(VALID_TYPES)}")

        for repo in _as_list(data.get("repos")):
            for name in str(repo).split(","):
                name = name.strip()
                if name and name not in VALID_REPOS:
                    errors.append(f"{rel}: unknown repo `{name}`")

        # Status must agree with location — state is directory placement.
        expected = _expected_status(rel_dir)
        status = data.get("status")
        if expected and status != expected:
            errors.append(
                f"{rel}: status `{status}` but lives in {rel_dir}/ "
                f"(expected `{expected}`) — move the file or fix the field")

        # done/fixed must say what closed them.
        if status in EVIDENCE_REQUIRED and not rel_dir.startswith(FREE_STATUS_DIRS):
            if not _as_list(data.get("commits")) and not data.get("jira"):
                errors.append(
                    f"{rel}: status `{status}` requires evidence — "
                    f"a non-empty `commits:` list or a `jira:` key")

        # SHAs must be quoted. YAML reads a leading-zero digit string as octal,
        # so an unquoted `0346470` silently becomes the integer 118072.
        for sha in _as_list(data.get("commits")):
            if not isinstance(sha, str):
                errors.append(
                    f"{rel}: commit `{sha}` parsed as {type(sha).__name__}, not a "
                    f"string — quote it (YAML reads a leading-zero SHA as octal)")
            elif not re.fullmatch(r"[0-9a-f]{7,40}", sha):
                errors.append(f"{rel}: `{sha}` is not a valid commit SHA")

        errors.extend(_check_links(rel, path, body, known_ids, known_adrs))

    return errors


def strip_code(text):
    """Remove fenced blocks and inline code spans.

    A `[[id]]` or `](path)` inside backticks is documenting syntax, not
    referencing anything — AGENTS.md's own templates are full of both.
    """
    text = re.sub(r"^\s*```.*?^\s*```", "", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


def _check_links(rel, path, body, known_ids, known_adrs):
    """Wikilinks, ADR references, and relative markdown links must resolve."""
    errors = []
    body = strip_code(body)

    for m in WIKILINK_RE.finditer(body):
        target = m.group(1).strip()
        if target not in known_ids:
            errors.append(f"{rel}: [[{target}]] does not resolve to any ledger id")

    for adr in sorted(set(ADR_REF_RE.findall(body))):
        if known_adrs and adr not in known_adrs:
            errors.append(f"{rel}: references {adr}, which does not exist")

    for link in re.findall(r"\]\((?!https?://|#)([^)]+)\)", body):
        target = link.split("#")[0].strip()
        if not target:
            continue
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
        if not os.path.exists(resolved):
            errors.append(f"{rel}: broken link → {target}")

    return errors


# ── --diff ──────────────────────────────────────────────────────────────────

def changed_files(rev_range, repo_root=REPO_ROOT):
    """Files changed in a git revision range."""
    result = subprocess.run(
        ["git", "diff", "--name-only", rev_range],
        cwd=repo_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def is_code(path):
    return (path.startswith(CODE_PREFIXES)
            and path.endswith(CODE_SUFFIXES)
            and not path.startswith(LEDGER_PREFIXES))


def is_ledger(path):
    return path.startswith(LEDGER_PREFIXES)


def check_diff(files, body=""):
    """Returns (ok, message). ok is False when a companion is missing."""
    code = sorted(p for p in files if is_code(p))
    ledger = sorted(p for p in files if is_ledger(p))

    if not code:
        return True, "no code changes — companion not required"
    if ledger:
        return True, (f"{len(code)} code file(s), "
                      f"{len(ledger)} ledger file(s): {', '.join(ledger)}")
    if body and LEDGER_NONE_RE.search(body):
        return True, "explicit `Ledger: none` in PR body"

    listed = "\n".join(f"    {p}" for p in code[:10])
    more = f"\n    … and {len(code) - 10} more" if len(code) > 10 else ""
    return False, (
        f"{len(code)} code file(s) changed with no ledger companion:\n"
        f"{listed}{more}\n\n"
        "  Add a file under docs/tasks/ or docs/bugs/ (and an ADR if you made a\n"
        "  decision), or write `Ledger: none — <reason>` in the PR body.\n"
        "  See AGENTS.md §3.")


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true",
                    help="validate every ledger file")
    ap.add_argument("--diff", metavar="RANGE",
                    help="check a git range, e.g. main..HEAD")
    ap.add_argument("--body", metavar="FILE",
                    help="PR body file, for the `Ledger: none` escape hatch")
    ap.add_argument("--strict", action="store_true",
                    help="make a missing companion exit 1 instead of warning")
    args = ap.parse_args()

    if not args.all and not args.diff:
        ap.error("one of --all or --diff is required")

    failed = False

    if args.all:
        errors = check_all()
        if errors:
            print(f"✗ ledger: {len(errors)} problem(s)\n", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            failed = True
        else:
            print(f"✓ ledger: {len(ledger_files())} files, all consistent")

    if args.diff:
        body = ""
        if args.body and os.path.exists(args.body):
            with open(args.body, encoding="utf-8") as f:
                body = f.read()
        try:
            files = changed_files(args.diff)
        except RuntimeError as e:
            print(f"✗ companion check: {e}", file=sys.stderr)
            return 1
        ok, message = check_diff(files, body)
        if ok:
            print(f"✓ companion check: {message}")
        else:
            label = "✗" if args.strict else "⚠"
            print(f"{label} companion check: {message}",
                  file=sys.stderr if args.strict else sys.stdout)
            if args.strict:
                failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
