"""Tests for V2 code review response functions.

Tests diff scope computation, comment filtering, and scope checking.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pr_lifecycle import (
    compute_diff_scope,
    filter_unprocessed_comments,
    is_comment_in_scope,
    load_processed_comment_ids,
    _parse_patch_lines,
)


class TestParsePatchLines:

    def test_simple_addition(self):
        patch = (
            "@@ -10,3 +10,5 @@ func foo() {\n"
            " existing line\n"
            "+new line 1\n"
            "+new line 2\n"
            " another existing\n"
        )
        lines = _parse_patch_lines(patch)
        assert lines == {11, 12}

    def test_deletion_does_not_count(self):
        patch = (
            "@@ -10,4 +10,2 @@ func foo() {\n"
            " existing\n"
            "-deleted line 1\n"
            "-deleted line 2\n"
            " kept\n"
        )
        lines = _parse_patch_lines(patch)
        assert lines == set()

    def test_mixed_additions_and_deletions(self):
        patch = (
            "@@ -5,5 +5,5 @@ package main\n"
            " context\n"
            "-old line\n"
            "+new line\n"
            " context\n"
            " context\n"
        )
        lines = _parse_patch_lines(patch)
        assert 6 in lines
        assert len(lines) == 1

    def test_multiple_hunks(self):
        patch = (
            "@@ -1,3 +1,4 @@\n"
            " line 1\n"
            "+inserted at 2\n"
            " line 2\n"
            " line 3\n"
            "@@ -10,3 +11,4 @@ func bar() {\n"
            " existing\n"
            "+new at 12\n"
            " end\n"
        )
        lines = _parse_patch_lines(patch)
        assert 2 in lines
        assert 12 in lines

    def test_empty_patch(self):
        assert _parse_patch_lines("") == set()


class TestComputeDiffScope:

    def test_single_file(self):
        pr_files = [{
            "filename": "src/main.go",
            "patch": "@@ -10,3 +10,5 @@\n context\n+added1\n+added2\n end\n",
        }]
        scope = compute_diff_scope(pr_files)
        assert "src/main.go" in scope
        assert scope["src/main.go"] == {11, 12}

    def test_multiple_files(self):
        pr_files = [
            {
                "filename": "a.go",
                "patch": "@@ -1,2 +1,3 @@\n line\n+new\n end\n",
            },
            {
                "filename": "b.go",
                "patch": "@@ -5,2 +5,3 @@\n ctx\n+added\n end\n",
            },
        ]
        scope = compute_diff_scope(pr_files)
        assert len(scope) == 2
        assert 2 in scope["a.go"]
        assert 6 in scope["b.go"]

    def test_file_without_patch_is_skipped(self):
        pr_files = [
            {"filename": "binary.png", "patch": ""},
            {"filename": "binary2.png"},
        ]
        scope = compute_diff_scope(pr_files)
        assert len(scope) == 0

    def test_empty_file_list(self):
        assert compute_diff_scope([]) == {}


class TestIsCommentInScope:

    def test_comment_on_changed_line(self):
        scope = {"src/main.go": {10, 11, 12}}
        comment = {"path": "src/main.go", "line": 11}
        assert is_comment_in_scope(comment, scope) is True

    def test_comment_on_unchanged_line(self):
        scope = {"src/main.go": {10, 11, 12}}
        comment = {"path": "src/main.go", "line": 50}
        assert is_comment_in_scope(comment, scope) is False

    def test_comment_on_unmodified_file(self):
        scope = {"src/main.go": {10}}
        comment = {"path": "src/other.go", "line": 10}
        assert is_comment_in_scope(comment, scope) is False

    def test_comment_without_line(self):
        scope = {"src/main.go": {10}}
        comment = {"path": "src/main.go", "line": None}
        assert is_comment_in_scope(comment, scope) is False

    def test_comment_without_path(self):
        scope = {"src/main.go": {10}}
        comment = {"path": "", "line": 10}
        assert is_comment_in_scope(comment, scope) is False

    def test_empty_scope(self):
        comment = {"path": "src/main.go", "line": 10}
        assert is_comment_in_scope(comment, {}) is False


class TestFilterUnprocessedComments:

    def _comment(self, id=1, user="reviewer", in_reply_to=None):
        return {
            "id": id,
            "user": user,
            "path": "src/main.go",
            "line": 10,
            "body": "fix this",
            "created_at": "2026-07-01T00:00:00Z",
            "in_reply_to": in_reply_to,
        }

    def test_filters_our_own_comments(self):
        comments = [self._comment(id=1, user="dora-the-ai-coder")]
        result = filter_unprocessed_comments(comments, set(), "dora-the-ai-coder")
        assert len(result) == 0

    def test_filters_reply_comments(self):
        comments = [self._comment(id=2, in_reply_to=1)]
        result = filter_unprocessed_comments(comments, set(), "our-bot")
        assert len(result) == 0

    def test_filters_already_processed(self):
        comments = [self._comment(id=42)]
        result = filter_unprocessed_comments(comments, {42}, "our-bot")
        assert len(result) == 0

    def test_keeps_unprocessed_top_level(self):
        comments = [self._comment(id=99, user="human-reviewer")]
        result = filter_unprocessed_comments(comments, set(), "our-bot")
        assert len(result) == 1
        assert result[0]["id"] == 99

    def test_mixed_filtering(self):
        comments = [
            self._comment(id=1, user="human"),
            self._comment(id=2, user="our-bot"),
            self._comment(id=3, user="human", in_reply_to=1),
            self._comment(id=4, user="another-human"),
            self._comment(id=5, user="bot-reviewer"),
        ]
        processed = {5}
        result = filter_unprocessed_comments(comments, processed, "our-bot")
        assert [c["id"] for c in result] == [1, 4]


class TestLoadProcessedCommentIds:

    def test_nonexistent_file(self):
        ids = load_processed_comment_ids("/nonexistent/path.json")
        assert ids == set()

    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "version": 2,
                "replies": [
                    {"comment_id": 100, "action": "fix", "reply_body": "Fixed"},
                    {"comment_id": 200, "action": "skip", "reply_body": "N/A"},
                ],
            }, f)
            f.flush()
            ids = load_processed_comment_ids(f.name)
        os.unlink(f.name)
        assert ids == {100, 200}

    def test_empty_replies(self):
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as f:
            json.dump({"version": 2, "replies": []}, f)
            f.flush()
            ids = load_processed_comment_ids(f.name)
        os.unlink(f.name)
        assert ids == set()
