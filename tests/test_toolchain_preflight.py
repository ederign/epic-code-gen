"""Tests for toolchain preflight and unrunnable-check detection.

A missing tool must be reported as "could not run", never as a failing
check — conflating the two turns an environment fault into a code-quality
score, which is how a missing uv became lint=5.0 on a real PR.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from artifact_utils import validation_document_status
from validate_target import (
    _extract_missing_tool,
    _parse_makefile_rules,
    _parse_makefile_vars,
    _tools_in_recipe_line,
    detect_required_tools,
    preflight,
    run_check,
    tools_for_target,
    validate,
)


KALE_STYLE_MAKEFILE = """\
UV := uv
JLPM := $(UV) run jlpm

.PHONY: lint test docker-build

lint: lint-backend lint-labextension

lint-backend:
\t@printf "Linting backend...\\n"
\t$(UV) run ruff check kale
\t$(UV) run ruff format --check kale

lint-labextension:
\tcd labextension && $(JLPM) run eslint:check

test: test-backend

test-backend:
\t$(UV) run pytest kale/tests

docker-build:
\tdocker build -t kale .
"""

# Verbatim shape of kale's real self-install guard, continuation lines and all.
KALE_SELF_INSTALL_MAKEFILE = """\
UV := uv

check-uv:
\t@command -v $(UV) >/dev/null 2>&1 || { \\
\t\tprintf "uv not found. Installing...\\n"; \\
\t\tcurl -LsSf https://astral.sh/uv/install.sh | sh; \\
\t}
"""


class TestMakefileVarExpansion:

    def test_expands_nested_variables(self):
        variables = _parse_makefile_vars(KALE_STYLE_MAKEFILE)
        assert variables["UV"] == "uv"
        tools = _tools_in_recipe_line("cd labextension && $(JLPM) install",
                                      variables)
        # JLPM := $(UV) run jlpm — resolves to uv, two levels deep.
        assert "uv" in tools

    def test_strips_make_line_prefixes(self):
        tools = _tools_in_recipe_line("@ruff check .", {})
        assert tools == ["ruff"]

    def test_ignores_shell_builtins(self):
        tools = _tools_in_recipe_line('@printf "hello\\n"', {})
        assert tools == []

    def test_ignores_unexpanded_variables(self):
        """An unresolved $(FOO) is parsing noise and must not gate codegen."""
        tools = _tools_in_recipe_line("$(UNDEFINED_VAR) check", {})
        assert tools == []

    def test_skips_leading_env_assignments(self):
        tools = _tools_in_recipe_line("SKIP_HOOK=1 uv sync", {})
        assert tools == ["uv"]

    def test_drops_cd_prefix_and_finds_real_command(self):
        tools = _tools_in_recipe_line("cd sub && cargo build", {})
        assert "cargo" in tools
        assert "cd" not in tools


class TestFalsePositiveGuards:
    """A wrongly extracted tool blocks codegen on a healthy repo, so
    extraction must not require anything the recipe does not truly need."""

    @pytest.mark.parametrize("line", [
        # Repo-local script: never on PATH, so `lint.sh` would always "miss".
        "./scripts/lint.sh --strict",
        "scripts/lint.sh",
        # Failure explicitly swallowed — the recipe carries on without it.
        "optional-linter --check || true",
        "optional-linter --check || :",
        "cd sub && optional-linter --check || true",
        "optional-linter --check || fallback-linter || true",
        # make's `-` prefix ignores the recipe's exit status, 127 included.
        "-flaky-tool --check",
        "@-flaky-tool --check",
        # Tools live inside the virtualenv, not on the PATH we would search.
        ". .venv/bin/activate && pytest",
        "source venv/bin/activate && ruff check .",
        ". ./venv/bin/activate; pytest -q",
    ])
    def test_not_required(self, line):
        assert _tools_in_recipe_line(line, {}) == []

    def test_repo_local_script_present_is_still_not_required(self, tmp_path):
        """Even when the script exists, its basename is not a PATH tool."""
        script = tmp_path / "scripts" / "lint.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        assert _tools_in_recipe_line(
            "./scripts/lint.sh --strict", {}, str(tmp_path)) == []

    def test_absolute_path_is_resolved_not_looked_up_on_path(self):
        """`/usr/bin/env python3` must not turn into a required `env`."""
        assert _tools_in_recipe_line("/opt/nope/linter --check", {}) == []

    def test_tolerance_does_not_cross_a_semicolon(self):
        """`;` starts an independent command, which is still required."""
        tools = _tools_in_recipe_line("ruff check . || true; pytest", {})
        assert tools == ["pytest"]


class TestNoRegressionOnRealTools:
    """The tools these lines genuinely need must keep gating codegen."""

    @pytest.mark.parametrize("line,expected", [
        # bash IS the executable here; the script is only its argument.
        ("bash tools/check.sh", ["bash"]),
        ("SKIP_HOOK=1 uv sync", ["uv"]),
        ("cd sub && cargo build", ["cargo"]),
        ("$(UV) run pytest kale/tests -vv", ["uv"]),
        # Two-level expansion: JLPM := $(UV) run jlpm.
        ("cd labextension && $(JLPM) install", ["uv"]),
        # Unresolved variables are parsing noise, not tools.
        ("$(UNDEFINED_VAR) check", []),
    ])
    def test_extracts_expected_tools(self, line, expected):
        variables = _parse_makefile_vars(KALE_STYLE_MAKEFILE)
        assert _tools_in_recipe_line(line, variables) == expected

    def test_self_install_guard_needs_curl_and_sh_but_not_uv(self):
        """kale's `command -v $(UV) || { curl ... | sh; }` installs uv itself,
        so uv is only an argument here — requiring it would block wrongly."""
        variables = _parse_makefile_vars(KALE_SELF_INSTALL_MAKEFILE)
        rules = _parse_makefile_rules(KALE_SELF_INSTALL_MAKEFILE)
        tools = tools_for_target(rules, variables, "check-uv")
        assert "curl" in tools
        assert "sh" in tools
        assert "uv" not in tools


class TestToolsForTarget:

    def test_follows_prerequisites(self):
        variables = _parse_makefile_vars(KALE_STYLE_MAKEFILE)
        rules = _parse_makefile_rules(KALE_STYLE_MAKEFILE)
        # lint -> lint-backend + lint-labextension, both via $(UV).
        assert "uv" in tools_for_target(rules, variables, "lint")

    def test_unrelated_targets_are_not_inspected(self):
        """docker-build needs docker, but we never run it — must not gate."""
        variables = _parse_makefile_vars(KALE_STYLE_MAKEFILE)
        rules = _parse_makefile_rules(KALE_STYLE_MAKEFILE)
        assert "docker" not in tools_for_target(rules, variables, "lint")
        assert "docker" in tools_for_target(rules, variables, "docker-build")

    def test_recursion_terminates_on_cycle(self):
        content = "a: b\n\techo a\nb: a\n\techo b\n"
        variables = _parse_makefile_vars(content)
        rules = _parse_makefile_rules(content)
        assert tools_for_target(rules, variables, "a") == []


class TestDetectRequiredTools:

    def _write(self, tmp_path, **files):
        for name, content in files.items():
            path = tmp_path / name.replace("__", ".")
            path.write_text(content)
        return str(tmp_path)

    def test_finds_uv_from_makefile_recipe(self, tmp_path):
        repo = self._write(
            tmp_path, Makefile=KALE_STYLE_MAKEFILE,
            pyproject__toml="[project]\nname='x'\n")
        tools = detect_required_tools(repo, "python")
        assert "uv" in tools
        assert "make" in tools
        assert "python3" in tools

    def test_does_not_require_docker_for_lint(self, tmp_path):
        repo = self._write(
            tmp_path, Makefile=KALE_STYLE_MAKEFILE,
            pyproject__toml="[project]\nname='x'\n")
        assert "docker" not in detect_required_tools(repo, "python")

    def test_yarn_required_when_lockfile_present(self, tmp_path):
        repo = self._write(
            tmp_path, package__json='{"scripts":{"lint":"eslint ."}}',
            yarn__lock="")
        assert "yarn" in detect_required_tools(repo, "javascript")

    def test_no_makefile_still_returns_base_tools(self, tmp_path):
        repo = self._write(tmp_path, go__mod="module x\n")
        tools = detect_required_tools(repo, "go")
        assert "go" in tools
        assert "make" not in tools

    def test_repo_local_lint_script_does_not_gate(self, tmp_path):
        """A Makefile driving a repo-local script must not require `lint.sh`."""
        repo = self._write(
            tmp_path,
            Makefile="lint:\n\t./scripts/lint.sh --strict\n",
            pyproject__toml="[project]\nname='x'\n")
        tools = detect_required_tools(repo, "python")
        assert "lint.sh" not in tools

    def test_venv_activated_lint_does_not_gate(self, tmp_path):
        repo = self._write(
            tmp_path,
            Makefile="lint:\n\t. .venv/bin/activate && flake8 .\n",
            pyproject__toml="[project]\nname='x'\n")
        assert "flake8" not in detect_required_tools(repo, "python")

    def test_tools_are_deduplicated(self, tmp_path):
        repo = self._write(
            tmp_path, Makefile=KALE_STYLE_MAKEFILE,
            pyproject__toml="[project]\nname='x'\n")
        tools = detect_required_tools(repo, "python")
        assert len(tools) == len(set(tools))


class TestPreflight:

    def test_reports_ok_when_tools_present(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x\n")
        result = preflight(str(tmp_path))
        # git and go: git is certainly installed in any test environment.
        assert "git" in result["required"]
        assert isinstance(result["ok"], bool)

    def test_reports_missing_tool(self, tmp_path):
        (tmp_path / "Makefile").write_text(
            "lint:\n\tdefinitely-not-a-real-binary-xyz check\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        result = preflight(str(tmp_path))
        assert result["ok"] is False
        assert "definitely-not-a-real-binary-xyz" in result["missing"]

    def test_missing_repo_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            preflight(str(tmp_path / "nope"))


class TestUnrunnableDetection:

    def test_missing_command_is_unrunnable_not_failed(self, tmp_path):
        result = run_check(
            "definitely-not-a-real-binary-xyz --check", str(tmp_path))
        assert result["passed"] is False
        assert result["unrunnable"] is True
        assert result["exit_code"] in (126, 127)

    def test_real_failure_is_not_unrunnable(self, tmp_path):
        """A tool that ran and found problems must stay distinguishable."""
        result = run_check("python3 -c 'import sys; sys.exit(1)'",
                           str(tmp_path))
        assert result["passed"] is False
        assert result["unrunnable"] is False
        assert result["missing_tool"] is None

    def test_success_is_not_unrunnable(self, tmp_path):
        result = run_check("python3 -c 'pass'", str(tmp_path))
        assert result["passed"] is True
        assert result["unrunnable"] is False

    def test_extracts_tool_name_from_shell_error(self):
        assert _extract_missing_tool(
            "/bin/sh: line 1: uv: command not found") == "uv"
        assert _extract_missing_tool("make: uv: No such file or directory") \
            == "uv"

    def test_extract_returns_none_for_unrelated_output(self):
        assert _extract_missing_tool("3 errors found") is None


class TestValidateAggregation:

    def test_unrunnable_check_cannot_produce_a_pass(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "Makefile").write_text(
            "lint:\n\tdefinitely-not-a-real-binary-xyz check\n")
        result = validate(str(tmp_path))
        assert result["all_passed"] is False
        assert result["has_unrunnable"] is True
        assert "lint" in result["unrunnable"]

    def test_zero_discovered_checks_is_not_a_pass(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        result = validate(str(tmp_path), checks=["nonexistent-check"])
        assert result["all_passed"] is False


class TestMakeExitCodeHandling:
    """GNU make exits 2 and reports `Error 127`, so exit code alone is
    insufficient to spot a missing tool inside a recipe."""

    def test_make_recipe_missing_tool_is_unrunnable(self, tmp_path):
        (tmp_path / "Makefile").write_text(
            "lint:\n\tdefinitely-not-a-real-binary-xyz check\n")
        result = run_check("make lint", str(tmp_path))
        assert result["passed"] is False
        assert result["unrunnable"] is True
        assert result["missing_tool"] == "definitely-not-a-real-binary-xyz"

    def test_make_recipe_real_failure_is_not_unrunnable(self, tmp_path):
        """A recipe whose tool ran and exited non-zero is a real failure."""
        (tmp_path / "Makefile").write_text(
            "lint:\n\tpython3 -c 'import sys; sys.exit(1)'\n")
        result = run_check("make lint", str(tmp_path))
        assert result["passed"] is False
        assert result["unrunnable"] is False

    def test_missing_fixture_file_is_not_misread_as_unrunnable(self, tmp_path):
        """A test failing on a missing data file must stay a real failure,
        not be excused as an environment problem."""
        (tmp_path / "Makefile").write_text(
            "test:\n\tpython3 -c \"open('/nope/missing-fixture.json')\"\n")
        result = run_check("make test", str(tmp_path))
        assert result["passed"] is False
        assert result["unrunnable"] is False

    def test_does_not_extract_make_as_the_missing_tool(self):
        tool = _extract_missing_tool(
            "make: definitely-not-real: No such file or directory")
        assert tool == "definitely-not-real"


class TestValidationDocumentStatus:
    """Classifying a validation.json by whether validate_target.py wrote it."""

    def test_genuine_document_is_ok(self, tmp_path):
        p = tmp_path / "validation.json"
        p.write_text(json.dumps({"all_passed": True, "checks": []}))
        status, detail = validation_document_status(str(p))
        assert status == "ok"
        assert detail is None

    def test_rhai75_shaped_document_is_foreign(self, tmp_path):
        """The real hand-written document that let Prettier through."""
        p = tmp_path / "validation.json"
        p.write_text(json.dumps({
            "tests_total": 35, "tests_passed": 35, "success": True}))
        status, detail = validation_document_status(str(p))
        assert status == "foreign"
        assert "all_passed" in detail and "checks" in detail
        # The message must say how to fix it.
        assert "--out" in detail

    def test_partial_document_is_foreign(self, tmp_path):
        p = tmp_path / "validation.json"
        p.write_text(json.dumps({"all_passed": True}))
        assert validation_document_status(str(p))[0] == "foreign"

    def test_absent_file_is_missing(self, tmp_path):
        status, _ = validation_document_status(str(tmp_path / "nope.json"))
        assert status == "missing"

    def test_malformed_json_is_unreadable(self, tmp_path):
        p = tmp_path / "validation.json"
        p.write_text("{not json")
        assert validation_document_status(str(p))[0] == "unreadable"

    def test_json_array_is_foreign(self, tmp_path):
        p = tmp_path / "validation.json"
        p.write_text("[]")
        assert validation_document_status(str(p))[0] == "foreign"


class TestValidateOutFlag:
    """--out must write the canonical document, so the skill never needs a
    shell redirection it could replace with a hand-rolled file."""

    def test_out_writes_canonical_document(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "go.mod").write_text("module x\n")
        out = tmp_path / "nested" / "validation.json"

        subprocess.run(
            [sys.executable,
             os.path.join(os.path.dirname(__file__), "..", "scripts",
                          "validate_target.py"),
             str(repo), "--out", str(out)],
            capture_output=True, text=True, timeout=300)

        assert out.is_file()
        assert validation_document_status(str(out))[0] == "ok"
