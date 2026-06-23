#!/usr/bin/env python3
"""Aggregate reviewer scores with weights and determine pass/fail.

Reads reviewer output files from a reviews directory. Each file must
contain a YAML frontmatter block with a `score` field (1-10).

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
NEAR_MISS_THRESHOLD = 7.5
MIN_DIMENSION_SCORE = 6.0
HARD_FLOOR = 5.0


def _parse_score_from_file(filepath):
    """Extract dimension name and score from a review file.

    Expects filename like review-tests.md, review-intent.md, etc.
    Score extracted from YAML frontmatter `score: N` or from
    a line matching `**Score:** N` or `Score: N/10`.
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

    score = _extract_score(content)
    return dimension, score


def _extract_score(content):
    """Extract a numeric score from review content.

    Checks (in order):
    1. YAML frontmatter: `score: N`
    2. Markdown: `**Score:** N` or `**Score:** N/10`
    3. Markdown: `Score: N` or `Score: N/10`
    """
    frontmatter_match = re.search(
        r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if frontmatter_match:
        fm = frontmatter_match.group(1)
        score_match = re.search(r"^score:\s*(\d+(?:\.\d+)?)", fm, re.MULTILINE)
        if score_match:
            return float(score_match.group(1))

    patterns = [
        r"\*\*Score:\*\*\s*(\d+(?:\.\d+)?)\s*(?:/\s*10)?",
        r"Score:\s*(\d+(?:\.\d+)?)\s*(?:/\s*10)?",
    ]
    for pattern in patterns:
        m = re.search(pattern, content)
        if m:
            return float(m.group(1))

    return None


def score_reviews(reviews_dir):
    """Read all review files and compute aggregate scores.

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
        dimension, score = _parse_score_from_file(filepath)
        if dimension is None:
            continue
        if score is None:
            result["errors"].append(f"Could not extract score from {filename}")
            continue
        if dimension in DIMENSION_WEIGHTS:
            result["dimensions"][dimension] = {
                "score": score,
                "weight": DIMENSION_WEIGHTS[dimension],
                "weighted": score * DIMENSION_WEIGHTS[dimension],
                "file": filename,
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

    scores = [d["score"] for d in result["dimensions"].values()]
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
            "| Dimension | Score | Weight | Weighted |",
            "|-----------|-------|--------|----------|",
        ])
        for dim in DIMENSION_WEIGHTS:
            if dim in result["dimensions"]:
                info = result["dimensions"][dim]
                lines.append(
                    f"| {dim} | {info['score']:.1f} | "
                    f"{info['weight']:.0%} | {info['weighted']:.2f} |"
                )
            else:
                lines.append(f"| {dim} | MISSING | — | — |")

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
        description="Aggregate reviewer scores with weights")
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
