# CI Runtime Maintenance Implementation Plan

> **For agentic workers:** Use `executing-plans`, TDD, systematic debugging,
> and verification-before-completion. Work inline without subagents or a
> worktree.

**Status:** Complete

**Goal:** Remove the known GitHub Actions Node.js 20 runtime cause and harden
public text validation without changing CI coverage or product behavior.

**Architecture:** Treat the workflow and public copy as release contracts.
Focused tests freeze the reviewed action-to-SHA mapping and exact limitations
statement before the workflow or documentation changes; the normal release
gates then prove the rest of the repository remains unchanged in behavior.

**Tech Stack:** GitHub Actions YAML, pytest, Markdown, PowerShell release gates.

## Global constraints

- Preserve all five CI jobs, triggers, commands, permissions, concurrency, and
  Python/Node tool versions.
- Pin every third-party Action to the immutable SHA approved in the design.
- Work on authorized local `main`; commit only as `kuotunyu` with no trailers.
- Do not push, tag, release, deploy, publish a model, or submit to MVTec.

### Task 1: Freeze and apply the Node.js 24 Action set

**Files:**

- Modify: `tests/release/test_release.py`
- Modify: `tests/security/test_scanners.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/verify_public_boundary.py`
- Modify: this plan

- [x] Add a release test requiring the exact four approved Action SHA/comment
  pairs and every occurrence to use only that mapping.
- [x] Add a scanner test requiring corrupt UTF-8 public text to fail with a
  stable `invalid_public_text` error.
- [x] Run both focused tests and observe failures against the current files.
- [x] Replace all workflow pins, implement the general text gate, and verify
  the apparently corrupted sentence already has correct UTF-8 bytes.
- [x] Run focused release/publication tests, Ruff, format, and `git diff --check`.
- [x] Audit author, committer, trailers, and staged scope; commit
  `chore(ci): update action runtimes`.

### Task 2: Verify the local release candidate

**Files:**

- Modify: this plan
- Update locally: `.codex-local/PROJECT_STATUS.md`
- Append locally: `.codex-local/WORKLOG.md`

- [x] Run the complete non-GPU pytest suite and frontend verification.
- [x] Run Ruff, format, mypy, docs assets, claims, security, experiment, and
  public-boundary verifiers.
- [x] Run an exact-HEAD clean export including packages, SBOMs, Docker smoke,
  E2E, and isolated browser system workflow.
- [x] Record the verified source and external report in continuity files.
- [x] Mark this plan Complete, commit final bookkeeping, and require a clean
  tracked worktree with local `main` ahead of unchanged `origin/main`.
