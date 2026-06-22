#!/usr/bin/env python3
"""Validate a target repo by detecting language and running checks.

Detects the language from marker files (go.mod, package.json, pyproject.toml),
discovers validation commands from Makefile targets / package.json scripts,
and runs them. Returns structured JSON.

Usage:
    python3 scripts/validate_target.py <repo-path>
    python3 scripts/validate_target.py <repo-path> --json
    python3 scripts/validate_target.py <repo-path> --checks lint,test
"""

import argparse
import json
import os
import re
import subprocess
import sys


LANGUAGE_MARKERS = {
    "go": ["go.mod"],
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"],
    "typescript": ["tsconfig.json"],
    "javascript": ["package.json"],
    "rust": ["Cargo.toml"],
}

LANGUAGE_PRIORITY = ["go", "typescript", "python", "rust", "javascript"]

CHECK_NAMES = ["lint", "typecheck", "test"]


def detect_language(repo_path):
    """Detect primary language from marker files.

    Returns (language, marker_file) or (None, None).
    """
    for lang in LANGUAGE_PRIORITY:
        for marker in LANGUAGE_MARKERS[lang]:
            if os.path.isfile(os.path.join(repo_path, marker)):
                return lang, marker
    return None, None


def _parse_makefile_targets(repo_path):
    """Extract target names from a Makefile."""
    makefile = os.path.join(repo_path, "Makefile")
    if not os.path.isfile(makefile):
        return []
    try:
        with open(makefile, encoding="utf-8") as f:
            content = f.read()
        return re.findall(r"^([a-zA-Z][a-zA-Z0-9_/.-]*)\s*:", content, re.MULTILINE)
    except (OSError, UnicodeDecodeError):
        return []


def _parse_package_json_scripts(repo_path):
    """Extract script names from package.json."""
    pkg = os.path.join(repo_path, "package.json")
    if not os.path.isfile(pkg):
        return []
    try:
        with open(pkg, encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("scripts", {}).keys())
    except (OSError, json.JSONDecodeError):
        return []


def discover_commands(repo_path, language):
    """Discover available validation commands for the repo.

    Returns dict mapping check_name -> command string.
    """
    make_targets = _parse_makefile_targets(repo_path)
    npm_scripts = _parse_package_json_scripts(repo_path)
    commands = {}

    if language == "go":
        commands.update(_discover_go_commands(make_targets))
    elif language in ("typescript", "javascript"):
        commands.update(_discover_js_commands(make_targets, npm_scripts))
    elif language == "python":
        commands.update(_discover_python_commands(make_targets))
    elif language == "rust":
        commands.update(_discover_rust_commands(make_targets))

    return commands


def _discover_go_commands(make_targets):
    commands = {}
    lint_targets = [t for t in make_targets if "lint" in t.lower()]
    if lint_targets:
        commands["lint"] = f"make {lint_targets[0]}"
    elif any("vet" in t.lower() for t in make_targets):
        vet = next(t for t in make_targets if "vet" in t.lower())
        commands["lint"] = f"make {vet}"
    else:
        commands["lint"] = "go vet ./..."

    commands["typecheck"] = "go build ./..."

    test_targets = [t for t in make_targets if re.match(r"test(/unit|$)", t, re.I)]
    if test_targets:
        commands["test"] = f"make {test_targets[0]}"
    else:
        commands["test"] = "go test ./..."

    return commands


def _discover_js_commands(make_targets, npm_scripts):
    commands = {}

    if "lint" in npm_scripts:
        commands["lint"] = "npm run lint"
    elif any("lint" in t.lower() for t in make_targets):
        target = next(t for t in make_targets if "lint" in t.lower())
        commands["lint"] = f"make {target}"

    if "typecheck" in npm_scripts:
        commands["typecheck"] = "npm run typecheck"
    elif "tsc" in npm_scripts:
        commands["typecheck"] = "npm run tsc"
    elif os.path.isfile("tsconfig.json"):
        commands["typecheck"] = "npx tsc --noEmit"

    if "test" in npm_scripts:
        commands["test"] = "npm test"
    elif any("test" in t.lower() for t in make_targets):
        target = next(t for t in make_targets if "test" in t.lower())
        commands["test"] = f"make {target}"

    return commands


