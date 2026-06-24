"""Tests for run_index.py."""

import json
import os
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from run_index import (
    build_index,
    write_index,
    _read_run_metadata,
    _parse_yaml_simple,
    _coerce_value,
)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


SAMPLE_METADATA = """\
epic_id: RHAISTRAT-1749-E001
target_repo: https://github.com/opendatahub-io/mlflow-go
branch: epic/RHAISTRAT-1749-E001
language: go
status: completed
versions: 1
final_score: 9.4
scores_by_dimension:
  architecture: 10.0
  tests: 8.0
  lint: 10.0
  intent: 10.0
started_at: "2026-06-23"
mode: dry-run
"""

EXHAUSTED_METADATA = """\
epic_id: RHAISTRAT-1749-E002
target_repo: https://github.com/opendatahub-io/odh-dashboard
branch: epic/RHAISTRAT-1749-E002
language: typescript
status: exhausted
versions: 3
final_score: 7.2
scores_by_dimension:
  architecture: 8.0
  tests: 6.0
  lint: 7.0
  intent: 7.0
started_at: "2026-06-24"
mode: dry-run
"""

ERROR_METADATA = """\
epic_id: RHAISTRAT-1748-E001
target_repo: https://github.com/opendatahub-io/odh-dashboard
branch: epic/RHAISTRAT-1748-E001
language: typescript
status: error
versions: 0
final_score: 0
started_at: "2026-06-25"
"""


# --- _coerce_value ---

class TestCoerceValue:
    def test_integer(self):
        assert _coerce_value("42") == 42

    def test_float(self):
        assert _coerce_value("9.4") == 9.4

    def test_string(self):
        assert _coerce_value("hello") == "hello"

    def test_true(self):
        assert _coerce_value("true") is True

    def test_false(self):
        assert _coerce_value("false") is False

    def test_null(self):
        assert _coerce_value("null") is None


# --- _parse_yaml_simple ---

class TestParseYamlSimple:
    def test_flat_values(self):
        result = _parse_yaml_simple("key1: value1\nkey2: 42\n")
        assert result["key1"] == "value1"
        assert result["key2"] == 42

    def test_nested_values(self):
        content = "parent:\n  child1: 10.0\n  child2: 8.0\n"
        result = _parse_yaml_simple(content)
        assert result["parent"]["child1"] == 10.0
        assert result["parent"]["child2"] == 8.0

    def test_quoted_strings(self):
        result = _parse_yaml_simple('date: "2026-06-23"\n')
        assert result["date"] == "2026-06-23"

    def test_skips_comments(self):
        result = _parse_yaml_simple("# comment\nkey: value\n")
        assert result["key"] == "value"
        assert len(result) == 1

    def test_full_metadata(self):
        result = _parse_yaml_simple(SAMPLE_METADATA)
        assert result["epic_id"] == "RHAISTRAT-1749-E001"
        assert result["status"] == "completed"
        assert result["final_score"] == 9.4
        assert result["scores_by_dimension"]["architecture"] == 10.0
        assert result["scores_by_dimension"]["tests"] == 8.0


# --- _read_run_metadata ---

class TestReadRunMetadata:
    def test_reads_valid_file(self, tmp_path):
        path = tmp_path / "run-metadata.yaml"
        path.write_text(SAMPLE_METADATA)
        result = _read_run_metadata(str(path))
        assert result["epic_id"] == "RHAISTRAT-1749-E001"
        assert result["final_score"] == 9.4

    def test_returns_none_for_missing(self, tmp_path):
        result = _read_run_metadata(str(tmp_path / "nope.yaml"))
        assert result is None

    def test_returns_none_for_empty(self, tmp_path):
        path = tmp_path / "run-metadata.yaml"
        path.write_text("")
        result = _read_run_metadata(str(path))
        assert result is None


# --- build_index ---

