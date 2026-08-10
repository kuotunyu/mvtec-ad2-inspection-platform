# Memory-Bounded PatchCore Research Implementation Plan

**Status:** Complete

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether the proven 640 x 640 `wallplugs` localization gain survives a 5-10x smaller PatchCore coreset without repeating the resource-limited ratio-0.10 contract.

**Architecture:** Add two ratio-only research configs, a deterministic conditional study module, and an optional child-only resource guard for the existing subprocess executor. Probe ratio 0.01 at seed 42, run the predeclared ratio-0.02 rescue only after a safe quality miss, and replicate the first passing ratio at seeds 17 and 2026 while keeping all raw evidence external.

**Tech Stack:** Python 3.12, Pydantic contracts, pytest, psutil, anomalib 2.5 PatchCore, PyTorch/CUDA, existing `RunStore`, `Supervisor`, GPU lease, public evaluator, and release gates.

## Global Constraints

- Category is exactly `wallplugs`; training/evaluation data remain public-only and evaluation geometry remains 256 x 256.
- Candidate geometry is exactly 640 x 640; candidate ratios are exactly 0.01 and 0.02; seeds are exactly 42, 17, and 2026.
- Candidate configs may differ from `patchcore-640.yaml` only in `family_options.coreset_sampling_ratio`.
- Ratio 0.01 is always probed first. Ratio 0.02 runs only after a resource-safe ratio-0.01 quality miss. Replication uses only the first passing ratio.
- Existing 512 baselines and 640 ratio-0.10 frontier evidence are immutable references; never rerun ratio 0.10, 576, or 768.
- Raw outputs stay under `D:\mvtec-ad2-memory-bounded-patchcore-20260811`; only reviewed sanitized aggregate evidence may enter Git.
- The guard may terminate only the child process it created. Never stop, pause, signal, or modify another workload.
- Champions, official `PRIVATE-NO-GO`, and one-submission state remain unchanged.
- Do not push, submit to MVTec, tag, create a Release, deploy, or publish a model.
- Work inline on `main`, use TDD, and commit only as `kuotunyu <61350295+kuotunyu@users.noreply.github.com>`.

---

### Task 1: Freeze ratio configs, candidate ladder, and verdict contracts

**Files:**
- Create: `experiments/configs/research/patchcore-640-coreset-001.yaml`
- Create: `experiments/configs/research/patchcore-640-coreset-002.yaml`
- Create: `experiments/memory_bounded_patchcore.py`
- Create: `tests/unit/research/test_memory_bounded_patchcore.py`
- Modify: `docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md`

**Interfaces:**
- Consumes: `ModelConfig`, `RunSpec`, `StudyMetrics`, `StudyComparison`, immutable `FrontierReport`, and matching public baseline records.
- Produces: `validate_memory_bounded_config(candidate, reference, ratio) -> None`, `build_candidate_specs(config_001, config_002, dataset_manifest_sha256) -> tuple[RunSpec, ...]`, `CandidateOutcome`, `passes_seed42_gate(outcome, frontier) -> bool`, `select_ratio(probes) -> float | None`, and `classify_memory_bounded_study(...) -> StudyVerdict`.

- [x] **Step 1: Write failing config-difference and candidate-order tests**

```python
def test_ratio_configs_change_only_the_declared_coreset_ratio() -> None:
    reference = load_model_config(Path("experiments/configs/research/patchcore-640.yaml"))
    one = load_model_config(
        Path("experiments/configs/research/patchcore-640-coreset-001.yaml")
    )
    two = load_model_config(
        Path("experiments/configs/research/patchcore-640-coreset-002.yaml")
    )
    validate_memory_bounded_config(one, reference=reference, ratio=0.01)
    validate_memory_bounded_config(two, reference=reference, ratio=0.02)


def test_candidate_specs_freeze_ratio_then_seed_order() -> None:
    specs = build_candidate_specs(one, two, dataset_manifest_sha256="a" * 64)
    assert [(s.config["family_options"]["coreset_sampling_ratio"], s.seed) for s in specs] == [
        (0.01, 42), (0.02, 42), (0.01, 17),
        (0.01, 2026), (0.02, 17), (0.02, 2026),
    ]
```

