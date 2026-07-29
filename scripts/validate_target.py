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
import shutil
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

# Shell exit codes for "cannot execute": 127 = command not found,
# 126 = found but not executable. GNU make propagates these from a recipe,
# so `make lint-backend` calling a missing `uv` surfaces as 127 here.
UNRUNNABLE_EXIT_CODES = (126, 127)

# Ordered: the make-prefixed forms must be tried first, or the generic
# patterns would extract "make" as the missing tool.
_MISSING_TOOL_PATTERNS = [
    re.compile(r"make(?:\[\d+\])?: ([\w.+\-/]+): "
               r"(?:No such file or directory|Command not found|"
               r"command not found)"),
    re.compile(r"(?:^|[\s/])([\w.+\-]+): command not found"),
    re.compile(r"command not found: ([\w.+\-]+)"),
    re.compile(r"(?:^|[\s/])([\w.+\-]+): No such file or directory"),
]

# Output that means "could not execute", not "executed and found problems".
# GNU make does not propagate 127 — it exits 2 and reports `Error 127` — so
# the exit code alone is not enough. Kept deliberately narrow: a bare
# "No such file or directory" is NOT included, since a genuinely failing test
# missing a fixture file would otherwise be misread as no-signal.
_UNRUNNABLE_OUTPUT_PATTERNS = [
    re.compile(r"command not found"),
    re.compile(r"make(?:\[\d+\])?: \*\*\* .*Error 12[67]\b"),
    re.compile(r"make(?:\[\d+\])?: [\w.+\-/]+: No such file or directory"),
]


def _looks_unrunnable(exit_code, output):
    """Distinguish "tool missing" from "tool ran and failed"."""
    if exit_code in UNRUNNABLE_EXIT_CODES:
        return True
    return any(p.search(output or "") for p in _UNRUNNABLE_OUTPUT_PATTERNS)

# Tools a language needs before codegen is worth attempting. Anything
# conditional (uv, yarn) is added by detect_required_tools() from repo markers.
BASE_TOOLS = {
    "go": ["go"],
    "python": ["python3"],
    "typescript": ["node", "npm"],
    "javascript": ["node", "npm"],
    "rust": ["cargo"],
}


def _extract_missing_tool(output):
    """Pull the missing executable's name out of shell/make error output."""
    for pattern in _MISSING_TOOL_PATTERNS:
        match = pattern.search(output or "")
        if match:
            return os.path.basename(match.group(1))
    return None


def detect_required_tools(repo_path, language=None):
    """Determine which executables this repo's checks actually need.

    Enumerating tools by hand per target repo does not scale, so this reads
    the repo's own definitions:

    1. Repo markers — a uv.lock or `uv` in the Makefile means uv is
       mandatory, a yarn.lock means yarn.
    2. Makefile recipes — for the exact lint/typecheck/test targets
       discover_commands() would run, the recipe lines are variable-expanded
       and their executables extracted, following prerequisites. This is what
       catches a tool referenced only inside a recipe (kale's `uv run ruff`
       behind `UV := uv`), which no lockfile check would reveal.

    Only the targets we actually intend to run are inspected, so an unrelated
    recipe needing docker or helm does not block codegen.

    Returns:
        list[str]: executable names, deduplicated, in a stable order.
    """
    if language is None:
        language, _ = detect_language(repo_path)

    tools = ["git"]
    if os.path.isfile(os.path.join(repo_path, "Makefile")):
        tools.append("make")
    tools.extend(BASE_TOOLS.get(language, []))

    def _read(name):
        path = os.path.join(repo_path, name)
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    makefile = _read("Makefile")
    pyproject = _read("pyproject.toml")

    # uv: lockfile, a Makefile driving commands through it, or a [tool.uv]
    # section. kale sets `UV := uv` and routes every target through it.
    if (os.path.isfile(os.path.join(repo_path, "uv.lock"))
            or re.search(r"^\s*UV\s*[:?]?=", makefile, re.M)
            or "uv run" in makefile
            or "uv sync" in makefile
            or "[tool.uv]" in pyproject):
        tools.append("uv")

    if os.path.isfile(os.path.join(repo_path, "yarn.lock")):
        tools.append("yarn")
    if os.path.isfile(os.path.join(repo_path, "requirements.txt")):
        tools.append("pip3")

    # Executables named inside the recipes we are actually going to run.
    if makefile:
        variables = _parse_makefile_vars(makefile)
        rules = _parse_makefile_rules(makefile)
        commands = discover_commands(repo_path, language)
        for command in commands.values():
            match = re.match(r"^make\s+([A-Za-z][A-Za-z0-9_/.-]*)", command)
            if match:
                tools.extend(
                    tools_for_target(rules, variables, match.group(1)))
            else:
                tools.extend(_tools_in_recipe_line(command, variables))

    seen = set()
    ordered = []
    for tool in tools:
        if tool not in seen:
            seen.add(tool)
            ordered.append(tool)
    return ordered


