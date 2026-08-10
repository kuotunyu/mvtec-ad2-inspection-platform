# HTTPX2 Test Client Migration Implementation Plan

> **For agentic workers:** Use TDD, systematic debugging, and
> verification-before-completion. Work inline without subagents or a worktree.

**Status:** Active

**Goal:** Adopt Starlette's maintained TestClient backend and remove the unused
legacy HTTP client from the production dependency contract.

## Task 1: Migrate and freeze the dependency contract

- [ ] Add a release test requiring dev-only `httpx2>=2.7,<3` and no direct
  production `httpx` dependency.
- [ ] Run the contract test and backend tests with the Starlette warning as an
  error; observe the expected failures.
- [ ] Update `pyproject.toml` and `uv.lock` with uv's resolver.
- [ ] Run focused warning-as-error tests, lock checks, Ruff, mypy, and verify
  the production wheel metadata excludes both test clients.
- [ ] Commit as `kuotunyu` with no contributor trailers.

## Task 2: Verify and close

- [ ] Run complete Python/frontend, claims, security, experiment, and boundary
  gates with no Starlette TestClient deprecation warning.
- [ ] Run exact-HEAD clean export including package/SBOM/Docker/system/browser
  gates.
- [ ] Complete bookkeeping, continuity, and sole-contributor/clean-tree audits.