- [x] **Step 2: Run the focused test and observe RED**

Run: `uv run pytest tests/unit/research/test_memory_bounded_patchcore.py -q`

Expected: collection fails because the configs and module do not exist.

- [x] **Step 3: Add minimal configs and exact normalization guard**

Copy `patchcore-640.yaml` twice. Change only
`family_options.coreset_sampling_ratio` to `0.01` and `0.02`. Implement config
validation by restoring the declared ratio to `0.1` in the normalized candidate
payload and requiring byte-equivalent canonical payloads.

- [x] **Step 4: Write failing gate, rescue, and verdict tests**

```python
def test_ratio_one_advances_when_quality_and_efficiency_are_preserved() -> None:
    outcome = _outcome(ratio=.01, au_pro=.04, image=-.03, pixel=.01,
                       artifact_mib=150, p95=110)
    assert passes_seed42_gate(outcome, frontier=_frontier())
    assert select_ratio((outcome,)) == .01


def test_ratio_two_is_allowed_only_after_safe_quality_miss() -> None:
    miss = _outcome(ratio=.01, au_pro=.01, resource_ok=True)
    rescue = _outcome(ratio=.02, au_pro=.04, resource_ok=True)
    assert select_probe_specs(SPECS, probes=(miss,)) == (SPECS[1],)
    assert select_ratio((miss, rescue)) == .02
    assert select_probe_specs(SPECS, probes=(_resource_failure(.01),)) == ()


def test_three_seed_verdict_is_recomputed() -> None:
    passing = (_outcome(seed=42, au_pro=.04), _outcome(seed=17, au_pro=.03),
               _outcome(seed=2026, au_pro=.01))
    assert classify_memory_bounded_study(passing) == "EFFICIENT_REPRODUCIBLE"
```

- [x] **Step 5: Implement minimal immutable contract models and classifiers**

Use explicit verdict literals:
`EFFICIENT_REPRODUCIBLE`, `EFFICIENT_SEED42_ONLY`,
`NO_QUALITY_PRESERVATION`, and `RESOURCE_LIMIT_EXCEEDED`. Require finite
metrics, exact seed/ratio ordering, ratio-specific artifact caps, fixed latency
caps, zero image failures, recomputed arithmetic means, and no caller-trusted
verdict.

- [x] **Step 6: Run focused quality gates**

```powershell
uv run pytest tests/unit/research/test_memory_bounded_patchcore.py -q
uv run ruff format --check experiments/memory_bounded_patchcore.py tests/unit/research/test_memory_bounded_patchcore.py
uv run ruff check experiments/memory_bounded_patchcore.py tests/unit/research/test_memory_bounded_patchcore.py
uv run mypy experiments/memory_bounded_patchcore.py
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 7: Mark Task 1 complete and commit**

```powershell
git add experiments/configs/research/patchcore-640-coreset-001.yaml experiments/configs/research/patchcore-640-coreset-002.yaml experiments/memory_bounded_patchcore.py tests/unit/research/test_memory_bounded_patchcore.py docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md
git commit -m "feat(research): define memory bounded patchcore study"
```

### Task 2: Add an optional debounced child-only resource guard

**Files:**
- Create: `experiments/orchestration/resource_guard.py`
- Create: `tests/unit/orchestration/test_resource_guard.py`
- Modify: `experiments/orchestration/supervisor.py`
- Modify: `tests/unit/orchestration/test_subprocess_executor.py`
- Modify: `docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md`

**Interfaces:**
- Produces: `ResourceSnapshot`, `ResourceLimits`, `probe_resource_snapshot()`, `assert_resource_preflight(snapshot, free_disk_bytes) -> None`, and `ResourceGuard.__call__(elapsed_seconds) -> str | None`.
- Extends: `FailureKind` with `resource_limit` and `SubprocessExecutor(..., resource_guard: Callable[[float], str | None] | None = None, terminate_grace_seconds: float = 10.0)`.

- [x] **Step 1: Write failing preflight and debounce tests**

```python
def test_preflight_requires_memory_disk_temperature_and_idle_gpu() -> None:
    assert_resource_preflight(_snapshot(ram=20_000, gpu=500, temp=45), 200 * 1024**3)
    with pytest.raises(StopConditionError, match="16 GiB"):
        assert_resource_preflight(_snapshot(ram=15_000), 200 * 1024**3)


