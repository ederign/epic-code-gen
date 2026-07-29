"""Tests for rebase_pr — rebasing epic branches onto their upstream base.

Uses real local git repositories rather than mocks, so the conflict
resolution loop is exercised against actual git behaviour.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from rebase_pr import (
    conflicted_files,
    detect_base_branch,
    rebase_in_progress,
    rebase_onto_base,
)


def _git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True)


def _commit(repo, name, content, message):
    with open(os.path.join(repo, name), "w") as f:
        f.write(content)
    _git(["add", name], repo)
    _git(["commit", "-m", message], repo)


@pytest.fixture
def upstream_and_clone(tmp_path):
    """An 'upstream' repo plus a clone with an epic branch on an older base."""
    upstream = str(tmp_path / "upstream")
    os.makedirs(upstream)
    _git(["init", "-b", "main"], upstream)
    _git(["config", "user.email", "t@example.com"], upstream)
    _git(["config", "user.name", "Test"], upstream)
    _commit(upstream, "shared.txt", "line1\nline2\nline3\n", "base")

    clone = str(tmp_path / "clone")
    _git(["clone", upstream, clone], str(tmp_path))
    _git(["config", "user.email", "t@example.com"], clone)
    _git(["config", "user.name", "Test"], clone)
    return upstream, clone


class TestDetectBaseBranch:

    def test_detects_main_from_origin(self, upstream_and_clone):
        _, clone = upstream_and_clone
        assert detect_base_branch(clone) == "main"

    def test_falls_back_when_no_remote(self, tmp_path):
        solo = str(tmp_path / "solo")
        os.makedirs(solo)
        _git(["init", "-b", "main"], solo)
        assert detect_base_branch(solo) == "main"


class TestRebaseOntoBase:

    def test_already_current_is_a_noop(self, upstream_and_clone):
        _, clone = upstream_and_clone
        _git(["checkout", "-b", "epic/E1"], clone)

        result = rebase_onto_base(clone, "epic/E1")

        assert result["already_current"] is True
        assert result["rebased"] is False
        assert result["error"] is None

    def test_replays_branch_onto_new_upstream_commit(self, upstream_and_clone):
        upstream, clone = upstream_and_clone
        _git(["checkout", "-b", "epic/E1"], clone)
        _commit(clone, "feature.txt", "feature\n", "add feature")
        old_head = _git(["rev-parse", "HEAD"], clone).stdout.strip()

        # Upstream moves on, touching a different file — no conflict.
        _commit(upstream, "other.txt", "other\n", "upstream work")

        result = rebase_onto_base(clone, "epic/E1")

        assert result["error"] is None
        assert result["rebased"] is True
        assert result["new_head"] != old_head
        assert result["conflict_rounds"] == 0
        # Both the upstream commit and our feature survive.
        assert os.path.isfile(os.path.join(clone, "other.txt"))
        assert os.path.isfile(os.path.join(clone, "feature.txt"))

    def test_conflict_without_resolver_aborts_cleanly(
            self, upstream_and_clone):
        upstream, clone = upstream_and_clone
        _git(["checkout", "-b", "epic/E1"], clone)
        _commit(clone, "shared.txt", "line1\nBRANCH\nline3\n", "branch edit")
        old_head = _git(["rev-parse", "HEAD"], clone).stdout.strip()

        _commit(upstream, "shared.txt", "line1\nUPSTREAM\nline3\n",
                "upstream edit")

        result = rebase_onto_base(clone, "epic/E1", resolver=None)

        assert result["error"] is not None
        assert result["aborted"] is True
        assert result["rebased"] is False
        assert "shared.txt" in result["conflicted_files"]
        # Aborting must leave the branch exactly where it was.
        assert _git(["rev-parse", "HEAD"], clone).stdout.strip() == old_head
        assert rebase_in_progress(clone) is False

    def test_resolver_completes_the_rebase(self, upstream_and_clone):
        upstream, clone = upstream_and_clone
        _git(["checkout", "-b", "epic/E1"], clone)
        _commit(clone, "shared.txt", "line1\nBRANCH\nline3\n", "branch edit")

        _commit(upstream, "shared.txt", "line1\nUPSTREAM\nline3\n",
                "upstream edit")

        calls = []

        def resolver(conflicts, repo):
            calls.append(list(conflicts))
            # Keep both sides, as a real resolver should.
            with open(os.path.join(repo, "shared.txt"), "w") as f:
                f.write("line1\nUPSTREAM\nBRANCH\nline3\n")
            return True

        result = rebase_onto_base(clone, "epic/E1", resolver=resolver)

        assert result["error"] is None
        assert result["rebased"] is True
        assert result["conflict_rounds"] == 1
        assert calls == [["shared.txt"]]
        assert rebase_in_progress(clone) is False
        with open(os.path.join(clone, "shared.txt")) as f:
            content = f.read()
        assert "UPSTREAM" in content and "BRANCH" in content

    def test_failing_resolver_aborts_and_reports(self, upstream_and_clone):
        upstream, clone = upstream_and_clone
        _git(["checkout", "-b", "epic/E1"], clone)
        _commit(clone, "shared.txt", "line1\nBRANCH\nline3\n", "branch edit")
        old_head = _git(["rev-parse", "HEAD"], clone).stdout.strip()

        _commit(upstream, "shared.txt", "line1\nUPSTREAM\nline3\n",
                "upstream edit")

        result = rebase_onto_base(
            clone, "epic/E1", resolver=lambda conflicts, repo: False)

        assert result["error"] is not None
        assert result["aborted"] is True
        assert _git(["rev-parse", "HEAD"], clone).stdout.strip() == old_head

    def test_recovers_from_a_rebase_left_in_progress(self, upstream_and_clone):
        """A crashed previous run must not wedge the next one."""
        upstream, clone = upstream_and_clone
        _git(["checkout", "-b", "epic/E1"], clone)
        _commit(clone, "shared.txt", "line1\nBRANCH\nline3\n", "branch edit")
        _commit(upstream, "shared.txt", "line1\nUPSTREAM\nline3\n",
                "upstream edit")
        _git(["fetch", "origin"], clone)

        # Leave a conflicted rebase mid-flight.
        _git(["rebase", "origin/main"], clone)
        assert rebase_in_progress(clone) is True

        def resolver(conflicts, repo):
            with open(os.path.join(repo, "shared.txt"), "w") as f:
                f.write("line1\nUPSTREAM\nBRANCH\nline3\n")
            return True

        result = rebase_onto_base(clone, "epic/E1", resolver=resolver)

        assert result["error"] is None
        assert result["rebased"] is True

    def test_rejects_non_git_directory(self, tmp_path):
        plain = str(tmp_path / "plain")
        os.makedirs(plain)
        result = rebase_onto_base(plain, "epic/E1")
        assert result["error"] is not None
        assert "not a git repository" in result["error"]

    def test_missing_base_ref_is_an_error(self, upstream_and_clone):
        _, clone = upstream_and_clone
        _git(["checkout", "-b", "epic/E1"], clone)
        result = rebase_onto_base(clone, "epic/E1", base_branch="nonexistent")
        assert result["error"] is not None
        assert "not found" in result["error"]


class TestConflictedFiles:

    def test_empty_when_clean(self, upstream_and_clone):
        _, clone = upstream_and_clone
        assert conflicted_files(clone) == []
