#!/usr/bin/env python3
"""Deterministic review cycle orchestration for epic code generation.

Handles reviewer dispatch, file-based completion polling, scoring, and
triage prompt construction. The LLM orchestrator calls these commands
and follows their output mechanically — no AI judgment in the loop
except for triage decisions.

Mirrors rfe-creator's pipeline_state.py pattern:
- prompts: output YAML agent entries for dispatch
- wait: poll for review files on disk, exit 3 if pending
- verify: post-barrier file check
- score: run score_reviews.py, save scores.json
- triage-prompt: generate vars for triage agent dispatch
- dispatch-context: re-inject dispatch loop after context compaction

Usage:
    python3 scripts/review_cycle.py prompts <epic_id> <version>
    python3 scripts/review_cycle.py wait <epic_id> <version> [--max-wait 90]
    python3 scripts/review_cycle.py verify <epic_id> <version>
    python3 scripts/review_cycle.py score <epic_id> <version>
    python3 scripts/review_cycle.py triage-prompt <epic_id> <version>
    python3 scripts/review_cycle.py dispatch-context
"""

import argparse
import glob
import json
import os
import sys
import time

import yaml


ARTIFACTS_DIR = "artifacts/codegen-runs"
EPIC_TASKS_DIR = "artifacts/epic-tasks"
TMP_DIR = "tmp"

REVIEWERS = [
    {
        "dimension": "architecture",
        "agent": ".claude/agents/architecture-reviewer.md",
        "review_file": "review-architecture.md",
        "scored": True,
        "extra_vars": {"CLAUDE_MD_FILE": ".target-repo/CLAUDE.md"},
    },
    {
        "dimension": "tests",
        "agent": ".claude/agents/tests-reviewer.md",
        "review_file": "review-tests.md",
        "scored": True,
    },
    {
        "dimension": "lint",
        "agent": ".claude/agents/lint-reviewer.md",
        "review_file": "review-lint.md",
        "scored": True,
        "extra_vars": {"VALIDATION_FILE": "{VERSION_DIR}/validation.json"},
    },
    {
        "dimension": "intent",
        "agent": ".claude/agents/intent-reviewer.md",
        "review_file": "review-intent.md",
        "scored": True,
        "extra_vars": {
            "EPIC_FILE": "{EPIC_TASKS_DIR}/{EPIC_ID}.md",
            "UX_ACS_FILE": "{ARTIFACTS_DIR}/{EPIC_ID}/ux-acceptance-criteria.md",
        },
        "optional_vars": ["UX_ACS_FILE"],
    },
    {
        "dimension": "wiring",
        "agent": ".claude/agents/wiring-verifier.md",
        "review_file": "review-wiring.md",
        "scored": False,
        "extra_vars": {"EPIC_FILE": "{EPIC_TASKS_DIR}/{EPIC_ID}.md"},
    },
    {
        "dimension": "interactions",
        "agent": ".claude/agents/interaction-verifier.md",
        "review_file": "review-interactions.md",
        "scored": False,
    },
]

REVIEW_DISPATCH_LOOP = """\
Resume the review dispatch loop:
  1. python3 scripts/review_cycle.py prompts ${EPIC_ID} ${VERSION}
  2. Parse YAML output. For each agent in agents list:
     - Build prompt: vars + "\\n\\nRead " + prompt_file \
+ " and follow all instructions exactly."
     - Launch as background Agent. Do NOT use agentType/subagent_type.
  3. python3 scripts/review_cycle.py wait ${EPIC_ID} ${VERSION} --max-wait 90
     - If exit code 3: re-run this command (agents still working)
  4. python3 scripts/review_cycle.py verify ${EPIC_ID} ${VERSION}
     - If exit code 1: log FAILED dimensions, re-dispatch only those
  5. python3 scripts/review_cycle.py score ${EPIC_ID} ${VERSION}
     - If exit code 2: incomplete — re-dispatch missing (step 1 with --only)
  6. Read scores.json
     - If pass: save final diff, push if configured, done
     - If fail/near-miss: continue to step 7
  7. triage_vars=$(python3 scripts/review_cycle.py triage-prompt \
${EPIC_ID} ${VERSION})
  8. Launch Agent:
     prompt = triage_vars + "\\n\\nRead \
.claude/agents/iteration-reviewer.md and follow all instructions exactly."
     Do NOT use agentType.
  9. Parse triage result JSON
     - If fix_applied: VERSION = fix_version, go to step 1
     - Else: break (nothing fixable)"""


