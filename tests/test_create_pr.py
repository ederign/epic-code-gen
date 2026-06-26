"""Tests for create_pr.py."""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from create_pr import create_pr


class TestCreatePr:

    def test_creates_pr_with_default_base(self, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "ghp_test")

        mock_repo = {"default_branch": "main", "full_name": "org/repo"}
        mock_pr = {
            "number": 42,
            "url": "https://api.github.com/repos/org/repo/pulls/42",
            "html_url": "https://github.com/org/repo/pull/42",
            "state": "open",
        }

        with patch("github_utils.get_repo", return_value=mock_repo), \
             patch("github_utils.create_pull_request", return_value=mock_pr) as mock_create:
            result = create_pr(
                "org/repo", "ederign", "epic/TEST-001",
                title="TEST-001: Add feature",
                body="Generated code",
            )

        assert result["number"] == 42
        assert result["html_url"] == "https://github.com/org/repo/pull/42"
        assert result["base"] == "main"
        mock_create.assert_called_once_with(
            "org", "repo", "ederign", "epic/TEST-001", "main",
            "TEST-001: Add feature", "Generated code", "ghp_test",
        )

    def test_creates_pr_with_explicit_base(self, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "ghp_test")

        mock_pr = {
            "number": 10,
            "url": "https://api.github.com/repos/org/repo/pulls/10",
            "html_url": "https://github.com/org/repo/pull/10",
            "state": "open",
        }

        with patch("github_utils.get_repo") as mock_get, \
             patch("github_utils.create_pull_request", return_value=mock_pr):
            result = create_pr(
                "org/repo", "ederign", "epic/TEST-001",
                title="title", body="body", base="develop",
            )

        assert result["base"] == "develop"
        mock_get.assert_not_called()

    def test_raises_on_missing_upstream(self, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "ghp_test")

        with patch("github_utils.get_repo", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                create_pr(
                    "org/nonexistent", "ederign", "epic/TEST-001",
                    title="title", body="body",
                )

    def test_raises_on_missing_token(self, monkeypatch):
        monkeypatch.delenv("EPIC_CODEGEN_GITHUB_TOKEN", raising=False)

        with pytest.raises(EnvironmentError):
            create_pr(
                "org/repo", "ederign", "epic/TEST-001",
                title="title", body="body",
            )

    def test_custom_token_var(self, monkeypatch):
        monkeypatch.setenv("MY_GH_TOKEN", "ghp_custom")

        mock_repo = {"default_branch": "master", "full_name": "org/repo"}
        mock_pr = {
            "number": 1,
            "url": "https://api.github.com/repos/org/repo/pulls/1",
            "html_url": "https://github.com/org/repo/pull/1",
            "state": "open",
        }

        with patch("github_utils.get_repo", return_value=mock_repo), \
             patch("github_utils.create_pull_request", return_value=mock_pr):
            result = create_pr(
                "org/repo", "ederign", "epic/TEST-001",
                title="title", body="body",
                token_var="MY_GH_TOKEN",
            )

        assert result["base"] == "master"
