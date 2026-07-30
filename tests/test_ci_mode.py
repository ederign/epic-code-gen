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


def _args(data_repo, dry_run=False, no_strategy=False):
    return SimpleNamespace(
        data_repo=str(data_repo),
        dry_run=dry_run,
        output_dir="artifacts",
        fork_owner="dora-the-ai-coder",
        max_iterations=None,
        run_script=None,
        timeout=60,
        log_dir="pipeline-runs",
        no_strategy=no_strategy,
    )


class TestLoadSaveState:

    def test_save_and_load(self, tmp_path):
        state = {
            "status": "Ready",
            "target_repo": "mlflow/mlflow",
            "current_version": 1,
        }
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1", state)
        loaded = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")

        assert loaded["status"] == "Ready"
        assert loaded["epic_id"] == "RHAI-1"
        assert loaded["strategy_key"] == "RHAISTRAT-1"
        assert loaded["current_version"] == 1

    def test_load_nonexistent(self, tmp_path):
        result = load_epic_state(tmp_path, "RHAISTRAT-1", "MISSING")
        assert result is None

    def test_save_creates_directories(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        {"status": "Pending"})
        assert (tmp_path / "RHAISTRAT-1" / "RHAI-1"
                / "run-metadata.yaml").exists()


class TestCIStateMachine:

    def test_new_epic_no_deps_becomes_ready(self, tmp_path):
        epic = _epic("RHAI-1")
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, None, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert from_s == "Pending"
        assert to_s == "Ready"

        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert state["status"] == "Ready"

    def test_new_epic_with_unmet_deps_becomes_blocked(self, tmp_path):
        epic = _epic("RHAI-2", deps=["RHAI-1"])
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, None, args, "srv", "usr", "tok")

        assert action == BLOCKED
        assert to_s == "Blocked"
        assert "RHAI-1" in detail

    def test_new_epic_with_met_deps_becomes_ready(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        {"status": "Done"})

        epic = _epic("RHAI-2", deps=["RHAI-1"])
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, None, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert to_s == "Ready"

    def test_done_epic_is_skipped(self, tmp_path):
        epic = _epic("RHAI-1")
        state = {"status": "Done", "current_version": 2}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED
        assert "Terminal" in detail

    def test_failed_epic_is_skipped(self, tmp_path):
        epic = _epic("RHAI-1")
        state = {"status": "Failed", "failure_reason": "codegen failed"}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED

    def test_blocked_falls_through_to_ready_when_deps_done(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        {"status": "Done"})

        epic = _epic("RHAI-2", deps=["RHAI-1"])
        state = {"status": "Blocked", "blocked_by": ["RHAI-1"]}
        args = _args(tmp_path, dry_run=True)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert from_s == "Blocked"
        assert "unblocked" in detail.lower()

        saved = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-2")
        assert saved["status"] == "Ready"
        assert "blocked_by" not in saved

    def test_blocked_stays_blocked_with_unmet_deps(self, tmp_path):
        epic = _epic("RHAI-2", deps=["RHAI-1"])
        state = {"status": "Blocked", "blocked_by": ["RHAI-1"]}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == BLOCKED
        assert to_s == "Blocked"

    def test_review_pending_fails_when_exhausted(self, tmp_path):
        epic = _epic("RHAI-1")
        state = {"status": "ReviewPending", "current_version": 3,
                 "max_iterations": 3}

        scores_dir = os.path.join("artifacts", "codegen-runs", "RHAI-1", "v3")
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
        epic = _epic("RHAI-1")
        state = {"status": "ReviewPending", "current_version": 3,
                 "max_iterations": 3}

        scores_dir = os.path.join("artifacts", "codegen-runs", "RHAI-1", "v3")
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
        assert pr_created == ["RHAI-1"]

        os.remove(os.path.join(scores_dir, "scores.json"))
        os.removedirs(scores_dir)

    def test_review_pending_skips_without_scores(self, tmp_path):
        epic = _epic("RHAI-1")
        state = {"status": "ReviewPending", "current_version": 1}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED
        assert "Waiting" in detail

    def test_review_pending_iterates_on_low_scores(self, tmp_path):
        """Low scores with remaining iterations → iterate (Ready)."""
        epic = _epic("RHAI-1")
        state = {"status": "ReviewPending", "current_version": 1}
        args = _args(tmp_path)

        scores_dir = os.path.join(
            "artifacts", "codegen-runs", "RHAI-1", "v1")
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
        epic = _epic("RHAI-1")
        state = {"status": "Ready", "current_version": 0}
        args = _args(tmp_path, dry_run=True)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert "dry-run" in detail

    def test_pr_created_skips_without_token(self, tmp_path, monkeypatch):
        monkeypatch.delenv("EPIC_CODEGEN_GITHUB_TOKEN", raising=False)

        epic = _epic("RHAI-1")
        state = {"status": "PRCreated",
                 "pr_url": "https://github.com/org/repo/pull/1"}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED

    def test_pr_changes_requested_skips_without_token(self, tmp_path,
                                                       monkeypatch):
        monkeypatch.delenv("EPIC_CODEGEN_GITHUB_TOKEN", raising=False)

        epic = _epic("RHAI-1")
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

        epic = _epic("RHAI-1")
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
        epic = _epic("RHAI-1")
        args = _args(tmp_path)

        ci_process_epic(epic, None, args, "srv", "usr", "tok")

        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert state["max_iterations"] == 10

    def test_pr_changes_skips_without_pr_url(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "fake-token")

        epic = _epic("RHAI-1")
        state = {"status": "PRChangesRequested",
                 "current_version": 1, "max_iterations": 5}
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED
        assert "No PR URL" in detail

    def test_pr_changes_dry_run_does_not_invoke(self, tmp_path):
        epic = _epic("RHAI-1")
        state = {"status": "PRChangesRequested",
                 "pr_url": "https://github.com/org/repo/pull/1",
                 "current_version": 1, "max_iterations": 5}
        args = _args(tmp_path, dry_run=True)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert "dry-run" in detail
        loaded = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert loaded is None