def _str_representer(dumper, data):
    """Use block scalar (|) for multi-line strings in YAML output."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _BlockDumper(yaml.Dumper):
    pass


_BlockDumper.add_representer(str, _str_representer)


def _version_dir(epic_id, version):
    return os.path.join(ARTIFACTS_DIR, epic_id, f"v{version}")


def _accepted_findings_path(epic_id):
    return os.path.join(TMP_DIR, f"accepted-findings-{epic_id}.json")


def _state_file_path(epic_id):
    return os.path.join(TMP_DIR, f"epic-codegen-{epic_id}.json")


def _resolve_vars(reviewer, epic_id, version):
    """Build KEY=VALUE variable lines for a reviewer agent prompt."""
    vdir = _version_dir(epic_id, version)
    lines = []
    lines.append(f"EPIC_ID={epic_id}")
    lines.append(f"VERSION={version}")
    lines.append(
        f"DIFF_FILE={os.path.join(vdir, 'diff.patch')}"
    )
    lines.append(
        f"SPEC_FILE={os.path.join(ARTIFACTS_DIR, epic_id, 'codegen-spec.md')}"
    )
    lines.append(
        f"REVIEW_FILE={os.path.join(vdir, reviewer['review_file'])}"
    )

    optional = set(reviewer.get("optional_vars", []))
    for key, template in reviewer.get("extra_vars", {}).items():
        value = template.format(
            VERSION_DIR=vdir,
            EPIC_ID=epic_id,
            EPIC_TASKS_DIR=EPIC_TASKS_DIR,
            ARTIFACTS_DIR=ARTIFACTS_DIR,
        )
        if key in optional and not os.path.isfile(value):
            continue
        lines.append(f"{key}={value}")

    return "\n".join(lines) + "\n"


# -- Commands ----------------------------------------------------------------

def cmd_prompts(args):
    """Output YAML agent entries for reviewer dispatch."""
    epic_id = args.epic_id
    version = args.version

    only_dims = None
    if args.only:
        only_dims = set(args.only.split(","))

    agents = []
    for reviewer in REVIEWERS:
        dim = reviewer["dimension"]
        if only_dims and dim not in only_dims:
            continue
        agents.append({
            "label": f"Review {epic_id} v{version} — {dim}",
            "prompt_file": reviewer["agent"],
            "vars": _resolve_vars(reviewer, epic_id, version),
        })

    output = {"agents": agents}
    print(
        yaml.dump(output, Dumper=_BlockDumper,
                  default_flow_style=False, sort_keys=False),
        end="",
    )


def cmd_wait(args):
    """Poll for review files on disk with adaptive intervals."""
    epic_id = args.epic_id
    version = args.version
    max_wait = args.max_wait
    vdir = _version_dir(epic_id, version)

    scored_dims = {r["dimension"] for r in REVIEWERS if r["scored"]}

    start = time.monotonic()
    while True:
        completed = []
        pending = []
        for reviewer in REVIEWERS:
            path = os.path.join(vdir, reviewer["review_file"])
            if _check_review_file(path):
                completed.append(reviewer["dimension"])
            else:
                pending.append(reviewer["dimension"])

        total = len(REVIEWERS)
        done = len(completed)
        frac = done / total if total > 0 else 1.0

        scored_pending = [d for d in pending if d in scored_dims]

        if not pending:
            print(f"{done}/{total} complete ({', '.join(completed)}). All done.")
            sys.exit(0)

        if not scored_pending:
            unscored_pending = [d for d in pending if d not in scored_dims]
            print(
                f"{done}/{total} complete ({', '.join(completed)}). "
                f"All scored dimensions done. "
                f"Unscored still pending: {', '.join(unscored_pending)}.",
                flush=True,
            )
            sys.exit(0)

        if frac >= 0.75:
            interval = 15
        elif frac >= 0.5:
            interval = 30
        else:
            interval = 60

        elapsed = time.monotonic() - start
        if max_wait > 0 and (elapsed + interval) > max_wait:
            print(
                f"{done}/{total} complete ({', '.join(completed)}). "
                f"Still pending: {', '.join(pending)}. "
                f"Waited {int(elapsed)}s. Re-run this command.",
                flush=True,
            )
            sys.exit(3)

        print(
            f"{done}/{total} complete ({', '.join(completed)}). "
            f"Sleeping {interval}s...",
            flush=True,
        )
        time.sleep(interval)


def _check_review_file(path):
    """Check if a review file exists and has substantive content."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return False
    if len(content.strip()) < 50:
        return False
    if "## Findings" not in content and "## Summary" not in content:
        return False
    return True


def cmd_verify(args):
    """Post-barrier: verify all scored review files exist with valid content."""
    epic_id = args.epic_id
    version = args.version
    vdir = _version_dir(epic_id, version)

    failed = []
    passed = []
    for reviewer in REVIEWERS:
        if not reviewer["scored"]:
            continue
        path = os.path.join(vdir, reviewer["review_file"])
        if _check_review_file(path):
            passed.append(reviewer["dimension"])
        else:
            failed.append(reviewer["dimension"])

    if failed:
        print(f"FAILED={','.join(failed)}")
        print(f"Passed: {', '.join(passed)}")
        sys.exit(1)
    else:
        print(f"All {len(passed)} scored dimensions verified: {', '.join(passed)}")
        sys.exit(0)


