"""Tests for validate_target.py."""

import json
import os
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from validate_target import (
    detect_language,
    discover_commands,
    run_check,
    validate,
    format_report,
)


@pytest.fixture
def repo(tmp_path):
    """Create a minimal repo directory for testing."""
    return tmp_path


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("")


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


# ─── Language Detection ─────────────────────────────────────────────────────

class TestDetectLanguage:

    def test_go(self, repo):
        _touch(str(repo / "go.mod"))
        lang, marker = detect_language(str(repo))
        assert lang == "go"
        assert marker == "go.mod"

    def test_python_pyproject(self, repo):
        _write(str(repo / "pyproject.toml"), "[project]\nname = 'myapp'")
        lang, marker = detect_language(str(repo))
        assert lang == "python"
        assert marker == "pyproject.toml"

    def test_python_requirements(self, repo):
        _touch(str(repo / "requirements.txt"))
        lang, marker = detect_language(str(repo))
        assert lang == "python"

    def test_typescript(self, repo):
        _write(str(repo / "tsconfig.json"), "{}")
        lang, marker = detect_language(str(repo))
        assert lang == "typescript"
        assert marker == "tsconfig.json"

    def test_javascript_package_json(self, repo):
        _write(str(repo / "package.json"), '{"name": "test"}')
        lang, marker = detect_language(str(repo))
        assert lang == "javascript"

    def test_rust(self, repo):
        _touch(str(repo / "Cargo.toml"))
        lang, marker = detect_language(str(repo))
        assert lang == "rust"

    def test_go_wins_over_js(self, repo):
        _touch(str(repo / "go.mod"))
        _write(str(repo / "package.json"), '{"name": "test"}')
        lang, _ = detect_language(str(repo))
        assert lang == "go"

    def test_typescript_wins_over_js(self, repo):
        _write(str(repo / "tsconfig.json"), "{}")
        _write(str(repo / "package.json"), '{"name": "test"}')
        lang, _ = detect_language(str(repo))
        assert lang == "typescript"

    def test_unknown_repo(self, repo):
        lang, marker = detect_language(str(repo))
        assert lang is None
        assert marker is None


# ─── Command Discovery ──────────────────────────────────────────────────────

class TestDiscoverCommands:

    def test_go_defaults(self, repo):
        _touch(str(repo / "go.mod"))
        cmds = discover_commands(str(repo), "go")
        assert cmds["lint"] == "go vet ./..."
        assert cmds["typecheck"] == "go build ./..."
        assert cmds["test"] == "go test ./..."

    def test_go_with_makefile(self, repo):
        _touch(str(repo / "go.mod"))
        _write(str(repo / "Makefile"),
               "lint:\n\tgolangci-lint run\n\ntest/unit:\n\tgo test ./...\n")
        cmds = discover_commands(str(repo), "go")
        assert cmds["lint"] == "make lint"
        assert cmds["test"] == "make test/unit"

    def test_js_with_package_scripts(self, repo):
        _write(str(repo / "package.json"), json.dumps({
            "name": "test",
            "scripts": {"lint": "eslint .", "test": "jest"}
        }))
        cmds = discover_commands(str(repo), "javascript")
        assert cmds["lint"] == "npm run lint"
        assert cmds["test"] == "npm test"

    def test_ts_with_typecheck(self, repo):
        _write(str(repo / "package.json"), json.dumps({
            "name": "test",
            "scripts": {"lint": "eslint .", "typecheck": "tsc --noEmit", "test": "vitest"}
        }))
        cmds = discover_commands(str(repo), "typescript")
        assert cmds["typecheck"] == "npm run typecheck"

    def test_python_defaults(self, repo):
        _write(str(repo / "pyproject.toml"), "[project]\nname = 'test'")
        cmds = discover_commands(str(repo), "python")
        assert cmds["lint"] == "ruff check ."
        assert cmds["test"] == "pytest"

    def test_python_with_makefile(self, repo):
        _write(str(repo / "Makefile"), "lint:\n\truff check\ntest-unit:\n\tpytest\n")
        cmds = discover_commands(str(repo), "python")
        assert cmds["lint"] == "make lint"
        assert cmds["test"] == "make test-unit"

    def test_rust_defaults(self, repo):
        cmds = discover_commands(str(repo), "rust")
        assert cmds["lint"] == "cargo clippy -- -D warnings"
        assert cmds["typecheck"] == "cargo check"
        assert cmds["test"] == "cargo test"

    def test_go_makefile_vet_fallback(self, repo):
        _write(str(repo / "Makefile"), "vet:\n\tgo vet ./...\n")
        cmds = discover_commands(str(repo), "go")
        assert cmds["lint"] == "make vet"