class TestReadyArtifactFetch:
    """Verify _ci_handle_ready ensures artifact files before codegen."""

    def test_ready_ensures_artifacts_before_codegen(self, tmp_path,
                                                     monkeypatch):
        """Both fetch functions must be called before setup_target_repo."""
        calls = []

        def fake_generate(epic_data, output_dir):
            calls.append(("generate", epic_data["epic_id"], output_dir))

        def fake_fetch_strategy(strategy_key, output_dir):
            calls.append(("fetch_strategy", strategy_key, output_dir))
            return None

        def fake_setup(epic, args):
            calls.append(("setup_target_repo",))
            return False

        monkeypatch.setattr(
            "run_pipeline.generate_epic_task_from_jira", fake_generate)
        monkeypatch.setattr(
            "run_pipeline.fetch_strategy", fake_fetch_strategy)
        monkeypatch.setattr(
            "run_pipeline.setup_target_repo", fake_setup)

        epic = _epic("RHAI-1", strategy_key="RHAISTRAT-99")
        state = {"status": "Ready", "current_version": 0}
        args = _args(tmp_path)

        ci_process_epic(epic, state, args, "srv", "usr", "tok")

        assert calls[0] == ("generate", "RHAI-1", "artifacts/epic-tasks")
        assert calls[1] == (
            "fetch_strategy", "RHAISTRAT-99", "artifacts/strategies")
        assert calls[2] == ("setup_target_repo",)

    def test_ready_skips_strategy_when_no_strategy(self, tmp_path,
                                                     monkeypatch):
        """fetch_strategy must NOT be called when --no-strategy is set."""
        calls = []

        def fake_generate(epic_data, output_dir):
            calls.append("generate")

        def fake_fetch_strategy(strategy_key, output_dir):
            calls.append("fetch_strategy")
            return None

        def fake_setup(epic, args):
            return False

        monkeypatch.setattr(
            "run_pipeline.generate_epic_task_from_jira", fake_generate)
        monkeypatch.setattr(
            "run_pipeline.fetch_strategy", fake_fetch_strategy)
        monkeypatch.setattr(
            "run_pipeline.setup_target_repo", fake_setup)

        epic = _epic("RHAI-1")
        state = {"status": "Ready", "current_version": 0}
        args = _args(tmp_path, no_strategy=True)

        ci_process_epic(epic, state, args, "srv", "usr", "tok")

        assert "generate" in calls
        assert "fetch_strategy" not in calls

    def test_ready_dry_run_skips_artifact_fetch(self, tmp_path, monkeypatch):
        """Dry run returns early before any fetch or codegen."""
        calls = []

        def fake_generate(epic_data, output_dir):
            calls.append("generate")

        monkeypatch.setattr(
            "run_pipeline.generate_epic_task_from_jira", fake_generate)

        epic = _epic("RHAI-1")
        state = {"status": "Ready", "current_version": 0}
        args = _args(tmp_path, dry_run=True)

        action, _, _, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert "dry-run" in detail
        assert "generate" not in calls


