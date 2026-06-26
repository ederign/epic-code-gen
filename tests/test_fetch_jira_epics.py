"""Tests for fetch_jira_epics.py — Jira-direct fetch, DAG building, artifact generation."""

import json
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from artifact_utils import read_frontmatter_validated
from fetch_jira_epics import (
    build_dependency_dag,
    fetch_children,
    generate_epic_task_from_jira,
    generate_status_report,
    is_eligible,
    issue_to_epic_data,
)


# ─── Test Fixtures ────────────────────────────────────────────────────────────

def _make_issue(key, summary="Test issue", status="To Do",
                issuelinks=None, components=None, description=None):
    """Build a minimal Jira issue dict."""
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": status},
            "priority": {"name": "Major"},
            "issuelinks": issuelinks or [],
            "components": [{"name": c} for c in (components or [])],
            "description": description,
        },
    }


def _blocks_link(blocker_key=None, blocked_key=None):
    """Build a Blocks issue link.

    If blocker_key: the current issue is blocked BY blocker_key (inward).
    If blocked_key: the current issue blocks blocked_key (outward).
    """
    link = {"type": {"name": "Blocks"}}
    if blocker_key:
        link["inwardIssue"] = {"key": blocker_key}
    if blocked_key:
        link["outwardIssue"] = {"key": blocked_key}
    return link


# ─── fetch_children ───────────────────────────────────────────────────────────

class TestFetchChildren:

    @mock.patch("fetch_jira_epics.search_issues")
    def test_calls_search_with_correct_jql(self, mock_search):
        mock_search.return_value = []
        fetch_children("https://jira.example.com", "u", "t", "RHAISTRAT-1699")
        mock_search.assert_called_once()
        args = mock_search.call_args
        assert args[0][3] == "parent = RHAISTRAT-1699 ORDER BY key ASC"

    @mock.patch("fetch_jira_epics.search_issues")
    def test_requests_expected_fields(self, mock_search):
        mock_search.return_value = []
        fetch_children("https://jira.example.com", "u", "t", "RHAISTRAT-1699")
        fields = mock_search.call_args[1].get("fields") or mock_search.call_args[0][4]
        assert "summary" in fields
        assert "issuelinks" in fields
        assert "description" in fields

    @mock.patch("fetch_jira_epics.search_issues")
    def test_returns_issues(self, mock_search):
        issues = [_make_issue("RHOAIENG-1"), _make_issue("RHOAIENG-2")]
        mock_search.return_value = issues
        result = fetch_children("s", "u", "t", "RHAISTRAT-1")
        assert len(result) == 2


# ─── build_dependency_dag ─────────────────────────────────────────────────────

class TestBuildDependencyDag:

    def test_two_issues_with_blocks_link(self):
        issues = [
            _make_issue("RHOAIENG-1", issuelinks=[
                _blocks_link(blocked_key="RHOAIENG-2"),
            ]),
            _make_issue("RHOAIENG-2", issuelinks=[
                _blocks_link(blocker_key="RHOAIENG-1"),
            ]),
        ]
        dag = build_dependency_dag(issues)
        assert dag["RHOAIENG-1"]["blocks"] == ["RHOAIENG-2"]
        assert dag["RHOAIENG-1"]["dependencies"] == []
        assert dag["RHOAIENG-2"]["dependencies"] == ["RHOAIENG-1"]
        assert dag["RHOAIENG-2"]["blocks"] == []

    def test_no_links(self):
        issues = [_make_issue("RHOAIENG-1"), _make_issue("RHOAIENG-2")]
        dag = build_dependency_dag(issues)
        assert dag["RHOAIENG-1"]["dependencies"] == []
        assert dag["RHOAIENG-1"]["blocks"] == []
        assert dag["RHOAIENG-2"]["dependencies"] == []

    def test_non_sibling_links_ignored(self):
        issues = [
            _make_issue("RHOAIENG-1", issuelinks=[
                _blocks_link(blocked_key="EXTERNAL-999"),
            ]),
        ]
        dag = build_dependency_dag(issues)
        assert dag["RHOAIENG-1"]["blocks"] == []

    def test_non_blocks_link_type_ignored(self):
        issues = [
            _make_issue("RHOAIENG-1", issuelinks=[
                {"type": {"name": "Cloners"},
                 "outwardIssue": {"key": "RHOAIENG-2"}},
            ]),
            _make_issue("RHOAIENG-2"),
        ]
        dag = build_dependency_dag(issues)
        assert dag["RHOAIENG-1"]["blocks"] == []

    def test_no_duplicate_entries(self):
        issues = [
            _make_issue("RHOAIENG-1", issuelinks=[
                _blocks_link(blocked_key="RHOAIENG-2"),
                _blocks_link(blocked_key="RHOAIENG-2"),
            ]),
            _make_issue("RHOAIENG-2"),
        ]
        dag = build_dependency_dag(issues)
        assert dag["RHOAIENG-1"]["blocks"] == ["RHOAIENG-2"]

    def test_chain_of_three(self):
        issues = [
            _make_issue("A-1", issuelinks=[_blocks_link(blocked_key="A-2")]),
            _make_issue("A-2", issuelinks=[
                _blocks_link(blocker_key="A-1"),
                _blocks_link(blocked_key="A-3"),
            ]),
            _make_issue("A-3", issuelinks=[_blocks_link(blocker_key="A-2")]),
        ]
        dag = build_dependency_dag(issues)
        assert dag["A-1"]["blocks"] == ["A-2"]
        assert dag["A-2"]["dependencies"] == ["A-1"]
        assert dag["A-2"]["blocks"] == ["A-3"]
        assert dag["A-3"]["dependencies"] == ["A-2"]


