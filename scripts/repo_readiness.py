#!/usr/bin/env python3
"""Assess target repo readiness for AI code generation.

6 dimensions, each scored 0-2 (total /12, threshold 8):
  1. Integration tests: test infrastructure exists and covers key paths
  2. Lint in CI: automated linting configured in CI pipeline
  3. Clear CI signals: CI config present with defined jobs/workflows
  4. Context docs: CLAUDE.md, CONTRIBUTING.md, or AGENTS.md present
  5. CODEOWNERS: ownership file exists
  6. Language properties: type checking, lockfile, standard project config

Usage:
    python3 scripts/repo_readiness.py <repo-path>
    python3 scripts/repo_readiness.py <repo-path> --json
    python3 scripts/repo_readiness.py <repo-path> --threshold 8
"""

import argparse
import json
import os
import sys


THRESHOLD_DEFAULT = 8
MAX_SCORE = 12


def check_integration_tests(repo_path):
    """Check for integration test infrastructure.

    Score 2: test directory with test files
    Score 1: test config exists but few/no test files
    Score 0: no test infrastructure found
    """
    indicators = {
        "test_dirs": [],
        "test_files": 0,
        "test_configs": [],
    }

    test_dir_names = [
        "tests", "test", "__tests__", "spec",
        "integration-tests", "e2e",
    ]

    for name in test_dir_names:
        path = os.path.join(repo_path, name)
        if os.path.isdir(path):
            indicators["test_dirs"].append(name)

    test_config_files = [
        "pytest.ini", "setup.cfg", "pyproject.toml",
        "jest.config.js", "jest.config.ts", "jest.config.mjs",
        "vitest.config.ts", "vitest.config.js",
        "cypress.config.ts", "cypress.config.js",
        ".mocharc.yml", ".mocharc.json",
        "go.mod",
    ]

    for name in test_config_files:
        if os.path.isfile(os.path.join(repo_path, name)):
            indicators["test_configs"].append(name)

    test_extensions = (".test.ts", ".test.tsx", ".test.js", ".test.jsx",
                       "_test.go", "_test.py", ".spec.ts", ".spec.js")

    for root, dirs, files in os.walk(repo_path):
        if ".git" in root or "node_modules" in root or ".venv" in root:
            continue
        for f in files:
            if any(f.endswith(ext) for ext in test_extensions):
                indicators["test_files"] += 1
                if indicators["test_files"] >= 10:
                    break
        if indicators["test_files"] >= 10:
            break

    if indicators["test_dirs"] and indicators["test_files"] >= 5:
        score = 2
    elif indicators["test_dirs"] or indicators["test_configs"]:
        score = 1
    else:
        score = 0

    return score, indicators


def check_lint_in_ci(repo_path):
    """Check for lint configuration in CI pipeline.

    Score 2: lint step in CI + lint config present
    Score 1: lint config present but not clearly in CI
    Score 0: no lint configuration found
    """
    indicators = {
        "lint_configs": [],
        "lint_in_ci": False,
    }

    lint_configs = [
        ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc",
        "eslint.config.js", "eslint.config.mjs",
        ".flake8", ".pylintrc", "pyproject.toml",
        ".golangci.yml", ".golangci.yaml",
        ".rubocop.yml",
        "biome.json",
        ".prettierrc", ".prettierrc.json", ".prettierrc.yml",
    ]

    for name in lint_configs:
        if os.path.isfile(os.path.join(repo_path, name)):
            indicators["lint_configs"].append(name)

    ci_files = _find_ci_files(repo_path)
    lint_keywords = ["lint", "eslint", "flake8", "pylint", "golangci",
                     "rubocop", "prettier", "biome"]

    for ci_file in ci_files:
        try:
            with open(ci_file, encoding="utf-8") as f:
                content = f.read().lower()
            if any(kw in content for kw in lint_keywords):
                indicators["lint_in_ci"] = True
                break
        except (OSError, UnicodeDecodeError):
            continue

    if indicators["lint_configs"] and indicators["lint_in_ci"]:
        score = 2
    elif indicators["lint_configs"]:
        score = 1
    else:
        score = 0

    return score, indicators


