---
id: wontfix-stream-claude-sigterm-exit-42
title: "stream-claude.py signals completion by SIGTERM-ing its parent and exiting 42"
type: bug
status: wontfix
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# Bug: stream-claude.py signals completion by SIGTERM-ing its parent and exiting 42

## Status

**Won't fix — intentional.** Documented so nobody "cleans it up".

## Summary

On seeing `FULL RUN COMPLETE` in a tool result, `stream-claude.py` calls
`os.kill(claude_pid, SIGTERM)` and `sys.exit(42)`. `run-claude.sh` then treats exit code 143 or 141
combined with `stream_rc == 42` as **success**.

This looks exactly like a bug: a child killing its parent, a magic exit code, and a wrapper laundering
signal-death into success.

## Why it is deliberate

The Claude CLI with `--include-partial-messages` does not reliably exit when the work is done. The
`result` event can arrive **before** background agents finish, so exiting on it truncates the run — the
comment in the source says so explicitly. And waiting for the process to exit on its own can hang past the
job timeout.

So the renderer, which is the only component that can see the completion marker in the stream, is the
component that ends the session. Exit 42 is the out-of-band channel telling the wrapper that the SIGTERM
was intentional rather than a crash.

## What would need to change first

A supported way to detect "this session is finished, including background agents" from the stream. Until
then, replacing this with a timeout or a `result`-event exit would reintroduce either truncated runs or
hung jobs — both of which this replaced.

## Related

- [[task-ci-observability]]
- [ADR-0012] — the wrapper's exit-code handling is part of why the outer Claude layer was removable
- [[task-deduplicate-stream-claude]] — there are two copies of this file
