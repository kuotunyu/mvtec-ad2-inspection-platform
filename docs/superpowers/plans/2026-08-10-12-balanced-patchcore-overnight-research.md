# Balanced PatchCore Overnight Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reproduce the 640 x 640 `wallplugs` localization gain across three seeds and conditionally evaluate 576 x 576 as a more balanced public-only PatchCore candidate.

**Architecture:** Add one focused research module that reuses the existing `RunSpec`, isolated `Supervisor`, GPU lease, public evaluator, and immutable 512 baseline evidence. It executes the two missing 640 seeds, always evaluates 576 seed 42, conditionally expands 576 to seeds 17 and 2026, and writes an atomic identity-bound aggregate report while keeping all raw artifacts external.

**Tech Stack:** Python 3.12, Pydantic contracts, pytest, anomalib PatchCore, PyTorch/CUDA, existing experiment supervisor and public metric pipeline.

## Global Constraints

- Category is exactly `wallplugs`; baseline resolution is 512 x 512 and public evaluation remains 256 x 256.
- Candidate geometries are exactly 640 x 640 and 576 x 576; candidate seeds are exactly 42, 17, and 2026 as defined by the approved spec.
- Reuse immutable 640 seed-42 evidence; never rerun 768 x 768.
- Read only `test_public`; never read private images, metrics, predictions, or submission artifacts.
- Existing frozen run roots, champions, release verdict, and one-submission state remain unchanged.
- Raw outputs stay under a new external `D:\` root; only sanitized aggregate evidence may enter Git.
- Do not push, tag, create a Release, deploy, publish a model, or submit to MVTec.
- Work inline on `main`, use TDD, and commit only as `kuotunyu <61350295+kuotunyu@users.noreply.github.com>`.

---

### Task 1: Freeze configs, run matrix, and verdict contracts

**Files:**
- Create: `experiments/configs/research/patchcore-576.yaml`
- Create: `experiments/balanced_patchcore_study.py`
- Create: `tests/unit/research/test_balanced_patchcore_study.py`

**Interfaces:**
- Consumes: `ModelConfig`, `RunSpec`, `StudyMetrics`, `StudyComparison`, `StudyFailure`, and the committed seed-42 `FrontierReport`.
- Produces: `validate_balanced_config(candidate, baseline, resolution) -> None`, `build_candidate_specs(config_640, config_576, dataset_manifest_sha256) -> tuple[RunSpec, ...]`, `classify_stage_a(outcomes) -> StageAVerdict`, `passes_stage_b_advance(comparison) -> bool`, and `classify_stage_b(outcomes) -> StageBVerdict`.

- [x] **Step 1: Write failing config and run-matrix tests**

```python
def test_candidate_configs_change_only_geometry() -> None:
    baseline = load_model_config(Path("experiments/configs/models/patchcore.yaml"))
    config_640 = load_model_config(Path("experiments/configs/research/patchcore-640.yaml"))
    config_576 = load_model_config(Path("experiments/configs/research/patchcore-576.yaml"))
    validate_balanced_config(config_640, baseline=baseline, resolution=(640, 640))
    validate_balanced_config(config_576, baseline=baseline, resolution=(576, 576))


def test_fixed_specs_exclude_completed_640_seed_42() -> None:
    specs = build_candidate_specs(config_640, config_576, dataset_manifest_sha256="a" * 64)
    assert [(s.seed, s.config["input_size"]) for s in specs] == [
        (17, [640, 640]), (2026, [640, 640]), (42, [576, 576]),
        (17, [576, 576]), (2026, [576, 576]),
    ]
```

- [x] **Step 2: Run the focused tests and observe RED**

Run: `uv run pytest tests/unit/research/test_balanced_patchcore_study.py -q`

Expected: fail because the 576 config and balanced-study module do not exist.

- [x] **Step 3: Add the minimal 576 config and validation/spec builders**

Copy the frozen PatchCore model config, changing only `input_size` and `preprocessing.resize` to `[576, 576]`. Implement exact normalized-payload equality after restoring those two fields to `[512, 512]`; build the five ordered specs shown in the test.

- [x] **Step 4: Write failing frozen-verdict tests**

```python
def test_stage_a_requires_reproducible_localization_gain() -> None:
    assert classify_stage_a((_cmp(.069, image=-.040), _cmp(.03), _cmp(.01))) == "REPRODUCIBLE_LOCALIZATION_GAIN"
    assert classify_stage_a((_cmp(.069), _cmp(.03), _cmp(-.03))) == "MIXED"


def test_stage_b_advance_and_balanced_verdict() -> None:
    assert passes_stage_b_advance(_cmp(.03, image=-.005, pixel=.001))
    assert not passes_stage_b_advance(_cmp(.03, image=-.011, pixel=.001))
    assert classify_stage_b((_cmp(.03), _cmp(.025), _cmp(.02))) == "BALANCED_PROMISING"