def cmd_score(args):
    """Run score_reviews.py and save scores.json."""
    epic_id = args.epic_id
    version = args.version
    vdir = _version_dir(epic_id, version)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    score_script = os.path.join(script_dir, "score_reviews.py")

    sys.path.insert(0, script_dir)
    from score_reviews import score_reviews, format_report

    result = score_reviews(vdir)

    scores_path = os.path.join(vdir, "scores.json")
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    print(format_report(result))
    print(f"Scores saved to: {scores_path}")

    if result["verdict"] == "incomplete":
        sys.exit(2)
    sys.exit(0)


def cmd_triage_prompt(args):
    """Generate vars block for triage agent dispatch."""
    epic_id = args.epic_id
    version = args.version
    vdir = _version_dir(epic_id, version)

    prior_notes = []
    for v in range(1, int(version)):
        notes_path = os.path.join(
            ARTIFACTS_DIR, epic_id, f"v{v}", "revision-notes.md"
        )
        if os.path.exists(notes_path):
            prior_notes.append(notes_path)

    af_path = _accepted_findings_path(epic_id)
    if not os.path.exists(af_path):
        os.makedirs(os.path.dirname(af_path), exist_ok=True)
        with open(af_path, "w", encoding="utf-8") as f:
            json.dump([], f)

    state_path = _state_file_path(epic_id)
    max_iterations = "10"
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("max_iterations:"):
                        max_iterations = line.split(":", 1)[1].strip()
        except OSError:
            pass

    lines = [
        f"EPIC_ID={epic_id}",
        f"VERSION={version}",
        f"SCORES_FILE={os.path.join(vdir, 'scores.json')}",
        f"REVIEWS_DIR={vdir}/",
        f"SPEC_FILE={os.path.join(ARTIFACTS_DIR, epic_id, 'codegen-spec.md')}",
        f"ACCEPTED_FINDINGS_FILE={af_path}",
        f"PRIOR_REVISION_NOTES={','.join(prior_notes) if prior_notes else 'none'}",
        f"MAX_ITERATIONS={max_iterations}",
    ]
    print("\n".join(lines))


def cmd_dispatch_context(args):
    """Print current phase + dispatch loop for post-compaction recovery."""
    epic_id = None
    for path in glob.glob(os.path.join(TMP_DIR, "epic-codegen-*.json")):
        basename = os.path.basename(path)
        epic_id = basename.replace("epic-codegen-", "").replace(".json", "")
        break

    if not epic_id:
        return

    state_path = _state_file_path(epic_id)
    if not os.path.exists(state_path):
        return

    phase = "unknown"
    version = "1"
    try:
        with open(state_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("phase:"):
                    phase = line.split(":", 1)[1].strip()
                elif line.startswith("version:"):
                    version = line.split(":", 1)[1].strip()
    except OSError:
        return

    if phase not in ("review", "fixing", "implementing"):
        return

    print(f"[REVIEW CYCLE RECOVERY] EPIC_ID={epic_id} VERSION={version} phase={phase}")
    print()
    print(REVIEW_DISPATCH_LOOP.replace("${EPIC_ID}", epic_id)
          .replace("${VERSION}", version))


# -- Main -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Deterministic review cycle orchestration",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_prompts = sub.add_parser("prompts", help="Output YAML agent entries")
    p_prompts.add_argument("epic_id")
    p_prompts.add_argument("version")
    p_prompts.add_argument("--only", help="Comma-separated dimensions to include")

    p_wait = sub.add_parser("wait", help="Poll for review files")
    p_wait.add_argument("epic_id")
    p_wait.add_argument("version")
    p_wait.add_argument("--max-wait", type=int, default=90,
                        help="Max seconds to wait (default 90, exit 3 if exceeded)")

    p_verify = sub.add_parser("verify", help="Post-barrier file check")
    p_verify.add_argument("epic_id")
    p_verify.add_argument("version")

    p_score = sub.add_parser("score", help="Run scoring and save scores.json")
    p_score.add_argument("epic_id")
    p_score.add_argument("version")

    p_triage = sub.add_parser("triage-prompt", help="Generate triage agent vars")
    p_triage.add_argument("epic_id")
    p_triage.add_argument("version")

    sub.add_parser("dispatch-context",
                    help="Print recovery context after compaction")

    args = parser.parse_args()

    commands = {
        "prompts": cmd_prompts,
        "wait": cmd_wait,
        "verify": cmd_verify,
        "score": cmd_score,
        "triage-prompt": cmd_triage_prompt,
        "dispatch-context": cmd_dispatch_context,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
