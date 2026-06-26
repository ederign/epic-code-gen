#!/bin/bash
# Wrapper for running Claude with live-streamed, human-readable output.
# Adapted from AgenticCI/strat-pipeline/ci-scripts/run-claude.sh.
#
# Usage:  bash ci-scripts/run-claude.sh "<prompt>"
# Env:    LOG_FILE — if set, tee output to this file
set -euo pipefail

ci_scripts="$(cd "$(dirname "$0")" && pwd)"

claude_fifo="/tmp/claude-stream.fifo"
rm -f "$claude_fifo"
mkfifo "$claude_fifo"

set +e
claude -p "${1:?Usage: $0 <prompt>}" \
  --model "${CLAUDE_MODEL:-claude-opus-4-6}" \
  --dangerously-skip-permissions \
  --output-format stream-json \
  --verbose 2>"${LOG_DIR:-/tmp}/claude-stderr.log" > "$claude_fifo" &
claude_pid=$!

if [ -n "${LOG_FILE:-}" ]; then
  python3 -u "$ci_scripts/stream-claude.py" --claude-pid "$claude_pid" < "$claude_fifo" | tee "$LOG_FILE"
else
  python3 -u "$ci_scripts/stream-claude.py" --claude-pid "$claude_pid" < "$claude_fifo"
fi
stream_rc=$?

# Safety net: kill Claude if still running
if kill -0 "$claude_pid" 2>/dev/null; then
  echo "--- Claude still running after stream exit, killing (pid=$claude_pid) ---"
  kill "$claude_pid" 2>/dev/null
fi
wait "$claude_pid" 2>/dev/null
rc=$?

# SIGTERM/SIGPIPE: treat as success when stream-claude.py detected completion
if [ "$rc" -eq 143 ] || [ "$rc" -eq 141 ]; then
  if [ "$stream_rc" -eq 42 ]; then
    echo "--- FULL RUN COMPLETE: Claude terminated as expected ---"
    rc=0
  else
    echo "WARNING: Claude killed unexpectedly (rc=$rc, stream_rc=$stream_rc)"
  fi
elif [ "$rc" -ne 0 ]; then
  echo "WARNING: Claude exited with rc=$rc"
fi

rm -f "$claude_fifo"

echo "--- Claude exit code: $rc ---"
exit $rc