```

- [x] **Step 5: Implement the minimal classifications and aggregate contract models**

Use explicit `Literal` verdicts, finite numeric fields, exact mean calculations, mandatory per-seed outcomes, and model validators that recompute rather than trust stored verdicts. Treat a run failure, latency over 500 ms, nonzero image failure rate, or declared resource breach as `RESOURCE_LIMIT_EXCEEDED`.

- [x] **Step 6: Run focused quality gates**

Run:

```powershell
uv run pytest tests/unit/research/test_balanced_patchcore_study.py -q
uv run ruff format --check experiments/balanced_patchcore_study.py tests/unit/research/test_balanced_patchcore_study.py
uv run ruff check experiments/balanced_patchcore_study.py tests/unit/research/test_balanced_patchcore_study.py
uv run mypy experiments/balanced_patchcore_study.py
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 7: Commit Task 1**

```powershell
git add experiments/configs/research/patchcore-576.yaml experiments/balanced_patchcore_study.py tests/unit/research/test_balanced_patchcore_study.py docs/superpowers/plans/2026-08-10-12-balanced-patchcore-overnight-research.md
git commit -m "feat(research): define balanced patchcore study"
```

### Task 2: Implement resumable sequential execution and sanitized reporting

**Files:**
- Modify: `experiments/balanced_patchcore_study.py`
- Modify: `tests/unit/research/test_balanced_patchcore_study.py`
- Modify: `docs/EXPERIMENT_RUNBOOK.md`

**Interfaces:**
- Consumes: Task 1 specs and verdict functions, `Supervisor`, `RunStore`, `GpuLease`, `_evaluate_run`, and committed `reports/patchcore_resolution_frontier.json`.
- Produces: `BalancedStudyReport`, `write_balanced_report(path, report) -> Path`, `execute_balanced_study(args) -> BalancedStudyReport | None`, and CLI `python -m experiments.balanced_patchcore_study`.

- [x] **Step 1: Write failing orchestration tests**

Test that dry-run emits the five deterministic identities, the committed 640 seed-42 identity is required and not scheduled, Stage A and 576 seed-42 run even after an independent candidate failure, 576 replication specs execute only after the fixed advance gate, an existing identical report is idempotent, a differing report is rejected, and serialized evidence excludes predictions, paths, raw errors, and private fields.

- [x] **Step 2: Run orchestration tests and observe RED**

Run: `uv run pytest tests/unit/research/test_balanced_patchcore_study.py -q`

Expected: fail on missing CLI/report/orchestration behavior.

- [x] **Step 3: Implement the minimum resumable executor**

Construct one `Supervisor` and external `RunStore`; execute each spec as a one-item tuple so completed identities resume safely. Always process the two 640 replication specs and 576 seed 42. Expand to the remaining 576 specs only when `passes_stage_b_advance` is true. Evaluate completed runs under the same GPU lease contract, heartbeat between evaluations, preserve sanitized `StudyFailure` evidence, and atomically write one canonical-hash report.

- [x] **Step 4: Add the exact CLI contract and runbook command**

Required flags: `--data-root`, `--dataset-manifest`, `--runs-root`, `--config-640`, `--config-576`; optional flags: `--baseline-config`, `--baseline-public-benchmark`, `--frontier-report`, `--output`, `--device`, `--gpu-lock`, and `--dry-run`. Document that the source must be committed and clean and that rerunning the same command resumes completed identities.

- [x] **Step 5: Run focused and adjacent tests**

Run:

```powershell
uv run pytest tests/unit/research/test_balanced_patchcore_study.py tests/unit/research/test_patchcore_resolution_frontier.py tests/unit/research/test_high_resolution_patchcore.py -q
uv run ruff format --check experiments/balanced_patchcore_study.py tests/unit/research/test_balanced_patchcore_study.py
uv run ruff check experiments/balanced_patchcore_study.py tests/unit/research/test_balanced_patchcore_study.py
uv run mypy experiments/balanced_patchcore_study.py
git diff --check
```

Expected: all commands exit 0.

- [x] **Step 6: Commit Task 2**

```powershell
git add experiments/balanced_patchcore_study.py tests/unit/research/test_balanced_patchcore_study.py docs/EXPERIMENT_RUNBOOK.md docs/superpowers/plans/2026-08-10-12-balanced-patchcore-overnight-research.md
git commit -m "feat(research): run balanced patchcore study"
```

### Task 3: Execute the bounded GPU study

**Files:**
- External only: `D:\mvtec-ad2-balanced-patchcore-20260810`
- Modify after review: `reports/balanced_patchcore_study.json`
- Modify after review: `docs/MODEL_SELECTION.md`
- Modify: `tests/unit/research/test_balanced_patchcore_study.py`

