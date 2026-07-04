"""Tests for artifact_utils.py — schema validation, frontmatter I/O, file discovery."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from artifact_utils import (
    SCHEMAS,
    ValidationError,
    validate,
    apply_defaults,
    get_schema_yaml,
    read_frontmatter,
    read_frontmatter_validated,
    write_frontmatter,
    update_frontmatter,
    find_epic_task,
    find_codegen_run,
    find_codegen_review,
    scan_epic_tasks,
    rebuild_index,
)


# ─── Schema Validation ──────────────────────────────────────────────────────

class TestEpicTaskSchema:

    def _valid_data(self, **overrides):
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "title": "Add text search",
            "strategy_key": "RHAISTRAT-1665",
            "target_repo": "opendatahub-io/odh-dashboard",
            "target_branch": "main",
            "status": "Pending",
        }
        data.update(overrides)
        return data

    def test_valid_minimal(self):
        errors = validate(self._valid_data(), "epic-task")
        assert errors == []

    def test_valid_with_optional_fields(self):
        data = self._valid_data(
            components=["dashboard"],
            dependencies=["RHAISTRAT-1665-E000"],
            effort_size="S",
            readiness_score=8,
            codegen_branch="epic/RHAISTRAT-1665-E001",
        )
        errors = validate(data, "epic-task")
        assert errors == []

    def test_missing_required_epic_id(self):
        data = self._valid_data()
        del data["epic_id"]
        errors = validate(data, "epic-task")
        assert any("epic_id" in e for e in errors)

    def test_invalid_epic_id_pattern(self):
        errors = validate(self._valid_data(epic_id="bad-123"), "epic-task")
        assert any("does not match" in e for e in errors)

    def test_valid_real_jira_key(self):
        errors = validate(self._valid_data(epic_id="RHOAIENG-72103"), "epic-task")
        assert errors == []

    def test_blocks_field_accepted(self):
        data = self._valid_data(blocks=["RHOAIENG-72104"])
        errors = validate(data, "epic-task")
        assert errors == []

    def test_jira_status_field_accepted(self):
        data = self._valid_data(jira_status="In Progress")
        errors = validate(data, "epic-task")
        assert errors == []

    def test_pr_url_field_accepted(self):
        data = self._valid_data(
            pr_url="https://github.com/org/repo/pull/42")
        errors = validate(data, "epic-task")
        assert errors == []

    def test_invalid_status_enum(self):
        errors = validate(self._valid_data(status="Unknown"), "epic-task")
        assert any("not in" in e for e in errors)

    def test_valid_status_values(self):
        for status in ["Pending", "Ready", "InProgress", "Generated",
                        "Validated", "Failed"]:
            errors = validate(self._valid_data(status=status), "epic-task")
            assert errors == [], f"Status '{status}' should be valid"

    def test_invalid_effort_size(self):
        errors = validate(self._valid_data(effort_size="XXL"), "epic-task")
        assert any("not in" in e for e in errors)

    def test_unknown_field(self):
        data = self._valid_data(unknown_field="value")
        errors = validate(data, "epic-task")
        assert any("Unknown field" in e for e in errors)

    def test_wrong_type(self):
        errors = validate(self._valid_data(readiness_score="eight"), "epic-task")
        assert any("expected int" in e for e in errors)

    def test_components_must_be_list(self):
        errors = validate(self._valid_data(components="dashboard"), "epic-task")
        assert any("expected list" in e for e in errors)


class TestCodegenRunSchema:

    def _valid_data(self, **overrides):
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "status": "Running",
            "iterations": 0,
            "max_iterations": 10,
            "target_repo": "opendatahub-io/odh-dashboard",
            "target_branch": "main",
            "codegen_branch": "epic/RHAISTRAT-1665-E001",
        }
        data.update(overrides)
        return data

    def test_valid_minimal(self):
        errors = validate(self._valid_data(), "codegen-run")
        assert errors == []

    def test_valid_with_validation_dict(self):
        data = self._valid_data(validation={
            "lint_pass": True,
            "typecheck_pass": True,
            "tests_pass": False,
        })
        errors = validate(data, "codegen-run")
        assert errors == []

    def test_invalid_status(self):
        errors = validate(self._valid_data(status="Pending"), "codegen-run")
        assert any("not in" in e for e in errors)

    def test_validation_nested_type_error(self):
        data = self._valid_data(validation={
            "lint_pass": "yes",
            "typecheck_pass": True,
            "tests_pass": True,
        })
        errors = validate(data, "codegen-run")
        assert any("lint_pass" in e and "expected bool" in e for e in errors)

    def test_validation_unknown_nested_field(self):
        data = self._valid_data(validation={
            "lint_pass": True,
            "typecheck_pass": True,
            "tests_pass": True,
            "coverage": 85,
        })
        errors = validate(data, "codegen-run")
        assert any("unknown field" in e for e in errors)


class TestCodegenReviewSchema:

    def _valid_data(self, **overrides):
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "recommendation": "approve",
            "total_score": 9,
            "scores": {
                "lint": 2,
                "typecheck": 2,
                "tests": 2,
                "intent_coverage": 2,
                "architecture": 1,
            },
        }
        data.update(overrides)
        return data

    def test_valid(self):
        errors = validate(self._valid_data(), "codegen-review")
        assert errors == []

    def test_invalid_recommendation(self):
        errors = validate(
            self._valid_data(recommendation="maybe"), "codegen-review")
        assert any("not in" in e for e in errors)

    def test_missing_scores(self):
        data = self._valid_data()
        del data["scores"]
        errors = validate(data, "codegen-review")
        assert any("scores" in e for e in errors)


# ─── Defaults ────────────────────────────────────────────────────────────────

class TestApplyDefaults:

    def test_epic_task_defaults(self):
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "title": "Test",
            "strategy_key": "RHAISTRAT-1665",
            "target_repo": "repo",
            "status": "Pending",
        }
        result = apply_defaults(data, "epic-task")
        assert result["target_branch"] == ""
        assert result["components"] is None
        assert result["dependencies"] is None
        assert result["effort_size"] is None

    def test_codegen_run_defaults(self):
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "status": "Running",
            "target_repo": "repo",
            "target_branch": "main",
            "codegen_branch": "branch",
        }
        result = apply_defaults(data, "codegen-run")
        assert result["iterations"] == 0
        assert result["max_iterations"] == 10


# ─── Schema YAML ─────────────────────────────────────────────────────────────

class TestGetSchemaYaml:

    def test_all_schemas_produce_yaml(self):
        for schema_type in SCHEMAS:
            yaml_str = get_schema_yaml(schema_type)
            assert "required:" in yaml_str
            assert len(yaml_str) > 50

    def test_unknown_schema_raises(self):
        with pytest.raises(ValueError, match="Unknown schema"):
            get_schema_yaml("nonexistent")


# ─── Frontmatter Read/Write ─────────────────────────────────────────────────

class TestFrontmatterIO:

    def test_write_and_read_roundtrip(self, tmp_path):
        path = str(tmp_path / "test.md")
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "title": "Test Epic",
            "strategy_key": "RHAISTRAT-1665",
            "target_repo": "opendatahub-io/odh-dashboard",
            "target_branch": "main",
            "status": "Pending",
        }
        write_frontmatter(path, data, "epic-task")

        read_data, body = read_frontmatter_validated(path, "epic-task")
        assert read_data["epic_id"] == "RHAISTRAT-1665-E001"
        assert read_data["title"] == "Test Epic"
        assert read_data["target_branch"] == "main"

    def test_preserves_body(self, tmp_path):
        path = str(tmp_path / "test.md")
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "title": "Test",
            "strategy_key": "RHAISTRAT-1665",
            "target_repo": "repo",
            "target_branch": "main",
            "status": "Pending",
        }
        write_frontmatter(path, data, "epic-task")

        with open(path, "a") as f:
            f.write("\n## Body Content\n\nSome text.\n")

        read_data, body = read_frontmatter(path)
        assert "## Body Content" in body
        assert "Some text." in body

    def test_update_frontmatter(self, tmp_path):
        path = str(tmp_path / "test.md")
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "title": "Test",
            "strategy_key": "RHAISTRAT-1665",
            "target_repo": "repo",
            "target_branch": "main",
            "status": "Pending",
        }
        write_frontmatter(path, data, "epic-task")
        update_frontmatter(path, {"status": "InProgress"}, "epic-task")

        read_data, _ = read_frontmatter_validated(path, "epic-task")
        assert read_data["status"] == "InProgress"

    def test_write_invalid_data_raises(self, tmp_path):
        path = str(tmp_path / "test.md")
        data = {"epic_id": "BAD"}
        with pytest.raises(ValidationError):
            write_frontmatter(path, data, "epic-task")

    def test_read_no_frontmatter_raises(self, tmp_path):
        path = str(tmp_path / "test.md")
        with open(path, "w") as f:
            f.write("# No frontmatter\n")
        with pytest.raises(ValidationError, match="No frontmatter"):
            read_frontmatter_validated(path, "epic-task")

    def test_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "deep" / "nested" / "test.md")
        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "title": "Test",
            "strategy_key": "RHAISTRAT-1665",
            "target_repo": "repo",
            "target_branch": "main",
            "status": "Pending",
        }
        write_frontmatter(path, data, "epic-task")
        assert os.path.isfile(path)


# ─── File Discovery ──────────────────────────────────────────────────────────

class TestFileDiscovery:

    def _setup_artifacts(self, tmp_path):
        tasks_dir = tmp_path / "epic-tasks"
        tasks_dir.mkdir(parents=True)
        reviews_dir = tmp_path / "codegen-reviews"
        reviews_dir.mkdir(parents=True)
        runs_dir = tmp_path / "codegen-runs" / "RHAISTRAT-1665-E001"
        runs_dir.mkdir(parents=True)

        data = {
            "epic_id": "RHAISTRAT-1665-E001",
            "title": "Test",
            "strategy_key": "RHAISTRAT-1665",
            "target_repo": "repo",
            "target_branch": "main",
            "status": "Pending",
        }
        write_frontmatter(
            str(tasks_dir / "RHAISTRAT-1665-E001.md"), data, "epic-task")

        review = {
            "epic_id": "RHAISTRAT-1665-E001",
            "recommendation": "approve",
            "total_score": 9,
            "scores": {
                "lint": 2, "typecheck": 2, "tests": 2,
                "intent_coverage": 2, "architecture": 1,
            },
        }
        write_frontmatter(
            str(reviews_dir / "RHAISTRAT-1665-E001-review.md"),
            review, "codegen-review")

        return str(tmp_path)

    def test_find_epic_task(self, tmp_path):
        artifacts = self._setup_artifacts(tmp_path)
        path = find_epic_task(artifacts, "RHAISTRAT-1665-E001")
        assert path is not None
        assert path.endswith("RHAISTRAT-1665-E001.md")

    def test_find_epic_task_not_found(self, tmp_path):
        artifacts = self._setup_artifacts(tmp_path)
        path = find_epic_task(artifacts, "RHAISTRAT-9999-E001")
        assert path is None

    def test_find_codegen_run(self, tmp_path):
        artifacts = self._setup_artifacts(tmp_path)
        path = find_codegen_run(artifacts, "RHAISTRAT-1665-E001")
        assert path is not None
        assert path.endswith("RHAISTRAT-1665-E001")

    def test_find_codegen_review(self, tmp_path):
        artifacts = self._setup_artifacts(tmp_path)
        path = find_codegen_review(artifacts, "RHAISTRAT-1665-E001")
        assert path is not None
        assert path.endswith("-review.md")

    def test_scan_epic_tasks(self, tmp_path):
        artifacts = self._setup_artifacts(tmp_path)
        results = scan_epic_tasks(artifacts)
        assert len(results) == 1
        assert results[0][1]["epic_id"] == "RHAISTRAT-1665-E001"

    def test_rebuild_index(self, tmp_path):
        artifacts = self._setup_artifacts(tmp_path)
        content = rebuild_index(artifacts)
        assert "RHAISTRAT-1665-E001" in content
        assert "9/10" in content
        assert "approve" in content
