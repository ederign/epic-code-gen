"""Tests for review_cycle.py."""

import json
import os
import sys

import pytest
import yaml

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from review_cycle import (
    REVIEWERS,
    REVIEW_DISPATCH_LOOP,
    _resolve_vars,
    _check_review_file,
    _version_dir,
    _accepted_findings_path,
    _state_file_path,
    cmd_prompts,
    cmd_wait,
    cmd_verify,
    cmd_score,
    cmd_triage_prompt,
    cmd_dispatch_context,
)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


SAMPLE_REVIEW = """\
---
epic_id: TEST-001
dimension: {dimension}
version: 1
---

## Summary
Overall assessment.

## Findings

#### Critical
{critical_items}

#### Important
{important_items}

#### Minor
{minor_items}
"""


def _write_review_file(reviews_dir, dimension, criticals=0, importants=0, minors=0):
    """Write a review file matching score_reviews.py expected format."""
    crit = "\n".join(
        f'{i+1}. **Critical {i+1}** — `file.ts:{i+1}`\n   Description.'
        for i in range(criticals)
    )
    imp = "\n".join(
        f'{i+1}. **Important {i+1}** — `file.ts:{i+10}`\n   Description.'
        for i in range(importants)
    )
    minor = "\n".join(
        f'{i+1}. **Minor {i+1}** — `file.ts:{i+20}`\n   Description.'
        for i in range(minors)
    )
    content = SAMPLE_REVIEW.format(
        dimension=dimension,
        critical_items=crit if crit else "(none)",
        important_items=imp if imp else "(none)",
        minor_items=minor if minor else "(none)",
    )
    _write(os.path.join(reviews_dir, f"review-{dimension}.md"), content)


# -- prompts command ---------------------------------------------------------

class TestPrompts:
    def test_outputs_valid_yaml(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="prompts", epic_id="TEST-001", version="1",
                          only=None)
        cmd_prompts(args)
        output = capsys.readouterr().out
        data = yaml.safe_load(output)
        assert "agents" in data
        assert len(data["agents"]) == 6

    def test_agent_entries_have_required_fields(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="prompts", epic_id="TEST-001", version="1",
                          only=None)
        cmd_prompts(args)
        data = yaml.safe_load(capsys.readouterr().out)
        for agent in data["agents"]:
            assert "label" in agent
            assert "prompt_file" in agent
            assert "vars" in agent
            assert "DIFF_FILE=" in agent["vars"]
            assert "SPEC_FILE=" in agent["vars"]
            assert "REVIEW_FILE=" in agent["vars"]

    def test_vars_use_block_scalar(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="prompts", epic_id="TEST-001", version="1",
                          only=None)
        cmd_prompts(args)
        raw = capsys.readouterr().out
        assert "vars: |" in raw or "vars: |\n" in raw

    def test_only_flag_filters_dimensions(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="prompts", epic_id="TEST-001", version="1",
                          only="architecture,lint")
        cmd_prompts(args)
        data = yaml.safe_load(capsys.readouterr().out)
        dims = [a["label"].split(" — ")[1] for a in data["agents"]]
        assert dims == ["architecture", "lint"]

    def test_extra_vars_substituted(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="prompts", epic_id="TEST-001", version="2",
                          only="architecture")
        cmd_prompts(args)
        data = yaml.safe_load(capsys.readouterr().out)
        arch = data["agents"][0]
        assert "CLAUDE_MD_FILE=.target-repo/CLAUDE.md" in arch["vars"]

    def test_version_dir_in_paths(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="prompts", epic_id="TEST-001", version="3",
                          only="lint")
        cmd_prompts(args)
        data = yaml.safe_load(capsys.readouterr().out)
        lint = data["agents"][0]
        assert "v3/validation.json" in lint["vars"]
        assert "v3/diff.patch" in lint["vars"]
        assert "v3/review-lint.md" in lint["vars"]

    def test_epic_id_in_paths(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="prompts", epic_id="RHOAIENG-72103", version="1",
                          only="intent")
        cmd_prompts(args)
        data = yaml.safe_load(capsys.readouterr().out)
        intent = data["agents"][0]
        assert "RHOAIENG-72103" in intent["vars"]
        assert "EPIC_FILE=" in intent["vars"]


# -- wait command ------------------------------------------------------------