class TestReviewResponseNoOpGuard:
    """A cycle that changes nothing must not consume an iteration.

    Otherwise an unaddressable review (empty CHANGES_REQUESTED body, no
    inline comments, nothing to rebase) loops forever, burning a version
    on every run while reporting success.
    """

    def _setup(self, tmp_path, monkeypatch, response):
        import run_pipeline

        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-10", {
            "status": "PRChangesRequested",
            "current_version": 3,
            "max_iterations": 10,
            "pr_url": "https://github.com/o/r/pull/1",
            "target_repo": "o/r",
            "target_branch": "main",
        })
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "tok")
        monkeypatch.setattr(
            run_pipeline, "_setup_target_for_review_response",
            lambda *a, **k: True)
        monkeypatch.setattr(
            run_pipeline, "_copy_codegen_artifacts_to_data_repo",
            lambda *a, **k: None)

        class _Result:
            stdout = json.dumps(response)
            stderr = ""
        monkeypatch.setattr(
            run_pipeline.subprocess, "run", lambda *a, **k: _Result())
        return _epic("RHAI-10", target_repo="o/r"), load_epic_state(
            tmp_path, "RHAISTRAT-1", "RHAI-10")

    def test_noop_cycle_does_not_bump_version(self, tmp_path, monkeypatch):
        epic, state = self._setup(tmp_path, monkeypatch, {
            "success": True, "comments_processed": 0, "fixes_applied": 0,
            "rebase": {"rebased": False, "already_current": True,
                       "base": "main", "conflict_rounds": 0},
        })
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == SKIPPED
        assert to_s == "PRCreated"
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-10")
        assert state["current_version"] == 3

    def test_rebase_only_cycle_counts_as_work(self, tmp_path, monkeypatch):
        epic, state = self._setup(tmp_path, monkeypatch, {
            "success": True, "comments_processed": 0, "fixes_applied": 0,
            "rebase": {"rebased": True, "already_current": False,
                       "base": "main", "conflict_rounds": 2},
        })
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert "rebased onto main" in detail
        assert "2 conflict round(s)" in detail
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-10")
        assert state["current_version"] == 4

    def test_fixes_cycle_counts_as_work(self, tmp_path, monkeypatch):
        epic, state = self._setup(tmp_path, monkeypatch, {
            "success": True, "comments_processed": 2, "fixes_applied": 2,
            "rebase": {"rebased": False, "already_current": True,
                       "base": "main", "conflict_rounds": 0},
        })
        args = _args(tmp_path)

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert "2 fixes applied" in detail
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-10")
        assert state["current_version"] == 4