def test_guard_stops_only_after_three_consecutive_breaches() -> None:
    snapshots = iter((_snapshot(ram=3000), _snapshot(ram=3000), _snapshot(ram=3000)))
    guard = ResourceGuard(probe=lambda: next(snapshots), limits=FROZEN_LIMITS)
    assert guard(10) is None
    assert guard(20) is None
    assert guard(30) == "system available memory below 4096 MiB for 3 samples"


def test_healthy_sample_resets_debounce_and_timeout_is_immediate() -> None:
    guard = ResourceGuard(probe=_sequence(3000, 20_000, 3000, 3000, 3000), limits=limits)
    assert [guard(t) for t in (10, 20, 30, 40, 50)][-1] is not None
    assert ResourceGuard(probe=_healthy, limits=limits)(limits.timeout_seconds) == (
        "wall-clock limit reached"
    )
```

- [x] **Step 2: Observe RED**

Run: `uv run pytest tests/unit/orchestration/test_resource_guard.py -q`

Expected: fail because `resource_guard.py` does not exist.

- [x] **Step 3: Implement pure snapshots, preflight, and debounced guard**

Use `psutil.virtual_memory().available`, existing `probe_gpu_health()`, and
`shutil.disk_usage`. Frozen formal limits are 16 GiB preflight RAM, 160 GiB
preflight disk, three consecutive runtime samples below 4 GiB RAM, above
22,500 MiB GPU memory, or at/above 83 C. Timeout is supplied per ratio.

- [x] **Step 4: Write failing subprocess termination and sibling-safety test**

Start a long-lived sibling process and a guarded executor child. Make the guard
return `test resource stop` on its first heartbeat. Assert the executor returns
`error_kind == "resource_limit"`, its child exits, its logs are preserved, and
the sibling remains alive until the test's `finally` cleanup.

- [x] **Step 5: Extend `SubprocessExecutor` minimally**

At each timeout heartbeat, call the optional guard with elapsed monotonic time.
On a reason, emit `resource_guard_stop`, terminate only the owned `Popen`
instance, wait the configured grace period, kill only that instance if needed,
and return a `resource_limit` result containing stdout/stderr hashes. Existing
callers with no guard must remain byte-for-byte behavior compatible.

- [x] **Step 6: Run orchestration gates**

```powershell
uv run pytest tests/unit/orchestration/test_resource_guard.py tests/unit/orchestration/test_subprocess_executor.py tests/unit/orchestration/test_run_matrix.py -q
uv run ruff format --check experiments/orchestration/resource_guard.py experiments/orchestration/supervisor.py tests/unit/orchestration/test_resource_guard.py tests/unit/orchestration/test_subprocess_executor.py
uv run ruff check experiments/orchestration/resource_guard.py experiments/orchestration/supervisor.py tests/unit/orchestration/test_resource_guard.py tests/unit/orchestration/test_subprocess_executor.py
uv run mypy experiments/orchestration
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 7: Mark Task 2 complete and commit**

```powershell
git add experiments/orchestration/resource_guard.py experiments/orchestration/supervisor.py tests/unit/orchestration/test_resource_guard.py tests/unit/orchestration/test_subprocess_executor.py docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md
git commit -m "feat(research): guard formal worker resources"
```

### Task 3: Implement resumable conditional execution and sanitized reporting

**Files:**
- Modify: `experiments/memory_bounded_patchcore.py`
- Modify: `tests/unit/research/test_memory_bounded_patchcore.py`
- Modify: `docs/EXPERIMENT_RUNBOOK.md`
- Modify: `docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md`

**Interfaces:**
- Consumes: Task 1 contracts, Task 2 resource guard, immutable baseline/frontier reports, `Supervisor`, `_attempt_command_factory`, and `_evaluate_run`.
- Produces: `MemoryBoundedStudyReport`, `write_memory_bounded_report(path, report) -> Path`, `execute_memory_bounded_study(args) -> MemoryBoundedStudyReport | None`, and CLI `python -m experiments.memory_bounded_patchcore`.