class TestBuildIndex:
    def test_single_run(self, tmp_path):
        run_dir = tmp_path / "RHAISTRAT-1749-E001"
        run_dir.mkdir()
        (run_dir / "run-metadata.yaml").write_text(SAMPLE_METADATA)

        index = build_index(str(tmp_path))
        assert index["total"] == 1
        assert index["runs"][0]["epic_id"] == "RHAISTRAT-1749-E001"
        assert index["summary"]["completed"] == 1

    def test_multiple_runs(self, tmp_path):
        for name, content in [
            ("RHAISTRAT-1749-E001", SAMPLE_METADATA),
            ("RHAISTRAT-1749-E002", EXHAUSTED_METADATA),
            ("RHAISTRAT-1748-E001", ERROR_METADATA),
        ]:
            run_dir = tmp_path / name
            run_dir.mkdir()
            (run_dir / "run-metadata.yaml").write_text(content)

        index = build_index(str(tmp_path))
        assert index["total"] == 3
        assert index["summary"]["completed"] == 1
        assert index["summary"]["exhausted"] == 1
        assert index["summary"]["error"] == 1

    def test_skips_dirs_without_metadata(self, tmp_path):
        (tmp_path / "some-dir").mkdir()
        run_dir = tmp_path / "RHAISTRAT-1749-E001"
        run_dir.mkdir()
        (run_dir / "run-metadata.yaml").write_text(SAMPLE_METADATA)

        index = build_index(str(tmp_path))
        assert index["total"] == 1

    def test_skips_index_json(self, tmp_path):
        run_dir = tmp_path / "RHAISTRAT-1749-E001"
        run_dir.mkdir()
        (run_dir / "run-metadata.yaml").write_text(SAMPLE_METADATA)
        (tmp_path / "index.json").write_text("{}")

        index = build_index(str(tmp_path))
        assert index["total"] == 1

    def test_empty_dir(self, tmp_path):
        index = build_index(str(tmp_path))
        assert index["total"] == 0
        assert index["runs"] == []
        assert index["summary"] == {}

    def test_missing_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            build_index(str(tmp_path / "nope"))

    def test_sorted_by_epic_id(self, tmp_path):
        for name, content in [
            ("RHAISTRAT-1749-E002", EXHAUSTED_METADATA),
            ("RHAISTRAT-1748-E001", ERROR_METADATA),
            ("RHAISTRAT-1749-E001", SAMPLE_METADATA),
        ]:
            run_dir = tmp_path / name
            run_dir.mkdir()
            (run_dir / "run-metadata.yaml").write_text(content)

        index = build_index(str(tmp_path))
        epic_ids = [r["epic_id"] for r in index["runs"]]
        assert epic_ids == [
            "RHAISTRAT-1748-E001",
            "RHAISTRAT-1749-E001",
            "RHAISTRAT-1749-E002",
        ]


# --- write_index ---

class TestWriteIndex:
    def test_writes_json_file(self, tmp_path):
        run_dir = tmp_path / "RHAISTRAT-1749-E001"
        run_dir.mkdir()
        (run_dir / "run-metadata.yaml").write_text(SAMPLE_METADATA)

        index = write_index(str(tmp_path))

        index_path = tmp_path / "index.json"
        assert index_path.exists()

        with open(index_path) as f:
            written = json.load(f)

        assert written["total"] == 1
        assert written["runs"][0]["epic_id"] == "RHAISTRAT-1749-E001"

    def test_overwrites_existing(self, tmp_path):
        run_dir = tmp_path / "RHAISTRAT-1749-E001"
        run_dir.mkdir()
        (run_dir / "run-metadata.yaml").write_text(SAMPLE_METADATA)
        (tmp_path / "index.json").write_text('{"old": true}')

        write_index(str(tmp_path))

        with open(tmp_path / "index.json") as f:
            written = json.load(f)
        assert "old" not in written
        assert written["total"] == 1

    def test_returns_index(self, tmp_path):
        run_dir = tmp_path / "RHAISTRAT-1749-E001"
        run_dir.mkdir()
        (run_dir / "run-metadata.yaml").write_text(SAMPLE_METADATA)

        result = write_index(str(tmp_path))
        assert result["total"] == 1