class TestForeignStatusNormalisation:
    """A status from another producer must not deadlock the epic.

    run-metadata.yaml has carried three status vocabularies. An unrecognised
    value used to fall through to a silent SKIPPED, so the epic was skipped on
    every run forever and its dependents stayed Blocked while CI exited 0
    (RHAIFIRST-374).
    """

    def _pipeline_state(self, **overrides):
        state = {
            "status": "completed",
            "target_repo": "mlflow/mlflow",
            "target_branch": "main",
            "current_version": 2,
            "max_iterations": 10,
            "timestamps": {"created": "t0", "last_run": "t1"},
            "scores": {"weighted_average": 8.4},
        }
        state.update(overrides)
        return state

    def _stub_merged_pr(self, monkeypatch):
        import pr_lifecycle
        import run_pipeline

        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "tok")
        monkeypatch.setattr(pr_lifecycle, "get_pr_status",
                            lambda url, token: {"merged": True,
                                                "state": "closed"})
        monkeypatch.setattr(pr_lifecycle, "derive_pr_state", lambda s: "Done")
        monkeypatch.setattr(run_pipeline, "transition_issue",
                            lambda *a, **k: (True, "Done"))

    def test_completed_with_pr_url_is_processed_as_pr_created(
            self, tmp_path, monkeypatch):
        self._stub_merged_pr(monkeypatch)
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1", self._pipeline_state(
            pr_url="https://github.com/org/repo/pull/7"))

        epic = _epic("RHAI-1")
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert state["status"] == "PRCreated"

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, _args(tmp_path), "srv", "usr", "tok")

        assert action == PROCESSED
        assert from_s == "PRCreated"
        assert to_s == "Done"

    def test_completed_without_pr_url_is_review_pending(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        self._pipeline_state())

        epic = _epic("RHAI-1")
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert state["status"] == "ReviewPending"

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, _args(tmp_path), "srv", "usr", "tok")

        # No scores yet for this version — the review handler ran, which is
        # the point: it is no longer an unrecognised state.
        assert from_s == "ReviewPending"
        assert "Waiting" in detail

    def test_completed_without_pr_url_creates_pr_when_scored(
            self, tmp_path, monkeypatch):
        import run_pipeline

        created = []
        monkeypatch.setattr(run_pipeline, "_create_pr_for_epic",
                            lambda ep, st, ar: created.append(ep["epic_id"])
                            or "https://github.com/org/repo/pull/9")
        monkeypatch.setattr(run_pipeline, "transition_issue",
                            lambda *a, **k: (True, "Review"))
        monkeypatch.setattr(run_pipeline, "link_pr_to_jira",
                            lambda *a, **k: None)

        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        self._pipeline_state(current_version=1))

        scores_dir = tmp_path / "out" / "codegen-runs" / "RHAI-1" / "v1"
        scores_dir.mkdir(parents=True)
        (scores_dir / "scores.json").write_text(json.dumps({
            "weighted_average": 9.0,
            "verdict": "pass",
            "dimensions": {
                "architecture": {"score": 9.0},
                "tests": {"score": 9.0},
                "lint": {"score": 9.0},
                "intent": {"score": 9.0},
            },
        }))

        args = _args(tmp_path)
        args.output_dir = str(tmp_path / "out")

        epic = _epic("RHAI-1")
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert from_s == "ReviewPending"
        assert to_s == "PRCreated"
        assert created == ["RHAI-1"]

    @pytest.mark.parametrize("raw,expected", [
        ("completed", "PRCreated"),
        ("Completed", "PRCreated"),
        ("COMPLETED", "PRCreated"),
        ("prcreated", "PRCreated"),
        ("Running", "Generating"),
        ("done", "Done"),
    ])
    def test_case_variants_normalise_on_load(self, tmp_path, raw, expected):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1", self._pipeline_state(
            status=raw, pr_url="https://github.com/org/repo/pull/7"))

        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert state["status"] == expected
        if raw != expected:
            assert state["status_normalized_from"] == raw

    @pytest.mark.parametrize("raw", ["exhausted", "Exhausted", "error"])
    def test_exhausted_and_error_become_failed(self, tmp_path, raw):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        self._pipeline_state(status=raw))

        epic = _epic("RHAI-1")
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert state["status"] == "Failed"

        action, from_s, to_s, detail = ci_process_epic(
            epic, state, _args(tmp_path), "srv", "usr", "tok")

        assert action == SKIPPED
        assert "Terminal state: Failed" in detail

    def test_normalisation_preserves_pipeline_fields(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1", self._pipeline_state(
            pr_url="https://github.com/org/repo/pull/7", pr_state="open"))

        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")

        assert state["current_version"] == 2
        assert state["max_iterations"] == 10
        assert state["pr_state"] == "open"
        assert state["pr_url"] == "https://github.com/org/repo/pull/7"
        assert state["timestamps"] == {"created": "t0", "last_run": "t1"}
        assert state["scores"] == {"weighted_average": 8.4}
        assert state["strategy_key"] == "RHAISTRAT-1"

    def test_unknown_state_fails_loudly(self, tmp_path, caplog):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        self._pipeline_state(status="banana"))

        epic = _epic("RHAI-1")
        state = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")

        with caplog.at_level("ERROR"):
            action, from_s, to_s, detail = ci_process_epic(
                epic, state, _args(tmp_path), "srv", "usr", "tok")

        assert action == FAILED, "an unknown state must not be a silent skip"
        assert "Unrecognised state" in detail
        assert "banana" in detail
        assert any("unrecognised run status" in r.message.lower()
                   for r in caplog.records)

    def test_unknown_state_file_is_left_intact(self, tmp_path):
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1",
                        self._pipeline_state(status="banana"))

        epic = _epic("RHAI-1")
        ci_process_epic(epic, load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1"),
                        _args(tmp_path), "srv", "usr", "tok")

        raw = yaml.safe_load(
            (tmp_path / "RHAISTRAT-1" / "RHAI-1" / "run-metadata.yaml")
            .read_text())
        assert raw["status"] == "banana"
        assert raw["current_version"] == 2