def check_ci_signals(repo_path):
    """Check for clear CI configuration.

    Score 2: CI config with multiple defined jobs/stages
    Score 1: CI config present
    Score 0: no CI config found
    """
    indicators = {
        "ci_files": [],
        "has_jobs": False,
    }

    ci_files = _find_ci_files(repo_path)
    indicators["ci_files"] = [os.path.relpath(f, repo_path) for f in ci_files]

    job_keywords = ["jobs:", "stages:", "steps:", "script:", "runs-on:",
                    "stage:", "pipeline"]

    for ci_file in ci_files:
        try:
            with open(ci_file, encoding="utf-8") as f:
                content = f.read()
            if sum(1 for kw in job_keywords if kw in content) >= 2:
                indicators["has_jobs"] = True
                break
        except (OSError, UnicodeDecodeError):
            continue

    if ci_files and indicators["has_jobs"]:
        score = 2
    elif ci_files:
        score = 1
    else:
        score = 0

    return score, indicators


def check_context_docs(repo_path):
    """Check for AI/contributor context documentation.

    Score 2: CLAUDE.md or AGENTS.md present (AI-specific context)
    Score 1: CONTRIBUTING.md or README.md with dev setup section
    Score 0: no context docs
    """
    indicators = {
        "docs_found": [],
    }

    ai_docs = ["CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md"]
    for name in ai_docs:
        if os.path.isfile(os.path.join(repo_path, name)):
            indicators["docs_found"].append(name)

    if indicators["docs_found"]:
        return 2, indicators

    contributor_docs = ["CONTRIBUTING.md", "CONTRIBUTING.rst"]
    for name in contributor_docs:
        if os.path.isfile(os.path.join(repo_path, name)):
            indicators["docs_found"].append(name)

    if indicators["docs_found"]:
        return 1, indicators

    readme_path = os.path.join(repo_path, "README.md")
    if os.path.isfile(readme_path):
        try:
            with open(readme_path, encoding="utf-8") as f:
                content = f.read().lower()
            dev_keywords = ["development", "getting started", "setup",
                            "contributing", "build"]
            if any(kw in content for kw in dev_keywords):
                indicators["docs_found"].append("README.md (has dev section)")
                return 1, indicators
        except (OSError, UnicodeDecodeError):
            pass

    return 0, indicators


def check_codeowners(repo_path):
    """Check for CODEOWNERS file.

    Score 2: CODEOWNERS with path-specific rules
    Score 1: CODEOWNERS exists (default/global only)
    Score 0: no CODEOWNERS
    """
    indicators = {
        "codeowners_path": None,
        "has_path_rules": False,
    }

    locations = [
        "CODEOWNERS",
        ".github/CODEOWNERS",
        "docs/CODEOWNERS",
    ]

    for loc in locations:
        path = os.path.join(repo_path, loc)
        if os.path.isfile(path):
            indicators["codeowners_path"] = loc
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
                path_rules = [l for l in lines
                              if l.strip() and not l.startswith("#")
                              and "/" in l.split()[0] if l.split()]
                if path_rules:
                    indicators["has_path_rules"] = True
            except (OSError, UnicodeDecodeError):
                pass
            break

    if indicators["codeowners_path"] and indicators["has_path_rules"]:
        score = 2
    elif indicators["codeowners_path"]:
        score = 1
    else:
        score = 0

    return score, indicators


def check_language_properties(repo_path):
    """Check for type checking, lockfiles, and standard project config.

    Score 2: type checking configured + lockfile present
    Score 1: one of the above
    Score 0: neither
    """
    indicators = {
        "type_checking": [],
        "lockfiles": [],
        "project_configs": [],
    }

    type_check_files = {
        "tsconfig.json": "TypeScript",
        "pyproject.toml": "Python (potential mypy/pyright)",
        "mypy.ini": "mypy",
        ".mypy.ini": "mypy",
        "pyrightconfig.json": "pyright",
    }

    for name, lang in type_check_files.items():
        if os.path.isfile(os.path.join(repo_path, name)):
            indicators["type_checking"].append(f"{name} ({lang})")

    lockfile_names = [
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "uv.lock", "poetry.lock", "Pipfile.lock",
        "go.sum", "Gemfile.lock", "Cargo.lock",
    ]

    for name in lockfile_names:
        if os.path.isfile(os.path.join(repo_path, name)):
            indicators["lockfiles"].append(name)

    project_configs = [
        "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "go.mod", "Cargo.toml", "Gemfile", "build.gradle",
        "pom.xml", "CMakeLists.txt",
    ]

    for name in project_configs:
        if os.path.isfile(os.path.join(repo_path, name)):
            indicators["project_configs"].append(name)

    has_types = bool(indicators["type_checking"])
    has_lock = bool(indicators["lockfiles"])

    if has_types and has_lock:
        score = 2
    elif has_types or has_lock:
        score = 1
    else:
        score = 0

    return score, indicators