# ─── Run Check ───────────────────────────────────────────────────────────────

class TestRunCheck:

    def test_passing_command(self, repo):
        result = run_check("true", str(repo))
        assert result["passed"] is True
        assert result["exit_code"] == 0

    def test_failing_command(self, repo):
        result = run_check("false", str(repo))
        assert result["passed"] is False
        assert result["exit_code"] != 0

    def test_output_captured(self, repo):
        result = run_check("echo hello_validate", str(repo))
        assert "hello_validate" in result["output"]

    def test_timeout(self, repo):
        result = run_check("sleep 10", str(repo), timeout=1)
        assert result["passed"] is False
        assert "Timed out" in result["output"]

    def test_output_truncation(self, repo):
        result = run_check("python3 -c \"print('x' * 10000)\"", str(repo))
        assert len(result["output"]) <= 6000


# ─── Full Validation ─────────────────────────────────────────────────────────

class TestValidate:

    def test_unknown_language(self, repo):
        result = validate(str(repo))
        assert result["language"] is None
        assert result["all_passed"] is False
        assert result["checks"] == []

    def test_nonexistent_path(self):
        with pytest.raises(FileNotFoundError):
            validate("/nonexistent/repo/path")

    def test_go_repo_with_passing_checks(self, repo):
        _touch(str(repo / "go.mod"))
        _write(str(repo / "Makefile"),
               "lint:\n\ttrue\ntest:\n\ttrue\n")
        result = validate(str(repo), checks=["lint", "test"])
        assert result["language"] == "go"
        assert len(result["checks"]) == 2
        assert result["all_passed"] is True

    def test_go_repo_with_failing_lint(self, repo):
        _touch(str(repo / "go.mod"))
        _write(str(repo / "Makefile"),
               "lint:\n\tfalse\ntest:\n\ttrue\n")
        result = validate(str(repo))
        assert result["all_passed"] is False
        lint_check = next(c for c in result["checks"] if c["name"] == "lint")
        assert lint_check["passed"] is False

    def test_selective_checks(self, repo):
        _touch(str(repo / "go.mod"))
        _write(str(repo / "Makefile"),
               "lint:\n\ttrue\ntest:\n\ttrue\n")
        result = validate(str(repo), checks=["lint"])
        check_names = [c["name"] for c in result["checks"]]
        assert "lint" in check_names
        assert "test" not in check_names

    def test_python_repo(self, repo):
        _write(str(repo / "pyproject.toml"), "[project]\nname = 'test'")
        _write(str(repo / "Makefile"), "lint:\n\ttrue\ntest:\n\ttrue\n")
        result = validate(str(repo))
        assert result["language"] == "python"
        assert result["all_passed"] is True


# ─── Format Report ───────────────────────────────────────────────────────────

class TestFormatReport:

    def test_format_contains_language(self, repo):
        _touch(str(repo / "go.mod"))
        _write(str(repo / "Makefile"), "lint:\n\ttrue\ntest:\n\ttrue\n")
        result = validate(str(repo))
        report = format_report(result)
        assert "go" in report
        assert "PASS" in report

    def test_format_unknown_language(self, repo):
        result = validate(str(repo))
        report = format_report(result)
        assert "unknown" in report

    def test_format_shows_failures(self, repo):
        _touch(str(repo / "go.mod"))
        _write(str(repo / "Makefile"), "lint:\n\tfalse\n")
        result = validate(str(repo))
        report = format_report(result)
        assert "FAIL" in report
        assert "Failures" in report
