"""Tests for pr_lifecycle.py — PR status and review feedback."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pr_lifecycle import (
    derive_pr_state,
    format_review_feedback,
    parse_pr_url,
)


class TestParsePrUrl:

    def test_valid_url(self):
        owner, repo, num = parse_pr_url(
            "https://github.com/mlflow/mlflow/pull/42")
        assert owner == "mlflow"
        assert repo == "mlflow"
        assert num == 42

    def test_valid_url_with_trailing_slash(self):
        owner, repo, num = parse_pr_url(
            "https://github.com/org/repo/pull/123/")
        assert owner == "org"
        assert repo == "repo"
        assert num == 123

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Not a valid"):
            parse_pr_url("https://gitlab.com/org/repo/merge_requests/1")

    def test_non_github_url_raises(self):
        with pytest.raises(ValueError):
            parse_pr_url("https://example.com/pull/1")


class TestDerivePrState:

    def test_merged_returns_done(self):
        assert derive_pr_state({
            "merged": True, "state": "closed",
            "reviews_changes_requested": 0,
        }) == "Done"

    def test_closed_not_merged_returns_ready(self):
        assert derive_pr_state({
            "merged": False, "state": "closed",
            "reviews_changes_requested": 0,
        }) == "Ready"

    def test_open_with_changes_requested(self):
        assert derive_pr_state({
            "merged": False, "state": "open",
            "reviews_changes_requested": 2,
        }) == "PRChangesRequested"

    def test_open_no_changes_requested(self):
        assert derive_pr_state({
            "merged": False, "state": "open",
            "reviews_changes_requested": 0,
        }) == "PRCreated"


class TestFormatReviewFeedback:

    def test_no_feedback(self):
        result = format_review_feedback({"reviews": [], "comments": []})
        assert "No actionable review feedback" in result

    def test_changes_requested(self):
        result = format_review_feedback({
            "reviews": [{
                "user": "reviewer1",
                "state": "CHANGES_REQUESTED",
                "body": "Please fix the tests",
                "submitted_at": "2026-06-30T10:00:00Z",
            }],
            "comments": [],
        })
        assert "Requested Changes" in result
        assert "reviewer1" in result
        assert "fix the tests" in result

    def test_inline_comments_grouped_by_file(self):
        result = format_review_feedback({
            "reviews": [],
            "comments": [
                {"user": "alice", "path": "src/main.py", "line": 10,
                 "body": "Missing docstring", "created_at": "",
                 "in_reply_to": None},
                {"user": "bob", "path": "src/main.py", "line": 20,
                 "body": "Use a constant here", "created_at": "",
                 "in_reply_to": None},
                {"user": "alice", "path": "tests/test_main.py", "line": 5,
                 "body": "Add edge case", "created_at": "",
                 "in_reply_to": None},
            ],
        })
        assert "`src/main.py`" in result
        assert "`tests/test_main.py`" in result
        assert "Missing docstring" in result

    def test_replies_are_excluded(self):
        result = format_review_feedback({
            "reviews": [],
            "comments": [
                {"user": "alice", "path": "f.py", "line": 1,
                 "body": "Fix this", "created_at": "",
                 "in_reply_to": None},
                {"user": "bob", "path": "f.py", "line": 1,
                 "body": "Done", "created_at": "",
                 "in_reply_to": 123},
            ],
        })
        assert "Fix this" in result
        assert "Done" not in result

    def test_approvals_section(self):
        result = format_review_feedback({
            "reviews": [{
                "user": "lead",
                "state": "APPROVED",
                "body": "LGTM",
                "submitted_at": "",
            }],
            "comments": [],
        })
        assert "Approvals" in result
        assert "lead" in result
        assert "LGTM" in result