def preflight(repo_path, language=None):
    """Check the toolchain before generating any code.

    A missing tool makes every downstream check unrunnable, and an
    unrunnable check is indistinguishable from a real failure once it is
    scored. Callers should refuse to generate code when this reports not ok.

    Returns:
        dict: {language, required, missing, found, ok}
    """
    if not os.path.isdir(repo_path):
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    if language is None:
        language, _ = detect_language(repo_path)

    required = detect_required_tools(repo_path, language)
    found = {}
    missing = []
    for tool in required:
        path = shutil.which(tool)
        found[tool] = path
        if path is None:
            missing.append(tool)

    return {
        "language": language,
        "required": required,
        "found": found,
        "missing": missing,
        "ok": not missing,
    }


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


# Shell builtins, keywords, and ubiquitous coreutils. Not worth gating on:
# either they always exist, or they are syntax rather than executables.
_NOT_A_TOOL = {
    "if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done",
    "case", "esac", "in", "function", "return", "break", "continue",
    "echo", "printf", "cd", "exit", "true", "false", "set", "unset", "export",
    "local", "read", "shift", "eval", "exec", "trap", "wait", "source",
    "test", "[", "[[", ":", ".", "time", "command", "type", "hash", "umask",
    "rm", "mkdir", "rmdir", "cp", "mv", "ln", "cat", "touch", "chmod", "chown",
    "sleep", "kill", "pwd", "basename", "dirname", "env", "true",
    "make", "$(MAKE)", "@",
}

# A bare executable name. Anything with unexpanded variables, quotes, globs,
# or redirections is parsing noise and must not gate codegen.
_TOOL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.+-]*$")


def _parse_makefile_vars(content):
    """Collect simple Makefile variable assignments (NAME := value)."""
    variables = {}
    for match in re.finditer(
            r"^([A-Za-z_][A-Za-z0-9_]*)\s*[:?+]?=\s*(.*)$", content, re.M):
        variables[match.group(1)] = match.group(2).strip()
    return variables


def _expand_makefile_vars(text, variables, depth=3):
    """Expand $(VAR) / ${VAR} references, a few levels deep.

    kale defines `UV := uv` and `JLPM := $(UV) run jlpm`, so recipes only
    reveal their real executables after expansion.
    """
    for _ in range(depth):
        original = text

        def _sub(match):
            name = match.group(1) or match.group(2)
            return variables.get(name, match.group(0))

        text = re.sub(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)"
                      r"|\$\{([A-Za-z_][A-Za-z0-9_]*)\}", _sub, text)
        if text == original:
            break
    return text


def _parse_makefile_rules(content):
    """Map target -> {prereqs, recipe lines} from Makefile text."""
    rules = {}
    current = None
    for line in content.split("\n"):
        if line.startswith("\t"):
            if current:
                rules[current]["recipe"].append(line.strip())
            continue
        match = re.match(
            r"^([A-Za-z][A-Za-z0-9_/.-]*)\s*:{1,2}\s*([^=].*)?$", line)
        if match:
            current = match.group(1)
            prereqs = (match.group(2) or "").split()
            rules.setdefault(
                current, {"prereqs": [], "recipe": []})["prereqs"].extend(
                    prereqs)
        elif line.strip() and not line.startswith(" "):
            current = None
    return rules