# ─── issue_to_epic_data ──────────────────────────────────────────────────────

class TestIssueToEpicData:

    def test_maps_basic_fields(self):
        issue = _make_issue("RHOAIENG-72103", summary="Add feature",
                            status="In Progress", components=["Dashboard"])
        dag = {"RHOAIENG-72103": {"dependencies": [], "blocks": ["RHOAIENG-72104"]}}
        result = issue_to_epic_data(issue, "RHAISTRAT-1699", dag)

        assert result["epic_id"] == "RHOAIENG-72103"
        assert result["title"] == "Add feature"
        assert result["strategy_key"] == "RHAISTRAT-1699"
        assert result["target_repo"] == ""
        assert result["status"] == "Pending"
        assert result["jira_status"] == "In Progress"
        assert result["components"] == ["Dashboard"]
        assert result["blocks"] == ["RHOAIENG-72104"]

    def test_empty_components_become_none(self):
        issue = _make_issue("RHOAIENG-1")
        dag = {"RHOAIENG-1": {"dependencies": [], "blocks": []}}
        result = issue_to_epic_data(issue, "RHAISTRAT-1", dag)
        assert result["components"] is None

    def test_empty_deps_become_none(self):
        issue = _make_issue("RHOAIENG-1")
        dag = {"RHOAIENG-1": {"dependencies": [], "blocks": []}}
        result = issue_to_epic_data(issue, "RHAISTRAT-1", dag)
        assert result["dependencies"] is None
        assert result["blocks"] is None

    def test_description_converted_to_markdown(self):
        adf = {
            "type": "doc", "version": 1,
            "content": [
                {"type": "paragraph",
                 "content": [{"type": "text", "text": "Hello world"}]}
            ],
        }
        issue = _make_issue("RHOAIENG-1", description=adf)
        dag = {"RHOAIENG-1": {"dependencies": [], "blocks": []}}
        result = issue_to_epic_data(issue, "RHAISTRAT-1", dag)
        assert "Hello world" in result["body"]

    def test_no_description_gives_empty_body(self):
        issue = _make_issue("RHOAIENG-1")
        dag = {"RHOAIENG-1": {"dependencies": [], "blocks": []}}
        result = issue_to_epic_data(issue, "RHAISTRAT-1", dag)
        assert result["body"] == ""

    def test_dependencies_sorted(self):
        issue = _make_issue("RHOAIENG-3")
        dag = {"RHOAIENG-3": {"dependencies": ["RHOAIENG-2", "RHOAIENG-1"],
                               "blocks": []}}
        result = issue_to_epic_data(issue, "RHAISTRAT-1", dag)
        assert result["dependencies"] == ["RHOAIENG-1", "RHOAIENG-2"]


# ─── generate_epic_task_from_jira ────────────────────────────────────────────

class TestGenerateEpicTask:

    def test_creates_file_with_valid_frontmatter(self, tmp_path):
        epic = {
            "epic_id": "RHOAIENG-72103",
            "title": "Add feature",
            "strategy_key": "RHAISTRAT-1699",
            "target_repo": "",
            "target_branch": "main",
            "status": "Pending",
            "jira_status": "To Do",
            "components": None,
            "dependencies": None,
            "blocks": ["RHOAIENG-72104"],
            "body": "## Description\n\nSome text.\n",
        }
        path = generate_epic_task_from_jira(epic, str(tmp_path))
        assert os.path.isfile(path)
        assert path.endswith("RHOAIENG-72103.md")

        data, body = read_frontmatter_validated(path, "epic-task")
        assert data["epic_id"] == "RHOAIENG-72103"
        assert data["blocks"] == ["RHOAIENG-72104"]
        assert data["jira_status"] == "To Do"
        assert "Some text." in body

    def test_empty_body(self, tmp_path):
        epic = {
            "epic_id": "RHOAIENG-1",
            "title": "Test",
            "strategy_key": "RHAISTRAT-1",
            "target_repo": "",
            "target_branch": "main",
            "status": "Pending",
            "jira_status": "To Do",
            "components": None,
            "dependencies": None,
            "blocks": None,
            "body": "",
        }
        path = generate_epic_task_from_jira(epic, str(tmp_path))
        data, body = read_frontmatter_validated(path, "epic-task")
        assert data["epic_id"] == "RHOAIENG-1"

    def test_creates_output_dir(self, tmp_path):
        epic = {
            "epic_id": "RHOAIENG-1",
            "title": "Test",
            "strategy_key": "RHAISTRAT-1",
            "target_repo": "",
            "target_branch": "main",
            "status": "Pending",
            "jira_status": None,
            "components": None,
            "dependencies": None,
            "blocks": None,
            "body": "",
        }
        output = str(tmp_path / "nested" / "dir")
        path = generate_epic_task_from_jira(epic, output)
        assert os.path.isfile(path)


