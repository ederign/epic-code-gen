"""Tests for CI-mode state machine in run_pipeline.py."""

import json
import os
import sys
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from run_pipeline import (
    BLOCKED,
    FAILED,
    PROCESSED,
    SKIPPED,
    ci_process_epic,
    load_epic_state,
    save_epic_state,
)


def _epic(epic_id, strategy_key="RHAISTRAT-1", deps=None, **kwargs):
    data = {
        "epic_id": epic_id,
        "strategy_key": strategy_key,
        "title": f"Epic {epic_id}",
        "target_repo": "mlflow/mlflow",
        "target_branch": "main",
        "jira_status": "New",
        "dependencies": deps,
        "blocks": None,
        "body": "",
    }
    data.update(kwargs)
    return data


def _args(data_repo, dry_run=False):
    return SimpleNamespace(
        data_repo=str(data_repo),
        dry_run=dry_run,
        output_dir="artifacts",
        fork_owner="dora-the-ai-coder",
        max_iterations=None,
        run_script=None,
        timeout=60,
        log_dir="pipeline-runs",
    )


class TestLoadSaveState:

    def test_save_and_load(self, tmp_path):
        state = {
            "status": "Ready",
            "target_repo": "mlflow/mlflow",
            "current_version": 1,
        }
        save_epic_state(tmp_path, "RHAISTRAT-1", "E001", state)
        loaded = load_epic_state(tmp_path, "RHAISTRAT-1", "E001")

        assert loaded["status"] == "Ready"
        assert loaded["epic_id"] == "E001"
        assert loaded["strategy_key"] == "RHAISTRAT-1"
        assert loaded["current_version"] == 1

    def test_load_nonexistent(self, tmp_path):
        result = load_epic_state(tmp_path, "RHAISTRAT-1", "MISSING")
        assert result is None

    def test_save_creates_directories(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "E001",
                        {"status": "Pending"})
        assert (tmp_path / "RHAISTRAT-1" / "E001"
                / "run-metadata.yaml").exists()