def _tools_in_recipe_line(line, variables):
    """Extract candidate executable names from one recipe line."""
    line = _expand_makefile_vars(line, variables)
    # Strip make's per-line prefixes (@ silent, - ignore-errors, + always-run).
    line = line.lstrip("@-+ \t")

    tools = []
    # Split on shell operators to reach each command's first token.
    for segment in re.split(r"&&|\|\||[;|]", line):
        segment = segment.strip()
        if not segment:
            continue
        # `cd dir && cmd` already split; drop a leading `cd` segment.
        tokens = segment.split()
        if not tokens:
            continue
        candidate = tokens[0]
        # Skip leading VAR=value assignments before the real command.
        idx = 0
        while idx < len(tokens) and re.match(
                r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[idx]):
            idx += 1
        if idx >= len(tokens):
            continue
        candidate = tokens[idx]
        if candidate.startswith("$"):
            continue
        candidate = candidate.strip("\"'")
        base = os.path.basename(candidate)
        if base in _NOT_A_TOOL or not _TOOL_NAME_RE.match(base):
            continue
        tools.append(base)
    return tools


def tools_for_target(rules, variables, target, _seen=None):
    """Executables a Makefile target needs, following its prerequisites."""
    if _seen is None:
        _seen = set()
    if target in _seen or target not in rules:
        return []
    _seen.add(target)

    tools = []
    for prereq in rules[target]["prereqs"]:
        tools.extend(tools_for_target(rules, variables, prereq, _seen))
    for line in rules[target]["recipe"]:
        tools.extend(_tools_in_recipe_line(line, variables))
    return tools


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

        # "Could not run" is not "ran and found problems". Conflating them
        # turns a missing tool into a code-quality score.
        unrunnable = _looks_unrunnable(result.returncode, output)
        missing_tool = _extract_missing_tool(output) if unrunnable else None

        return {
            "command": command,
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "output": output.strip(),
            "unrunnable": unrunnable,
            "missing_tool": missing_tool,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "passed": False,
            "exit_code": -1,
            "output": f"Timed out after {timeout}s",
            "unrunnable": False,
            "missing_tool": None,
        }
    except OSError as e:
        return {
            "command": command,
            "passed": False,
            "exit_code": -1,
            "output": str(e),
            "unrunnable": True,
            "missing_tool": _extract_missing_tool(str(e)),
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
        "unrunnable": [],
        "missing_tools": [],
        "has_unrunnable": False,
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
        if check_result.get("unrunnable"):
            result["unrunnable"].append(name)
            tool = check_result.get("missing_tool")
            if tool and tool not in result["missing_tools"]:
                result["missing_tools"].append(tool)

    # An unrunnable check yields no signal, so it can never support a pass.
    result["all_passed"] = (
        all_passed and len(result["checks"]) > 0 and not result["unrunnable"])
    result["has_unrunnable"] = bool(result["unrunnable"])
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
            if check.get("unrunnable"):
                tool = check.get("missing_tool")
                status = f"UNRUNNABLE (missing {tool})" if tool \
                    else "UNRUNNABLE"
            else:
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
    parser.add_argument("--preflight", action="store_true",
                        help="Only check the toolchain; run no checks. "
                             "Exit 2 when a required tool is missing.")
    args = parser.parse_args()

    checks = args.checks.split(",") if args.checks else None

    if args.preflight:
        try:
            result = preflight(args.repo_path)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            json.dump(result, sys.stdout, indent=2)
            print()
        else:
            print(f"Language: {result['language'] or 'unknown'}")
            print(f"Required: {', '.join(result['required']) or '—'}")
            if result["ok"]:
                print("Toolchain OK")
            else:
                print(f"MISSING: {', '.join(result['missing'])}")
        # Exit 2 distinguishes a broken environment from a failing check.
        sys.exit(0 if result["ok"] else 2)

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
