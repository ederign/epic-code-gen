"""Tests for create_pr.py."""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from create_pr import create_pr, _apply_template


MLFLOW_TEMPLATE = """## Summary

- Describe the change and why it is needed.
- Link the related Jira or GitHub issue, if applicable.

## Upstream / Downstream Impact

- [ ] Downstream-only change for `opendatahub-io/mlflow`
- [ ] Also affects upstream `mlflow/mlflow`
- [ ] No upstream impact / not applicable

If relevant, add any upstream issue or follow-up link here:

## Testing

- [ ] CI
- [ ] Unit tests
- [ ] Manual testing
- [ ] Not run (explain why)

Testing details:"""


def _no_template():
    return patch("github_utils.get_pr_template", return_value=None)


class TestApplyTemplate:

    def test_appends_missing_sections(self):
        body = "## Summary\n\nMy changes here."
        result = _apply_template(body, MLFLOW_TEMPLATE)

        assert "## Summary" in result
        assert "My changes here." in result
        assert "## Upstream / Downstream Impact" in result
        assert "## Testing" in result
        assert result.count("## Summary") == 1

    def test_preserves_existing_sections(self):
        body = ("## Summary\n\nStuff\n\n"
                "## Testing\n\n- [x] CI\n- [x] Unit tests")
        result = _apply_template(body, MLFLOW_TEMPLATE)

        assert "## Upstream / Downstream Impact" in result
        assert result.count("## Testing") == 1
        assert result.count("## Summary") == 1

    def test_no_change_when_all_sections_present(self):
        body = ("## Summary\n\nDone\n\n"
                "## Upstream / Downstream Impact\n\nN/A\n\n"
                "## Testing\n\nCI passed")
        result = _apply_template(body, MLFLOW_TEMPLATE)

        assert result.count("## Summary") == 1
        assert result.count("## Upstream / Downstream Impact") == 1
        assert result.count("## Testing") == 1

    def test_template_checkbox_content_preserved(self):
        body = "## Summary\n\nHello"
        result = _apply_template(body, MLFLOW_TEMPLATE)

        assert "- [ ] Downstream-only change" in result
        assert "- [ ] CI" in result


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
             patch("github_utils.create_pull_request",
                   return_value=mock_pr) as mock_create, \
             _no_template():
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
             patch("github_utils.create_pull_request",
                   return_value=mock_pr), \
             _no_template():
            result = create_pr(
                "org/repo", "ederign", "epic/TEST-001",
                title="title", body="body", base="develop",
            )

        assert result["base"] == "develop"
        mock_get.assert_not_called()

    def test_applies_template_to_body(self, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "ghp_test")

        mock_pr = {
            "number": 99,
            "url": "https://api.github.com/repos/org/repo/pulls/99",
            "html_url": "https://github.com/org/repo/pull/99",
            "state": "open",
        }

        with patch("github_utils.get_repo") as mock_get, \
             patch("github_utils.create_pull_request",
                   return_value=mock_pr) as mock_create, \
             patch("github_utils.get_pr_template",
                   return_value=MLFLOW_TEMPLATE):
            create_pr(
                "org/repo", "ederign", "epic/TEST-001",
                title="title",
                body="## Summary\n\nMy PR",
                base="master",
            )

        actual_body = mock_create.call_args[0][6]
        assert "## Upstream / Downstream Impact" in actual_body
        assert "## Testing" in actual_body

    def test_raises_on_missing_upstream(self, monkeypatch):
        monkeypatch.setenv("EPIC_CODEGEN_GITHUB_TOKEN", "ghp_test")

        with patch("github_utils.get_repo", return_value=None), \
             _no_template():
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
             patch("github_utils.create_pull_request",
                   return_value=mock_pr), \
             _no_template():
            result = create_pr(
                "org/repo", "ederign", "epic/TEST-001",
                title="title", body="body",
                token_var="MY_GH_TOKEN",
            )

        assert result["base"] == "master"
