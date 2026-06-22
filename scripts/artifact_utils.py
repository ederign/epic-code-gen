"""Artifact schema definitions, frontmatter read/write/validate, and index rebuilding.

Owns all structured metadata for epic-task, codegen-run, and codegen-review
artifacts. Scripts and skills use this module instead of regex-parsing markdown.

Frontmatter is stored as YAML between --- delimiters at the top of markdown files.
"""

import os
import re
import sys

import yaml


# ─── Schema Definitions ────────────────────────────────────────────────────────

# Each schema is a dict of field_name -> field_spec.
# field_spec keys:
#   type:     "string" | "int" | "bool" | "list" | "dict"
#   required: bool (default False)
#   enum:     list of allowed values (optional)
#   pattern:  regex pattern the value must match (optional, strings only)
#   default:  default value when not provided (optional)
#   fields:   nested schema for type="dict" (optional)

SCHEMAS = {
    "epic-task": {
        "epic_id": {
            "type": "string",
            "required": True,
            "pattern": r"^RHAISTRAT-\d+-E\d+$",
        },
        "title": {
            "type": "string",
            "required": True,
        },
        "strategy_key": {
            "type": "string",
            "required": True,
            "pattern": r"^RHAISTRAT-\d+$",
        },
        "target_repo": {
            "type": "string",
            "required": True,
        },
        "target_branch": {
            "type": "string",
            "required": True,
            "default": "main",
        },
        "components": {
            "type": "list",
            "required": False,
            "default": None,
        },
        "dependencies": {
            "type": "list",
            "required": False,
            "default": None,
        },
        "effort_size": {
            "type": "string",
            "required": False,
            "enum": ["S", "M", "L", "XL"],
            "default": None,
        },
        "status": {
            "type": "string",
            "required": True,
            "enum": [
                "Pending", "Ready", "InProgress",
                "Generated", "Validated", "Failed",
            ],
        },
        "readiness_score": {
            "type": "int",
            "required": False,
            "default": None,
        },
        "codegen_branch": {
            "type": "string",
            "required": False,
            "default": None,
        },
    },
    "codegen-run": {
        "epic_id": {
            "type": "string",
            "required": True,
            "pattern": r"^RHAISTRAT-\d+-E\d+$",
        },
        "status": {
            "type": "string",
            "required": True,
            "enum": ["Running", "Completed", "Failed", "Exhausted"],
        },
        "iterations": {
            "type": "int",
            "required": True,
            "default": 0,
        },
        "max_iterations": {
            "type": "int",
            "required": True,
            "default": 10,
        },
        "started_at": {
            "type": "string",
            "required": False,
            "default": None,
        },
        "completed_at": {
            "type": "string",
            "required": False,
            "default": None,
        },
        "target_repo": {
            "type": "string",
            "required": True,
        },
        "target_branch": {
            "type": "string",
            "required": True,
        },
        "codegen_branch": {
            "type": "string",
            "required": True,
        },
        "validation": {
            "type": "dict",
            "required": False,
            "default": None,
            "fields": {
                "lint_pass": {"type": "bool", "required": True},
                "typecheck_pass": {"type": "bool", "required": True},
                "tests_pass": {"type": "bool", "required": True},
            },
        },
    },
    "codegen-review": {
        "epic_id": {
            "type": "string",
            "required": True,
            "pattern": r"^RHAISTRAT-\d+-E\d+$",
        },
        "recommendation": {
            "type": "string",
            "required": True,
            "enum": ["approve", "revise", "reject"],
        },
        "total_score": {
            "type": "int",
            "required": True,
        },
        "scores": {
            "type": "dict",
            "required": True,
            "fields": {
                "lint": {"type": "int", "required": True},
                "typecheck": {"type": "int", "required": True},
                "tests": {"type": "int", "required": True},
                "intent_coverage": {"type": "int", "required": True},
                "architecture": {"type": "int", "required": True},
            },
        },
    },
}


# ─── Validation ─────────────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Raised when frontmatter fails schema validation."""
    pass


def _validate_field(name, value, spec, path=""):
    """Validate a single field against its spec. Returns list of errors."""
    errors = []
    full_name = f"{path}.{name}" if path else name

    if value is None:
        if spec.get("required", False) and "default" not in spec:
            errors.append(f"Missing required field: {full_name}")
        return errors

    expected_type = spec.get("type", "string")

    if expected_type == "string":
        if not isinstance(value, str):
            errors.append(
                f"{full_name}: expected string, got {type(value).__name__}")
            return errors
        if "enum" in spec and value not in spec["enum"]:
            errors.append(
                f"{full_name}: '{value}' not in {spec['enum']}")
        if "pattern" in spec and not re.match(spec["pattern"], value):
            errors.append(
                f"{full_name}: '{value}' does not match {spec['pattern']}")

    elif expected_type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(
                f"{full_name}: expected int, got {type(value).__name__}")

    elif expected_type == "bool":
        if not isinstance(value, bool):
            errors.append(
                f"{full_name}: expected bool, got {type(value).__name__}")

    elif expected_type == "list":
        if not isinstance(value, list):
            errors.append(
                f"{full_name}: expected list, got {type(value).__name__}")

    elif expected_type == "dict":
        if not isinstance(value, dict):
            errors.append(
                f"{full_name}: expected dict, got {type(value).__name__}")
            return errors
        nested_schema = spec.get("fields", {})
        for key in value:
            if key not in nested_schema:
                errors.append(f"{full_name}: unknown field '{key}'")
        for field_name, field_spec in nested_schema.items():
            errors.extend(_validate_field(
                field_name, value.get(field_name), field_spec, full_name))

    return errors


