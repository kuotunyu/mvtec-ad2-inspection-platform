# Official Result-Aware Experiment Verifier Implementation Plan

> **For agentic workers:** Use TDD, systematic debugging, and
> verification-before-completion. Work inline without subagents or a worktree.

**Status:** In Progress

**Goal:** Make a clean checkout recognize complete, integrity-bound official
result evidence without confusing gate success with the release verdict.

## Task 1: Freeze the evidence-state contract

- [ ] Add focused tests for pending, external-summary PASS, committed official
  PASS, and malformed/unmanifested/hash-mismatched official evidence.
- [ ] Run the focused tests and observe the expected failure against the
  current verifier.
- [ ] Implement the minimum fail-closed committed-evidence verification.
- [ ] Update the experiment runbook with the status/verdict distinction.
- [ ] Run focused tests, Ruff, format, mypy, and diff checks.
- [ ] Audit commit identity and commit the Task as `kuotunyu` without trailers.

## Task 2: Verify and close the maintenance task

- [ ] Run the complete non-GPU Python and frontend gates.
- [ ] Run claims, security, experiment, and public-boundary verification.
- [ ] Run the exact committed clean-export release gate.
- [ ] Update local continuity files, mark this plan Complete, and commit only
  tracked bookkeeping.
- [ ] Confirm a clean tracked worktree and sole-contributor reachable history.
