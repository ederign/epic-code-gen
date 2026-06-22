"""Tests for fetch_epic.py."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from fetch_epic import (
    parse_report,
    generate_epic_task,
    list_strategies,
    _parse_dag_dependencies,
    _parse_epic_bodies,
    _extract_title,
    _estimate_effort,
)
from artifact_utils import read_frontmatter_validated


MINIMAL_REPORT = """<!DOCTYPE html>
<html><body>

<div class="strat-section" id="RHAISTRAT-9999">
  <h2>RHAISTRAT-9999 <span>2 epics</span></h2>

  <div class="dag-container"><pre class="mermaid">
graph TD
    E001["E001: First Epic (Implementation)"]
    E002["E002: Second Epic (Implementation)"]
    E001 --> E002
</pre></div>

<div class="card" id="RHAISTRAT-9999-E001">
  <div class="epic-header">
    <span class="epic-id">RHAISTRAT-9999-E001</span>
    <span class="epic-title">RHAISTRAT-9999-E001</span>
    <span class="badge badge-p0">P0</span>
    <span class="badge badge-high">High (6)</span>
    <span class="badge badge-impl">Implementation</span>
  </div>
  <div class="meta-grid">
    <div class="meta-item"><span class="meta-label">Component:</span><span class="meta-value">Dashboard</span></div>
    <div class="meta-item"><span class="meta-label">Team:</span><span class="meta-value">Frontend</span></div>
    <div class="meta-item"><span class="meta-label">Dependencies:</span><span style="color:var(--muted);">None</span></div>
  </div>
  <details>
    <summary>AI Implementability Signals</summary>
    <div class="signals-grid"><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">change_specificity</span> +1</div><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">pattern_precedent</span> +1</div><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">existing_foundation</span> +1</div><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">repo_access</span> +1</div><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">architecture_claims</span> +1</div><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">adapter_pattern</span> +1</div><div class="signal signal-zero"><div class="signal-dot"></div><span class="signal-name">open_questions</span> 0</div><div class="signal signal-zero"><div class="signal-dot"></div><span class="signal-name">external_dependency</span> 0</div><div class="signal signal-zero"><div class="signal-dot"></div><span class="signal-name">human_process_gates</span> 0</div></div>
  </details>
  <div class="epic-body" data-body="RHAISTRAT-9999-E001"></div>
</div>
<div class="card" id="RHAISTRAT-9999-E002">
  <div class="epic-header">
    <span class="epic-id">RHAISTRAT-9999-E002</span>
    <span class="epic-title">RHAISTRAT-9999-E002</span>
    <span class="badge badge-p1">P1</span>
    <span class="badge badge-medium">Medium (2)</span>
    <span class="badge badge-impl">Implementation</span>
  </div>
  <div class="meta-grid">
    <div class="meta-item"><span class="meta-label">Component:</span><span class="meta-value">Backend</span></div>
    <div class="meta-item"><span class="meta-label">Team:</span><span class="meta-value">API</span></div>
    <div class="meta-item"><span class="meta-label">Dependencies:</span><div class="deps-list"><a class="dep-chip" href="#RHAISTRAT-9999-E001">E001</a></div></div>
  </div>
  <details>
    <summary>AI Implementability Signals</summary>
    <div class="signals-grid"><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">change_specificity</span> +1</div><div class="signal signal-pos"><div class="signal-dot"></div><span class="signal-name">pattern_precedent</span> +1</div><div class="signal signal-zero"><div class="signal-dot"></div><span class="signal-name">existing_foundation</span> 0</div><div class="signal signal-zero"><div class="signal-dot"></div><span class="signal-name">repo_access</span> 0</div></div>
  </details>
  <div class="epic-body" data-body="RHAISTRAT-9999-E002"></div>
</div>

</div>

