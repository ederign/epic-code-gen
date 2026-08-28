"""Tests for check_ledger.py."""

import os
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from check_ledger import (  # noqa: E402
    check_all,
    check_diff,
    is_code,
    is_ledger,
    ledger_files,
    strip_code,
)

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


def write(path, frontmatter, body=""):
    """Write a ledger file with the given frontmatter dict."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["---"]
    for k, v in frontmatter.items():
        lines.append(f"{k}: {v}")
    lines += ["---", "", body]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


VALID = {
    "id": "task-example",
    "title": "Example",
    "type": "task",
    "status": "pending",
    "repos": "[epic-code-gen]",
}


@pytest.fixture
def docs(tmp_path):
    """A minimal valid ledger tree."""
    d = tmp_path / "docs"
    write(str(d / "tasks" / "pending" / "task-example.md"), VALID, "Body.")
    return d


class TestCheckAllValid:
    def test_valid_tree_has_no_errors(self, docs, tmp_path):
        assert check_all(str(docs), str(tmp_path)) == []

    def test_empty_tree_is_an_error(self, tmp_path):
        empty = tmp_path / "docs"
        empty.mkdir()
        errors = check_all(str(empty), str(tmp_path))
        assert len(errors) == 1
        assert "no ledger files" in errors[0]


class TestRequiredFields:
    @pytest.mark.parametrize("field", ["id", "title", "type", "status", "repos"])
    def test_missing_required_field(self, docs, tmp_path, field):
        fm = {k: v for k, v in VALID.items() if k != field}
        write(str(docs / "tasks" / "pending" / "task-example.md"), fm)
        errors = check_all(str(docs), str(tmp_path))
        assert any(f"missing required field `{field}`" in e for e in errors)

    def test_no_frontmatter_at_all(self, docs, tmp_path):
        p = docs / "tasks" / "pending" / "task-example.md"
        p.write_text("Just prose, no frontmatter.\n")
        errors = check_all(str(docs), str(tmp_path))
        assert any("no frontmatter" in e for e in errors)

    def test_invalid_type(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"),
              {**VALID, "type": "nonsense"})
        errors = check_all(str(docs), str(tmp_path))
        assert any("type `nonsense`" in e for e in errors)

    def test_unknown_repo(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"),
              {**VALID, "repos": "[not-a-real-repo]"})
        errors = check_all(str(docs), str(tmp_path))
        assert any("unknown repo `not-a-real-repo`" in e for e in errors)


class TestIdMatchesFilename:
    def test_mismatch_is_an_error(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"),
              {**VALID, "id": "task-something-else"})
        errors = check_all(str(docs), str(tmp_path))
        assert any("does not match filename" in e for e in errors)

    def test_readme_is_exempt(self, docs, tmp_path):
        """Index pages are not ledger entries."""
        (docs / "decisions").mkdir(parents=True, exist_ok=True)
        (docs / "decisions" / "README.md").write_text("# Index\n\nNo frontmatter.\n")
        assert check_all(str(docs), str(tmp_path)) == []


class TestStatusMatchesDirectory:
    """State is represented by location — the two must agree."""

    @pytest.mark.parametrize("subdir,status", [
        ("tasks/pending", "pending"),
        ("tasks/current", "current"),
        ("tasks/blocked", "blocked"),
        ("tasks/done", "done"),
        ("bugs/open", "open"),
        ("bugs/fixed", "fixed"),
        ("bugs/wontfix", "wontfix"),
    ])
    def test_matching_status_is_accepted(self, tmp_path, subdir, status):
        d = tmp_path / "docs"
        fm = {**VALID, "id": "item", "status": status}
        if status in ("done", "fixed"):
            fm["commits"] = "[abc1234]"
        if subdir.startswith("bugs"):
            fm["type"] = "bug"
        write(str(d / subdir / "item.md"), fm)
        assert check_all(str(d), str(tmp_path)) == []

    def test_status_disagreeing_with_directory(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"),
              {**VALID, "status": "done", "commits": "[abc1234]"})
        errors = check_all(str(docs), str(tmp_path))
        assert any("lives in tasks/pending/" in e for e in errors)

    def test_bug_in_wrong_tree(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "bugs" / "open" / "bug-x.md"),
              {**VALID, "id": "bug-x", "type": "bug", "status": "fixed"})
        errors = check_all(str(d), str(tmp_path))
        assert any("expected `open`" in e for e in errors)


class TestEvidenceRequired:
    """done/fixed must record what closed them."""

    def test_done_without_evidence_fails(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done"})
        errors = check_all(str(d), str(tmp_path))
        assert any("requires evidence" in e for e in errors)

    def test_done_with_commits_passes(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done", "commits": "[abc1234, def5678]"})
        assert check_all(str(d), str(tmp_path)) == []

    def test_done_with_jira_passes(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done", "jira": "RHAIFIRST-1"})
        assert check_all(str(d), str(tmp_path)) == []

    def test_empty_commits_list_is_not_evidence(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done", "commits": "[]"})
        errors = check_all(str(d), str(tmp_path))
        assert any("requires evidence" in e for e in errors)

    def test_pending_needs_no_evidence(self, docs, tmp_path):
        assert check_all(str(docs), str(tmp_path)) == []


class TestCommitShaTyping:
    """An unquoted leading-zero SHA is read by YAML as octal.

    `commits: [0346470]` silently becomes the integer 118072 — a real defect
    found in this ledger during its own verification pass.
    """

    def test_unquoted_octal_sha_is_caught(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done", "commits": "[0346470]"})
        errors = check_all(str(d), str(tmp_path))
        assert any("not a string" in e for e in errors), errors

    def test_quoted_octal_sha_passes(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done", "commits": '["0346470"]'})
        assert check_all(str(d), str(tmp_path)) == []

    def test_malformed_sha_is_caught(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done", "commits": '["not-a-sha"]'})
        errors = check_all(str(d), str(tmp_path))
        assert any("not a valid commit SHA" in e for e in errors), errors

    def test_uppercase_sha_is_caught(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done", "commits": '["ABC1234"]'})
        errors = check_all(str(d), str(tmp_path))
        assert any("not a valid commit SHA" in e for e in errors), errors

    def test_full_length_sha_passes(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "tasks" / "done" / "task-x.md"),
              {**VALID, "id": "task-x", "status": "done",
               "commits": '["c2264752da1a7f4add3bf138b08fbbc982d901ea"]'})
        assert check_all(str(d), str(tmp_path)) == []


class TestCrossReferences:
    def test_unresolved_wikilink(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"), VALID,
              "See [[task-does-not-exist]].")
        errors = check_all(str(docs), str(tmp_path))
        assert any("[[task-does-not-exist]] does not resolve" in e for e in errors)

    def test_resolved_wikilink(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-other.md"),
              {**VALID, "id": "task-other"})
        write(str(docs / "tasks" / "pending" / "task-example.md"), VALID,
              "See [[task-other]].")
        assert check_all(str(docs), str(tmp_path)) == []

    def test_missing_adr_reference(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "decisions" / "ADR-0001-real.md"),
              {"id": "ADR-0001-real", "title": "Real", "type": "adr",
               "status": "accepted", "repos": "[epic-code-gen]"})
        write(str(d / "tasks" / "pending" / "task-example.md"), VALID,
              "Per [ADR-0099] this is fine.")
        errors = check_all(str(d), str(tmp_path))
        assert any("ADR-0099" in e for e in errors)

    def test_existing_adr_reference(self, tmp_path):
        d = tmp_path / "docs"
        write(str(d / "decisions" / "ADR-0001-real.md"),
              {"id": "ADR-0001-real", "title": "Real", "type": "adr",
               "status": "accepted", "repos": "[epic-code-gen]"})
        write(str(d / "tasks" / "pending" / "task-example.md"), VALID,
              "Per [ADR-0001] this is fine.")
        assert check_all(str(d), str(tmp_path)) == []

    def test_broken_relative_link(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"), VALID,
              "See [the thing](./missing.md).")
        errors = check_all(str(docs), str(tmp_path))
        assert any("broken link" in e for e in errors)

    def test_external_and_anchor_links_ignored(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"), VALID,
              "[ext](https://example.com) and [anchor](#section).")
        assert check_all(str(docs), str(tmp_path)) == []


class TestStripCode:
    """A reference inside backticks documents syntax; it isn't a reference."""

    def test_inline_code_span_stripped(self):
        assert "[[id]]" not in strip_code("Link with `[[id]]` syntax.")

    def test_fenced_block_stripped(self):
        text = "before\n\n```\n[[not-a-link]]\n```\n\nafter"
        out = strip_code(text)
        assert "[[not-a-link]]" not in out
        assert "before" in out and "after" in out

    def test_real_link_survives(self):
        assert "[[real-id]]" in strip_code("See [[real-id]] for detail.")

    def test_wikilink_in_code_is_not_flagged(self, docs, tmp_path):
        write(str(docs / "tasks" / "pending" / "task-example.md"), VALID,
              "Use `[[id]]` to link. Fenced:\n\n```\n[[also-not-real]]\n```\n")
        assert check_all(str(docs), str(tmp_path)) == []


