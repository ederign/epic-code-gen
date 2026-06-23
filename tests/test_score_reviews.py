"""Tests for score_reviews.py."""

import os
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from score_reviews import (
    score_reviews,
    format_report,
    _extract_score,
    _parse_score_from_file,
    DIMENSION_WEIGHTS,
)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _write_review(reviews_dir, dimension, score, body="Review content."):
    """Write a review file with the given score."""
    content = f"""---
score: {score}
---

# {dimension.title()} Review

{body}

**Score:** {score}/10
"""
    _write(os.path.join(reviews_dir, f"review-{dimension}.md"), content)


def _write_all_reviews(reviews_dir, scores):
    """Write review files for all dimensions."""
    for dim, score in scores.items():
        _write_review(reviews_dir, dim, score)


# ─── Score Extraction ────────────────────────────────────────────────────────

class TestExtractScore:

    def test_from_frontmatter(self):
        content = "---\nscore: 8\n---\nBody"
        assert _extract_score(content) == 8.0

    def test_from_frontmatter_float(self):
        content = "---\nscore: 7.5\n---\nBody"
        assert _extract_score(content) == 7.5

    def test_from_bold_markdown(self):
        content = "# Review\n\n**Score:** 9/10\n"
        assert _extract_score(content) == 9.0

    def test_from_plain_markdown(self):
        content = "# Review\n\nScore: 7\n"
        assert _extract_score(content) == 7.0

    def test_from_bold_no_slash(self):
        content = "**Score:** 6"
        assert _extract_score(content) == 6.0

    def test_no_score(self):
        content = "# Review\n\nNo score here.\n"
        assert _extract_score(content) is None

    def test_frontmatter_takes_precedence(self):
        content = "---\nscore: 8\n---\n**Score:** 5/10"
        assert _extract_score(content) == 8.0


# ─── Parse Score From File ───────────────────────────────────────────────────

class TestParseScoreFromFile:

    def test_valid_review_file(self, tmp_path):
        filepath = str(tmp_path / "review-tests.md")
        _write(filepath, "---\nscore: 9\n---\nContent")
        dim, score = _parse_score_from_file(filepath)
        assert dim == "tests"
        assert score == 9.0

    def test_invalid_filename(self, tmp_path):
        filepath = str(tmp_path / "notes.md")
        _write(filepath, "---\nscore: 9\n---\n")
        dim, score = _parse_score_from_file(filepath)
        assert dim is None

    def test_no_score_in_content(self, tmp_path):
        filepath = str(tmp_path / "review-lint.md")
        _write(filepath, "No frontmatter, no score.")
        dim, score = _parse_score_from_file(filepath)
        assert dim == "lint"
        assert score is None


# ─── Score Reviews ───────────────────────────────────────────────────────────

class TestScoreReviews:

    def test_all_pass(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 8, "tests": 9, "lint": 8, "intent": 9,
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "pass"
        assert result["weighted_average"] >= 8.0
        assert len(result["missing"]) == 0

    def test_fail_low_average(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 5, "tests": 5, "lint": 5, "intent": 5,
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "fail"

    def test_fail_dimension_below_floor(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 9, "tests": 9, "lint": 4, "intent": 9,
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "fail"

    def test_near_miss(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 8, "tests": 8, "lint": 5.5, "intent": 8,
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "near-miss"

    def test_missing_dimension(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 9, "tests": 9, "lint": 8,
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "incomplete"
        assert "intent" in result["missing"]

    def test_nonexistent_dir(self):
        with pytest.raises(FileNotFoundError):
            score_reviews("/nonexistent/reviews")

    def test_weighted_average_calculation(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 10, "tests": 10, "lint": 10, "intent": 10,
        })
        result = score_reviews(reviews_dir)
        assert result["weighted_average"] == 10.0

    def test_weights_sum_to_one(self):
        assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.001

    def test_ignores_non_review_files(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 8, "tests": 9, "lint": 8, "intent": 9,
        })
        _write(os.path.join(reviews_dir, "notes.md"), "Not a review")
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "pass"

    def test_error_on_unparseable_score(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 8, "tests": 9, "lint": 8, "intent": 9,
        })
        _write(os.path.join(reviews_dir, "review-tests.md"), "No score here")
        result = score_reviews(reviews_dir)
        assert len(result["errors"]) > 0

    def test_pass_threshold_boundary(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 8, "tests": 8, "lint": 8, "intent": 8,
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "pass"
        assert result["weighted_average"] == 8.0


# ─── Format Report ───────────────────────────────────────────────────────────

class TestFormatReport:

    def test_format_pass(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": 8, "tests": 9, "lint": 8, "intent": 9,
        })
        result = score_reviews(reviews_dir)
        report = format_report(result)
        assert "PASS" in report
        assert "tests" in report

    def test_format_missing(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {"tests": 9})
        result = score_reviews(reviews_dir)
        report = format_report(result)
        assert "MISSING" in report
        assert "INCOMPLETE" in report