- [x] **Step 1: Write failing orchestration and report tests**

Test exact dry-run identities; source/config/dataset/reference mismatch rejection;
ratio-0.01 always first; ratio-0.02 only after safe quality miss; no rescue after
resource failure; replication only for the first passing ratio; completed
identity resume; differing existing report rejection; canonical identity
recomputation; and rejection of paths, raw errors, predictions, private fields,
credentials, or submission data.

- [x] **Step 2: Observe RED**

Run: `uv run pytest tests/unit/research/test_memory_bounded_patchcore.py -q`

Expected: fail on missing executor/report/CLI behavior.

- [x] **Step 3: Implement the minimal conditional executor**

Construct one external `RunStore`. Before the first run, call
`assert_resource_preflight`. For each candidate, create a fresh
`SubprocessExecutor` using a ratio-specific `ResourceGuard` timeout (2,700
seconds for 0.01 and 3,600 seconds for 0.02), run the one-item supervisor queue,
evaluate the completed identity under the same lease contract, and build a
sanitized outcome. Stop later work after integrity/resource failure; otherwise
follow only the frozen ladder.

- [x] **Step 4: Add exact CLI and runbook contract**

Required flags: `--data-root`, `--dataset-manifest`, `--runs-root`,
`--config-001`, and `--config-002`. Optional flags: `--reference-config`,
`--baseline-config`, `--baseline-public-benchmark`, `--frontier-report`,
`--output`, `--device`, `--gpu-lock`, and `--dry-run`. Document the exact
external root and identical-command resume rule.

- [x] **Step 5: Run focused and adjacent gates**

