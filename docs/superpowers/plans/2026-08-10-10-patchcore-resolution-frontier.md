# PatchCore Resolution Frontier Implementation Plan

> **For agentic workers:** Use TDD, systematic debugging, and
> verification-before-completion. Work inline without subagents or a worktree.

**Status:** Complete

**Goal:** Determine whether a resource-informed 640 x 640 `wallplugs`
PatchCore candidate fits the RTX 4090 and materially improves frozen public
AU-PRO, without changing release or submission state.

## Task 1: Implement the fixed one-run contract

- [x] Add the 640 x 640 candidate config and focused failing contract tests.
- [x] Observe RED for the missing frontier runner.
- [x] Implement exact config-difference validation, deterministic run identity,
  baseline selection, classification, external report, and resumable CLI.
- [x] Run focused tests, Ruff, format, mypy, CLI dry-run, and diff checks.
- [x] Commit as `kuotunyu` with no contributor trailers.

## Task 2: Execute and evaluate the bounded GPU run

- [x] Require a clean committed worktree, matching dataset/benchmark identity,
  free shared GPU lease, and no conflicting compute process.
- [x] Run the single formal fit and record either completed or sanitized
  failure evidence without retrying an OOM.
- [x] If completed, evaluate only `test_public` and freeze the external report.
- [x] Verify report/run/artifact/config hashes and objective resource evidence.

## Task 3: Record the reviewed aggregate outcome

- [x] Add only sanitized aggregate public evidence and unchanged-champion
  documentation with a failing committed-report test first.
- [x] Run complete non-GPU, frontend, claims, security, and boundary gates.
- [x] Commit the result, run an exact-HEAD clean export, complete bookkeeping,
  and confirm clean sole-contributor history.