class TestArtifactCopyDoesNotClobberState:
    """The skill's run-metadata must merge into the state file, never replace it."""

    def _setup(self, tmp_path, produced):
        import run_pipeline

        save_epic_state(tmp_path / "data", "RHAISTRAT-1", "RHAI-1", {
            "status": "PRCreated",
            "target_repo": "mlflow/mlflow",
            "current_version": 2,
            "max_iterations": 10,
            "pr_url": "https://github.com/org/repo/pull/7",
            "pr_state": "open",
            "timestamps": {"created": "t0"},
            "scores": {"weighted_average": 8.4},
        })

        run_dir = tmp_path / "artifacts" / "codegen-runs" / "RHAI-1"
        run_dir.mkdir(parents=True)
        (run_dir / "run-metadata.yaml").write_text(yaml.dump(produced))

        run_pipeline._copy_codegen_artifacts_to_data_repo(
            str(tmp_path / "data"), "RHAISTRAT-1", "RHAI-1",
            str(tmp_path / "artifacts"))

        return load_epic_state(tmp_path / "data", "RHAISTRAT-1", "RHAI-1")

    def test_pipeline_fields_survive_and_status_is_not_taken(self, tmp_path):
        state = self._setup(tmp_path, {
            "epic_id": "RHAI-1",
            "status": "completed",
            "versions": 3,
            "final_score": 8.6,
            "scores_by_dimension": {"architecture": 9, "tests": 8},
            "started_at": "t-start",
        })

        assert state["status"] == "PRCreated"
        assert state["current_version"] == 2
        assert state["max_iterations"] == 10
        assert state["pr_state"] == "open"
        assert state["timestamps"] == {"created": "t0"}
        assert state["scores"] == {"weighted_average": 8.4}

        # ...and the skill's run facts are folded in under their own key
        assert state["codegen_outcome"] == "completed"
        assert state["versions"] == 3
        assert state["final_score"] == 8.6
        assert state["scores_by_dimension"] == {"architecture": 9, "tests": 8}
        assert "status_normalized_from" not in state

    def test_codegen_outcome_key_is_carried_through(self, tmp_path):
        state = self._setup(tmp_path, {
            "epic_id": "RHAI-1",
            "codegen_outcome": "exhausted",
            "versions": 5,
        })

        assert state["status"] == "PRCreated"
        assert state["codegen_outcome"] == "exhausted"

    def test_facts_land_in_live_state_dict(self, tmp_path):
        """A later save_epic_state must not drop the merged facts."""
        import run_pipeline

        save_epic_state(tmp_path / "data", "RHAISTRAT-1", "RHAI-1",
                        {"status": "Generating", "current_version": 1})
        run_dir = tmp_path / "artifacts" / "codegen-runs" / "RHAI-1"
        run_dir.mkdir(parents=True)
        (run_dir / "run-metadata.yaml").write_text(
            yaml.dump({"status": "completed", "versions": 1,
                       "language": "go"}))

        state = load_epic_state(tmp_path / "data", "RHAISTRAT-1", "RHAI-1")
        run_pipeline._copy_codegen_artifacts_to_data_repo(
            str(tmp_path / "data"), "RHAISTRAT-1", "RHAI-1",
            str(tmp_path / "artifacts"), state)

        assert state["codegen_outcome"] == "completed"
        assert state["language"] == "go"
        assert state["status"] == "Generating"

        state["status"] = "ReviewPending"
        save_epic_state(tmp_path / "data", "RHAISTRAT-1", "RHAI-1", state)

        reloaded = load_epic_state(tmp_path / "data", "RHAISTRAT-1", "RHAI-1")
        assert reloaded["codegen_outcome"] == "completed"
        assert reloaded["language"] == "go"
        assert reloaded["status"] == "ReviewPending"


