# CI Runtime Maintenance Implementation Plan

> **For agentic workers:** Use `executing-plans`, TDD, systematic debugging,
> and verification-before-completion. Work inline without subagents or a
> worktree.

**Status:** Active

**Goal:** Remove the known GitHub Actions Node.js 20 runtime cause and repair
the corrupted public limitations sentence without changing CI coverage or
product behavior.

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
- Modify: `tests/publication/test_docs.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/LIMITATIONS.md`
- Modify: this plan

- [ ] Add a release test requiring the exact four approved Action SHA/comment
  pairs and every occurrence to use only that mapping.
- [ ] Add a publication test requiring “—not real model quality.” and rejecting
  the corrupted sequence.
- [ ] Run both focused tests and observe failures against the current files.
- [ ] Replace all workflow pins and repair only the corrupted sentence.
- [ ] Run focused release/publication tests, Ruff, format, and `git diff --check`.
- [ ] Audit author, committer, trailers, and staged scope; commit
  `chore(ci): update action runtimes`.

### Task 2: Verify the local release candidate

**Files:**

- Modify: this plan
- Update locally: `.codex-local/PROJECT_STATUS.md`
- Append locally: `.codex-local/WORKLOG.md`

- [ ] Run the complete non-GPU pytest suite and frontend verification.
- [ ] Run Ruff, format, mypy, docs assets, claims, security, experiment, and
  public-boundary verifiers.
- [ ] Run an exact-HEAD clean export including packages, SBOMs, Docker smoke,
  E2E, and isolated browser system workflow.
- [ ] Record the verified source and external report in continuity files.
- [ ] Mark this plan Complete, commit final bookkeeping, and require a clean
  tracked worktree with local `main` ahead of unchanged `origin/main`.
