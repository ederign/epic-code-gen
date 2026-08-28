---
id: bug-uv-verification-segfaults-under-qemu
title: Verifying the uv install segfaulted when cross-building the image from arm64
type: bug
status: fixed
repos: [epic-code-gen]
commits: ["e7c9dac"]
decisions: [ADR-0011]
---

# Bug: Verifying the uv install segfaulted when cross-building the image from arm64

## Summary

`Dockerfile.ci` verified the `uv` install by running `uv --version`. Executing the freshly installed amd64 binary segfaults under qemu emulation when cross-building from an arm64 host, failing the multi-arch build.

## Reproduction

1. Build the CI image with buildx for `linux/amd64` from an arm64 machine.
2. Observe the verification step segfault.

## Expected

The build verifies `uv` is installed and continues.

## Actual

Segfault under qemu; multi-arch build fails.

## Impact

Medium

## Evidence

Fixed by verifying presence with `test -x` rather than executing the binary. The Dockerfile comment records the reason so nobody 'improves' it back to `uv --version`.

## Related Tasks

- [[task-ci-image-and-build-infrastructure]]