<script>
const epicBodies = {
  "RHAISTRAT-9999-E001": `## Add Search Input to Resources Page

### Description

Add a PatternFly SearchInput component to filter resources.

### Acceptance Criteria

- [ ] SearchInput renders on the Resources page
- [ ] Typing filters the displayed resources
- [ ] Clearing the search shows all resources`,
  "RHAISTRAT-9999-E002": `## Implement Search Backend API

### Description

Add server-side search endpoint for resources.

### Acceptance Criteria

- [ ] GET /api/resources supports query parameter
- [ ] Results are paginated`,
};
</script>
</body></html>
"""


@pytest.fixture
def report_path(tmp_path):
    """Write minimal report to a temp file."""
    path = tmp_path / "report.html"
    path.write_text(MINIMAL_REPORT, encoding="utf-8")
    return str(path)


@pytest.fixture
def output_dir(tmp_path):
    return str(tmp_path / "epic-tasks")


# ─── parse_report ────────────────────────────────────────────────────────────

class TestParseReport:

    def test_finds_all_epics(self):
        epics = parse_report(MINIMAL_REPORT)
        assert "RHAISTRAT-9999-E001" in epics
        assert "RHAISTRAT-9999-E002" in epics
        assert len(epics) == 2

    def test_extracts_strategy_key(self):
        epics = parse_report(MINIMAL_REPORT)
        assert epics["RHAISTRAT-9999-E001"]["strategy_key"] == "RHAISTRAT-9999"

    def test_extracts_priority(self):
        epics = parse_report(MINIMAL_REPORT)
        assert epics["RHAISTRAT-9999-E001"]["priority"] == "P0"
        assert epics["RHAISTRAT-9999-E002"]["priority"] == "P1"

    def test_extracts_ai_score(self):
        epics = parse_report(MINIMAL_REPORT)
        assert epics["RHAISTRAT-9999-E001"]["ai_score"] == 6
        assert epics["RHAISTRAT-9999-E002"]["ai_score"] == 2

    def test_extracts_epic_type(self):
        epics = parse_report(MINIMAL_REPORT)
        assert epics["RHAISTRAT-9999-E001"]["epic_type"] == "Implementation"

    def test_extracts_component(self):
        epics = parse_report(MINIMAL_REPORT)
        assert epics["RHAISTRAT-9999-E001"]["component"] == "Dashboard"
        assert epics["RHAISTRAT-9999-E002"]["component"] == "Backend"

    def test_extracts_team(self):
        epics = parse_report(MINIMAL_REPORT)
        assert epics["RHAISTRAT-9999-E001"]["team"] == "Frontend"

    def test_extracts_body(self):
        epics = parse_report(MINIMAL_REPORT)
        body = epics["RHAISTRAT-9999-E001"]["body"]
        assert "## Add Search Input to Resources Page" in body
        assert "SearchInput renders" in body

    def test_extracts_signals(self):
        epics = parse_report(MINIMAL_REPORT)
        signals = epics["RHAISTRAT-9999-E001"]["signals"]
        assert signals["change_specificity"] == 1
        assert signals["pattern_precedent"] == 1
        assert signals["open_questions"] == 0

    def test_extracts_dependencies_from_dag(self):
        epics = parse_report(MINIMAL_REPORT)
        deps = epics["RHAISTRAT-9999-E002"]["dependencies"]
        assert "RHAISTRAT-9999-E001" in deps

    def test_no_dependencies_for_root_epic(self):
        epics = parse_report(MINIMAL_REPORT)
        deps = epics["RHAISTRAT-9999-E001"]["dependencies"]
        assert deps is None


# ─── _parse_dag_dependencies ─────────────────────────────────────────────────

class TestParseDagDependencies:

    def test_simple_chain(self):
        dag = "E001 --> E002\nE002 --> E003"
        deps = _parse_dag_dependencies(dag, "RHAISTRAT-1000")
        assert deps["RHAISTRAT-1000-E002"] == ["RHAISTRAT-1000-E001"]
        assert deps["RHAISTRAT-1000-E003"] == ["RHAISTRAT-1000-E002"]

    def test_multiple_deps(self):
        dag = "E001 --> E003\nE002 --> E003"
        deps = _parse_dag_dependencies(dag, "RHAISTRAT-1000")
        assert sorted(deps["RHAISTRAT-1000-E003"]) == [
            "RHAISTRAT-1000-E001", "RHAISTRAT-1000-E002"]


# ─── _parse_epic_bodies ──────────────────────────────────────────────────────

class TestParseEpicBodies:

    def test_extracts_bodies(self):
        bodies = _parse_epic_bodies(MINIMAL_REPORT)
        assert "RHAISTRAT-9999-E001" in bodies
        assert "RHAISTRAT-9999-E002" in bodies

    def test_body_content(self):
        bodies = _parse_epic_bodies(MINIMAL_REPORT)
        assert "PatternFly SearchInput" in bodies["RHAISTRAT-9999-E001"]


# ─── _extract_title ──────────────────────────────────────────────────────────

class TestExtractTitle:

    def test_title_from_body(self):
        epic = {"epic_id": "X-E001",
                "body": "## My Epic Title\n\nDescription"}
        assert _extract_title(epic) == "My Epic Title"

    def test_falls_back_to_id(self):
        epic = {"epic_id": "X-E001", "body": ""}
        assert _extract_title(epic) == "X-E001"


# ─── _estimate_effort ────────────────────────────────────────────────────────

class TestEstimateEffort:

    def test_high_signals_short_body(self):
        signals = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1}
        assert _estimate_effort(signals, "short") == "S"

    def test_no_signals(self):
        assert _estimate_effort(None, "body") is None

    def test_medium_signals(self):
        signals = {"a": 1, "b": 1, "c": 1, "d": 0, "e": 0}
        assert _estimate_effort(signals, "x" * 4000) == "M"


# ─── generate_epic_task ─────────────────────────────────────────────────────

class TestGenerateEpicTask:

    def test_generates_file(self, output_dir):
        epic = {
            "epic_id": "RHAISTRAT-9999-E001",
            "strategy_key": "RHAISTRAT-9999",
            "priority": "P0",
            "ai_score": 6,
            "epic_type": "Implementation",
            "component": "Dashboard",
            "team": "Frontend",
            "dependencies": None,
            "signals": {"change_specificity": 1, "pattern_precedent": 1},
            "body": "## Test Epic\n\nDescription here.",
        }
        path = generate_epic_task(epic, output_dir)
        assert os.path.isfile(path)

    def test_valid_frontmatter(self, output_dir):
        epic = {
            "epic_id": "RHAISTRAT-9999-E001",
            "strategy_key": "RHAISTRAT-9999",
            "priority": "P0",
            "ai_score": 6,
            "epic_type": "Implementation",
            "component": "Dashboard",
            "team": "Frontend",
            "dependencies": None,
            "signals": {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1},
            "body": "## Test Epic\n\nDescription here.",
        }
        path = generate_epic_task(epic, output_dir)
        data, body = read_frontmatter_validated(path, "epic-task")
        assert data["epic_id"] == "RHAISTRAT-9999-E001"
        assert data["strategy_key"] == "RHAISTRAT-9999"
        assert data["status"] == "Pending"
        assert data["target_branch"] == "main"

    def test_includes_dependencies(self, output_dir):
        epic = {
            "epic_id": "RHAISTRAT-9999-E002",
            "strategy_key": "RHAISTRAT-9999",
            "priority": "P1",
            "ai_score": 2,
            "epic_type": "Implementation",
            "component": "Backend",
            "team": "API",
            "dependencies": ["RHAISTRAT-9999-E001"],
            "signals": None,
            "body": "## Second Epic\n\nDepends on E001.",
        }
        path = generate_epic_task(epic, output_dir)
        data, _ = read_frontmatter_validated(path, "epic-task")
        assert data["dependencies"] == ["RHAISTRAT-9999-E001"]


# ─── list_strategies ─────────────────────────────────────────────────────────

class TestListStrategies:

    def test_lists_strategies(self):
        strategies = list_strategies(MINIMAL_REPORT)
        assert len(strategies) == 1
        assert strategies[0]["key"] == "RHAISTRAT-9999"
        assert strategies[0]["epic_count"] == 2
