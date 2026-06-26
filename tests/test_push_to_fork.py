"""Tests for push_to_fork.py."""

import os
import subprocess
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from push_to_fork import push


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


def _init_bare_repo(path):
    """Create a bare git repo to act as a remote."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(path)],
                   capture_output=True, check=True)
    return str(path)


class TestPush:

    def test_raises_without_fork_remote(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        with pytest.raises(ValueError, match="No 'fork' remote"):
            push(repo, "main")

    def test_pushes_to_fork_remote(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        bare = _init_bare_repo(tmp_path / "fork-bare")

        subprocess.run(["git", "remote", "add", "fork", bare],
                       cwd=repo, capture_output=True, check=True)

        result = push(repo, "main")

        assert result["pushed"] is True
        assert result["branch"] == "main"
        assert result["remote"] == "fork"

        out = subprocess.run(
            ["git", "branch", "-r"], cwd=repo,
            capture_output=True, text=True,
        )
        assert "fork/main" in out.stdout

    def test_pushes_non_current_branch(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        bare = _init_bare_repo(tmp_path / "fork-bare")

        subprocess.run(["git", "checkout", "-b", "epic/TEST-001"],
                       cwd=repo, capture_output=True, check=True)
        with open(os.path.join(repo, "new.txt"), "w") as f:
            f.write("new file\n")
        subprocess.run(["git", "add", "."], cwd=repo,
                       capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "epic work"],
                       cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "checkout", "main"],
                       cwd=repo, capture_output=True, check=True)

        subprocess.run(["git", "remote", "add", "fork", bare],
                       cwd=repo, capture_output=True, check=True)

        result = push(repo, "epic/TEST-001")

        assert result["pushed"] is True
        assert result["branch"] == "epic/TEST-001"

    def test_force_push(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        bare = _init_bare_repo(tmp_path / "fork-bare")

        subprocess.run(["git", "remote", "add", "fork", bare],
                       cwd=repo, capture_output=True, check=True)

        push(repo, "main")

        subprocess.run(["git", "commit", "--allow-empty", "-m", "amend"],
                       cwd=repo, capture_output=True, check=True)

        result = push(repo, "main", force=True)
        assert result["pushed"] is True
