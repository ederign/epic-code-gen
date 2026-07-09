"""Tests for score_reviews.py."""

import os
import sys

import pytest

sys_path_fix = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, sys_path_fix)

from score_reviews import (
    score_reviews,
    format_report,
    _extract_findings,
    _compute_score,
    _parse_findings_from_file,
    DIMENSION_WEIGHTS,
)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _write_review(reviews_dir, dimension, criticals=0, importants=0, minors=0,
                  extra_body=""):
    """Write a review file with structured findings."""
    critical_items = "\n".join(
        f'{i+1}. **Finding C{i+1}**: description' for i in range(criticals)
    ) if criticals else "None identified."

    important_items = "\n".join(
        f'{i+1}. **Finding I{i+1}**: description' for i in range(importants)
    ) if importants else "None identified."

    minor_items = "\n".join(
        f'{i+1}. **Finding M{i+1}**: description' for i in range(minors)
    ) if minors else "None identified."

    content = f"""### {dimension.title()} Review

{extra_body}

### Findings

#### Critical

{critical_items}

#### Important

{important_items}

#### Minor

{minor_items}
"""
    _write(os.path.join(reviews_dir, f"review-{dimension}.md"), content)


def _write_all_reviews(reviews_dir, findings_map):
    """Write review files for all dimensions.

    findings_map: dict of dimension -> (criticals, importants, minors)
    """
    for dim, counts in findings_map.items():
        _write_review(reviews_dir, dim, *counts)


# ─── Finding Extraction ────────────────────────────────────────────────────

class TestExtractFindings:

    def test_no_findings(self):
        content = """### Findings

#### Critical

None identified.

#### Important

None identified.

#### Minor

None identified.
"""
        findings = _extract_findings(content)
        assert findings == {"critical": 0, "important": 0, "minor": 0}

    def test_one_critical(self):
        content = """### Findings

#### Critical

1. **Broken API**: The endpoint returns 500

#### Important

None.

#### Minor

None.
"""
        findings = _extract_findings(content)
        assert findings["critical"] == 1
        assert findings["important"] == 0
        assert findings["minor"] == 0

    def test_multiple_findings(self):
        content = """### Findings

#### Critical

1. **Bug one**: description
2. **Bug two**: description

#### Important

1. **Warning one**: description

#### Minor

1. **Nit one**: description
2. **Nit two**: description
3. **Nit three**: description
"""
        findings = _extract_findings(content)
        assert findings["critical"] == 2
        assert findings["important"] == 1
        assert findings["minor"] == 3

    def test_only_counts_numbered_bold_items(self):
        content = """#### Critical

Some preamble text that isn't a finding.

1. **Real finding**: this counts

A paragraph between findings.

2. **Another finding**: this also counts

But this plain text does not count.
"""
        findings = _extract_findings(content)
        assert findings["critical"] == 2

    def test_stops_at_next_section(self):
        content = """#### Critical

1. **Finding**: description

#### Important

1. **Other finding**: description

### Reasoning

Score: 5/10 — this should not be counted as a finding.
"""
        findings = _extract_findings(content)
        assert findings["critical"] == 1
        assert findings["important"] == 1

    def test_handles_code_quality_subsection(self):
        content = """### Code Quality Findings

#### Critical

1. **Validation failures**: lint fails

#### Important

None.

#### Minor

1. **Commented code**: file:123
"""
        findings = _extract_findings(content)
        assert findings["critical"] == 1
        assert findings["minor"] == 1


# ─── Score Computation ──────────────────────────────────────────────────────

class TestComputeScore:

    def test_no_findings_is_10(self):
        assert _compute_score({"critical": 0, "important": 0, "minor": 0}) == 10.0

    def test_one_critical_caps_at_5(self):
        score = _compute_score({"critical": 1, "important": 0, "minor": 0})
        assert score == 5.0

    def test_two_criticals_floor_at_1(self):
        score = _compute_score({"critical": 2, "important": 0, "minor": 0})
        assert score == 1.0

    def test_three_minors(self):
        score = _compute_score({"critical": 0, "important": 0, "minor": 3})
        assert score == 8.5

    def test_two_importants_one_minor(self):
        score = _compute_score({"critical": 0, "important": 2, "minor": 1})
        assert score == 6.5

    def test_one_critical_one_important(self):
        score = _compute_score({"critical": 1, "important": 1, "minor": 0})
        assert score == 3.5

    def test_floor_at_1(self):
        score = _compute_score({"critical": 3, "important": 5, "minor": 10})
        assert score == 1.0

    def test_critical_cap_applied_after_formula(self):
        # 1 critical + 0 others: raw = 10-5 = 5, cap = 5 → 5
        score = _compute_score({"critical": 1, "important": 0, "minor": 0})
        assert score == 5.0
        # 1 critical + 2 importants: raw = 10-5-3 = 2, cap would be 5 but raw is lower
        score = _compute_score({"critical": 1, "important": 2, "minor": 0})
        assert score == 2.0


# ─── Parse Findings From File ──────────────────────────────────────────────