def _discover_python_commands(make_targets):
    commands = {}

    lint_targets = [t for t in make_targets if "lint" in t.lower()]
    if lint_targets:
        commands["lint"] = f"make {lint_targets[0]}"
    else:
        commands["lint"] = "ruff check ."

    test_targets = [t for t in make_targets if "test" in t.lower()]
    if test_targets:
        commands["test"] = f"make {test_targets[0]}"
    else:
        commands["test"] = "pytest"

    return commands


def _discover_rust_commands(make_targets):
    commands = {}
    commands["lint"] = "cargo clippy -- -D warnings"
    commands["typecheck"] = "cargo check"

    test_targets = [t for t in make_targets if "test" in t.lower()]
    if test_targets:
        commands["test"] = f"make {test_targets[0]}"
    else:
        commands["test"] = "cargo test"

    return commands


def run_check(command, repo_path, timeout=300):
    """Run a single validation command and return result.

    Returns dict with: command, passed, exit_code, output (truncated).
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        max_output = 5000
        if len(output) > max_output:
            output = output[:max_output] + f"\n... (truncated, {len(output)} total chars)"

        return {
            "command": command,
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "output": output.strip(),
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "passed": False,
            "exit_code": -1,
            "output": f"Timed out after {timeout}s",
        }
    except OSError as e:
        return {
            "command": command,
            "passed": False,
            "exit_code": -1,
            "output": str(e),
        }


def validate(repo_path, checks=None, timeout=300):
    """Run validation checks on a target repo.

    Args:
        repo_path: path to the repo
        checks: list of check names to run (default: all discovered)
        timeout: per-command timeout in seconds

    Returns:
        dict with: language, marker, commands, checks, all_passed
    """
    if not os.path.isdir(repo_path):
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    language, marker = detect_language(repo_path)

    result = {
        "repo_path": repo_path,
        "language": language,
        "marker": marker,
        "commands": {},
        "checks": [],
        "all_passed": False,
    }

    if language is None:
        return result

    commands = discover_commands(repo_path, language)
    result["commands"] = commands

    if checks:
        run_checks = {k: v for k, v in commands.items() if k in checks}
    else:
        run_checks = commands

    all_passed = True
    for name in CHECK_NAMES:
        if name not in run_checks:
            continue
        check_result = run_check(run_checks[name], repo_path, timeout)
        check_result["name"] = name
        result["checks"].append(check_result)
        if not check_result["passed"]:
            all_passed = False

    result["all_passed"] = all_passed and len(result["checks"]) > 0
    return result


def format_report(result):
    """Format validation result as readable markdown."""
    lines = [
        "# Target Validation",
        "",
        f"**Repo:** `{result['repo_path']}`",
        f"**Language:** {result['language'] or 'unknown'}",
        f"**Marker:** {result['marker'] or '—'}",
        f"**All Passed:** {'Yes' if result['all_passed'] else 'No'}",
        "",
    ]

    if result["checks"]:
        lines.extend([
            "## Checks",
            "",
            "| Check | Command | Result |",
            "|-------|---------|--------|",
        ])
        for check in result["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            lines.append(f"| {check['name']} | `{check['command']}` | {status} |")

        lines.append("")

        failed = [c for c in result["checks"] if not c["passed"]]
        if failed:
            lines.append("## Failures")
            lines.append("")
            for check in failed:
                lines.extend([
                    f"### {check['name']}: `{check['command']}`",
                    f"Exit code: {check['exit_code']}",
                    "```",
                    check["output"],
                    "```",
                    "",
                ])

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Validate target repo (language detection + checks)")
    parser.add_argument("repo_path", help="Path to the target repository")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of markdown")
    parser.add_argument("--checks", type=str, default=None,
                        help="Comma-separated check names to run (lint,typecheck,test)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Per-command timeout in seconds (default: 300)")
    args = parser.parse_args()

    checks = args.checks.split(",") if args.checks else None

    try:
        result = validate(args.repo_path, checks=checks, timeout=args.timeout)

        if args.json:
            json.dump(result, sys.stdout, indent=2)
            print()
        else:
            print(format_report(result))

        sys.exit(0 if result["all_passed"] else 1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