class TestWait:
    def test_all_done_exits_0(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        for r in REVIEWERS:
            _write_review_file(vdir, r["dimension"])
        args = _make_args(command="wait", epic_id="TEST-001", version="1",
                          max_wait=5)
        with pytest.raises(SystemExit) as exc:
            cmd_wait(args)
        assert exc.value.code == 0

    def test_none_done_exits_3(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs(_version_dir("TEST-001", "1"), exist_ok=True)
        args = _make_args(command="wait", epic_id="TEST-001", version="1",
                          max_wait=1)
        with pytest.raises(SystemExit) as exc:
            cmd_wait(args)
        assert exc.value.code == 3

    def test_partial_done_exits_3(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        _write_review_file(vdir, "architecture")
        _write_review_file(vdir, "tests")
        args = _make_args(command="wait", epic_id="TEST-001", version="1",
                          max_wait=1)
        with pytest.raises(SystemExit) as exc:
            cmd_wait(args)
        assert exc.value.code == 3

    def test_scored_done_unscored_pending_exits_0(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        for r in REVIEWERS:
            if r["scored"]:
                _write_review_file(vdir, r["dimension"])
        # wiring and interactions NOT written
        args = _make_args(command="wait", epic_id="TEST-001", version="1",
                          max_wait=5)
        with pytest.raises(SystemExit) as exc:
            cmd_wait(args)
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "All scored dimensions done" in out

    def test_progress_output(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        for r in REVIEWERS:
            _write_review_file(vdir, r["dimension"])
        args = _make_args(command="wait", epic_id="TEST-001", version="1",
                          max_wait=5)
        with pytest.raises(SystemExit):
            cmd_wait(args)
        out = capsys.readouterr().out
        assert "6/6 complete" in out
        assert "All done" in out


# -- _check_review_file -----------------------------------------------------

class TestCheckReviewFile:
    def test_nonexistent_file(self, tmp_path):
        assert not _check_review_file(str(tmp_path / "missing.md"))

    def test_empty_file(self, tmp_path):
        p = str(tmp_path / "review-tests.md")
        _write(p, "")
        assert not _check_review_file(p)

    def test_too_short(self, tmp_path):
        p = str(tmp_path / "review-tests.md")
        _write(p, "short")
        assert not _check_review_file(p)

    def test_missing_findings_heading(self, tmp_path):
        p = str(tmp_path / "review-tests.md")
        _write(p, "x" * 100)
        assert not _check_review_file(p)

    def test_valid_review(self, tmp_path):
        p = str(tmp_path / "review-tests.md")
        _write(p, SAMPLE_REVIEW.format(
            dimension="tests", critical_items="(none)",
            important_items="(none)", minor_items="(none)",
        ))
        assert _check_review_file(p)

    def test_summary_only_review(self, tmp_path):
        p = str(tmp_path / "review-tests.md")
        content = "## Summary\n" + "Good code. " * 20
        _write(p, content)
        assert _check_review_file(p)


# -- verify command ----------------------------------------------------------

class TestVerify:
    def test_all_scored_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        for r in REVIEWERS:
            if r["scored"]:
                _write_review_file(vdir, r["dimension"])
        args = _make_args(command="verify", epic_id="TEST-001", version="1")
        with pytest.raises(SystemExit) as exc:
            cmd_verify(args)
        assert exc.value.code == 0

    def test_missing_scored_dimension(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        _write_review_file(vdir, "architecture")
        _write_review_file(vdir, "tests")
        # lint and intent missing
        args = _make_args(command="verify", epic_id="TEST-001", version="1")
        with pytest.raises(SystemExit) as exc:
            cmd_verify(args)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "FAILED=" in out
        assert "lint" in out
        assert "intent" in out

    def test_unscored_dimensions_not_required(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        for r in REVIEWERS:
            if r["scored"]:
                _write_review_file(vdir, r["dimension"])
        # wiring and interactions NOT created — should still pass
        args = _make_args(command="verify", epic_id="TEST-001", version="1")
        with pytest.raises(SystemExit) as exc:
            cmd_verify(args)
        assert exc.value.code == 0


# -- score command -----------------------------------------------------------

class TestScore:
    def test_scores_saved_to_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        _write_review_file(vdir, "architecture", criticals=0, importants=1, minors=2)
        _write_review_file(vdir, "tests", criticals=0, importants=0, minors=1)
        _write_review_file(vdir, "lint", criticals=0, importants=0, minors=0)
        _write_review_file(vdir, "intent", criticals=0, importants=0, minors=0)
        args = _make_args(command="score", epic_id="TEST-001", version="1")
        with pytest.raises(SystemExit) as exc:
            cmd_score(args)
        assert exc.value.code == 0

        scores_path = os.path.join(vdir, "scores.json")
        assert os.path.exists(scores_path)
        with open(scores_path) as f:
            data = json.load(f)
        assert "verdict" in data
        assert "weighted_average" in data
        assert "dimensions" in data

    def test_incomplete_exits_2(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        vdir = _version_dir("TEST-001", "1")
        _write_review_file(vdir, "architecture")
        # missing tests, lint, intent
        args = _make_args(command="score", epic_id="TEST-001", version="1")
        with pytest.raises(SystemExit) as exc:
            cmd_score(args)
        assert exc.value.code == 2


# -- triage-prompt command ---------------------------------------------------

class TestTriagePrompt:
    def test_outputs_key_value_vars(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        os.makedirs("tmp", exist_ok=True)
        args = _make_args(command="triage-prompt", epic_id="TEST-001", version="1")
        cmd_triage_prompt(args)
        out = capsys.readouterr().out
        assert "EPIC_ID=TEST-001" in out
        assert "VERSION=1" in out
        assert "SCORES_FILE=" in out
        assert "REVIEWS_DIR=" in out
        assert "SPEC_FILE=" in out
        assert "ACCEPTED_FINDINGS_FILE=" in out
        assert "PRIOR_REVISION_NOTES=" in out
        assert "MAX_ITERATIONS=" in out

    def test_creates_empty_accepted_findings_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="triage-prompt", epic_id="TEST-001", version="1")
        cmd_triage_prompt(args)
        af_path = _accepted_findings_path("TEST-001")
        assert os.path.exists(af_path)
        with open(af_path) as f:
            data = json.load(f)
        assert data == []

    def test_prior_revision_notes_found(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        os.makedirs("tmp", exist_ok=True)
        v1_notes = os.path.join(
            "artifacts/codegen-runs/TEST-001/v1", "revision-notes.md"
        )
        _write(v1_notes, "# Revision notes v1")
        args = _make_args(command="triage-prompt", epic_id="TEST-001", version="2")
        cmd_triage_prompt(args)
        out = capsys.readouterr().out
        assert "v1/revision-notes.md" in out

    def test_no_prior_notes_shows_none(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        os.makedirs("tmp", exist_ok=True)
        args = _make_args(command="triage-prompt", epic_id="TEST-001", version="1")
        cmd_triage_prompt(args)
        out = capsys.readouterr().out
        assert "PRIOR_REVISION_NOTES=none" in out

    def test_reads_max_iterations_from_state(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        state_path = _state_file_path("TEST-001")
        _write(state_path, "phase: review\nversion: 1\nmax_iterations: 5\n")
        args = _make_args(command="triage-prompt", epic_id="TEST-001", version="1")
        cmd_triage_prompt(args)
        out = capsys.readouterr().out
        assert "MAX_ITERATIONS=5" in out


# -- dispatch-context command ------------------------------------------------

class TestDispatchContext:
    def test_no_state_file_silent(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = _make_args(command="dispatch-context")
        cmd_dispatch_context(args)
        assert capsys.readouterr().out == ""

    def test_review_phase_prints_loop(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        state_path = _state_file_path("TEST-001")
        _write(state_path, "phase: review\nversion: 2\n")
        args = _make_args(command="dispatch-context")
        cmd_dispatch_context(args)
        out = capsys.readouterr().out
        assert "REVIEW CYCLE RECOVERY" in out
        assert "review_cycle.py prompts" in out
        assert "TEST-001" in out

    def test_non_review_phase_silent(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        state_path = _state_file_path("TEST-001")
        _write(state_path, "phase: init\nversion: 0\n")
        args = _make_args(command="dispatch-context")
        cmd_dispatch_context(args)
        assert capsys.readouterr().out == ""


# -- _resolve_vars -----------------------------------------------------------

class TestResolveVars:
    def test_base_vars_present(self):
        reviewer = REVIEWERS[0]  # architecture
        result = _resolve_vars(reviewer, "TEST-001", "1")
        assert "EPIC_ID=TEST-001" in result
        assert "VERSION=1" in result
        assert "DIFF_FILE=" in result
        assert "SPEC_FILE=" in result
        assert "REVIEW_FILE=" in result

    def test_extra_vars_for_architecture(self):
        reviewer = REVIEWERS[0]
        result = _resolve_vars(reviewer, "TEST-001", "1")
        assert "CLAUDE_MD_FILE=.target-repo/CLAUDE.md" in result

    def test_extra_vars_for_lint(self):
        reviewer = REVIEWERS[2]  # lint
        result = _resolve_vars(reviewer, "TEST-001", "2")
        assert "VALIDATION_FILE=" in result
        assert "v2/validation.json" in result

    def test_extra_vars_for_intent(self):
        reviewer = REVIEWERS[3]  # intent
        result = _resolve_vars(reviewer, "TEST-001", "1")
        assert "EPIC_FILE=" in result
        assert "TEST-001.md" in result

    def test_no_extra_vars_for_tests(self):
        reviewer = REVIEWERS[1]  # tests
        result = _resolve_vars(reviewer, "TEST-001", "1")
        lines = result.strip().split("\n")
        keys = {l.split("=")[0] for l in lines}
        assert keys == {"EPIC_ID", "VERSION", "DIFF_FILE", "SPEC_FILE", "REVIEW_FILE"}


# -- Helpers -----------------------------------------------------------------

class _Args:
    """Simple namespace for command args."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_args(**kwargs):
    return _Args(**kwargs)