def validate(data, schema_type):
    """Validate frontmatter data against a schema.

    Args:
        data: dict of frontmatter fields
        schema_type: one of "epic-task", "codegen-run", "codegen-review"

    Returns:
        list of error strings (empty if valid)

    Raises:
        ValueError: if schema_type is unknown
    """
    if schema_type not in SCHEMAS:
        raise ValueError(
            f"Unknown schema type: {schema_type}. "
            f"Valid types: {list(SCHEMAS.keys())}")

    schema = SCHEMAS[schema_type]
    errors = []

    for key in data:
        if key not in schema:
            errors.append(f"Unknown field: {key}")

    for field_name, field_spec in schema.items():
        errors.extend(_validate_field(
            field_name, data.get(field_name), field_spec))

    return errors


def apply_defaults(data, schema_type):
    """Apply default values for missing optional fields.

    Modifies data in-place and returns it.
    """
    schema = SCHEMAS[schema_type]
    for field_name, field_spec in schema.items():
        if field_name not in data and "default" in field_spec:
            data[field_name] = field_spec["default"]
        if field_spec.get("type") == "dict" and field_name in data:
            nested = data[field_name]
            if isinstance(nested, dict):
                for nested_name, nested_spec in \
                        field_spec.get("fields", {}).items():
                    if nested_name not in nested and \
                            "default" in nested_spec:
                        nested[nested_name] = nested_spec["default"]
    return data


def get_schema_yaml(schema_type):
    """Return the schema definition as a YAML string for display."""
    if schema_type not in SCHEMAS:
        raise ValueError(
            f"Unknown schema type: {schema_type}. "
            f"Valid types: {list(SCHEMAS.keys())}")

    schema = SCHEMAS[schema_type]
    output = {"required": {}, "optional": {}}

    for name, spec in schema.items():
        entry = {"type": spec["type"]}
        if "enum" in spec:
            entry["enum"] = spec["enum"]
        if "pattern" in spec:
            entry["pattern"] = spec["pattern"]
        if "default" in spec:
            entry["default"] = spec["default"]
        if spec.get("type") == "dict" and "fields" in spec:
            entry["fields"] = {}
            for fname, fspec in spec["fields"].items():
                fentry = {"type": fspec["type"]}
                if "enum" in fspec:
                    fentry["enum"] = fspec["enum"]
                entry["fields"][fname] = fentry

        if spec.get("required", False):
            output["required"][name] = entry
        else:
            output["optional"][name] = entry

    return yaml.dump(output, default_flow_style=False, sort_keys=False)


# ─── Frontmatter Read/Write ────────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(
    r'^---\s*\n(.*?\n)---\s*\n', re.DOTALL)


def read_frontmatter(path):
    """Read and parse YAML frontmatter from a markdown file.

    Returns:
        (data_dict, body_string) — frontmatter as dict, remainder as string.
        Returns ({}, full_content) if no frontmatter found.
    """
    with open(path, encoding="utf-8") as f:
        content = f.read()

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    yaml_str = match.group(1)
    body = content[match.end():]

    data = yaml.safe_load(yaml_str)
    if not isinstance(data, dict):
        return {}, content

    return data, body


def read_frontmatter_validated(path, schema_type):
    """Read frontmatter and validate against schema.

    Returns:
        (data_dict, body_string)

    Raises:
        ValidationError: if frontmatter fails validation
        FileNotFoundError: if file doesn't exist
    """
    data, body = read_frontmatter(path)
    if not data:
        raise ValidationError(f"No frontmatter found in {path}")

    apply_defaults(data, schema_type)
    errors = validate(data, schema_type)
    if errors:
        raise ValidationError(
            f"Frontmatter validation failed in {path}:\n"
            + "\n".join(f"  - {e}" for e in errors))

    return data, body