**Interfaces:**
- Consumes: exact committed Task 2 source, verified MVTec AD 2 dataset manifest, immutable 512 baseline benchmark, committed 640 seed-42 report, and shared GPU lease.
- Produces: raw external run/evaluation evidence and one reviewed sanitized committed aggregate report.

- [x] **Step 1: Resolve and verify prerequisites without mutation**

Confirm a clean tracked worktree; dataset and manifest identities; the existing 640 report identity; sufficient free space on `D:\`; no conflicting GPU compute process; an absent or stale-safe project lease; and author/committer history containing only the required identity. Resolve `D:\mvtec-ad2-balanced-patchcore-20260810` as the exact external root and fail closed if it already exists before the first execution.

- [x] **Step 2: Run CLI dry-run**

Run the documented command with `--dry-run` and capture the exact candidate identities, dataset hash, config hashes, source SHA, ordered run count, and Stage B conditional rule. Verify no GPU process or run directory was created.

- [x] **Step 3: Execute the formal study to its designed stopping point**

Run the same command without `--dry-run`. Do not terminate a live model process. If interrupted, rerun the identical command so the supervisor skips completed identities. Capture peak VRAM, durations, exit status, worker hashes, public-evaluation hashes, and the external aggregate report identity.

Two independent 640 seed-17 attempts were interrupted by system-wide forced
reboots during coreset selection. Preserve both external attempt directories,
classify Stage A as `RESOURCE_LIMIT_EXCEEDED`, and use the tested
`--stage-b-probe-only` recovery path to execute the independent 576 seed-42
probe without retrying the unsafe 640 candidate a third time.

- [x] **Step 4: Verify external evidence before importing it**

Recompute dataset, source, config, run, artifact, and report hashes; ensure only declared seeds/geometries ran; ensure the Stage B branch matches the seed-42 gate; confirm the report scope is `test_public-only`, `submitted` is false, and no raw/private fields are present.

- [x] **Step 5: Write a failing committed-evidence test**

Add a test that loads `reports/balanced_patchcore_study.json`, removes `canonical_sha256`, validates `BalancedStudyReport`, recomputes its identity and verdicts, confirms champions still select PatchCore for `wallplugs`, and confirms the one-submission/`PRIVATE-NO-GO` state is unchanged.

- [x] **Step 6: Observe RED, then import only sanitized aggregates**

Run the new committed-evidence test and observe the missing-report failure. Copy only the reviewed aggregate report into `reports/balanced_patchcore_study.json`; update `docs/MODEL_SELECTION.md` with the objective multi-seed outcome, limitations, and unchanged champion.

- [x] **Step 7: Run research gates and commit Task 3**

```powershell
uv run pytest tests/unit/research -q
uv run python scripts/verify_experiments.py
uv run python scripts/verify_claims.py
uv run python scripts/security_scan.py --root .
uv run python scripts/verify_public_boundary.py --git-tree HEAD
git diff --check
git add reports/balanced_patchcore_study.json docs/MODEL_SELECTION.md tests/unit/research/test_balanced_patchcore_study.py docs/superpowers/plans/2026-08-10-12-balanced-patchcore-overnight-research.md
git commit -m "docs(research): record balanced patchcore study"
```

### Task 4: Complete release-candidate verification and bookkeeping

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-12-balanced-patchcore-overnight-research.md`
- Local-only overwrite: `.codex-local/PROJECT_STATUS.md`
- Local-only append: `.codex-local/WORKLOG.md`

**Interfaces:**
- Consumes: exact committed Task 3 source and sanitized evidence.
- Produces: checked plan, clean verified HEAD, and concise local handoff state.

- [ ] **Step 1: Run complete local gates**

Run:

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

Expected: every command exits 0 and the Python suite emits no Starlette TestClient deprecation warning.

- [ ] **Step 2: Verify an exact-HEAD clean export**

Run:

```powershell
$shortSha = git rev-parse --short HEAD
powershell -ExecutionPolicy Bypass -File scripts/clean_export.ps1 -Treeish HEAD -ReportPath "D:\mvtec-ad2-release-evidence-20260810\balanced-patchcore-$shortSha.json"
```

Expected: `Clean export PASS` for the exact committed SHA after frozen dependency installation, Python/frontend checks, wheel and sdist builds, Python and Node SBOMs, Docker smoke, system tests, and the real browser workflow.

- [ ] **Step 3: Complete plan bookkeeping and commit**

Mark every checkbox complete only after its evidence exists, update the local continuity files, rerun focused bookkeeping/claim checks, audit author/committer/trailers, and commit the tracked plan update:

```powershell
git add docs/superpowers/plans/2026-08-10-12-balanced-patchcore-overnight-research.md
git commit -m "docs: complete balanced patchcore study"
```

- [ ] **Step 4: Confirm final boundaries**

Require tracked `git status` clean, no active formal worker, no held project GPU lease, and no publication action. Do not push the new commits without a separate explicit authorization.
