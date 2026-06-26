"""Tests for github_utils.py."""

import json
import os
import sys
import urllib.error

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from github_utils import (
    extract_slug,
    authenticated_url,
    sanitized_url,
    require_env,
    DEFAULT_TOKEN_VAR,
)


# ─── URL Helpers ──────────────────────────────────────────────────────────────

class TestExtractSlug:

    def test_https_url(self):
        assert extract_slug("https://github.com/org/repo") == "org/repo"

    def test_https_with_git_suffix(self):
        assert extract_slug("https://github.com/org/repo.git") == "org/repo"

    def test_ssh_url(self):
        assert extract_slug("git@github.com:org/repo.git") == "org/repo"

    def test_trailing_slash(self):
        assert extract_slug("https://github.com/org/repo/") == "org/repo"

    def test_non_github(self):
        assert extract_slug("https://gitlab.com/org/repo") is None

    def test_no_repo(self):
        assert extract_slug("https://github.com/org") is None

    def test_empty_string(self):
        assert extract_slug("") is None


class TestAuthenticatedUrl:

    def test_builds_url_with_token(self):
        url = authenticated_url("org/repo", "ghp_abc123")
        assert url == "https://x-access-token:ghp_abc123@github.com/org/repo.git"

    def test_different_slug(self):
        url = authenticated_url("user/project", "token123")
        assert url == "https://x-access-token:token123@github.com/user/project.git"


class TestSanitizedUrl:

    def test_builds_url_without_token(self):
        assert sanitized_url("org/repo") == "https://github.com/org/repo.git"


# ─── Environment ─────────────────────────────────────────────────────────────

class TestRequireEnv:

    def test_reads_default_var(self, monkeypatch):
        monkeypatch.setenv(DEFAULT_TOKEN_VAR, "test-token")
        assert require_env() == "test-token"

    def test_reads_custom_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "custom-token")
        assert require_env("MY_TOKEN") == "custom-token"

    def test_missing_var_raises(self, monkeypatch):
        monkeypatch.delenv(DEFAULT_TOKEN_VAR, raising=False)
        with pytest.raises(EnvironmentError, match=DEFAULT_TOKEN_VAR):
            require_env()

    def test_empty_var_raises(self, monkeypatch):
        monkeypatch.setenv(DEFAULT_TOKEN_VAR, "")
        with pytest.raises(EnvironmentError):
            require_env()
