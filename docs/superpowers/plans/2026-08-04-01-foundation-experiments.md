# MVTec AD 2 Foundation and Experiments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reproducible project foundation, official dataset pipeline, frozen metrics, three-model experiment harness, unattended RTX 4090 supervisor, champion selection, and official submission bundles.

**Architecture:** A typed Python package owns immutable experiment contracts and machine-readable evidence. Large data and runs live outside Git. Anomalib adapters implement a common protocol, while a sequential supervisor records atomic run state and resumes only hash-compatible work.

**Tech Stack:** Python 3.12, uv, Pydantic 2, Anomalib 2.5.0, PyTorch CUDA, NumPy, pandas, scikit-learn, SciPy, psutil, pynvml, pytest, Ruff, mypy.

## Global Constraints

- Use only the official archive URL and verify size `32,739,596,982` and SHA-256 `c0ded99ef32bfc8e352d52beb44515e5b292b8598cb963aadfa91ca0763505e4` before extraction.
- Store dataset, weights, runs, checkpoints, and runtime artifacts outside Git; their locations come from environment variables or CLI arguments.
- Train only on `train/good`; calibrate only on `validation/good`; do not inspect public or private outputs before the specified gate.
- Compare exactly PatchCore, EfficientAD, and Dinomaly using Anomalib 2.5.0 unless a verified compatibility defect is recorded before formal runs.
- Formal seeds are `17`, `42`, and `2026`.
- Public test may select frozen contenders and champions; private and private-mixed results may only validate the frozen selection.
- Every public number must be derived from a machine-readable artifact containing code, config, dataset, model, and environment identity.
- Never push, publish, tag, release, upload to Hugging Face, or submit to the MVTec server without explicit user authorization.
- Use local Git identity `kuotunyu <61350295+kuotunyu@users.noreply.github.com>` and make small English commits.

---

## Planned File Map

- `pyproject.toml`: package metadata, dependency groups, test/lint/type configuration.
- `uv.lock`: exact dependency resolution.
- `.gitignore`: data, artifacts, credentials, caches, checkpoints, and UI build outputs.
- `.env.example`: variable names with non-secret examples.
- `src/inspection_platform/contracts/*.py`: versioned dataset, run, prediction, metric, and model-bundle schemas.
- `experiments/data/download.py`: resumable official archive download.
- `experiments/data/extract.py`: safe atomic extraction.
- `experiments/data/manifest.py`: dataset inventory and provenance.
- `experiments/metrics/{thresholds,image,pixel,bootstrap}.py`: frozen metric contract.
- `experiments/models/{base,patchcore,efficient_ad,dinomaly,factory}.py`: common model interface and adapters.
- `experiments/configs/models/*.yaml`: frozen model-family settings.
- `experiments/orchestration/{queue,gpu_lock,supervisor}.py`: run expansion, exclusivity, heartbeat, retry, and resume.
- `experiments/evaluate_public.py`: one-way public evaluation gate.
- `experiments/select_champions.py`: predeclared lexicographic selection.
- `experiments/submission/build.py`: private/private-mixed prediction bundle generation.
- `tests/{unit,ml_integrity,integration}/`: offline and GPU-gated verification.

### Task 1: Establish the Python project and immutable contracts

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/inspection_platform/__init__.py`
- Create: `src/inspection_platform/contracts/dataset.py`
- Create: `src/inspection_platform/contracts/experiments.py`
- Create: `src/inspection_platform/contracts/predictions.py`
- Create: `src/inspection_platform/contracts/models.py`
- Test: `tests/unit/contracts/test_contracts.py`

**Interfaces:**
- Produces: `DatasetManifest`, `RunSpec`, `RunRecord`, `PredictionRecord`, `ModelBundleManifest`, `sha256_file(Path) -> str`, and `canonical_hash(BaseModel) -> str`.
- Later tasks consume these exact Pydantic models; schema versions are string literals and reject unknown major versions.
- `RunSpec.model_family` accepts exactly `patchcore`, `efficient_ad`, or `dinomaly`. `ModelBundleManifest` additionally separates `runtime_kind: Literal["anomalib", "mock"]` from `model_family`: a real bundle requires one of those three families, while a mock bundle requires `model_family=None` and `evaluation_scope="synthetic-ci-only"`.

- [x] **Step 1: Write contract tests before project code**

```python
def test_run_spec_hash_is_order_independent() -> None:
    left = RunSpec(model_family="patchcore", category="can", seed=42, config={"a": 1, "b": 2})
    right = RunSpec(model_family="patchcore", category="can", seed=42, config={"b": 2, "a": 1})
    assert left.identity == right.identity

