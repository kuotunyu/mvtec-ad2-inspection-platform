# High-Resolution PatchCore Research Implementation Plan

> **For agentic workers:** Use executing-plans, TDD, systematic debugging, and
> verification-before-completion. Work inline without subagents or a worktree.

**Status:** Complete

**Goal:** Execute and verify the fixed public-only 768 x 768 PatchCore study for
`can` and `wallplugs` without changing frozen champions or performing another
official submission.

## Constraints

- Follow the approved high-resolution research design exactly.
- Keep all runs, maps, checkpoints, logs, and raw reports outside Git.
- Use only the committed public benchmark for comparison; do not read private
  metrics for selection or tuning.
- Use the shared GPU lease and never interfere with another compute workload.
- Commit only as `kuotunyu <61350295+kuotunyu@users.noreply.github.com>` with no
  contributor trailers.
- Do not push or perform any publication action.

### Task 1: Implement the frozen research contract and runner

**Files:**

- Create: `experiments/configs/research/patchcore-768.yaml`
- Create: `experiments/high_resolution_patchcore.py`
- Create: `tests/unit/research/test_high_resolution_patchcore.py`
- Modify: `docs/EXPERIMENT_RUNBOOK.md`
- Modify: this plan

- [x] Write a failing test requiring exactly `can` and `wallplugs`, seed 42,
  candidate geometry 768 x 768, and no config difference beyond input/resize.
- [x] Observe the expected import/module RED.
- [x] Implement candidate validation and deterministic `RunSpec` construction.
- [x] Add failing tests for baseline selection, aggregate comparison,
  classification thresholds, resource limits, external output safety, and
  sanitized identity-bound report serialization.
- [x] Implement the dedicated CLI by reusing the existing Supervisor,
  subprocess worker, GPU lease, and public evaluator.
- [x] Run focused tests, Ruff, format, mypy, and CLI dry-run gates.
- [x] Update bookkeeping and commit `feat(research): add high resolution patchcore study`.

### Task 2: Execute the formal public-only GPU study

**External root:** `D:\mvtec-ad2-highres-patchcore-20260810`

- [x] Require a clean committed worktree, verified dataset manifest, no live
  conflicting compute process, and an available shared GPU lease.
- [x] Attempt the two sequential 768 x 768 seed-42 fits with resumable external
  evidence; both fail closed with CUDA OOM.
- [x] Evaluate any completed run on `test_public` through the frozen 256 x 256
  metric pipeline; neither fit completed, so public evaluation is not applicable.
- [x] Freeze the external aggregate report and verify all run, artifact,
  manifest, config, and report hashes.
- [x] Record objective duration, VRAM, latency, and failure results in the local
  worklog; do not copy raw evidence into Git.

### Task 3: Publish sanitized research evidence locally

**Files:**

- Create: `reports/high_resolution_patchcore.json`
- Modify: `docs/MODEL_SELECTION.md`
- Modify: `docs/LIMITATIONS.md`
- Modify: `tests/publication/test_claims.py` or a focused research evidence test
- Modify: this plan

- [x] Write a failing test for the sanitized aggregate result, fixed study
  identity, public-only scope, classification, and unchanged champions.
- [x] Import only reviewed aggregate public metrics, hashes, run identities,
  and resource measurements from the external report.
- [x] Document the result without claiming private improvement or replacing a
  champion.
- [x] Run focused tests, full non-GPU gates, Ruff, format, mypy, experiment,
  claims, security, and public-boundary verifiers.
- [x] Commit `docs(research): record high resolution patchcore study`.
- [x] Run an exact-HEAD clean export, complete plan bookkeeping and continuity,
  and require a clean tracked worktree.