# ─── is_eligible ──────────────────────────────────────────────────────────────

class TestIsEligible:

    def test_no_deps_not_done(self):
        epic = {"epic_id": "A-1", "jira_status": "To Do", "dependencies": None}
        eligible, reason = is_eligible(epic, {})
        assert eligible is True
        assert reason == "Ready"

    def test_done_not_eligible(self):
        epic = {"epic_id": "A-1", "jira_status": "Done", "dependencies": None}
        eligible, reason = is_eligible(epic, {})
        assert eligible is False
        assert "Already done" in reason

    def test_closed_not_eligible(self):
        epic = {"epic_id": "A-1", "jira_status": "Closed", "dependencies": None}
        eligible, _ = is_eligible(epic, {})
        assert eligible is False

    def test_resolved_not_eligible(self):
        epic = {"epic_id": "A-1", "jira_status": "Resolved", "dependencies": None}
        eligible, _ = is_eligible(epic, {})
        assert eligible is False

    def test_blocked_by_undone_dep(self):
        epic = {"epic_id": "A-2", "jira_status": "To Do",
                "dependencies": ["A-1"]}
        all_epics = {"A-1": {"epic_id": "A-1", "jira_status": "In Progress"}}
        eligible, reason = is_eligible(epic, all_epics)
        assert eligible is False
        assert "A-1" in reason

    def test_all_deps_done(self):
        epic = {"epic_id": "A-2", "jira_status": "To Do",
                "dependencies": ["A-1"]}
        all_epics = {"A-1": {"epic_id": "A-1", "jira_status": "Done"}}
        eligible, reason = is_eligible(epic, all_epics)
        assert eligible is True

    def test_multiple_deps_one_undone(self):
        epic = {"epic_id": "A-3", "jira_status": "To Do",
                "dependencies": ["A-1", "A-2"]}
        all_epics = {
            "A-1": {"epic_id": "A-1", "jira_status": "Done"},
            "A-2": {"epic_id": "A-2", "jira_status": "To Do"},
        }
        eligible, reason = is_eligible(epic, all_epics)
        assert eligible is False
        assert "A-2" in reason
        assert "A-1" not in reason


# ─── generate_status_report ──────────────────────────────────────────────────

class TestGenerateStatusReport:

    def _sample_epics(self):
        return [
            {"epic_id": "RHOAIENG-1", "title": "Impl feature",
             "strategy_key": "RHAISTRAT-1", "jira_status": "To Do",
             "dependencies": None, "blocks": ["RHOAIENG-2"]},
            {"epic_id": "RHOAIENG-2", "title": "Write docs",
             "strategy_key": "RHAISTRAT-1", "jira_status": "To Do",
             "dependencies": ["RHOAIENG-1"], "blocks": None},
        ]

    def test_creates_html_file(self, tmp_path):
        path = generate_status_report(
            self._sample_epics(), "RHAISTRAT-1", str(tmp_path))
        assert os.path.isfile(path)
        assert path.endswith("-status.html")

    def test_contains_strategy_key(self, tmp_path):
        path = generate_status_report(
            self._sample_epics(), "RHAISTRAT-1", str(tmp_path))
        with open(path) as f:
            content = f.read()
        assert "RHAISTRAT-1" in content

    def test_contains_task_keys(self, tmp_path):
        path = generate_status_report(
            self._sample_epics(), "RHAISTRAT-1", str(tmp_path))
        with open(path) as f:
            content = f.read()
        assert "RHOAIENG-1" in content
        assert "RHOAIENG-2" in content

    def test_contains_mermaid_dag(self, tmp_path):
        path = generate_status_report(
            self._sample_epics(), "RHAISTRAT-1", str(tmp_path))
        with open(path) as f:
            content = f.read()
        assert "graph TD" in content
        assert "RHOAIENG-1" in content

    def test_shows_eligibility(self, tmp_path):
        path = generate_status_report(
            self._sample_epics(), "RHAISTRAT-1", str(tmp_path))
        with open(path) as f:
            content = f.read()
        assert "Eligible" in content
        assert "Blocked" in content

    def test_creates_output_dir(self, tmp_path):
        output = str(tmp_path / "nested" / "reports")
        path = generate_status_report(
            self._sample_epics(), "RHAISTRAT-1", output)
        assert os.path.isfile(path)