class TestParseFindingsFromFile:

    def test_valid_review_file(self, tmp_path):
        filepath = str(tmp_path / "review-tests.md")
        _write(filepath, """### Findings

#### Critical

1. **Missing test**: AC3 has no test

#### Important

None.

#### Minor

None.
""")
        dim, findings = _parse_findings_from_file(filepath)
        assert dim == "tests"
        assert findings["critical"] == 1

    def test_invalid_filename(self, tmp_path):
        filepath = str(tmp_path / "notes.md")
        _write(filepath, "content")
        dim, findings = _parse_findings_from_file(filepath)
        assert dim is None

    def test_no_findings_sections(self, tmp_path):
        filepath = str(tmp_path / "review-lint.md")
        _write(filepath, "No structured findings here.")
        dim, findings = _parse_findings_from_file(filepath)
        assert dim == "lint"
        assert findings == {"critical": 0, "important": 0, "minor": 0}


# ─── Score Reviews ──────────────────────────────────────────────────────────

class TestScoreReviews:

    def test_all_pass(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
            "intent": (0, 0, 0),
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "pass"
        assert result["weighted_average"] == 10.0
        assert len(result["missing"]) == 0

    def test_fail_with_criticals(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (1, 0, 0),
            "intent": (2, 1, 0),
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "fail"
        # lint: 1 critical → 5, intent: 2 criticals → 1
        assert result["dimensions"]["lint"]["score"] == 5.0
        assert result["dimensions"]["intent"]["score"] == 1.0

    def test_fail_dimension_below_floor(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (1, 0, 0),  # score = 5, capped → below HARD_FLOOR
            "intent": (0, 0, 0),
        })
        result = score_reviews(reviews_dir)
        # lint score = 5.0, which is >= HARD_FLOOR (5.0)
        # but below MIN_DIMENSION_SCORE (6.0)
        # weighted avg = 10*0.3 + 10*0.3 + 5*0.2 + 10*0.2 = 9.0
        assert result["dimensions"]["lint"]["score"] == 5.0
        # Below MIN but above HARD_FLOOR, avg >= 7.5, one dim 5.0-5.9
        assert result["verdict"] == "near-miss"

    def test_near_miss(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        # All clean except one dimension with minor findings
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (0, 0, 9),  # 10 - 4.5 = 5.5
            "intent": (0, 0, 0),
        })
        result = score_reviews(reviews_dir)
        assert result["dimensions"]["lint"]["score"] == 5.5
        # weighted avg = 10*0.3 + 10*0.3 + 5.5*0.2 + 10*0.2 = 9.1
        assert result["weighted_average"] >= 7.5
        assert result["verdict"] == "near-miss"

    def test_missing_dimension(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
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
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
            "intent": (0, 0, 0),
        })
        result = score_reviews(reviews_dir)
        assert result["weighted_average"] == 10.0

    def test_weights_sum_to_one(self):
        assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.001

    def test_ignores_non_review_files(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
            "intent": (0, 0, 0),
        })
        _write(os.path.join(reviews_dir, "notes.md"), "Not a review")
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "pass"

    def test_findings_included_in_output(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 1, 2),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
            "intent": (1, 0, 0),
        })
        result = score_reviews(reviews_dir)
        assert result["dimensions"]["architecture"]["findings"] == {
            "critical": 0, "important": 1, "minor": 2,
        }
        assert result["dimensions"]["intent"]["findings"]["critical"] == 1

    def test_pass_threshold_boundary(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        # All 10s → weighted avg = 10.0
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
            "intent": (0, 0, 0),
        })
        result = score_reviews(reviews_dir)
        assert result["verdict"] == "pass"
        assert result["weighted_average"] == 10.0

    def test_mixed_findings_score(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        # arch: 0C 2I 1M → 10-3-0.5 = 6.5
        # tests: 0C 0I 3M → 10-1.5 = 8.5
        # lint: 0C 0I 0M → 10
        # intent: 0C 1I 0M → 10-1.5 = 8.5
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 2, 1),
            "tests": (0, 0, 3),
            "lint": (0, 0, 0),
            "intent": (0, 1, 0),
        })
        result = score_reviews(reviews_dir)
        assert result["dimensions"]["architecture"]["score"] == 6.5
        assert result["dimensions"]["tests"]["score"] == 8.5
        assert result["dimensions"]["lint"]["score"] == 10.0
        assert result["dimensions"]["intent"]["score"] == 8.5
        # weighted: 6.5*0.3 + 8.5*0.3 + 10*0.2 + 8.5*0.2 = 1.95+2.55+2.0+1.7 = 8.2
        assert result["weighted_average"] == 8.2
        assert result["verdict"] == "pass"


# ─── Format Report ──────────────────────────────────────────────────────────

class TestFormatReport:

    def test_format_pass(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (0, 0, 0),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
            "intent": (0, 0, 0),
        })
        result = score_reviews(reviews_dir)
        report = format_report(result)
        assert "PASS" in report
        assert "tests" in report
        assert "Findings (C/I/M)" in report

    def test_format_missing(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {"tests": (0, 0, 0)})
        result = score_reviews(reviews_dir)
        report = format_report(result)
        assert "MISSING" in report
        assert "INCOMPLETE" in report

    def test_format_shows_finding_counts(self, tmp_path):
        reviews_dir = str(tmp_path / "reviews")
        os.makedirs(reviews_dir)
        _write_all_reviews(reviews_dir, {
            "architecture": (1, 2, 3),
            "tests": (0, 0, 0),
            "lint": (0, 0, 0),
            "intent": (0, 0, 0),
        })
        result = score_reviews(reviews_dir)
        report = format_report(result)
        assert "1/2/3" in report