def test_model_bundle_rejects_unknown_schema_major() -> None:
    with pytest.raises(ValueError, match="schema major"):
        ModelBundleManifest(
            schema_version="2.0.0",
            category="can",
            runtime_kind="anomalib",
            model_family="patchcore",
            files=[],
        )
```

- [x] **Step 2: Run the focused tests and confirm missing imports fail**

Run: `uv run pytest tests/unit/contracts/test_contracts.py -q`
Expected: FAIL because the package and models do not exist.

- [x] **Step 3: Create the package metadata and minimal typed contracts**

```python
SCHEMA_VERSION = "1.0.0"

class RunSpec(BaseModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    model_family: Literal["patchcore", "efficient_ad", "dinomaly"]
    category: MVTecAD2Category
    seed: int
    config: dict[str, JsonValue]

    @computed_field
    @property
    def identity(self) -> str:
        return canonical_hash(self)
```

Configure Python `>=3.12,<3.13`, the `dev` dependency group, Ruff, mypy strict mode for project modules, and pytest markers `gpu`, `dataset`, and `slow`. Put training dependencies in a separate `ml` extra so the later CPU product image does not inherit them.

- [x] **Step 4: Run contract, format, lint, and type gates**

Run: `uv sync --group dev`
Run: `uv run pytest tests/unit/contracts/test_contracts.py -q`
Run: `uv run ruff format --check .`
Run: `uv run ruff check .`
Run: `uv run mypy src experiments`
Expected: all commands pass.

- [x] **Step 5: Commit the foundation**

```powershell
git add pyproject.toml uv.lock .gitignore .env.example src tests
git commit -m "build: establish typed project contracts"
```

### Task 2: Implement resumable official dataset acquisition

**Files:**
- Create: `experiments/__init__.py`
- Create: `experiments/data/__init__.py`
- Create: `experiments/data/download.py`
- Create: `experiments/data/extract.py`
- Create: `experiments/data/manifest.py`
- Create: `experiments/data/cli.py`
- Test: `tests/unit/data/test_download.py`
- Test: `tests/unit/data/test_extract.py`
- Test: `tests/ml_integrity/test_dataset_manifest.py`

**Interfaces:**
- Produces: `download_archive(source: DatasetSource, destination: Path) -> Path`, `extract_archive(archive: Path, destination: Path) -> Path`, and `build_dataset_manifest(root: Path) -> DatasetManifest`.
- CLI: `python -m experiments.data.cli prepare --root PATH`, where `PATH` is an external dataset directory.

- [x] **Step 1: Write downloader tests using a local range-capable HTTP fixture**

```python
def test_download_resumes_partial_file(http_dataset_server: DatasetServer, tmp_path: Path) -> None:
    target = tmp_path / "dataset.tar.gz"
    Path(f"{target}.part").write_bytes(http_dataset_server.payload[:512])
    result = download_archive(http_dataset_server.source, target)
    assert result.read_bytes() == http_dataset_server.payload
    assert http_dataset_server.observed_ranges == ["bytes=512-"]

def test_download_removes_bad_complete_archive(http_dataset_server: DatasetServer, tmp_path: Path) -> None:
    target = tmp_path / "dataset.tar.gz"
    target.write_bytes(b"wrong")
    with pytest.raises(IntegrityError, match="SHA-256"):
        download_archive(http_dataset_server.source, target, max_attempts=1)
```

- [x] **Step 2: Run downloader tests and confirm failure**

Run: `uv run pytest tests/unit/data/test_download.py -q`
Expected: FAIL because acquisition functions do not exist.

- [x] **Step 3: Implement `.part` download, Range handling, and fail-closed verification**

```python
MVTECAD2_SOURCE = DatasetSource(
    name="mvtec_ad_2",
    url="https://www.mydrive.ch/shares/150997/701c90d3aea6588f404936e32a674602/download/466712769-1743429042/mvtec_ad_2.tar.gz",
    expected_size=32_739_596_982,
    sha256="c0ded99ef32bfc8e352d52beb44515e5b292b8598cb963aadfa91ca0763505e4",
)
```

If a server ignores Range and returns `200`, truncate the partial file before writing. Stream to disk, flush, verify size and SHA-256, then atomically rename `.part` to the final archive. Never log tokens, cookies, or response bodies.

- [x] **Step 4: Write malicious tar and dataset-structure tests**

```python
@pytest.mark.parametrize("member", ["../escape", "/absolute", "ok/../../escape"])
def test_extract_rejects_path_escape(member: str, tmp_path: Path) -> None:
    archive = build_tar(tmp_path, member)
    with pytest.raises(UnsafeArchiveError):
        extract_archive(archive, tmp_path / "out")

def test_manifest_requires_all_official_splits(valid_dataset_tree: Path) -> None:
    shutil.rmtree(valid_dataset_tree / "can" / "test_private_mixed")
    with pytest.raises(DatasetLayoutError, match="test_private_mixed"):
        build_dataset_manifest(valid_dataset_tree)
```

- [x] **Step 5: Implement safe extraction and manifest creation**

Reject absolute paths, `..`, symlinks, hardlinks, device entries, and extraction outside a temporary sibling directory. Validate all eight categories and required split folders, inventory PNG files and public masks, then atomically rename the verified tree into place. Write the manifest outside the dataset and include its canonical SHA-256.

- [x] **Step 6: Run offline data tests**

Run: `uv run pytest tests/unit/data tests/ml_integrity/test_dataset_manifest.py -q`
Expected: PASS without downloading the real archive.

- [x] **Step 7: Run the formal acquisition only when adequate disk is confirmed**

Run: `uv run python -m experiments.data.cli prepare --root "$env:MVTECAD2_DATA_ROOT"`
Expected: resumable download, exact byte/hash verification, safe extraction, and a manifest summary for eight categories. If another formal GPU job is active, dataset download may proceed only when it does not disturb that experiment's disk or network contract.

- [x] **Step 8: Commit the acquisition pipeline without data**

```powershell
git add experiments/data tests/unit/data tests/ml_integrity/test_dataset_manifest.py
git commit -m "feat(data): add verified MVTec AD 2 acquisition"
```

### Task 3: Freeze threshold and metric contracts

**Files:**
- Create: `experiments/metrics/__init__.py`
- Create: `experiments/metrics/thresholds.py`
- Create: `experiments/metrics/image.py`
- Create: `experiments/metrics/pixel.py`
- Create: `experiments/metrics/bootstrap.py`
- Create: `experiments/metrics/artifacts.py`
- Test: `tests/unit/metrics/test_thresholds.py`
- Test: `tests/unit/metrics/test_bootstrap.py`
- Test: `tests/ml_integrity/test_metric_contract.py`

**Interfaces:**
- Produces: `conformal_upper_threshold(scores: NDArrayFloat, alpha: float = 0.01) -> ThresholdResult`, `compute_image_metrics(labels: NDArrayInt, scores: NDArrayFloat) -> ImageMetrics`, `compute_pixel_metrics(masks: NDArrayBool, maps: NDArrayFloat) -> PixelMetrics`, and `paired_bootstrap_delta(left: NDArrayFloat, right: NDArrayFloat, seed: int, resamples: int = 10_000) -> ConfidenceInterval`.
- Metric artifacts include `metric_contract_version="1.0.0"` and refuse mixed prediction-contract versions.

- [x] **Step 1: Write exact conformal-order-statistic tests**

```python
def test_conformal_threshold_uses_finite_sample_rank() -> None:
    scores = np.arange(100, dtype=float)
    result = conformal_upper_threshold(scores, alpha=0.01)
    assert result.rank == 100
    assert result.threshold == 99.0

def test_threshold_ties_are_review() -> None:
    assert decision_for_score(score=0.7, threshold=0.7) is InspectionDecision.REVIEW
```

- [x] **Step 2: Run focused tests and confirm failure**

Run: `uv run pytest tests/unit/metrics/test_thresholds.py -q`
Expected: FAIL because the functions are missing.

- [x] **Step 3: Implement validation-only threshold calibration**

```python
def conformal_upper_threshold(scores: NDArrayFloat, alpha: float = 0.01) -> ThresholdResult:
    checked = validate_finite_vector(scores)
    rank = min(len(checked), math.ceil((len(checked) + 1) * (1 - alpha)))
    threshold = float(np.partition(checked, rank - 1)[rank - 1])
    return ThresholdResult(alpha=alpha, rank=rank, n=len(checked), threshold=threshold)
```

Reject empty, non-finite, non-one-dimensional, or out-of-range-alpha inputs.

- [x] **Step 4: Add hand-computed image, pixel, AU-PRO, and paired-bootstrap fixtures**

Use tiny arrays with manually calculable answers, constant-score cases, all-normal cases, and invalid mask shapes. Seed bootstrap resampling explicitly and record resample count.

- [x] **Step 5: Implement metrics and compare AU-PRO against official utilities**

The official-compatible adapter must compute pixel AU-PRO through FPR `0.30`, retain per-category values, and fail if image/mask order differs. Run a parity test against the downloaded official code utilities on synthetic masks; store the allowed numeric tolerance in the test.

- [x] **Step 6: Run metric gates**

Run: `uv run pytest tests/unit/metrics tests/ml_integrity/test_metric_contract.py -q`
Expected: PASS with deterministic bootstrap outputs.

- [x] **Step 7: Commit the metric contract**

```powershell
git add experiments/metrics tests/unit/metrics tests/ml_integrity/test_metric_contract.py
git commit -m "feat(eval): freeze anomaly metric contracts"
```

### Task 4: Implement the three-model adapter layer and frozen configs

**Files:**
- Create: `experiments/models/base.py`
- Create: `experiments/models/factory.py`
- Create: `experiments/models/patchcore.py`
- Create: `experiments/models/efficient_ad.py`
- Create: `experiments/models/dinomaly.py`
- Create: `experiments/configs/models/patchcore.yaml`
- Create: `experiments/configs/models/efficient_ad.yaml`
- Create: `experiments/configs/models/dinomaly.yaml`
- Create: `experiments/train.py`
- Create: `experiments/predict.py`
- Test: `tests/unit/models/test_factory.py`
- Test: `tests/ml_integrity/test_model_adapter_contract.py`

**Interfaces:**
- Produces: `AnomalyExperimentAdapter.fit(context: FitContext) -> FitArtifact`, `predict(context: PredictContext) -> PredictionArtifact`, and `export_bundle(context: ExportContext) -> ModelBundleManifest`.
- `create_adapter(family: ModelFamily, config: ModelConfig) -> AnomalyExperimentAdapter` is the only construction entry point.

- [x] **Step 1: Write adapter contract tests with a fake implementation**

```python
def test_prediction_artifact_preserves_input_order(fake_adapter: FakeAdapter, sample_batch: list[Path]) -> None:
    artifact = fake_adapter.predict(PredictContext(images=sample_batch, split="test_public"))
    assert [item.input_path for item in artifact.records] == sample_batch
    assert all(item.anomaly_map_sha256 for item in artifact.records)

def test_factory_rejects_unapproved_family() -> None:
    with pytest.raises(ValueError, match="approved model family"):
        create_adapter("ganomaly", config={})
```

- [x] **Step 2: Run adapter tests and confirm failure**

Run: `uv run pytest tests/unit/models/test_factory.py -q`
Expected: FAIL because adapter contracts do not exist.

- [x] **Step 3: Implement the common adapter and model factory**

Use explicit typed contexts; adapters may translate to Anomalib but must return project-owned contracts. Centralize seed setting, deterministic flags, preprocessing identity, device identity, environment capture, and output validation in the base class.

- [x] **Step 4: Add one pinned YAML config per family**

Each file must state Anomalib version, backbone/model name, input size, batch size, precision, trainer limits, `seed: null` to require runtime injection of an approved formal seed, preprocessing, checkpoint policy, and export mode. Resolve each YAML into a canonical `ModelConfig` before execution and store its hash.

- [x] **Step 5: Implement PatchCore, EfficientAD, and Dinomaly adapters**

Verify actual Anomalib 2.5.0 APIs in the installed environment before finalizing the translation layer. Keep any compatibility shim inside its family adapter and cover it with a regression test. Do not fork upstream model internals merely to improve results.

- [x] **Step 6: Add dataset-split guards**

```python
def assert_fit_split(paths: Sequence[Path]) -> None:
    if any("train/good" not in path.as_posix() for path in paths):
        raise SplitLeakageError("fit inputs must come only from train/good")
```

Use manifest identities rather than substring checks in production; the snippet expresses the required failure behavior.

- [x] **Step 7: Run offline adapter tests and one marked GPU smoke per family**

Run: `uv run pytest tests/unit/models tests/ml_integrity/test_model_adapter_contract.py -q`
Run after GPU preflight: `uv run pytest -m gpu tests/integration/test_model_gpu_smoke.py -q`
Expected: offline gates pass; each smoke produces finite scores, correctly shaped maps, and a loadable checkpoint/bundle.

- [x] **Step 8: Commit adapters and frozen configs**

```powershell
git add experiments/models experiments/configs experiments/train.py experiments/predict.py tests
git commit -m "feat(models): add frozen anomaly model adapters"
```

### Task 5: Build the resumable unattended supervisor

**Files:**
- Create: `experiments/orchestration/__init__.py`
- Create: `experiments/orchestration/queue.py`
- Create: `experiments/orchestration/gpu_lock.py`
- Create: `experiments/orchestration/health.py`
- Create: `experiments/orchestration/supervisor.py`
- Create: `experiments/run_matrix.py`
- Test: `tests/unit/orchestration/test_queue.py`
- Test: `tests/unit/orchestration/test_gpu_lock.py`
- Test: `tests/integration/test_supervisor_resume.py`

**Interfaces:**
- Produces: `expand_stage(stage: ExperimentStage) -> list[RunSpec]`, `GpuLease.acquire(owner: str)`, and `Supervisor.run(queue: Sequence[RunSpec]) -> SupervisorSummary`.
- Each run directory contains `spec.json`, `record.json`, `heartbeat.jsonl`, `checkpoints/`, `predictions/`, and `metrics/`.

- [x] **Step 1: Write queue identity and resume tests**

```python
def test_completed_matching_run_is_skipped(run_store: RunStore, spec: RunSpec) -> None:
    run_store.write_completed(spec, valid_artifacts=True)
    assert Supervisor(run_store).plan([spec]).skipped == [spec.identity]

def test_changed_config_never_reuses_checkpoint(run_store: RunStore, spec: RunSpec) -> None:
    run_store.write_checkpoint(spec)
    changed = spec.model_copy(update={"config": {"different": True}})
    assert Supervisor(run_store).plan([changed]).resumed == []
```

- [x] **Step 2: Run orchestration tests and confirm failure**

Run: `uv run pytest tests/unit/orchestration tests/integration/test_supervisor_resume.py -q`
Expected: FAIL because supervisor modules are missing.

- [x] **Step 3: Implement atomic queue expansion and evidence directories**

Stage 1 expands `3 families × 8 categories × seed 42`. Stage 2 reads the frozen per-category contender artifact and expands only seeds `17` and `2026`; it reuses valid seed-42 runs. Sort runs deterministically by category, family, then seed.

- [x] **Step 4: Implement the GPU lease and compute-workload preflight**

Use atomic exclusive file creation with owner PID, process start time, repository identity, and heartbeat. A lease is stale only when both heartbeat is expired and the recorded process identity is gone. Supplement the lease with NVML or `nvidia-smi` compute-process inspection; ignore ordinary WDDM desktop graphics entries, but refuse to start when another Python/WSL/CUDA compute workload is active. Preserve diagnostic output without killing processes.

- [x] **Step 5: Implement heartbeat, stop rules, and one OOM downgrade**

The only automatic config mutation is the model config's predeclared `oom_fallback_batch_size`; record the mutation as a separate attempt under the same run. Checksum mismatch, non-finite output, invalid shape, corrupt checkpoint, free disk below 80 GiB, or a second OOM fails the run and stops the formal queue.

- [x] **Step 6: Test crash and resume behavior with fake subprocesses**

Inject exit codes, truncated JSON, expired leases, a completed checkpoint, and a mismatched hash. Assert that completed work is preserved, resumable work resumes, invalid work is quarantined, and no incompatible directory is overwritten.

- [x] **Step 7: Run supervisor tests**

Run: `uv run pytest tests/unit/orchestration tests/integration/test_supervisor_resume.py -q`
Expected: PASS without a GPU.

- [x] **Step 8: Commit the supervisor**

```powershell
git add experiments/orchestration experiments/run_matrix.py tests
git commit -m "feat(experiments): add resumable GPU supervisor"
```

### Task 6: Execute the frozen public benchmark and select champions

**Files:**
- Create: `experiments/evaluate_public.py`
- Create: `experiments/select_contenders.py`
- Create: `experiments/select_champions.py`
- Create: `experiments/reports/render_benchmark.py`
- Create: `reports/schemas/benchmark.schema.json`
- Test: `tests/unit/selection/test_champions.py`
- Test: `tests/ml_integrity/test_public_gate.py`

**Interfaces:**
- Produces: `public_benchmark.json`, `contenders.json`, `champions.json`, `benchmark.md`, and figures generated from the JSON.
- `select_champion(candidates: Sequence[CandidateEvidence]) -> SelectionDecision` encodes the approved AU-PRO, AUROC, latency, VRAM, and size tie-break sequence.

- [x] **Step 1: Write synthetic selection cases for every tie-break**

```python
def test_unresolved_quality_prefers_lower_latency() -> None:
    decision = select_champion([candidate("a", au_pro=.50, ci=(-.01, .02), p95=8),
                                candidate("b", au_pro=.51, ci=(-.02, .01), p95=12)])
    assert decision.winner == "a"
    assert decision.reason == "quality_unresolved_lower_gpu_p95"

def test_latency_within_five_percent_prefers_lower_vram() -> None:
    decision = select_champion(tied_quality_candidates(p95=(10.0, 10.4), vram=(4_000, 6_000)))
    assert decision.winner == "a"
```

- [x] **Step 2: Run selection tests and confirm failure**

Run: `uv run pytest tests/unit/selection/test_champions.py -q`
Expected: FAIL because selection code is missing.

- [x] **Step 3: Implement one-way public gate and selection logic**

Require a signed/frozen-stage manifest listing all valid stage-1 runs before public evaluation starts. Write a gate event with timestamp and hashes. Refuse config changes or missing candidates after this event; corrections require a new explicit experiment version rather than mutating prior evidence.

- [x] **Step 4: Run stage 1 and freeze per-category contenders**

Run: `uv run python -m experiments.run_matrix --stage screening --data-root "$env:MVTECAD2_DATA_ROOT" --runs-root "$env:MVTECAD2_RUNS_ROOT"`
Run: `uv run python -m experiments.evaluate_public --stage screening`
Run: `uv run python -m experiments.select_contenders`
Expected: 24 valid seed-42 runs and exactly two contenders per category with recorded rationale.

- [x] **Step 5: Run replication stage and freeze champions**

Run: `uv run python -m experiments.run_matrix --stage replication --data-root "$env:MVTECAD2_DATA_ROOT" --runs-root "$env:MVTECAD2_RUNS_ROOT"`
Run: `uv run python -m experiments.evaluate_public --stage replication`
Run: `uv run python -m experiments.select_champions`
Expected: seed `17/42/2026` evidence for both contenders in every category and one frozen champion per category.

- [x] **Step 6: Generate the canonical aggregate report**

Render Markdown/figures only from `public_benchmark.json` and `champions.json`. Validate JSON schemas and fail if a number in Markdown is not traceable to an artifact path and hash.

- [x] **Step 7: Run selection and public-gate tests**

Run: `uv run pytest tests/unit/selection tests/ml_integrity/test_public_gate.py -q`
Expected: PASS.

- [x] **Step 8: Commit code, frozen aggregate evidence, and reports**

Do not commit raw predictions, checkpoints, private outputs, or MVTec images.

```powershell
git add experiments reports/schemas reports/public_benchmark.json reports/champions.json reports/benchmark.md docs/assets/bench
git commit -m "eval: freeze MVTec AD 2 champion evidence"
```

### Task 7: Build official private submission bundles without submitting

**Files:**
- Create: `experiments/submission/__init__.py`
- Create: `experiments/submission/official_utils.py`
- Create: `experiments/submission/build.py`
- Create: `experiments/submission/verify.py`
- Test: `tests/unit/submission/test_submission.py`
- Test: `tests/ml_integrity/test_private_boundary.py`

**Interfaces:**
- Produces external `private_submission.tar.gz`, `private_mixed_submission.tar.gz`, checksums, and `submission_summary.json`.
- No function in this package performs network submission or accepts credentials.

- [x] **Step 1: Write boundary and archive-layout tests**

```python
def test_private_predictions_are_never_written_under_repo(repo_root: Path, builder: SubmissionBuilder) -> None:
    with pytest.raises(PublicBoundaryError):
        builder.build(output_dir=repo_root / "reports")

def test_submission_contains_every_manifest_image_once(private_manifest: PrivateManifest, archive: Path) -> None:
    members = inspect_submission(archive)
    assert set(members.image_ids) == set(private_manifest.image_ids)
    assert len(members.image_ids) == len(set(members.image_ids))
```

- [x] **Step 2: Run submission tests and confirm failure**

Run: `uv run pytest tests/unit/submission tests/ml_integrity/test_private_boundary.py -q`
Expected: FAIL because the builder is missing.

- [x] **Step 3: Integrate checksum-verified official code utilities**

Download official utilities outside Git, record their URL and SHA-256, and invoke their validator through a narrow adapter. Do not vendor unreviewed code or silently normalize a rejected submission.

- [x] **Step 4: Implement private and private-mixed inference bundles**

Resolve only frozen champion bundles. Preserve official image identifiers, validate finite scores/maps and required dimensions, run the official validator, then create archives and SHA-256 sidecars in an external output directory.

- [x] **Step 5: Run private-boundary and format tests**

Run: `uv run pytest tests/unit/submission tests/ml_integrity/test_private_boundary.py -q`
Expected: PASS without exposing private predictions.

- [x] **Step 6: Generate but do not submit formal bundles**

Run: `uv run python -m experiments.submission.build --test-type private --output-root "$env:MVTECAD2_SUBMISSION_ROOT"`
Run: `uv run python -m experiments.submission.build --test-type private_mixed --output-root "$env:MVTECAD2_SUBMISSION_ROOT"`
Expected: two official-validator-passing archives, two checksum files, and a redacted summary.

- [ ] **Step 7: Commit only code and redacted summary schema**

```powershell
git add experiments/submission tests reports/schemas
git commit -m "feat(eval): prepare official private submissions"
```

### Task 8: Verify the foundation and experiment handoff

**Files:**
- Create: `scripts/verify_experiments.py`
- Create: `docs/EXPERIMENT_RUNBOOK.md`
- Create: `docs/DATA_CARD.md`
- Create: `docs/MODEL_SELECTION.md`
- Test: `tests/integration/test_clean_experiment_export.py`

**Interfaces:**
- Produces one command that validates source boundaries, locks, manifests, aggregate evidence, champion bundles, and submission summaries.

- [ ] **Step 1: Write a clean-export failure test**

Create a temporary Git archive, install only declared groups, and assert that data, weights, checkpoints, `.env`, private predictions, and absolute workstation paths are absent.

- [ ] **Step 2: Implement the experiment verifier**

The verifier checks committed-file policy, JSON schemas, source-to-report claim traceability, dataset provenance summary, complete run matrix, bundle hashes, threshold contract, and official-submission validator status. It prints `PASS`, `FAIL`, or `PENDING EXTERNAL SUBMISSION`; it never converts pending external work into success.

- [ ] **Step 3: Write exact operator commands and recovery procedures**

Document environment variables, acquisition, smoke, screening, replication, resume, report generation, submission generation, and failure recovery. Do not include personal absolute paths or credentials.

- [ ] **Step 4: Run all foundation gates**

Run: `uv run pytest -m "not gpu and not dataset" -q`
Run: `uv run ruff format --check .`
Run: `uv run ruff check .`
Run: `uv run mypy src experiments`
Run: `uv run python scripts/verify_experiments.py`
Expected: code gates pass; verifier reports `PENDING EXTERNAL SUBMISSION` until official results exist.

- [ ] **Step 5: Commit the verified handoff**

```powershell
git add scripts docs tests
git commit -m "docs: complete experiment reproducibility handoff"
```

## Completion Gate

This plan is complete only when Tasks 1–8 are committed, the worktree is clean, offline verification passes, real dataset provenance is verified, the public experiment matrix and champions are frozen, and private submission archives pass the official local validator. Official server submission remains an explicit external pending item.
