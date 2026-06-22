"""Tests for repo_readiness.py."""

import os
import tempfile

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
import sys
sys.path.insert(0, sys_path_fix)

from repo_readiness import (
    assess,
    check_integration_tests,
    check_lint_in_ci,
    check_ci_signals,
    check_context_docs,
    check_codeowners,
    check_language_properties,
    format_report,
)


@pytest.fixture
def repo(tmp_path):
    """Create a minimal repo directory for testing."""
    return tmp_path


def _touch(path):
    """Create a file and its parent directories."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("")


def _write(path, content):
    """Write content to a file, creating parent dirs."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


# ─── Integration Tests Dimension ─────────────────────────────────────────────

class TestCheckIntegrationTests:

    def test_score_0_no_tests(self, repo):
        score, indicators = check_integration_tests(str(repo))
        assert score == 0
        assert indicators["test_files"] == 0

    def test_score_1_test_dir_no_files(self, repo):
        os.makedirs(repo / "tests")
        score, indicators = check_integration_tests(str(repo))
        assert score == 1
        assert "tests" in indicators["test_dirs"]

    def test_score_1_test_config_only(self, repo):
        _touch(str(repo / "pytest.ini"))
        score, indicators = check_integration_tests(str(repo))
        assert score == 1
        assert "pytest.ini" in indicators["test_configs"]

    def test_score_2_test_dir_with_files(self, repo):
        tests_dir = repo / "tests"
        os.makedirs(tests_dir)
        for i in range(6):
            _touch(str(tests_dir / f"test_module_{i}.py"))
            # Make them match the extension pattern
            _write(str(tests_dir / f"test_module_{i}_test.py"), "")
        score, indicators = check_integration_tests(str(repo))
        assert score == 2


# ─── Lint in CI Dimension ────────────────────────────────────────────────────

class TestCheckLintInCI:

    def test_score_0_no_lint(self, repo):
        score, indicators = check_lint_in_ci(str(repo))
        assert score == 0

    def test_score_1_lint_config_only(self, repo):
        _touch(str(repo / ".eslintrc.json"))
        score, indicators = check_lint_in_ci(str(repo))
        assert score == 1
        assert ".eslintrc.json" in indicators["lint_configs"]
        assert not indicators["lint_in_ci"]

    def test_score_2_lint_in_ci(self, repo):
        _touch(str(repo / ".eslintrc.json"))
        _write(str(repo / ".github" / "workflows" / "lint.yml"),
               "name: lint\nsteps:\n  - run: eslint .")
        score, indicators = check_lint_in_ci(str(repo))
        assert score == 2
        assert indicators["lint_in_ci"]


# ─── CI Signals Dimension ────────────────────────────────────────────────────

class TestCheckCISignals:

    def test_score_0_no_ci(self, repo):
        score, indicators = check_ci_signals(str(repo))
        assert score == 0

    def test_score_1_ci_present(self, repo):
        _write(str(repo / ".gitlab-ci.yml"), "image: python:3.11")
        score, indicators = check_ci_signals(str(repo))
        assert score == 1

    def test_score_2_ci_with_jobs(self, repo):
        _write(str(repo / ".github" / "workflows" / "ci.yml"),
               "name: CI\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
               "    steps:\n      - run: pytest")
        score, indicators = check_ci_signals(str(repo))
        assert score == 2
        assert indicators["has_jobs"]


# ─── Context Docs Dimension ──────────────────────────────────────────────────

class TestCheckContextDocs:

    def test_score_0_no_docs(self, repo):
        score, indicators = check_context_docs(str(repo))
        assert score == 0

    def test_score_2_claude_md(self, repo):
        _touch(str(repo / "CLAUDE.md"))
        score, indicators = check_context_docs(str(repo))
        assert score == 2
        assert "CLAUDE.md" in indicators["docs_found"]

    def test_score_2_agents_md(self, repo):
        _touch(str(repo / "AGENTS.md"))
        score, indicators = check_context_docs(str(repo))
        assert score == 2

    def test_score_1_contributing(self, repo):
        _touch(str(repo / "CONTRIBUTING.md"))
        score, indicators = check_context_docs(str(repo))
        assert score == 1

    def test_score_1_readme_with_dev_section(self, repo):
        _write(str(repo / "README.md"), "# Project\n## Development\nSetup...")
        score, indicators = check_context_docs(str(repo))
        assert score == 1


# ─── CODEOWNERS Dimension ────────────────────────────────────────────────────

class TestCheckCodeowners:

    def test_score_0_no_codeowners(self, repo):
        score, indicators = check_codeowners(str(repo))
        assert score == 0

    def test_score_1_global_codeowners(self, repo):
        _write(str(repo / "CODEOWNERS"), "* @team")
        score, indicators = check_codeowners(str(repo))
        assert score == 1

    def test_score_2_path_rules(self, repo):
        _write(str(repo / ".github" / "CODEOWNERS"),
               "* @team\n/src/api/ @api-team\n/src/ui/ @ui-team\n")
        score, indicators = check_codeowners(str(repo))
        assert score == 2
        assert indicators["has_path_rules"]


# ─── Language Properties Dimension ───────────────────────────────────────────

class TestCheckLanguageProperties:

    def test_score_0_nothing(self, repo):
        score, indicators = check_language_properties(str(repo))
        assert score == 0

    def test_score_1_lockfile_only(self, repo):
        _touch(str(repo / "package-lock.json"))
        score, indicators = check_language_properties(str(repo))
        assert score == 1

    def test_score_1_typecheck_only(self, repo):
        _touch(str(repo / "tsconfig.json"))
        score, indicators = check_language_properties(str(repo))
        assert score == 1

    def test_score_2_both(self, repo):
        _touch(str(repo / "tsconfig.json"))
        _touch(str(repo / "yarn.lock"))
        score, indicators = check_language_properties(str(repo))
        assert score == 2


# ─── Full Assessment ─────────────────────────────────────────────────────────

class TestAssess:

    def test_assess_empty_repo(self, repo):
        results = assess(str(repo))
        assert results["total_score"] == 0
        assert not results["ready"]
        assert results["max_score"] == 12
        assert len(results["dimensions"]) == 6

    def test_assess_nonexistent_path(self):
        with pytest.raises(FileNotFoundError):
            assess("/nonexistent/repo/path")

    def test_assess_well_configured_repo(self, repo):
        # Set up a well-configured repo
        tests_dir = repo / "tests"
        os.makedirs(tests_dir)
        for i in range(6):
            _write(str(tests_dir / f"module_{i}_test.py"), "")

        _touch(str(repo / ".eslintrc.json"))
        _write(str(repo / ".github" / "workflows" / "ci.yml"),
               "name: CI\njobs:\n  lint:\n    runs-on: ubuntu\n"
               "    steps:\n      - run: eslint .")
        _touch(str(repo / "CLAUDE.md"))
        _write(str(repo / ".github" / "CODEOWNERS"),
               "* @team\n/src/ @eng\n")
        _touch(str(repo / "tsconfig.json"))
        _touch(str(repo / "package-lock.json"))

        results = assess(str(repo))
        assert results["total_score"] >= 8
        assert results["ready"]


class TestFormatReport:

    def test_format_contains_score(self, repo):
        results = assess(str(repo))
        report = format_report(results)
        assert "0/12" in report
        assert "Ready:** No" in report
