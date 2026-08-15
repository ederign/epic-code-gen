"""Tests for check_dependencies.py."""

import json
import os
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from check_dependencies import check_dependencies, main  # noqa: E402


def _write_epic(tasks_dir, epic_id, jira_status=None, dependencies=None):
    """Write a minimal epic-task file.

    `status: Pending` is hardcoded on every file the way fetch_jira_epics.py
    writes them, so the tests exercise the field the gate must ignore.
    """
    os.makedirs(tasks_dir, exist_ok=True)
    lines = ["---", f"epic_id: {epic_id}", "status: Pending"]
    if jira_status is not None:
        lines.append(f"jira_status: {jira_status}")
    if dependencies:
        lines.append("dependencies:")
        lines += [f"  - {d}" for d in dependencies]
    else:
        lines.append("dependencies: []")
    lines += ["---", "", f"# {epic_id}", ""]
    path = os.path.join(tasks_dir, f"{epic_id}.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


class TestCheckDependencies:
    def test_no_dependencies_is_done(self, tmp_path):
        d = str(tmp_path)
        _write_epic(d, "RHAI-542", jira_status="In Progress")

        result = check_dependencies("RHAI-542", d)

        assert result["all_done"] is True
        assert result["dependencies"] == []

    @pytest.mark.parametrize("done_status", ["Done", "Closed", "Resolved"])
    def test_every_done_status_satisfies_the_gate(self, tmp_path, done_status):
        d = str(tmp_path)
        _write_epic(d, "RHAI-543", jira_status=done_status)
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])

        result = check_dependencies("RHAI-544", d)

        assert result["all_done"] is True
        assert result["dependencies"][0]["jira_status"] == done_status

    def test_unfinished_dependency_blocks(self, tmp_path):
        d = str(tmp_path)
        _write_epic(d, "RHAI-543", jira_status="In Progress")
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])

        result = check_dependencies("RHAI-544", d)

        assert result["all_done"] is False
        assert result["dependencies"][0]["done"] is False
        assert "In Progress" in result["dependencies"][0]["reason"]

    def test_pending_status_field_does_not_block_a_done_dependency(self, tmp_path):
        """The RHAI-544 regression.

        Every epic-task file carries `status: Pending`; the old gate read it and
        blocked an epic whose dependency was finished in Jira.
        """
        d = str(tmp_path)
        _write_epic(d, "RHAI-543", jira_status="Done")
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])

        assert check_dependencies("RHAI-544", d)["all_done"] is True

    def test_missing_dependency_file_blocks(self, tmp_path):
        d = str(tmp_path)
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])

        result = check_dependencies("RHAI-544", d)

        assert result["all_done"] is False
        assert result["dependencies"][0]["jira_status"] is None
        assert "no epic-task file" in result["dependencies"][0]["reason"]

    def test_dependency_without_jira_status_blocks(self, tmp_path):
        d = str(tmp_path)
        _write_epic(d, "RHAI-543")
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])

        assert check_dependencies("RHAI-544", d)["all_done"] is False

    def test_one_unfinished_among_several_blocks(self, tmp_path):
        d = str(tmp_path)
        _write_epic(d, "RHAI-541", jira_status="Done")
        _write_epic(d, "RHAI-542", jira_status="Closed")
        _write_epic(d, "RHAI-543", jira_status="Review")
        _write_epic(d, "RHAI-544",
                    dependencies=["RHAI-541", "RHAI-542", "RHAI-543"])

        result = check_dependencies("RHAI-544", d)

        assert result["all_done"] is False
        assert [x["done"] for x in result["dependencies"]] == [True, True, False]

    def test_missing_epic_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            check_dependencies("RHAI-999", str(tmp_path))


class TestMain:
    def test_exit_zero_when_satisfied(self, tmp_path, monkeypatch):
        d = str(tmp_path)
        _write_epic(d, "RHAI-543", jira_status="Done")
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])
        monkeypatch.setattr(sys, "argv",
                            ["check_dependencies.py", "RHAI-544",
                             "--epic-tasks", d])

        assert main() == 0

    def test_exit_one_when_blocked(self, tmp_path, monkeypatch, capsys):
        d = str(tmp_path)
        _write_epic(d, "RHAI-543", jira_status="In Progress")
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])
        monkeypatch.setattr(sys, "argv",
                            ["check_dependencies.py", "RHAI-544",
                             "--epic-tasks", d])

        assert main() == 1
        assert "RHAI-543" in capsys.readouterr().err

    def test_exit_one_when_epic_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv",
                            ["check_dependencies.py", "RHAI-999",
                             "--epic-tasks", str(tmp_path)])

        assert main() == 1

    def test_json_output(self, tmp_path, monkeypatch, capsys):
        d = str(tmp_path)
        _write_epic(d, "RHAI-543", jira_status="Done")
        _write_epic(d, "RHAI-544", dependencies=["RHAI-543"])
        monkeypatch.setattr(sys, "argv",
                            ["check_dependencies.py", "RHAI-544",
                             "--epic-tasks", d, "--json"])

        assert main() == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["all_done"] is True
        assert payload["dependencies"][0]["epic_id"] == "RHAI-543"
