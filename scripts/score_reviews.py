#!/usr/bin/env python3
"""Aggregate reviewer findings with weights and determine pass/fail.

Reads reviewer output files from a reviews directory. Each file must
contain structured findings sections (#### Critical, #### Important,
#### Minor). Scores are computed deterministically from finding counts:

    Score = max(1, 10 - 5*Criticals - 1.5*Importants - 0.5*Minors)

Hard ceiling: any Critical finding caps the score at 5.

Weights:
  architecture: 30%, tests: 30%, lint: 20%, intent: 20%

Pass: weighted avg >= 8.0, no dimension < 6.0
Near-miss: weighted avg >= 7.5, at most one dimension 5.0-5.9
Fail: weighted avg < 7.5 or any dimension < 5.0

Usage:
    python3 scripts/score_reviews.py <reviews-dir>
    python3 scripts/score_reviews.py <reviews-dir> --json
"""

import argparse
import json
import os
import re
import sys


DIMENSION_WEIGHTS = {
    "architecture": 0.30,
    "tests": 0.30,
    "lint": 0.20,
    "intent": 0.20,
}

PASS_THRESHOLD = 8.0
NEAR_MISS_THRESHOLD = 7.0
MIN_DIMENSION_SCORE = 6.0
HARD_FLOOR = 5.0

CRITICAL_WEIGHT = 5.0
IMPORTANT_WEIGHT = 1.5
MINOR_WEIGHT = 0.5
CRITICAL_CAP = 5.0


def _parse_findings_from_file(filepath):
    """Extract dimension name and finding counts from a review file.

    Expects filename like review-tests.md, review-intent.md, etc.
    Counts findings under #### Critical, #### Important, #### Minor.

    Returns (dimension, findings_dict) where findings_dict has keys:
    critical, important, minor.
    """
    basename = os.path.basename(filepath)
    match = re.match(r"review-(\w+)\.md", basename)
    if not match:
        return None, None

    dimension = match.group(1)

    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return dimension, None

    findings = _extract_findings(content)
    return dimension, findings


def _extract_findings(content):
    """Extract finding counts from review content.

    Parses the #### Critical, #### Important, #### Minor sections.
    Counts numbered findings (lines starting with ``N. **``)
    within each section.

    Returns dict with critical, important, minor counts.
    """
    counts = {"critical": 0, "important": 0, "minor": 0}

    current_severity = None
    for line in content.split("\n"):
        stripped = line.strip()

        heading_match = re.match(r"^#{1,4}\s+(.+)$", stripped)
        if heading_match:
            heading_text = heading_match.group(1).strip().lower()
            if heading_text == "critical":
                current_severity = "critical"
            elif heading_text == "important":
                current_severity = "important"
            elif heading_text == "minor":
                current_severity = "minor"
            else:
                current_severity = None
            continue

        if current_severity and re.match(r"^\d+\.\s+\*\*", stripped):
            counts[current_severity] += 1

    return counts


def _compute_score(findings):
    """Compute a deterministic score from finding counts.

    Formula: max(1, 10 - 5*Criticals - 1.5*Importants - 0.5*Minors)
    Hard ceiling: any Critical caps score at 5.
    """
    raw = (10.0
           - CRITICAL_WEIGHT * findings["critical"]
           - IMPORTANT_WEIGHT * findings["important"]
           - MINOR_WEIGHT * findings["minor"])
    score = max(1.0, raw)

    if findings["critical"] > 0:
        score = min(score, CRITICAL_CAP)

    return round(score, 2)


def score_reviews(reviews_dir):
    """Read all review files and compute aggregate scores from findings.

    Args:
        reviews_dir: directory containing review-*.md files

    Returns:
        dict with: dimensions, weighted_average, verdict, missing, errors
    """
    if not os.path.isdir(reviews_dir):
        raise FileNotFoundError(f"Reviews directory not found: {reviews_dir}")

    result = {
        "reviews_dir": reviews_dir,
        "dimensions": {},
        "weighted_average": 0.0,
        "verdict": "fail",
        "missing": [],
        "errors": [],
    }

    for filename in sorted(os.listdir(reviews_dir)):
        if not filename.startswith("review-") or not filename.endswith(".md"):
            continue
        filepath = os.path.join(reviews_dir, filename)
        dimension, findings = _parse_findings_from_file(filepath)
        if dimension is None:
            continue
        if findings is None:
            result["errors"].append(f"Could not read {filename}")
            continue
        if dimension in DIMENSION_WEIGHTS:
            score = _compute_score(findings)
            result["dimensions"][dimension] = {
                "score": score,
                "weight": DIMENSION_WEIGHTS[dimension],
                "weighted": round(score * DIMENSION_WEIGHTS[dimension], 2),
                "file": filename,
                "findings": findings,
            }

    for dim in DIMENSION_WEIGHTS:
        if dim not in result["dimensions"]:
            result["missing"].append(dim)

    if result["missing"]:
        result["verdict"] = "incomplete"
        return result

    weighted_avg = sum(
        d["weighted"] for d in result["dimensions"].values()
    )
    result["weighted_average"] = round(weighted_avg, 2)

    below_floor = [d for d, info in result["dimensions"].items()
                   if info["score"] < HARD_FLOOR]
    below_min = [d for d, info in result["dimensions"].items()
                 if info["score"] < MIN_DIMENSION_SCORE]

    if below_floor:
        result["verdict"] = "fail"
    elif weighted_avg >= PASS_THRESHOLD and not below_min:
        result["verdict"] = "pass"
    elif weighted_avg >= NEAR_MISS_THRESHOLD and len(below_min) <= 1:
        result["verdict"] = "near-miss"
    else:
        result["verdict"] = "fail"

    return result


def format_report(result):
    """Format scoring result as readable markdown."""
    lines = [
        "# Review Score Summary",
        "",
        f"**Reviews:** `{result['reviews_dir']}`",
        f"**Weighted Average:** {result['weighted_average']:.1f}/10",
        f"**Verdict:** {result['verdict'].upper()}",
        "",
    ]

    if result["dimensions"]:
        lines.extend([
            "## Dimension Scores",
            "",
            "| Dimension | Score | Findings (C/I/M) | Weight | Weighted |",
            "|-----------|-------|-------------------|--------|----------|",
        ])
        for dim in DIMENSION_WEIGHTS:
            if dim in result["dimensions"]:
                info = result["dimensions"][dim]
                f = info.get("findings", {})
                findings_str = (f"{f.get('critical', 0)}/"
                                f"{f.get('important', 0)}/"
                                f"{f.get('minor', 0)}")
                lines.append(
                    f"| {dim} | {info['score']:.1f} | {findings_str} | "
                    f"{info['weight']:.0%} | {info['weighted']:.2f} |"
                )
            else:
                lines.append(f"| {dim} | MISSING | — | — | — |")

    if result["missing"]:
        lines.extend([
            "",
            f"**Missing dimensions:** {', '.join(result['missing'])}",
        ])

    if result["errors"]:
        lines.extend([
            "",
            "**Errors:**",
        ] + [f"- {e}" for e in result["errors"]])

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate reviewer findings with weights")
    parser.add_argument("reviews_dir", help="Directory with review-*.md files")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    try:
        result = score_reviews(args.reviews_dir)

        if args.json:
            json.dump(result, sys.stdout, indent=2)
            print()
        else:
            print(format_report(result))

        exit_codes = {"pass": 0, "near-miss": 0, "fail": 1, "incomplete": 2}
        sys.exit(exit_codes.get(result["verdict"], 1))
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
