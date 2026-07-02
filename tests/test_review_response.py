"""Tests for V2 code review response functions.

Tests diff scope computation, comment filtering, scope checking,
triage logic, and artifact writing.
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


# ─── Orchestrator Tests ──────────────────────────────────────────────────────

from review_response import (
    triage_comments,
    write_review_feedback,
    write_response_plan,
    save_pr_replies,
    load_review_config,
)


class TestTriageComments:

    def _comment(self, user="human", path="src/main.go", line=10):
        return {
            "id": 1,
            "user": user,
            "path": path,
            "line": line,
            "body": "fix this",
            "created_at": "2026-07-01T00:00:00Z",
            "in_reply_to": None,
            "diff_hunk": "",
            "commit_id": "",
        }

    def test_human_comment_in_scope_is_fix(self):
        scope = {"src/main.go": {10}}
        result = triage_comments(
            [self._comment(user="alice")], scope, {"coderabbitai"})
        assert result[0]["action"] == "fix"
        assert result[0]["is_bot"] is False

    def test_bot_comment_in_scope_is_fix(self):
        scope = {"src/main.go": {10}}
        result = triage_comments(
            [self._comment(user="coderabbitai")], scope, {"coderabbitai"})
        assert result[0]["action"] == "fix"
        assert result[0]["is_bot"] is True

    def test_comment_out_of_scope_is_skipped(self):
        scope = {"src/main.go": {99}}
        result = triage_comments(
            [self._comment(line=10)], scope, set())
        assert result[0]["action"] == "skip_out_of_scope"

    def test_comment_on_unmodified_file_is_skipped(self):
        scope = {"src/other.go": {10}}
        result = triage_comments(
            [self._comment(path="src/main.go")], scope, set())
        assert result[0]["action"] == "skip_out_of_scope"

    def test_mixed_triage(self):
        scope = {"src/main.go": {10, 20}}
        comments = [
            self._comment(user="human", line=10),
            self._comment(user="coderabbitai", line=20),
            self._comment(user="human", line=50),
        ]
        result = triage_comments(comments, scope, {"coderabbitai"})
        assert result[0]["action"] == "fix"
        assert result[1]["action"] == "fix"
        assert result[2]["action"] == "skip_out_of_scope"


class TestWriteArtifacts:

    def test_write_review_feedback(self):
        comments = [{
            "id": 1, "user": "alice", "path": "src/main.go", "line": 10,
            "body": "Missing nil check", "is_bot": False,
            "action": "fix", "reason": "human",
            "diff_hunk": "@@ -10 +10 @@\n-old\n+new",
            "created_at": "", "in_reply_to": None, "commit_id": "",
        }]
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False) as f:
            path = f.name
        write_review_feedback(comments, path)
        content = open(path).read()
        os.unlink(path)
        assert "`src/main.go`" in content
        assert "Missing nil check" in content
        assert "alice" in content

    def test_write_response_plan(self):
        comments = [
            {"id": 1, "user": "alice", "path": "a.go", "line": 10,
             "body": "Fix this", "action": "fix", "reason": "human",
             "is_bot": False},
            {"id": 2, "user": "bot", "path": "b.go", "line": 20,
             "body": "Refactor", "action": "skip_out_of_scope",
             "reason": "out of scope", "is_bot": True},
        ]
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False) as f:
            path = f.name
        write_response_plan(comments, path)
        content = open(path).read()
        os.unlink(path)
        assert "To fix:** 1" in content
        assert "To skip:** 1" in content
        assert "Fix this" in content


class TestSavePrReplies:

    def test_creates_new_file(self):
        with tempfile.NamedTemporaryFile(
                suffix=".json", delete=False) as f:
            path = f.name
        os.unlink(path)

        replies = [{"comment_id": 1, "action": "fix", "reply_body": "Done"}]
        save_pr_replies(replies, path, version=2)

        with open(path) as f:
            data = json.load(f)
        os.unlink(path)
        assert len(data["replies"]) == 1
        assert data["replies"][0]["version"] == 2

    def test_appends_to_existing(self):
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "replies": [
                    {"comment_id": 1, "version": 2, "action": "fix",
                     "reply_body": "Fixed"},
                ],
            }, f)
            path = f.name

        new_replies = [
            {"comment_id": 2, "action": "skip", "reply_body": "N/A"},
        ]
        save_pr_replies(new_replies, path, version=3)

        with open(path) as f:
            data = json.load(f)
        os.unlink(path)
        assert len(data["replies"]) == 2
        assert data["replies"][1]["version"] == 3


class TestLoadReviewConfig:

    def test_loads_config(self):
        config = load_review_config()
        assert "bot_reviewers" in config
        assert "our_user" in config
        assert "coderabbitai" in config["bot_reviewers"]
