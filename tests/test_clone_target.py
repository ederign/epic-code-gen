"""Tests for clone_target.py."""

import os
import subprocess
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from clone_target import (
    clone,
    _extract_slug,
    _url_matches,
    _ensure_branch,
    _setup_fork_remote,
)


def _init_bare_repo(path):
    """Create a bare git repo to act as a remote."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(path)],
                   capture_output=True, check=True)
    return str(path)


def _init_repo(path):
    """Create a non-bare git repo with an initial commit."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)],
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"],
                   cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=str(path), capture_output=True, check=True)
    readme = os.path.join(str(path), "README.md")
    with open(readme, "w") as f:
        f.write("# Test\n")
    subprocess.run(["git", "add", "."], cwd=str(path),
                   capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"],
                   cwd=str(path), capture_output=True, check=True)
    return str(path)


# ─── URL Utilities ───────────────────────────────────────────────────────────

class TestExtractSlug:

    def test_https_url(self):
        assert _extract_slug("https://github.com/org/repo") == "org/repo"

    def test_https_with_git_suffix(self):
        assert _extract_slug("https://github.com/org/repo.git") == "org/repo"

    def test_ssh_url(self):
        assert _extract_slug("git@github.com:org/repo.git") == "org/repo"

    def test_trailing_slash(self):
        assert _extract_slug("https://github.com/org/repo/") == "org/repo"

    def test_non_github(self):
        assert _extract_slug("https://gitlab.com/org/repo") is None


class TestUrlMatches:

    def test_matches_https(self):
        remote_output = "origin\thttps://github.com/org/repo.git (fetch)"
        assert _url_matches("https://github.com/org/repo", remote_output)

    def test_no_match(self):
        remote_output = "origin\thttps://github.com/other/repo.git (fetch)"
        assert not _url_matches("https://github.com/org/repo", remote_output)


# ─── Clone ───────────────────────────────────────────────────────────────────

class TestClone:

    def test_fresh_clone(self, tmp_path):
        remote = _init_repo(tmp_path / "remote")
        dest = str(tmp_path / "clone")

        result = clone(remote, "RHAISTRAT-1749-E001", dest=dest)

        assert result["status"] == "created"
        assert result["branch"] == "epic/RHAISTRAT-1749-E001"
        assert os.path.isdir(dest)
        assert os.path.isfile(os.path.join(dest, "README.md"))

        out = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=dest, capture_output=True, text=True,
        )
        assert out.stdout.strip() == "epic/RHAISTRAT-1749-E001"

    def test_existing_clone_reuses(self, tmp_path):
        remote = _init_repo(tmp_path / "remote")
        dest = str(tmp_path / "clone")

        clone(remote, "RHAISTRAT-1749-E001", dest=dest)
        result = clone(remote, "RHAISTRAT-1749-E001", dest=dest)

        assert result["status"] == "existing"

    def test_clean_flag_removes_existing(self, tmp_path):
        remote = _init_repo(tmp_path / "remote")
        dest = str(tmp_path / "clone")

        clone(remote, "RHAISTRAT-1749-E001", dest=dest)

        marker = os.path.join(dest, "MARKER")
        with open(marker, "w") as f:
            f.write("old")

        result = clone(remote, "RHAISTRAT-1749-E002", dest=dest, clean=True)

        assert result["status"] == "created"
        assert result["branch"] == "epic/RHAISTRAT-1749-E002"
        assert not os.path.isfile(marker)

    def test_different_repo_raises(self, tmp_path):
        remote1 = _init_repo(tmp_path / "remote1")
        remote2 = _init_repo(tmp_path / "remote2")
        dest = str(tmp_path / "clone")

        clone(remote1, "EPIC-001", dest=dest)

        with pytest.raises(ValueError, match="different repo"):
            clone(remote2, "EPIC-002", dest=dest)

    def test_fork_owner_with_local_remote(self, tmp_path):
        remote = _init_repo(tmp_path / "remote")
        dest = str(tmp_path / "clone")

        result = clone(remote, "EPIC-001", dest=dest, fork_owner="ederign")

        assert result["status"] == "created"
        assert result["fork_url"] is None  # non-github URL, so no fork

    def test_nonexistent_remote_fails(self, tmp_path):
        with pytest.raises(subprocess.CalledProcessError):
            clone("/nonexistent/repo", "EPIC-001",
                  dest=str(tmp_path / "clone"))


# ─── Branch Handling ─────────────────────────────────────────────────────────

class TestEnsureBranch:

    def test_creates_new_branch(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _ensure_branch(repo, "epic/TEST-001")

        out = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo, capture_output=True, text=True,
        )
        assert out.stdout.strip() == "epic/TEST-001"

    def test_switches_to_existing_branch(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        subprocess.run(["git", "checkout", "-b", "epic/TEST-001"],
                       cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "main"],
                       cwd=repo, capture_output=True, check=True)

        _ensure_branch(repo, "epic/TEST-001")

        out = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo, capture_output=True, text=True,
        )
        assert out.stdout.strip() == "epic/TEST-001"


# ─── Fork Remote ─────────────────────────────────────────────────────────────

class TestSetupForkRemote:

    def test_adds_fork_remote(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        url = _setup_fork_remote(
            repo, "https://github.com/org/myrepo.git", "ederign")

        assert url == "https://github.com/ederign/myrepo.git"

        out = subprocess.run(
            ["git", "remote", "-v"], cwd=repo,
            capture_output=True, text=True,
        )
        assert "ederign/myrepo" in out.stdout

    def test_updates_existing_fork_remote(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _setup_fork_remote(
            repo, "https://github.com/org/myrepo.git", "user1")
        url = _setup_fork_remote(
            repo, "https://github.com/org/myrepo.git", "user2")

        assert url == "https://github.com/user2/myrepo.git"

    def test_non_github_returns_none(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        url = _setup_fork_remote(
            repo, "https://gitlab.com/org/repo.git", "ederign")
        assert url is None