class TestPathClassification:
    @pytest.mark.parametrize("path", [
        "scripts/run_pipeline.py",
        "scripts/parse_prototype.js",
        ".claude/agents/lint-reviewer.md",
        ".claude/skills/epic-codegen/SKILL.md",
        "ci-scripts/run-claude.sh",
    ])
    def test_code_paths(self, path):
        assert is_code(path)

    @pytest.mark.parametrize("path", [
        "docs/tasks/done/task-x.md",
        "docs/bugs/open/bug-y.md",
        "docs/decisions/ADR-0001-x.md",
        "README.md",
        "AGENTS.md",
        "tests/test_check_ledger.py",
        "scripts/notes.txt",
    ])
    def test_non_code_paths(self, path):
        assert not is_code(path)

    @pytest.mark.parametrize("path,expected", [
        ("docs/tasks/pending/task-x.md", True),
        ("docs/bugs/fixed/bug-y.md", True),
        ("docs/decisions/ADR-0001-x.md", True),
        ("docs/architecture/01-system-overview.md", False),
        ("scripts/run_pipeline.py", False),
    ])
    def test_ledger_paths(self, path, expected):
        assert is_ledger(path) is expected


class TestCheckDiff:
    def test_code_without_companion_fails(self):
        ok, msg = check_diff(["scripts/run_pipeline.py"])
        assert not ok
        assert "no ledger companion" in msg

    def test_code_with_task_passes(self):
        ok, msg = check_diff(
            ["scripts/run_pipeline.py", "docs/tasks/done/task-x.md"])
        assert ok

    def test_code_with_bug_passes(self):
        ok, _ = check_diff(["scripts/run_pipeline.py", "docs/bugs/fixed/bug-x.md"])
        assert ok

    def test_code_with_adr_passes(self):
        ok, _ = check_diff(
            ["scripts/run_pipeline.py", "docs/decisions/ADR-0035-x.md"])
        assert ok

    def test_no_code_changes_passes(self):
        ok, msg = check_diff(["README.md", "docs/architecture/01-system-overview.md"])
        assert ok
        assert "no code changes" in msg

    def test_empty_diff_passes(self):
        ok, _ = check_diff([])
        assert ok

    def test_ledger_none_escape_hatch(self):
        ok, msg = check_diff(["scripts/run_pipeline.py"],
                             body="## Ledger\n\nLedger: none — typo fix\n")
        assert ok
        assert "Ledger: none" in msg

    def test_ledger_none_is_case_insensitive(self):
        ok, _ = check_diff(["scripts/run_pipeline.py"], body="ledger: NONE - trivial")
        assert ok

    def test_unrelated_body_does_not_excuse(self):
        ok, _ = check_diff(["scripts/run_pipeline.py"],
                           body="This PR does some things.")
        assert not ok

    def test_architecture_doc_is_not_a_companion(self):
        """Architecture docs explain; they don't record work."""
        ok, _ = check_diff(
            ["scripts/run_pipeline.py", "docs/architecture/02-pipeline-state-machine.md"])
        assert not ok

    def test_many_code_files_are_truncated_in_message(self):
        files = [f"scripts/mod_{i}.py" for i in range(15)]
        ok, msg = check_diff(files)
        assert not ok
        assert "and 5 more" in msg


class TestRealLedger:
    """The repo's own ledger must satisfy its own rules."""

    def test_real_ledger_is_consistent(self):
        errors = check_all()
        assert errors == [], "\n".join(errors)

    def test_real_ledger_is_not_empty(self):
        assert len(ledger_files()) > 100
