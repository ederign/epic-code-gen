"""Tests for clone_target.py."""

import os
import subprocess
import sys
from unittest.mock import patch

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from clone_target import (
    clone,
    _extract_slug,
    _url_matches,
    _ensure_branch,
    _setup_fork_remote,
    _configure_git_identity,
    DEFAULT_FORK_OWNER,
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

    def test_fork_owner_with_local_remote(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "ghp_fake")
        remote = _init_repo(tmp_path / "remote")
        dest = str(tmp_path / "clone")

        with patch("github_utils.get_authenticated_user",
                   return_value={"login": "ederign", "email": None}):
            result = clone(remote, "EPIC-001", dest=dest, fork_owner="ederign")

        assert result["status"] == "created"
        assert result["fork_url"] is None  # non-github URL, so no fork
        assert result["fork_created"] is False

    def test_fork_owner_without_token_fails_early(self, tmp_path, monkeypatch):
        monkeypatch.delenv("EPIC_CODEGEN_GITHUB_TOKEN", raising=False)
        remote = _init_repo(tmp_path / "remote")
        dest = str(tmp_path / "clone")

        with pytest.raises(EnvironmentError, match="EPIC_CODEGEN_GITHUB_TOKEN"):
            clone(remote, "EPIC-001", dest=dest, fork_owner="ederign")

    def test_no_fork_owner_skips_token(self, tmp_path, monkeypatch):
        monkeypatch.delenv("EPIC_CODEGEN_GITHUB_TOKEN", raising=False)
        remote = _init_repo(tmp_path / "remote")
        dest = str(tmp_path / "clone")

        result = clone(remote, "EPIC-001", dest=dest, fork_owner=None)

        assert result["status"] == "created"
        assert result["fork_url"] is None

    def test_default_fork_owner(self):
        assert DEFAULT_FORK_OWNER == "dora-the-ai-coder"

    def test_nonexistent_remote_fails(self, tmp_path):
        with pytest.raises(subprocess.CalledProcessError):
            clone("/nonexistent/repo", "EPIC-001",
                  dest=str(tmp_path / "clone"), fork_owner=None)


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


# ─── Git Identity ───────────────────────────────────────────────────────────

class TestConfigureGitIdentity:

    def test_sets_name_and_email_from_token(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        mock_user = {"login": "dora-the-ai-coder", "email": "dora@example.com"}

        with patch("github_utils.get_authenticated_user", return_value=mock_user):
            _configure_git_identity(repo, "fake-token")

        name = subprocess.run(
            ["git", "config", "user.name"], cwd=repo,
            capture_output=True, text=True,
        )
        email = subprocess.run(
            ["git", "config", "user.email"], cwd=repo,
            capture_output=True, text=True,
        )
        assert name.stdout.strip() == "dora-the-ai-coder"
        assert email.stdout.strip() == "dora@example.com"

    def test_falls_back_to_noreply_email(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        mock_user = {"login": "dora-the-ai-coder", "email": None}

        with patch("github_utils.get_authenticated_user", return_value=mock_user):
            _configure_git_identity(repo, "fake-token")

        email = subprocess.run(
            ["git", "config", "user.email"], cwd=repo,
            capture_output=True, text=True,
        )
        assert email.stdout.strip() == "dora-the-ai-coder@users.noreply.github.com"


# ─── Fork Remote ─────────────────────────────────────────────────────────────

class TestSetupForkRemote:

    def test_adds_fork_remote(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        result = _setup_fork_remote(
            repo, "https://github.com/org/myrepo.git", "ederign")

        assert result["fork_url"] == "https://github.com/ederign/myrepo.git"
        assert result["fork_created"] is False

        out = subprocess.run(
            ["git", "remote", "-v"], cwd=repo,
            capture_output=True, text=True,
        )
        assert "ederign/myrepo" in out.stdout

    def test_updates_existing_fork_remote(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _setup_fork_remote(
            repo, "https://github.com/org/myrepo.git", "user1")
        result = _setup_fork_remote(
            repo, "https://github.com/org/myrepo.git", "user2")

        assert result["fork_url"] == "https://github.com/user2/myrepo.git"

    def test_non_github_returns_none(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        result = _setup_fork_remote(
            repo, "https://gitlab.com/org/repo.git", "ederign")
        assert result["fork_url"] is None
        assert result["fork_created"] is False

    def test_with_token_uses_authenticated_url(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        with patch("github_utils.ensure_fork", return_value=("ederign/myrepo", False)):
            result = _setup_fork_remote(
                repo, "https://github.com/org/myrepo.git", "ederign",
                token="ghp_test123")

        assert result["fork_url"] == "https://github.com/ederign/myrepo.git"
        assert result["fork_created"] is False

        out = subprocess.run(
            ["git", "remote", "-v"], cwd=repo,
            capture_output=True, text=True,
        )
        assert "x-access-token" in out.stdout

    def test_with_token_creates_fork(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        with patch("github_utils.ensure_fork", return_value=("newuser/myrepo", True)):
            result = _setup_fork_remote(
                repo, "https://github.com/org/myrepo.git", "newuser",
                token="ghp_test123")

        assert result["fork_created"] is True