def _find_ci_files(repo_path):
    """Find CI configuration files in the repo."""
    ci_files = []

    ci_paths = [
        ".github/workflows",
        ".gitlab-ci.yml",
        ".circleci/config.yml",
        "Jenkinsfile",
        ".travis.yml",
        "azure-pipelines.yml",
        ".tekton",
    ]

    for ci_path in ci_paths:
        full = os.path.join(repo_path, ci_path)
        if os.path.isfile(full):
            ci_files.append(full)
        elif os.path.isdir(full):
            for f in os.listdir(full):
                fp = os.path.join(full, f)
                if os.path.isfile(fp) and (f.endswith(".yml")
                                           or f.endswith(".yaml")):
                    ci_files.append(fp)

    return ci_files


DIMENSIONS = [
    ("integration_tests", "Integration Tests", check_integration_tests),
    ("lint_in_ci", "Lint in CI", check_lint_in_ci),
    ("ci_signals", "CI Signals", check_ci_signals),
    ("context_docs", "Context Docs", check_context_docs),
    ("codeowners", "CODEOWNERS", check_codeowners),
    ("language_properties", "Language Properties", check_language_properties),
]


def assess(repo_path):
    """Run all readiness checks and return assessment result.

    Returns:
        dict with keys: total_score, max_score, threshold, ready,
                        dimensions (list of per-dimension results)
    """
    if not os.path.isdir(repo_path):
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    results = {
        "repo_path": repo_path,
        "total_score": 0,
        "max_score": MAX_SCORE,
        "threshold": THRESHOLD_DEFAULT,
        "ready": False,
        "dimensions": [],
    }

    for key, label, check_fn in DIMENSIONS:
        score, indicators = check_fn(repo_path)
        results["total_score"] += score
        results["dimensions"].append({
            "key": key,
            "label": label,
            "score": score,
            "max": 2,
            "indicators": indicators,
        })

    results["ready"] = results["total_score"] >= results["threshold"]
    return results


def format_report(results):
    """Format assessment results as a readable markdown report."""
    lines = [
        f"# Repo Readiness Assessment",
        f"",
        f"**Repo:** `{results['repo_path']}`",
        f"**Score:** {results['total_score']}/{results['max_score']} "
        f"(threshold: {results['threshold']})",
        f"**Ready:** {'Yes' if results['ready'] else 'No'}",
        f"",
        f"## Dimensions",
        f"",
        f"| Dimension | Score | Details |",
        f"|-----------|-------|---------|",
    ]

    for dim in results["dimensions"]:
        score_str = f"{dim['score']}/{dim['max']}"
        detail_parts = []
        for k, v in dim["indicators"].items():
            if isinstance(v, list) and v:
                detail_parts.append(f"{k}: {', '.join(str(x) for x in v)}")
            elif isinstance(v, bool):
                detail_parts.append(f"{k}: {'yes' if v else 'no'}")
            elif v is not None and not isinstance(v, list):
                detail_parts.append(f"{k}: {v}")
        details = "; ".join(detail_parts) if detail_parts else "—"
        lines.append(f"| {dim['label']} | {score_str} | {details} |")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Assess repo readiness for AI code generation")
    parser.add_argument("repo_path", help="Path to the target repository")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of markdown")
    parser.add_argument("--threshold", type=int, default=THRESHOLD_DEFAULT,
                        help=f"Readiness threshold (default: {THRESHOLD_DEFAULT})")
    args = parser.parse_args()

    try:
        results = assess(args.repo_path)
        results["threshold"] = args.threshold
        results["ready"] = results["total_score"] >= args.threshold

        if args.json:
            json.dump(results, sys.stdout, indent=2)
            print()
        else:
            print(format_report(results))

        sys.exit(0 if results["ready"] else 1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