```powershell
uv run pytest tests/unit/research/test_memory_bounded_patchcore.py tests/unit/research/test_balanced_patchcore_study.py tests/unit/research/test_patchcore_resolution_frontier.py tests/unit/orchestration/test_resource_guard.py -q
uv run ruff format --check experiments/memory_bounded_patchcore.py tests/unit/research/test_memory_bounded_patchcore.py
uv run ruff check experiments/memory_bounded_patchcore.py tests/unit/research/test_memory_bounded_patchcore.py
uv run mypy experiments/memory_bounded_patchcore.py
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 6: Mark Task 3 complete and commit**

```powershell
git add experiments/memory_bounded_patchcore.py tests/unit/research/test_memory_bounded_patchcore.py docs/EXPERIMENT_RUNBOOK.md docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md
git commit -m "feat(research): run memory bounded patchcore study"
```

### Task 4: Execute the bounded GPU study and import sanitized evidence

**Files:**
- External only: `D:\mvtec-ad2-memory-bounded-patchcore-20260811`
- Create after review: `reports/memory_bounded_patchcore.json`
- Modify after review: `docs/MODEL_SELECTION.md`
- Modify: `tests/unit/research/test_memory_bounded_patchcore.py`
- Modify: `docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md`

**Interfaces:**
- Consumes: exact committed Task 3 source, verified dataset manifest, immutable public baselines/frontier, free-resource preflight, and exclusive GPU lease.
- Produces: raw external evidence and one reviewed sanitized aggregate report.

- [x] **Step 1: Verify formal prerequisites without mutation**

Require tracked status clean; local `main` exact Task 3 SHA; dataset, config,
benchmark, frontier, environment-lock, author/committer, and trailer audits;
`D:` free space at least 160 GiB; system available memory at least 16 GiB; no
foreign CUDA compute process; no live project lease; and a nonexistent external
root before first execution. Do not stop the unrelated
`coding-agent-eval-v0.1-publication` workload; wait if it owns needed resources.

- [x] **Step 2: Run and verify dry-run**

Run the documented CLI with `--dry-run`. Capture source, dataset, config,
reference, and ordered run identities plus the conditional ladder. Confirm no
GPU process, lease, or run directory was created.

- [x] **Step 3: Execute to the frozen stopping point**

Run the identical command without `--dry-run`. Monitor durable heartbeats but
do not manually stop a healthy worker. If interrupted, rerun only the identical
command. Allow the child-only guard to enforce the frozen thresholds. Preserve
every attempted outcome and skip all branches not selected by the ladder.

- [x] **Step 4: Verify external evidence before import**

Recompute source/config/dataset/reference/run/artifact/report identities;
confirm only declared ratios/seeds ran; confirm branching matches the seed-42
outcome; confirm all large/raw fields remain external; and confirm scope is
`test_public-only`, `submitted` is false, champions are unchanged, and no
private data was accessed.

- [x] **Step 5: Write and observe a failing committed-evidence test**

Load `reports/memory_bounded_patchcore.json`, remove `canonical_sha256`, validate
`MemoryBoundedStudyReport`, recompute the identity/verdict/selected ratio,
assert every selected-ratio artifact is within its cap, assert `wallplugs`
champion remains PatchCore, and assert official `PRIVATE-NO-GO`/one-submission
state is unchanged.
Run the test and observe the missing-report failure.

- [x] **Step 6: Import only reviewed aggregates and document the result**

Copy the sanitized report into `reports/memory_bounded_patchcore.json`; update
`docs/MODEL_SELECTION.md` with quality, resource, latency, artifact-size,
limitations, fixed verdict, and unchanged champion. Do not copy raw maps,
predictions, images, checkpoints, or logs.

- [x] **Step 7: Run research gates, mark Task 4 complete, and commit**

```powershell
uv run pytest tests/unit/research -q
uv run python scripts/verify_experiments.py
uv run python scripts/verify_claims.py
uv run python scripts/security_scan.py --root .
uv run python scripts/verify_public_boundary.py --git-tree HEAD
git diff --check
git add reports/memory_bounded_patchcore.json docs/MODEL_SELECTION.md tests/unit/research/test_memory_bounded_patchcore.py docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md
git commit -m "docs(research): record memory bounded patchcore study"
```

### Task 5: Complete exact-HEAD release verification and bookkeeping

**Files:**
- Modify: `docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md`
- Local-only overwrite: `.codex-local/PROJECT_STATUS.md`
- Local-only append: `.codex-local/WORKLOG.md`

**Interfaces:**
- Consumes: exact committed Task 4 source and sanitized evidence.
- Produces: checked Plan 13, clean verified local `main`, and concise local handoff state.

- [x] **Step 1: Run complete local gates**

```powershell
$env:PYTHONWARNINGS = "error::DeprecationWarning:starlette.testclient"
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m "not gpu and not dataset" -q
npm --prefix apps/web run verify
npm --prefix apps/web run e2e
uv run python scripts/render_docs_assets.py --check-manifest
uv run python scripts/verify_experiments.py
uv run python scripts/verify_claims.py
uv run python scripts/security_scan.py --root .
uv run python scripts/verify_public_boundary.py --git-tree HEAD
```

Expected: every command exits 0.

- [x] **Step 2: Run exact-HEAD clean export**

```powershell
$shortSha = (git rev-parse --short HEAD).Trim()
powershell -ExecutionPolicy Bypass -File scripts/clean_export.ps1 -Treeish HEAD -ReportPath "D:\mvtec-ad2-release-evidence-20260811\memory-bounded-$shortSha.json"
```

Expected: package, Python/Node SBOM, Docker smoke, system, and real-container
browser gates pass for the exact committed SHA.

- [x] **Step 3: Mark final checkboxes and commit bookkeeping**

Mark Task 5 and the plan completion checklist only after Step 2 passes, then
run focused plan/report/release tests and commit:

```powershell
git add docs/superpowers/plans/2026-08-11-13-memory-bounded-patchcore.md
git commit -m "docs: complete memory bounded patchcore study"
```

- [x] **Step 4: Update local continuity and perform final audits**

Overwrite `.codex-local/PROJECT_STATUS.md`, append one compact entry per Task to
`.codex-local/WORKLOG.md`, and verify ignored-file status. Confirm no project
worker, GPU lease, or container remains; tracked status is clean; all reachable
author/committer identities are `kuotunyu`; no contributor trailers exist; and
local `main` is ahead of `origin/main` only by the new Plan 13 commits. Do not
push without a new explicit authorization.