class TestRescueOfClobberedState:
    """An epic already wedged in the field must converge, not idle forever.

    The clobbering write left only the skill's fields: an outcome word in
    `status`, `versions` instead of `current_version`, and no artifacts in a
    fresh CI checkout — only the data repo's copies.
    """

    def _clobbered_state(self, tmp_path, **overrides):
        state = {
            "epic_id": "RHAI-1",
            "target_repo": "https://github.com/mlflow/mlflow",
            "branch": "epic/E001",
            "language": "python",
            "status": "completed",
            "versions": 2,
            "final_score": 8.6,
            "started_at": "t0",
        }
        state.update(overrides)
        save_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1", state)
        return load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")

    def test_versions_restores_current_version(self, tmp_path):
        state = self._clobbered_state(tmp_path)
        assert state["status"] == "ReviewPending"
        assert state["current_version"] == 2

    def test_scores_are_read_from_data_repo(self, tmp_path, monkeypatch):
        import run_pipeline

        monkeypatch.setattr(run_pipeline, "_create_pr_for_epic",
                            lambda ep, st, ar: "https://x/pull/3")
        monkeypatch.setattr(run_pipeline, "transition_issue",
                            lambda *a, **k: (True, "Review"))
        monkeypatch.setattr(run_pipeline, "link_pr_to_jira",
                            lambda *a, **k: None)

        state = self._clobbered_state(tmp_path)

        v2 = tmp_path / "RHAISTRAT-1" / "RHAI-1" / "v2"
        v2.mkdir(parents=True)
        (v2 / "scores.json").write_text(json.dumps({
            "weighted_average": 8.6,
            "verdict": "pass",
            "dimensions": {
                "architecture": {"score": 9.0},
                "tests": {"score": 8.0},
                "lint": {"score": 9.0},
                "intent": {"score": 8.5},
            },
        }))

        args = _args(tmp_path)
        args.output_dir = str(tmp_path / "empty-artifacts")

        action, from_s, to_s, detail = ci_process_epic(
            _epic("RHAI-1"), state, args, "srv", "usr", "tok")

        assert action == PROCESSED
        assert from_s == "ReviewPending"
        assert to_s == "PRCreated"

        saved = load_epic_state(tmp_path, "RHAISTRAT-1", "RHAI-1")
        assert saved["status"] == "PRCreated"
        assert saved["pr_url"] == "https://x/pull/3"


class TestUnknownStateExitCode:
    """A loud failure must reach the process exit code, not just the log."""

    def test_main_exits_nonzero_when_an_epic_fails(self, tmp_path,
                                                   monkeypatch):
        import run_pipeline

        monkeypatch.setattr(run_pipeline, "require_env",
                            lambda: ("srv", "usr", "tok"))
        monkeypatch.setattr(
            run_pipeline, "process_strategy_ci",
            lambda key, s, u, t, args: ([], {
                PROCESSED: [], SKIPPED: [], BLOCKED: [],
                FAILED: [("RHAI-1", "Unrecognised state 'completed'")],
            }, []))

        rc = run_pipeline.main([
            "RHAISTRAT-1", "--ci",
            "--data-repo", str(tmp_path / "data"),
            "--log-dir", str(tmp_path / "logs"),
            "--output-dir", str(tmp_path / "artifacts"),
        ])

        assert rc == 1