def write_frontmatter(path, data, schema_type):
    """Write/update YAML frontmatter on a markdown file.

    Validates data against the schema before writing. Preserves the
    markdown body below the frontmatter. Creates the file if it doesn't
    exist (with empty body).

    Raises:
        ValidationError: if data fails schema validation
    """
    apply_defaults(data, schema_type)
    errors = validate(data, schema_type)
    if errors:
        raise ValidationError(
            f"Frontmatter validation failed:\n"
            + "\n".join(f"  - {e}" for e in errors))

    body = ""
    if os.path.exists(path):
        _, body = read_frontmatter(path)

    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False,
                         allow_unicode=True)
    content = f"---\n{yaml_str}---\n{body}"

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def update_frontmatter(path, updates, schema_type):
    """Merge updates into existing frontmatter and rewrite.

    Reads existing frontmatter, merges updates (overwriting on conflict),
    validates, and writes back.

    Raises:
        ValidationError: if merged data fails validation
        FileNotFoundError: if file doesn't exist
    """
    data, body = read_frontmatter(path)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key].update(value)
        else:
            data[key] = value

    apply_defaults(data, schema_type)
    errors = validate(data, schema_type)
    if errors:
        raise ValidationError(
            f"Frontmatter validation failed after update in {path}:\n"
            + "\n".join(f"  - {e}" for e in errors))

    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False,
                         allow_unicode=True)
    content = f"---\n{yaml_str}---\n{body}"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ─── Artifact File Discovery ───────────────────────────────────────────────────

def find_epic_task(artifacts_dir, epic_id):
    """Find the epic-task file for a given epic ID.

    Args:
        artifacts_dir: path to artifacts directory
        epic_id: e.g. "RHAISTRAT-1665-E001"

    Returns:
        Full path to epic-task file, or None if not found.
    """
    tasks_dir = os.path.join(artifacts_dir, "epic-tasks")
    if not os.path.isdir(tasks_dir):
        return None

    target = f"{epic_id}.md"
    path = os.path.join(tasks_dir, target)
    if os.path.isfile(path):
        return path

    return None


def find_codegen_run(artifacts_dir, epic_id):
    """Find the codegen run directory for a given epic ID.

    Args:
        artifacts_dir: path to artifacts directory
        epic_id: e.g. "RHAISTRAT-1665-E001"

    Returns:
        Full path to codegen-runs/EPIC_ID/ directory, or None.
    """
    run_dir = os.path.join(artifacts_dir, "codegen-runs", epic_id)
    if os.path.isdir(run_dir):
        return run_dir
    return None


def find_codegen_review(artifacts_dir, epic_id):
    """Find the codegen review file for a given epic ID.

    Args:
        artifacts_dir: path to artifacts directory
        epic_id: e.g. "RHAISTRAT-1665-E001"

    Returns:
        Full path to review file, or None.
    """
    reviews_dir = os.path.join(artifacts_dir, "codegen-reviews")
    if not os.path.isdir(reviews_dir):
        return None

    target = f"{epic_id}-review.md"
    path = os.path.join(reviews_dir, target)
    if os.path.isfile(path):
        return path

    return None


def scan_epic_tasks(artifacts_dir):
    """Scan all epic-task files and return their frontmatter.

    Returns:
        list of (path, frontmatter_dict) tuples, sorted by epic_id.
        Files without valid frontmatter are skipped with a warning.
    """
    tasks_dir = os.path.join(artifacts_dir, "epic-tasks")
    if not os.path.isdir(tasks_dir):
        return []

    results = []
    for filename in sorted(os.listdir(tasks_dir)):
        if not filename.endswith(".md"):
            continue

        path = os.path.join(tasks_dir, filename)
        try:
            data, _ = read_frontmatter_validated(path, "epic-task")
            results.append((path, data))
        except (ValidationError, Exception) as e:
            print(f"Warning: skipping {filename}: {e}", file=sys.stderr)

    return sorted(results, key=lambda x: x[1].get("epic_id", ""))


def rebuild_index(artifacts_dir):
    """Rebuild artifacts/epics.md from frontmatter across task and review files.

    Scans epic-tasks/ for task metadata and codegen-reviews/ for scores.
    Generates a summary table.

    Returns:
        The generated markdown string.
    """
    tasks = scan_epic_tasks(artifacts_dir)

    # Build review lookup by epic_id
    review_by_id = {}
    reviews_dir = os.path.join(artifacts_dir, "codegen-reviews")
    if os.path.isdir(reviews_dir):
        for filename in sorted(os.listdir(reviews_dir)):
            if not filename.endswith("-review.md"):
                continue
            path = os.path.join(reviews_dir, filename)
            try:
                data, _ = read_frontmatter_validated(path, "codegen-review")
                review_by_id[data["epic_id"]] = data
            except (ValidationError, Exception) as e:
                print(f"Warning: skipping {filename}: {e}",
                      file=sys.stderr)

    lines = [
        "# Epic Summary",
        "",
        "| Epic ID | Title | Repo | Size | Score | Rec | Status |",
        "|---------|-------|------|------|-------|-----|--------|",
    ]

    for _, task_data in tasks:
        epic_id = task_data["epic_id"]
        title = task_data.get("title", "Untitled")
        repo = task_data.get("target_repo", "—")
        size = task_data.get("effort_size") or "—"
        status = task_data.get("status", "—")

        review = review_by_id.get(epic_id)
        if review:
            score = f"{review['total_score']}/10"
            rec = review["recommendation"]
        else:
            score = "—"
            rec = "—"

        lines.append(
            f"| {epic_id} | {title} "
            f"| {repo} | {size} | {score} "
            f"| {rec} | {status} |"
        )

    content = "\n".join(lines) + "\n"

    epics_path = os.path.join(artifacts_dir, "epics.md")
    with open(epics_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content