class TestCIStateMachine:

    def test_new_epic_no_deps_becomes_ready(self, tmp_path):
        epic = _epic("E001")
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, None, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert from_s == "Pending"
        assert to_s == "Ready"

        state = load_epic_state(tmp_path, "RHAISTRAT-1", "E001")
        assert state["status"] == "Ready"

    def test_new_epic_with_unmet_deps_becomes_blocked(self, tmp_path):
        epic = _epic("E002", deps=["E001"])
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, None, args, "srv", "usr", "tok")

        assert action == BLOCKED
        assert to_s == "Blocked"
        assert "E001" in detail

    def test_new_epic_with_met_deps_becomes_ready(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "E001",
                        {"status": "Done"})

        epic = _epic("E002", deps=["E001"])
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, None, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert to_s == "Ready"

    def test_done_epic_is_skipped(self, tmp_path):
        epic = _epic("E001")
        state = {"status": "Done", "current_version": 2}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED
        assert "Terminal" in detail

    def test_failed_epic_is_skipped(self, tmp_path):
        epic = _epic("E001")
        state = {"status": "Failed", "failure_reason": "codegen failed"}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED

    def test_blocked_falls_through_to_ready_when_deps_done(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "E001",
                        {"status": "Done"})

        epic = _epic("E002", deps=["E001"])
        state = {"status": "Blocked", "blocked_by": ["E001"]}
        args = _args(tmp_path, dry_run=True)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert from_s == "Blocked"
        assert "unblocked" in detail.lower()

        saved = load_epic_state(tmp_path, "RHAISTRAT-1", "E002")
        assert saved["status"] == "Ready"
        assert "blocked_by" not in saved

    def test_blocked_stays_blocked_with_unmet_deps(self, tmp_path):
        epic = _epic("E002", deps=["E001"])
        state = {"status": "Blocked", "blocked_by": ["E001"]}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == BLOCKED
        assert to_s == "Blocked"

    def test_review_pending_fails_when_exhausted(self, tmp_path):
        epic = _epic("E001")
        state = {"status": "ReviewPending", "current_version": 3,
                 "max_iterations": 3}

        scores_dir = os.path.join("artifacts", "codegen-runs", "E001", "v3")
        os.makedirs(scores_dir, exist_ok=True)
        with open(os.path.join(scores_dir, "scores.json"), "w") as f:
            json.dump({"architecture": 5, "tests": 4, "lint": 6,
                       "intent": 5, "weighted_avg": 5.0}, f)

        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == FAILED
        assert to_s == "Failed"
        assert "Exhausted" in detail

        os.remove(os.path.join(scores_dir, "scores.json"))
        os.removedirs(scores_dir)

    def test_review_pending_near_miss_exhausted_attempts_pr(self, tmp_path,
                                                             monkeypatch):
        """Near-miss verdict when exhausted should attempt PR creation."""
        epic = _epic("E001")
        state = {"status": "ReviewPending", "current_version": 3,
                 "max_iterations": 3}

        scores_dir = os.path.join("artifacts", "codegen-runs", "E001", "v3")
        os.makedirs(scores_dir, exist_ok=True)
        with open(os.path.join(scores_dir, "scores.json"), "w") as f:
            json.dump({
                "weighted_average": 7.2,
                "verdict": "near-miss",
                "dimensions": {
                    "architecture": {"score": 6.5},
                    "tests": {"score": 6.5},
                    "lint": {"score": 8.0},
                    "intent": {"score": 8.5},
                },
            }, f)

        pr_created = []

        def fake_create_pr(ep, st, args):
            pr_created.append(ep["epic_id"])
            return "https://github.com/org/repo/pull/99"

        monkeypatch.setattr(
            "run_pipeline._create_pr_for_epic", fake_create_pr)

        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert to_s == "PRCreated"
        assert "Near-miss" in detail
        assert pr_created == ["E001"]

        os.remove(os.path.join(scores_dir, "scores.json"))
        os.removedirs(scores_dir)

    def test_review_pending_skips_without_scores(self, tmp_path):
        epic = _epic("E001")
        state = {"status": "ReviewPending", "current_version": 1}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED
        assert "Waiting" in detail

    def test_review_pending_iterates_on_low_scores(self, tmp_path):
        """Low scores with remaining iterations → iterate (Ready)."""
        epic = _epic("E001")
        state = {"status": "ReviewPending", "current_version": 1}
        args = _args(tmp_path)

        scores_dir = os.path.join(
            "artifacts", "codegen-runs", "E001", "v1")
        os.makedirs(scores_dir, exist_ok=True)
        with open(os.path.join(scores_dir, "scores.json"), "w") as f:
            json.dump({
                "weighted_average": 5.0,
                "dimensions": {
                    "architecture": {"score": 5},
                    "tests": {"score": 4},
                    "lint": {"score": 6},
                    "intent": {"score": 5},
                },
            }, f)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert to_s == "Ready"

        os.remove(os.path.join(scores_dir, "scores.json"))
        os.removedirs(scores_dir)

    def test_ready_dry_run_doesnt_invoke(self, tmp_path):
        epic = _epic("E001")
        state = {"status": "Ready", "current_version": 0}
        args = _args(tmp_path, dry_run=True)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert "dry-run" in detail

    def test_pr_created_skips_without_token(self, tmp_path, monkeypatch):
        monkeypatch.delenv("EPIC_CODEGEN_GITHUB_TOKEN", raising=False)

        epic = _epic("E001")
        state = {"status": "PRCreated",
                 "pr_url": "https://github.com/org/repo/pull/1"}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED

    def test_pr_changes_requested_skips_without_token(self, tmp_path,
                                                       monkeypatch):
        monkeypatch.delenv("EPIC_CODEGEN_GITHUB_TOKEN", raising=False)

        epic = _epic("E001")
        state = {"status": "PRChangesRequested",
                 "pr_url": "https://github.com/org/repo/pull/1",
                 "current_version": 1, "max_iterations": 5}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED

    def test_pr_changes_exhausted_at_max_iterations(self, tmp_path,
                                                     monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "fake-token")

        epic = _epic("E001")
        state = {"status": "PRChangesRequested",
                 "pr_url": "https://github.com/org/repo/pull/1",
                 "current_version": 5, "max_iterations": 5}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == FAILED
        assert to_s == "Failed"
        assert "Exhausted" in detail

    def test_init_state_has_max_iterations_10(self, tmp_path):
        """Default max_iterations should be 10."""
        epic = _epic("E001")
        args = _args(tmp_path)

        ci_process_epic(epic, None, args, "srv", "usr", "tok")

        state = load_epic_state(tmp_path, "RHAISTRAT-1", "E001")
        assert state["max_iterations"] == 10

    def test_pr_changes_skips_without_pr_url(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "fake-token")

        epic = _epic("E001")
        state = {"status": "PRChangesRequested",
                 "current_version": 1, "max_iterations": 5}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED
        assert "No PR URL" in detail

    def test_pr_changes_dry_run_does_not_invoke(self, tmp_path):
        epic = _epic("E001")
        state = {"status": "PRChangesRequested",
                 "pr_url": "https://github.com/org/repo/pull/1",
                 "current_version": 1, "max_iterations": 5}
        args = _args(tmp_path, dry_run=True)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert "dry-run" in detail
        loaded = load_epic_state(tmp_path, "RHAISTRAT-1", "E001")
        assert loaded is None
