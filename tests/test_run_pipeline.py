"""Tests for run_pipeline.py — pipeline orchestrator."""

import json
import os
import subprocess
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from run_pipeline import (
    BLOCKED,
    FAILED,
    PROCESSED,
    SKIPPED,
    build_run_log,
    clean_artifacts,
    find_eligible,
    link_pr_to_jira,
    load_repo_mapping,
    read_pr_url,
    resolve_repo_via_llm,
    resolve_target_repo,
    transition_issue,
    invoke_codegen,
    parse_args,
    print_summary,
    process_strategy,
    write_run_log,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _epic(epic_id, jira_status="New", dependencies=None, blocks=None,
          title=None):
    """Build a minimal epic data dict."""
    return {
        "epic_id": epic_id,
        "title": title or f"Epic {epic_id}",
        "strategy_key": "RHAISTRAT-1",
        "target_repo": "",
        "target_branch": "main",
        "status": "Pending",
        "jira_status": jira_status,
        "components": None,
        "dependencies": dependencies,
        "blocks": blocks,
        "body": "",
    }


def _make_args(**overrides):
    """Build a mock args namespace."""
    defaults = {
        "keys": ["RHAISTRAT-1"],
        "dry_run": False,
        "run_script": None,
        "max_iterations": None,
        "fork_owner": None,
        "no_clean": False,
        "output_dir": "artifacts",
        "report_dir": "epic-reports",
        "log_dir": "pipeline-runs",
        "timeout": 3600,
        "no_strategy": True,
        "no_report": True,
    }
    defaults.update(overrides)
    return mock.MagicMock(**defaults)


# ─── TestFindEligible ─────────────────────────────────────────────────────────

class TestFindEligible:

    def test_no_deps_all_eligible(self):
        epics = {
            "A-1": _epic("A-1"),
            "A-2": _epic("A-2"),
            "A-3": _epic("A-3"),
        }
        result = find_eligible(epics, completed_keys=set(), handled_keys=set())
        assert result == ["A-1", "A-2", "A-3"]

    def test_dep_chain_first_only(self):
        epics = {
            "A-1": _epic("A-1"),
            "A-2": _epic("A-2", dependencies=["A-1"]),
            "A-3": _epic("A-3", dependencies=["A-2"]),
        }
        result = find_eligible(epics, completed_keys=set(), handled_keys=set())
        assert result == ["A-1"]

    def test_completed_dep_unblocks(self):
        epics = {
            "A-1": _epic("A-1"),
            "A-2": _epic("A-2", dependencies=["A-1"]),
        }
        result = find_eligible(
            epics, completed_keys={"A-1"}, handled_keys={"A-1"})
        assert result == ["A-2"]

    def test_already_handled_excluded(self):
        epics = {
            "A-1": _epic("A-1"),
            "A-2": _epic("A-2"),
        }
        result = find_eligible(
            epics, completed_keys=set(), handled_keys={"A-1"})
        assert result == ["A-2"]

    def test_empty_epics(self):
        result = find_eligible({}, completed_keys=set(), handled_keys=set())
        assert result == []

    def test_multiple_deps_all_must_be_completed(self):
        epics = {
            "A-1": _epic("A-1"),
            "A-2": _epic("A-2"),
            "A-3": _epic("A-3", dependencies=["A-1", "A-2"]),
        }
        result = find_eligible(
            epics, completed_keys={"A-1"}, handled_keys={"A-1"})
        assert "A-3" not in result
        assert "A-2" in result

    def test_returns_sorted(self):
        epics = {
            "C-1": _epic("C-1"),
            "A-1": _epic("A-1"),
            "B-1": _epic("B-1"),
        }
        result = find_eligible(epics, completed_keys=set(), handled_keys=set())
        assert result == ["A-1", "B-1", "C-1"]


# ─── TestProcessStrategy ─────────────────────────────────────────────────────

class TestProcessStrategy:

    @mock.patch("run_pipeline.transition_issue", return_value=(True, ""))
    @mock.patch("run_pipeline.invoke_codegen", return_value=True)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_linear_chain_processes_first_only(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        """A→B chain: only A is eligible (B blocked by A)."""
        issues = [{"key": "A-1", "fields": {}}, {"key": "A-2", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {
            "A-1": {"dependencies": [], "blocks": ["A-2"]},
            "A-2": {"dependencies": ["A-1"], "blocks": []},
        }

        with mock.patch("run_pipeline.issue_to_epic_data", side_effect=[
            _epic("A-1", blocks=["A-2"]),
            _epic("A-2", dependencies=["A-1"]),
        ]):
            args = _make_args(output_dir="/tmp/test-artifacts")
            epics, results, *_ = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        assert len(results[PROCESSED]) == 1
        assert results[PROCESSED][0][0] == "A-1"
        assert len(results[BLOCKED]) == 1
        assert results[BLOCKED][0][0] == "A-2"
        mock_invoke.assert_called_once_with("A-1", args)

    @mock.patch("run_pipeline.transition_issue", return_value=(True, ""))
    @mock.patch("run_pipeline.invoke_codegen", return_value=True)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_no_deps_all_eligible(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        """Two independent epics: both eligible."""
        issues = [{"key": "A-1", "fields": {}}, {"key": "A-2", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {
            "A-1": {"dependencies": [], "blocks": []},
            "A-2": {"dependencies": [], "blocks": []},
        }

        with mock.patch("run_pipeline.issue_to_epic_data", side_effect=[
            _epic("A-1"), _epic("A-2"),
        ]):
            args = _make_args(output_dir="/tmp/test-artifacts")
            epics, results, *_ = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        assert len(results[PROCESSED]) == 2
        assert len(results[BLOCKED]) == 0

    @mock.patch("run_pipeline.transition_issue", return_value=(True, ""))
    @mock.patch("run_pipeline.invoke_codegen", return_value=False)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_failure_blocks_dependents(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        """A fails → B stays blocked."""
        issues = [{"key": "A-1", "fields": {}}, {"key": "A-2", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {
            "A-1": {"dependencies": [], "blocks": ["A-2"]},
            "A-2": {"dependencies": ["A-1"], "blocks": []},
        }

        with mock.patch("run_pipeline.issue_to_epic_data", side_effect=[
            _epic("A-1", blocks=["A-2"]),
            _epic("A-2", dependencies=["A-1"]),
        ]):
            args = _make_args(output_dir="/tmp/test-artifacts")
            epics, results, *_ = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        assert len(results[FAILED]) == 1
        assert results[FAILED][0][0] == "A-1"
        assert len(results[BLOCKED]) == 1
        assert results[BLOCKED][0][0] == "A-2"

    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_all_done_in_jira(self, mock_gen, mock_dag, mock_fetch):
        """All epics already Done → all skipped."""
        issues = [{"key": "A-1", "fields": {}}, {"key": "A-2", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {
            "A-1": {"dependencies": [], "blocks": []},
            "A-2": {"dependencies": [], "blocks": []},
        }

        with mock.patch("run_pipeline.issue_to_epic_data", side_effect=[
            _epic("A-1", jira_status="Done"),
            _epic("A-2", jira_status="Closed"),
        ]):
            args = _make_args(output_dir="/tmp/test-artifacts")
            epics, results, *_ = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        assert len(results[SKIPPED]) == 2
        assert len(results[PROCESSED]) == 0
        assert len(results[BLOCKED]) == 0

    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_dry_run_skips_invocation(self, mock_gen, mock_dag, mock_fetch):
        """Dry run: epics marked processed but no subprocess call."""
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(dry_run=True, output_dir="/tmp/test-artifacts")
            epics, results, *_ = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        assert len(results[PROCESSED]) == 1
        assert results[PROCESSED][0][1] == "dry-run"

    @mock.patch("run_pipeline.fetch_children", return_value=[])
    def test_no_children(self, mock_fetch):
        """Strategy with no children → empty results."""
        args = _make_args(output_dir="/tmp/test-artifacts")
        epics, results, transitions_log, pr_urls = process_strategy(
            "RHAISTRAT-1", "s", "u", "t", args)
        assert epics == []
        assert all(len(v) == 0 for v in results.values())
        assert transitions_log == {}
        assert pr_urls == {}

    @mock.patch("run_pipeline.transition_issue", return_value=(True, ""))
    @mock.patch("run_pipeline.invoke_codegen")
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_mixed_results(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        """One done, one eligible succeeds, one eligible fails, one blocked."""
        issues = [{"key": f"A-{i}", "fields": {}} for i in range(1, 5)]
        mock_fetch.return_value = issues
        mock_dag.return_value = {
            "A-1": {"dependencies": [], "blocks": []},
            "A-2": {"dependencies": [], "blocks": []},
            "A-3": {"dependencies": [], "blocks": ["A-4"]},
            "A-4": {"dependencies": ["A-3"], "blocks": []},
        }

        with mock.patch("run_pipeline.issue_to_epic_data", side_effect=[
            _epic("A-1", jira_status="Done"),
            _epic("A-2"),
            _epic("A-3", blocks=["A-4"]),
            _epic("A-4", dependencies=["A-3"]),
        ]):
            mock_invoke.side_effect = [True, False]
            args = _make_args(output_dir="/tmp/test-artifacts")
            epics, results, *_ = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        assert len(results[SKIPPED]) == 1
        assert len(results[PROCESSED]) == 1
        assert len(results[FAILED]) == 1
        assert len(results[BLOCKED]) == 1


# ─── TestInvokeCodegen ────────────────────────────────────────────────────────

class TestInvokeCodegen:

    @mock.patch("run_pipeline.subprocess.run")
    def test_direct_mode_command(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=0)
        args = _make_args()
        result = invoke_codegen("RHOAIENG-72103", args)

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "/epic-codegen RHOAIENG-72103" in cmd
        assert "--dangerously-skip-permissions" in cmd

    @mock.patch("run_pipeline.subprocess.run")
    def test_ci_mode_command(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=0)
        args = _make_args(run_script="ci-scripts/run-claude.sh")
        result = invoke_codegen("RHOAIENG-72103", args)

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "bash"
        assert cmd[1] == "ci-scripts/run-claude.sh"
        assert "/epic-codegen RHOAIENG-72103" in cmd[2]

    @mock.patch("run_pipeline.subprocess.run")
    def test_passes_max_iterations(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=0)
        args = _make_args(max_iterations=5)
        invoke_codegen("A-1", args)

        cmd = mock_run.call_args[0][0]
        skill_arg = cmd[2]  # -p argument
        assert "--max-iterations 5" in skill_arg

    @mock.patch("run_pipeline.subprocess.run")
    def test_passes_fork_owner(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=0)
        args = _make_args(fork_owner="dora-the-ai-coder")
        invoke_codegen("A-1", args)

        cmd = mock_run.call_args[0][0]
        skill_arg = cmd[2]  # -p argument
        assert "--fork-owner dora-the-ai-coder" in skill_arg

    @mock.patch("run_pipeline.subprocess.run")
    def test_nonzero_exit_returns_false(self, mock_run):
        mock_run.return_value = mock.MagicMock(returncode=1)
        args = _make_args()
        result = invoke_codegen("A-1", args)
        assert result is False

    @mock.patch("run_pipeline.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=10))
    def test_timeout_returns_false(self, mock_run):
        args = _make_args(timeout=10)
        result = invoke_codegen("A-1", args)
        assert result is False

    @mock.patch("run_pipeline.subprocess.run",
                side_effect=FileNotFoundError("claude"))
    def test_command_not_found_returns_false(self, mock_run):
        args = _make_args()
        result = invoke_codegen("A-1", args)
        assert result is False


# ─── TestCleanArtifacts ───────────────────────────────────────────────────────

class TestCleanArtifacts:

    def test_wipes_epic_tasks_and_strategies(self, tmp_path):
        output_dir = str(tmp_path / "artifacts")
        et = os.path.join(output_dir, "epic-tasks")
        st = os.path.join(output_dir, "strategies")
        os.makedirs(et)
        os.makedirs(st)
        with open(os.path.join(et, "test.md"), "w") as f:
            f.write("test")
        with open(os.path.join(st, "test.md"), "w") as f:
            f.write("test")

        clean_artifacts(output_dir)

        assert os.path.isdir(et)
        assert os.path.isdir(st)
        assert os.listdir(et) == []
        assert os.listdir(st) == []

    def test_preserves_codegen_runs(self, tmp_path):
        output_dir = str(tmp_path / "artifacts")
        cr = os.path.join(output_dir, "codegen-runs")
        os.makedirs(cr)
        with open(os.path.join(cr, "run.yaml"), "w") as f:
            f.write("test")

        clean_artifacts(output_dir)

        assert os.path.isfile(os.path.join(cr, "run.yaml"))

    def test_creates_dirs_if_missing(self, tmp_path):
        output_dir = str(tmp_path / "artifacts")

        clean_artifacts(output_dir)

        assert os.path.isdir(os.path.join(output_dir, "epic-tasks"))
        assert os.path.isdir(os.path.join(output_dir, "strategies"))


# ─── TestBuildRunLog ──────────────────────────────────────────────────────────

class TestBuildRunLog:

    def test_captures_all_epics_with_actions(self):
        from datetime import datetime, timezone
        epics = [_epic("A-1"), _epic("A-2", dependencies=["A-1"])]
        results = {
            PROCESSED: [("A-1", "codegen completed")],
            SKIPPED: [],
            BLOCKED: [("A-2", "Blocked by A-1")],
            FAILED: [],
        }
        transitions_log = {"A-1": [{"to": "In Progress", "success": True}]}
        start = datetime(2026, 6, 26, 20, 0, 0, tzinfo=timezone.utc)
        log = build_run_log({"RHAISTRAT-1": (epics, results, transitions_log, {})}, start)

        strat = log["strategies"]["RHAISTRAT-1"]
        assert "A-1" in strat["epics"]
        assert "A-2" in strat["epics"]
        assert strat["epics"]["A-1"]["action"] == PROCESSED
        assert strat["epics"]["A-1"]["result"] == "success"
        assert strat["epics"]["A-2"]["action"] == BLOCKED

    def test_includes_strategy_summary_counts(self):
        from datetime import datetime, timezone
        epics = [_epic("A-1"), _epic("A-2", jira_status="Done")]
        results = {
            PROCESSED: [("A-1", "codegen completed")],
            SKIPPED: [("A-2", "Already done")],
            BLOCKED: [],
            FAILED: [],
        }
        start = datetime(2026, 6, 26, 20, 0, 0, tzinfo=timezone.utc)
        log = build_run_log({"RHAISTRAT-1": (epics, results, {}, {})}, start)

        summary = log["strategies"]["RHAISTRAT-1"]["summary"]
        assert summary[PROCESSED] == 1
        assert summary[SKIPPED] == 1
        assert summary[BLOCKED] == 0
        assert summary[FAILED] == 0

    def test_multiple_strategies(self):
        from datetime import datetime, timezone
        epics_a = [_epic("A-1")]
        results_a = {
            PROCESSED: [("A-1", "done")], SKIPPED: [],
            BLOCKED: [], FAILED: [],
        }
        epics_b = [_epic("B-1")]
        results_b = {
            PROCESSED: [], SKIPPED: [],
            BLOCKED: [], FAILED: [("B-1", "failed")],
        }
        start = datetime(2026, 6, 26, 20, 0, 0, tzinfo=timezone.utc)
        log = build_run_log({
            "RHAISTRAT-1": (epics_a, results_a, {}, {}),
            "RHAISTRAT-2": (epics_b, results_b, {}, {}),
        }, start)

        assert "RHAISTRAT-1" in log["strategies"]
        assert "RHAISTRAT-2" in log["strategies"]

    def test_run_id_format(self):
        from datetime import datetime, timezone
        start = datetime(2026, 6, 26, 20, 30, 0, tzinfo=timezone.utc)
        log = build_run_log({}, start)
        assert log["run_id"] == "2026-06-26T20-30-00Z"

    def test_dry_run_result(self):
        from datetime import datetime, timezone
        epics = [_epic("A-1")]
        results = {
            PROCESSED: [("A-1", "dry-run")], SKIPPED: [],
            BLOCKED: [], FAILED: [],
        }
        start = datetime(2026, 6, 26, 20, 0, 0, tzinfo=timezone.utc)
        log = build_run_log({"RHAISTRAT-1": (epics, results, {}, {})}, start)

        assert log["strategies"]["RHAISTRAT-1"]["epics"]["A-1"]["result"] == "dry-run"


# ─── TestWriteRunLog ──────────────────────────────────────────────────────────

class TestWriteRunLog:

    def test_writes_json_file(self, tmp_path):
        log = {
            "run_id": "2026-06-26T20-30-00Z",
            "start_time": "2026-06-26T20:30:00+00:00",
            "end_time": "2026-06-26T21:00:00+00:00",
            "strategies": {},
        }
        path = write_run_log(log, str(tmp_path / "pipeline-runs"))

        assert os.path.isfile(path)
        assert path.endswith("2026-06-26T20-30-00Z.json")
        with open(path) as f:
            data = json.load(f)
        assert data["run_id"] == "2026-06-26T20-30-00Z"

    def test_creates_output_dir(self, tmp_path):
        log = {"run_id": "test", "strategies": {}}
        out_dir = str(tmp_path / "new-dir")
        path = write_run_log(log, out_dir)
        assert os.path.isdir(out_dir)
        assert os.path.isfile(path)


# ─── TestParseArgs ────────────────────────────────────────────────────────────

class TestParseArgs:

    def test_single_key(self):
        args = parse_args(["RHAISTRAT-1699"])
        assert args.keys == ["RHAISTRAT-1699"]
        assert args.dry_run is False
        assert args.no_clean is False
        assert args.timeout == 3600

    def test_multiple_keys(self):
        args = parse_args(["RHAISTRAT-1699", "RHAISTRAT-1700"])
        assert args.keys == ["RHAISTRAT-1699", "RHAISTRAT-1700"]

    def test_dry_run(self):
        args = parse_args(["RHAISTRAT-1", "--dry-run"])
        assert args.dry_run is True

    def test_all_options(self):
        args = parse_args([
            "RHAISTRAT-1",
            "--dry-run",
            "--run-script", "run.sh",
            "--max-iterations", "5",
            "--fork-owner", "dora",
            "--no-clean",
            "--timeout", "600",
            "--no-report",
            "--no-strategy",
        ])
        assert args.run_script == "run.sh"
        assert args.max_iterations == 5
        assert args.fork_owner == "dora"
        assert args.no_clean is True
        assert args.timeout == 600
        assert args.no_report is True
        assert args.no_strategy is True


# ─── TestLoadRepoMapping ─────────────────────────────────────────────────────

class TestLoadRepoMapping:

    def test_loads_json_file(self, tmp_path):
        mapping = {"org/repo": {"keywords": ["test"]}}
        path = tmp_path / "mapping.json"
        with open(path, "w") as f:
            json.dump(mapping, f)

        result = load_repo_mapping(str(path))
        assert result == mapping

    def test_missing_file_returns_empty(self, tmp_path):
        result = load_repo_mapping(str(tmp_path / "nonexistent.json"))
        assert result == {}


# ─── TestResolveTargetRepo ───────────────────────────────────────────────────

class TestResolveTargetRepo:

    _MAPPING = {
        "opendatahub-io/odh-dashboard": {
            "keywords": ["dashboard", "frontend", "patternfly", "ui"]
        },
    }

    def test_matches_keyword_in_title(self):
        epic = _epic("A-1", title="Update dashboard component")
        result = resolve_target_repo(epic, self._MAPPING)
        assert result == "opendatahub-io/odh-dashboard"

    def test_matches_keyword_in_body(self):
        epic = _epic("A-1", title="Some feature")
        epic["body"] = "This uses PatternFly components for the form"
        result = resolve_target_repo(epic, self._MAPPING)
        assert result == "opendatahub-io/odh-dashboard"

    def test_case_insensitive(self):
        epic = _epic("A-1", title="DASHBOARD changes needed")
        result = resolve_target_repo(epic, self._MAPPING)
        assert result == "opendatahub-io/odh-dashboard"

    def test_empty_mapping_returns_empty(self):
        epic = _epic("A-1", title="Dashboard work")
        result = resolve_target_repo(epic, {})
        assert result == ""

    @mock.patch("run_pipeline.resolve_repo_via_llm", return_value="")
    def test_no_match_calls_llm(self, mock_llm):
        epic = _epic("A-1", title="Update operator controller")
        result = resolve_target_repo(epic, self._MAPPING)
        mock_llm.assert_called_once()
        assert result == ""

    @mock.patch("run_pipeline.resolve_repo_via_llm",
                return_value="opendatahub-io/odh-dashboard")
    def test_multiple_matches_calls_llm(self, mock_llm):
        mapping = {
            "opendatahub-io/odh-dashboard": {"keywords": ["dashboard"]},
            "opendatahub-io/other-repo": {"keywords": ["dashboard"]},
        }
        epic = _epic("A-1", title="Fix dashboard bug")
        result = resolve_target_repo(epic, mapping)
        mock_llm.assert_called_once()
        assert result == "opendatahub-io/odh-dashboard"

    @mock.patch("run_pipeline.subprocess.run")
    def test_llm_returns_valid_repo(self, mock_run, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text(
            "Title: {epic_title}\nDesc: {epic_description}\n"
            "Repos: {available_repos}")
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout="opendatahub-io/odh-dashboard\n")
        epic = _epic("A-1", title="Some operator work")

        result = resolve_repo_via_llm(
            epic, self._MAPPING, str(prompt_file))
        assert result == "opendatahub-io/odh-dashboard"

    @mock.patch("run_pipeline.subprocess.run")
    def test_llm_returns_none(self, mock_run, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text(
            "Title: {epic_title}\nDesc: {epic_description}\n"
            "Repos: {available_repos}")
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout="NONE\n")
        epic = _epic("A-1", title="Unknown work")

        result = resolve_repo_via_llm(
            epic, self._MAPPING, str(prompt_file))
        assert result == ""

    @mock.patch("run_pipeline.subprocess.run")
    def test_llm_returns_unknown_repo(self, mock_run, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text(
            "Title: {epic_title}\nDesc: {epic_description}\n"
            "Repos: {available_repos}")
        mock_run.return_value = mock.MagicMock(
            returncode=0, stdout="some/unknown-repo\n")
        epic = _epic("A-1", title="Unknown work")

        result = resolve_repo_via_llm(
            epic, self._MAPPING, str(prompt_file))
        assert result == ""

    def test_llm_missing_prompt_returns_empty(self):
        epic = _epic("A-1", title="Unknown work")
        result = resolve_repo_via_llm(
            epic, self._MAPPING, "/nonexistent/prompt.md")
        assert result == ""


# ─── TestTransitionIssue ────────────────────────────────────────────────────

class TestTransitionIssue:

    _TRANSITIONS = [
        {"id": "11", "to": {"name": "In Progress"}},
        {"id": "21", "to": {"name": "In Review"}},
        {"id": "31", "to": {"name": "Done"}},
    ]

    @mock.patch("run_pipeline.do_transition")
    @mock.patch("run_pipeline.get_transitions")
    def test_finds_matching_transition(self, mock_get, mock_do):
        mock_get.return_value = self._TRANSITIONS
        ok, _ = transition_issue("s", "u", "t", "A-1", "In Progress")
        assert ok is True
        mock_do.assert_called_once_with("s", "u", "t", "A-1", "11")

    @mock.patch("run_pipeline.do_transition")
    @mock.patch("run_pipeline.get_transitions")
    def test_no_matching_transition(self, mock_get, mock_do):
        mock_get.return_value = self._TRANSITIONS
        ok, _ = transition_issue("s", "u", "t", "A-1", "Cancelled")
        assert ok is False
        mock_do.assert_not_called()

    @mock.patch("run_pipeline.do_transition")
    @mock.patch("run_pipeline.get_transitions")
    def test_case_insensitive_match(self, mock_get, mock_do):
        mock_get.return_value = self._TRANSITIONS
        ok, _ = transition_issue("s", "u", "t", "A-1", "in progress")
        assert ok is True
        mock_do.assert_called_once_with("s", "u", "t", "A-1", "11")

    @mock.patch("run_pipeline.get_transitions",
                side_effect=Exception("Connection refused"))
    def test_handles_api_error(self, mock_get):
        ok, _ = transition_issue("s", "u", "t", "A-1", "In Progress")
        assert ok is False

    @mock.patch("run_pipeline.do_transition",
                side_effect=Exception("403 Forbidden"))
    @mock.patch("run_pipeline.get_transitions")
    def test_handles_do_transition_error(self, mock_get, mock_do):
        mock_get.return_value = self._TRANSITIONS
        ok, _ = transition_issue("s", "u", "t", "A-1", "In Progress")
        assert ok is False


# ─── TestProcessStrategy transitions ────────────────────────────────────────

class TestProcessStrategyTransitions:

    @mock.patch("run_pipeline.transition_issue")
    @mock.patch("run_pipeline.invoke_codegen", return_value=True)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_transitions_to_in_progress_before_codegen(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        mock_trans.return_value = (True, "")
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(output_dir="/tmp/test-artifacts")
            process_strategy("RHAISTRAT-1", "s", "u", "t", args)

        calls = mock_trans.call_args_list
        assert calls[0] == mock.call("s", "u", "t", "A-1", "In Progress")

    @mock.patch("run_pipeline.transition_issue")
    @mock.patch("run_pipeline.invoke_codegen", return_value=True)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_transitions_to_in_review_after_success(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        mock_trans.return_value = (True, "")
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(output_dir="/tmp/test-artifacts")
            process_strategy("RHAISTRAT-1", "s", "u", "t", args)

        calls = mock_trans.call_args_list
        assert len(calls) == 2
        assert calls[1] == mock.call("s", "u", "t", "A-1", "In Review")

    @mock.patch("run_pipeline.transition_issue")
    @mock.patch("run_pipeline.invoke_codegen", return_value=False)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_no_review_transition_on_failure(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        mock_trans.return_value = (True, "")
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(output_dir="/tmp/test-artifacts")
            process_strategy("RHAISTRAT-1", "s", "u", "t", args)

        calls = mock_trans.call_args_list
        assert len(calls) == 1
        assert calls[0] == mock.call("s", "u", "t", "A-1", "In Progress")

    @mock.patch("run_pipeline.transition_issue")
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_dry_run_skips_transitions(
            self, mock_gen, mock_dag, mock_fetch, mock_trans):
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(dry_run=True, output_dir="/tmp/test-artifacts")
            process_strategy("RHAISTRAT-1", "s", "u", "t", args)

        mock_trans.assert_not_called()

    @mock.patch("run_pipeline.transition_issue")
    @mock.patch("run_pipeline.invoke_codegen", return_value=True)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_transitions_captured_in_log(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke, mock_trans):
        mock_trans.return_value = (True, "")
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(output_dir="/tmp/test-artifacts")
            _, _, transitions_log, _ = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        assert "A-1" in transitions_log
        assert len(transitions_log["A-1"]) == 2
        assert transitions_log["A-1"][0]["to"] == "In Progress"
        assert transitions_log["A-1"][1]["to"] == "In Review"


# ─── TestBuildRunLogTransitions ─────────────────────────────────────────────

class TestBuildRunLogTransitions:

    def test_transitions_in_epic_entry(self):
        from datetime import datetime, timezone
        epics = [_epic("A-1")]
        results = {
            PROCESSED: [("A-1", "codegen completed")],
            SKIPPED: [], BLOCKED: [], FAILED: [],
        }
        transitions_log = {
            "A-1": [
                {"to": "In Progress", "success": True},
                {"to": "In Review", "success": True},
            ],
        }
        start = datetime(2026, 6, 26, 20, 0, 0, tzinfo=timezone.utc)
        log = build_run_log(
            {"RHAISTRAT-1": (epics, results, transitions_log, {})}, start)

        epic_log = log["strategies"]["RHAISTRAT-1"]["epics"]["A-1"]
        assert epic_log["transitions"] == transitions_log["A-1"]

    def test_empty_transitions_for_skipped(self):
        from datetime import datetime, timezone
        epics = [_epic("A-1", jira_status="Done")]
        results = {
            PROCESSED: [], SKIPPED: [("A-1", "Already done")],
            BLOCKED: [], FAILED: [],
        }
        start = datetime(2026, 6, 26, 20, 0, 0, tzinfo=timezone.utc)
        log = build_run_log(
            {"RHAISTRAT-1": (epics, results, {}, {})}, start)

        epic_log = log["strategies"]["RHAISTRAT-1"]["epics"]["A-1"]
        assert epic_log["transitions"] == []


# ─── TestReadPrUrl ──────────────────────────────────────────────────────────

class TestReadPrUrl:

    def test_reads_pr_url_from_frontmatter(self, tmp_path):
        tasks_dir = tmp_path / "epic-tasks"
        tasks_dir.mkdir()
        task_file = tasks_dir / "RHOAIENG-100.md"
        task_file.write_text(
            "---\n"
            "epic_id: RHOAIENG-100\n"
            "title: Test Epic\n"
            "strategy_key: RHAISTRAT-1\n"
            "target_repo: org/repo\n"
            "target_branch: main\n"
            "status: Generated\n"
            "pr_url: https://github.com/org/repo/pull/42\n"
            "---\n"
            "Body text\n"
        )
        result = read_pr_url("RHOAIENG-100", str(tmp_path))
        assert result == "https://github.com/org/repo/pull/42"

    def test_returns_none_when_no_pr_url(self, tmp_path):
        tasks_dir = tmp_path / "epic-tasks"
        tasks_dir.mkdir()
        task_file = tasks_dir / "RHOAIENG-100.md"
        task_file.write_text(
            "---\n"
            "epic_id: RHOAIENG-100\n"
            "title: Test Epic\n"
            "strategy_key: RHAISTRAT-1\n"
            "target_repo: org/repo\n"
            "target_branch: main\n"
            "status: Pending\n"
            "---\n"
            "Body text\n"
        )
        result = read_pr_url("RHOAIENG-100", str(tmp_path))
        assert result is None

    def test_returns_none_when_file_missing(self, tmp_path):
        result = read_pr_url("NONEXISTENT-1", str(tmp_path))
        assert result is None


# ─── TestLinkPrToJira ───────────────────────────────────────────────────────

class TestLinkPrToJira:

    @mock.patch("run_pipeline.add_comment")
    @mock.patch("run_pipeline.markdown_to_adf",
                return_value={"type": "doc", "content": []})
    def test_posts_comment_with_pr_url(self, mock_adf, mock_comment):
        result = link_pr_to_jira(
            "s", "u", "t", "A-1",
            "https://github.com/org/repo/pull/42")
        assert result is True
        mock_adf.assert_called_once()
        assert "https://github.com/org/repo/pull/42" in mock_adf.call_args[0][0]
        mock_comment.assert_called_once()

    @mock.patch("run_pipeline.add_comment",
                side_effect=Exception("403 Forbidden"))
    @mock.patch("run_pipeline.markdown_to_adf",
                return_value={"type": "doc", "content": []})
    def test_handles_api_error(self, mock_adf, mock_comment):
        result = link_pr_to_jira(
            "s", "u", "t", "A-1",
            "https://github.com/org/repo/pull/42")
        assert result is False


# ─── TestProcessStrategy PR linking ─────────────────────────────────────────

class TestProcessStrategyPrLinking:

    @mock.patch("run_pipeline.link_pr_to_jira", return_value=True)
    @mock.patch("run_pipeline.read_pr_url",
                return_value="https://github.com/org/repo/pull/42")
    @mock.patch("run_pipeline.transition_issue", return_value=(True, ""))
    @mock.patch("run_pipeline.invoke_codegen", return_value=True)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_links_pr_after_successful_codegen(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke,
            mock_trans, mock_read_pr, mock_link):
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(output_dir="/tmp/test-artifacts")
            _, _, _, pr_urls = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        mock_link.assert_called_once_with(
            "s", "u", "t", "A-1",
            "https://github.com/org/repo/pull/42")
        assert pr_urls == {"A-1": "https://github.com/org/repo/pull/42"}

    @mock.patch("run_pipeline.link_pr_to_jira")
    @mock.patch("run_pipeline.read_pr_url", return_value=None)
    @mock.patch("run_pipeline.transition_issue", return_value=(True, ""))
    @mock.patch("run_pipeline.invoke_codegen", return_value=True)
    @mock.patch("run_pipeline.fetch_children")
    @mock.patch("run_pipeline.build_dependency_dag")
    @mock.patch("run_pipeline.generate_epic_task_from_jira")
    def test_no_link_when_no_pr_url(
            self, mock_gen, mock_dag, mock_fetch, mock_invoke,
            mock_trans, mock_read_pr, mock_link):
        issues = [{"key": "A-1", "fields": {}}]
        mock_fetch.return_value = issues
        mock_dag.return_value = {"A-1": {"dependencies": [], "blocks": []}}

        with mock.patch("run_pipeline.issue_to_epic_data",
                        return_value=_epic("A-1")):
            args = _make_args(output_dir="/tmp/test-artifacts")
            _, _, _, pr_urls = process_strategy(
                "RHAISTRAT-1", "s", "u", "t", args)

        mock_link.assert_not_called()
        assert pr_urls == {}


# ─── TestBuildRunLog PR URL ─────────────────────────────────────────────────

class TestBuildRunLogPrUrl:

    def test_pr_url_in_run_log(self):
        from datetime import datetime, timezone
        epics = [_epic("A-1")]
        results = {
            PROCESSED: [("A-1", "codegen completed")],
            SKIPPED: [], BLOCKED: [], FAILED: [],
        }
        pr_urls = {"A-1": "https://github.com/org/repo/pull/42"}
        start = datetime(2026, 6, 26, 20, 0, 0, tzinfo=timezone.utc)
        log = build_run_log(
            {"RHAISTRAT-1": (epics, results, {}, pr_urls)}, start)

        epic_log = log["strategies"]["RHAISTRAT-1"]["epics"]["A-1"]
        assert epic_log["pr_url"] == "https://github.com/org/repo/pull/42"
