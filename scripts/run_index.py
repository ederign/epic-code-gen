#!/usr/bin/env python3
"""Aggregate all codegen run metadata into a single index.json.

Scans artifacts/codegen-runs/*/run-metadata.yaml for completed runs and
writes a structured JSON index for dashboard consumption.

Usage:
    python3 scripts/run_index.py <codegen-runs-dir>
    python3 scripts/run_index.py <codegen-runs-dir> --json
"""

import argparse
import json
import os
import sys

try:
    import yaml
except ImportError:
    yaml = None


def _parse_yaml_simple(content):
    """Parse simple flat YAML without requiring PyYAML.

    Handles the run-metadata.yaml format: flat key-value pairs and one
    level of nesting (scores_by_dimension).
    """
    result = {}
    current_nested = None

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if line.startswith("  ") and current_nested is not None:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"')
            result[current_nested][key] = _coerce_value(value)
            continue

        current_nested = None
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip().strip('"')

        if not value:
            result[key] = {}
            current_nested = key
        else:
            result[key] = _coerce_value(value)

    return result


def _coerce_value(value):
    """Coerce a string value to int, float, or leave as string."""
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None", "~"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _read_run_metadata(filepath):
    """Read a run-metadata.yaml file and return parsed dict."""
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    if not content.strip():
        return None

    if yaml:
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError:
            return None

    return _parse_yaml_simple(content)


def build_index(codegen_runs_dir):
    """Scan codegen-runs directory and build an index of all runs.

    Args:
        codegen_runs_dir: path to artifacts/codegen-runs/

    Returns:
        dict with: runs (list), summary (counts by status)
    """
    if not os.path.isdir(codegen_runs_dir):
        raise FileNotFoundError(
            f"Codegen runs directory not found: {codegen_runs_dir}")

    runs = []
    for entry in sorted(os.listdir(codegen_runs_dir)):
        if entry == "index.json":
            continue
        entry_path = os.path.join(codegen_runs_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        metadata_path = os.path.join(entry_path, "run-metadata.yaml")
        if not os.path.isfile(metadata_path):
            continue

        metadata = _read_run_metadata(metadata_path)
        if metadata is None:
            continue

        runs.append(metadata)

    summary = {}
    for run in runs:
        status = run.get("status", "unknown")
        summary[status] = summary.get(status, 0) + 1

    return {
        "runs": runs,
        "total": len(runs),
        "summary": summary,
    }


def write_index(codegen_runs_dir):
    """Build index and write to index.json in the runs directory.

    Returns the index dict.
    """
    index = build_index(codegen_runs_dir)
    index_path = os.path.join(codegen_runs_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
    return index


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate codegen run metadata into index.json")
    parser.add_argument("codegen_runs_dir",
                        help="Directory containing per-epic run directories")
    parser.add_argument("--json", action="store_true",
                        help="Output index to stdout as JSON (also writes file)")
    args = parser.parse_args()

    try:
        index = write_index(args.codegen_runs_dir)

        if args.json:
            json.dump(index, sys.stdout, indent=2)
            print()
        else:
            print(f"Index written: {len(index['runs'])} runs")
            for status, count in sorted(index["summary"].items()):
                print(f"  {status}: {count}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
