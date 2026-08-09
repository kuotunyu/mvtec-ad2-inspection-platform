# Thresholded Submission Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Active

**Goal:** Build and locally verify a complete MVTec AD 2 archive containing one hash-traceable continuous TIFF and one validation-calibrated binary PNG for every private image, without another official submission.

**Architecture:** A focused calibration module streams finite validation pixels from each frozen champion run and freezes the official baseline `mean + 3 * std` threshold. The submission builder uses the eight exact calibrations to write parallel continuous and thresholded trees, while a cache-only entry point rebuilds from the immutable external TIFF cache and runs both project and pinned-official preflight checks.

**Tech Stack:** Python 3.12, NumPy, Pillow, tifffile, Pydantic, pytest, Ruff, mypy, pinned MVTec AD 2 official utilities

## Global Constraints

- Work inline on `main` without subagents or a worktree, as authorized by local repository instructions.
- Use TDD for every production behavior: observe focused RED, implement the minimum GREEN, then run broader gates.
- Keep dataset images, anomaly maps, calibrations, archives, and raw official outputs outside Git.
- Preserve the original `D:\mvtec-ad2-submissions-20260807-171623\private_submission.tar.gz` byte-for-byte.
- Do not upload, submit, tag, release, deploy, or publish a model.
- Use only anomaly-free validation maps to calibrate thresholds; never use private labels, official scores, or private map distributions.
- Use strict `map > threshold`, output mode `L`, and values exactly `0` or `255`.
- Accept official utilities only at SHA-256 `fda9b379affbbde8b4d4fc1fe6ac52aaff981f347f3424e6b6de027457549f15`.
- Every commit author and committer is `kuotunyu <61350295+kuotunyu@users.noreply.github.com>` with no contributor trailers.

---

### Task 1: Freeze validation-only segmentation thresholds

**Files:**
- Create: `experiments/submission/thresholds.py`
- Create: `tests/unit/submission/test_threshold_calibration.py`
- Modify: `experiments/submission/__init__.py`
- Modify: `docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md`

**Interfaces:**
- Consumes: a completed seed-42 run directory containing `record.json`, `predictions/validation.json`, and its referenced `.npy` anomaly maps.
- Produces: `SubmissionThreshold`, `combine_population_statistics(...)`, and `calibrate_submission_threshold(run_dir: Path) -> SubmissionThreshold`.

- [x] **Step 1: Write the failing streaming-statistics test**

```python
def test_combined_statistics_match_literal_population_values() -> None:
    first = np.array([[0.0, 1.0]], dtype=np.float32)
    second = np.array([[2.0, 3.0]], dtype=np.float32)

    result = combine_population_statistics((first, second))

    assert result.pixel_count == 4
    assert result.mean == pytest.approx(1.5)
    assert result.standard_deviation == pytest.approx(np.sqrt(1.25))
    assert result.threshold == pytest.approx(1.5 + 3 * np.sqrt(1.25))
```

- [x] **Step 2: Run the focused test and observe the expected RED**

Run: `uv run pytest tests/unit/submission/test_threshold_calibration.py::test_combined_statistics_match_literal_population_values -q`

Expected: FAIL because `experiments.submission.thresholds` does not exist.

- [x] **Step 3: Implement the immutable contract and bounded statistic combiner**

```python
@dataclass(frozen=True, slots=True)
class PopulationStatistics:
    pixel_count: int
    mean: float
    standard_deviation: float
    threshold: float


class SubmissionThreshold(ContractModel):
    method: Literal["validation_pixel_mean_plus_3_population_std"] = (
        "validation_pixel_mean_plus_3_population_std"
    )
    calibration_split: Literal["validation/good"] = "validation/good"
    category: MVTecAD2Category
    run_identity: Sha256
    validation_artifact_sha256: Sha256
    pixel_count: Annotated[int, Field(gt=0)]
    mean: Annotated[float, Field(allow_inf_nan=False)]
    standard_deviation: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    threshold: Annotated[float, Field(allow_inf_nan=False)]


def combine_population_statistics(
    arrays: Iterable[NDArray[np.floating[Any]]],
) -> PopulationStatistics:
    count = 0
    mean = 0.0
    m2 = 0.0
    for array in arrays:
        checked = np.asarray(array, dtype=np.float64)
        if checked.ndim != 2 or checked.size == 0 or not np.isfinite(checked).all():
            raise ValueError("calibration maps must be non-empty finite 2D arrays")
        chunk_count = checked.size
        chunk_mean = float(checked.mean())
        chunk_m2 = float(np.square(checked - chunk_mean).sum(dtype=np.float64))
        delta = chunk_mean - mean
        total = count + chunk_count
        mean += delta * chunk_count / total
        m2 += chunk_m2 + delta * delta * count * chunk_count / total
        count = total
    if count == 0:
        raise ValueError("calibration maps must not be empty")
    standard_deviation = math.sqrt(m2 / count)
    return PopulationStatistics(count, mean, standard_deviation, mean + 3 * standard_deviation)
```

- [x] **Step 4: Run the focused test and observe GREEN**

Run: `uv run pytest tests/unit/submission/test_threshold_calibration.py::test_combined_statistics_match_literal_population_values -q`

Expected: `1 passed`.

- [x] **Step 5: Add RED tests for artifact identity, hash mismatch, invalid maps, and completed seed-42 provenance**

Use real temporary `.npy`, `PredictionArtifact`, `spec.json`, and `record.json` files. Assert the literal category, run directory name, validation JSON SHA-256, pixel count, mean, standard deviation, and threshold. Mutate one map after writing the artifact and require a `ValueError` containing `hash`; set the run status to failed or seed to 7 and require rejection.

- [x] **Step 6: Implement calibration from a completed run**

Load and validate the prediction contract, require `split == "validation"`, `record.status == "completed"`, `spec.seed == 42`, and `artifact.category == spec.category`. Verify each `ArtifactFile` size and SHA-256 before loading it with `allow_pickle=False`. Compute the validation JSON hash from bytes and construct `SubmissionThreshold` from the combined statistics.

- [x] **Step 7: Run focused and static gates**

Run:

```powershell
uv run pytest tests/unit/submission/test_threshold_calibration.py -q
uv run ruff check experiments/submission/thresholds.py tests/unit/submission/test_threshold_calibration.py
uv run mypy experiments/submission/thresholds.py
```

Expected: all commands exit zero.

- [x] **Step 8: Update bookkeeping and commit Task 1**

Mark Task 1 complete, update the ignored continuity files, audit identity/trailers, and commit only the Task 1 tracked files:

```powershell
git add experiments/submission/thresholds.py experiments/submission/__init__.py tests/unit/submission/test_threshold_calibration.py docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md
git commit -m "feat(submission): calibrate pixel thresholds"
```

---

### Task 2: Require complete continuous and thresholded archive trees

**Files:**
- Modify: `experiments/submission/build.py`
- Modify: `experiments/submission/verify.py`
- Modify: `tests/unit/submission/test_submission.py`
- Modify: `docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md`

**Interfaces:**
- Consumes: `Mapping[str, SubmissionThreshold]`, `PrivateManifest`, and exact TIFF `SubmissionPrediction` objects.
- Produces: archives with parallel `anomaly_images` and `anomaly_images_thresholded` trees; `SubmissionInspection` and `ArchiveVerification` with separate counts.

- [x] **Step 1: Write the failing dual-tree archive test**

```python
def test_submission_contains_matching_binary_thresholded_images(tmp_path: Path) -> None:
    prediction = _prediction(tmp_path, values=np.array([[0.0, 2.0]], dtype=np.float16))
    archive = SubmissionBuilder(manifest=_manifest()).build(
        output_dir=tmp_path / "external-output",
        predictions=(prediction,),
        thresholds={"can": _threshold(1.0)},
    )

    with tarfile.open(archive, "r:gz") as stream:
        member = stream.extractfile(
            "private_submission/anomaly_images_thresholded/can/test_private/000_regular.png"
        )
        assert member is not None
        with Image.open(member) as image:
            assert image.mode == "L"
            assert np.asarray(image).tolist() == [[0, 255]]
```

- [x] **Step 2: Run the focused test and observe RED**

Run: `uv run pytest tests/unit/submission/test_submission.py::test_submission_contains_matching_binary_thresholded_images -q`

Expected: FAIL because `build` does not accept thresholds and writes no PNG tree.

- [x] **Step 3: Implement minimal thresholded PNG generation**

Require the threshold keys to equal the manifest categories. For each finite 2D TIFF, copy the continuous source and save `np.where(values > threshold, 255, 0).astype(np.uint8)` through Pillow mode `L` at the mirrored `.png` path.

- [x] **Step 4: Run the focused test and observe GREEN**

Run: `uv run pytest tests/unit/submission/test_submission.py::test_submission_contains_matching_binary_thresholded_images -q`

Expected: `1 passed`.

- [x] **Step 5: Add RED tests for missing calibration, identity parity, duplicates, dimensions, and content**

Assert that a missing or extra category threshold fails before archive creation; inspection reports exact continuous and thresholded identities; verification rejects a tar with one missing PNG; generated PNG dimensions equal its TIFF dimensions; TIFF dtype remains `float16`; and thresholded values contain no value outside `{0, 255}`.

- [x] **Step 6: Extend archive inspection, verification, and summary schema**

```python
@dataclass(frozen=True, slots=True)
class SubmissionInspection:
    continuous_image_ids: tuple[str, ...]
    thresholded_image_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchiveVerification:
    archive: Path
    archive_sha256: str
    continuous_image_count: int
    thresholded_image_count: int
    calibration_sha256: dict[str, str]
```

Require both exact identity sets and preserve only sanitized counts/hashes in summary schema `2.0.0` with status `LOCAL-PREFLIGHT-NOT-SUBMITTED` or `PASS`.

- [x] **Step 7: Run submission regression and static gates**

Run:

```powershell
uv run pytest tests/unit/submission -q
uv run ruff check experiments/submission tests/unit/submission
uv run mypy experiments/submission
```

Expected: all commands exit zero.

- [x] **Step 8: Update bookkeeping and commit Task 2**

```powershell
git add experiments/submission/build.py experiments/submission/verify.py tests/unit/submission/test_submission.py docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md
git commit -m "feat(submission): require thresholded outputs"
```

---

### Task 3: Rebuild safely from the immutable prediction cache

**Files:**
- Create: `experiments/submission/rebuild.py`
- Create: `tests/unit/submission/test_rebuild.py`
- Modify: `experiments/submission/__init__.py`
- Modify: `docs/EXPERIMENT_RUNBOOK.md`
- Modify: `docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md`

**Interfaces:**
- Consumes: dataset root, runs root, frozen champions JSON, existing external prediction-cache root, new output root, and checksum-pinned official-utils root.
- Produces: a new corrected local archive, eight external calibration contracts, a sanitized summary, and no GPU lease or network request.

- [ ] **Step 1: Write the failing cache inventory test**

Create a controlled one-image manifest/cache and assert:

```python
predictions = cached_predictions(
    manifest=manifest,
    cache_root=cache_root,
    dataset_root=dataset_root,
)
assert predictions == (
    SubmissionPrediction("can", "test_private", "000_regular", source_tiff),
)
```

Then delete the TIFF, change its geometry, and add a spurious identity in separate tests; each must fail closed with a stable error.

- [ ] **Step 2: Run the focused tests and observe RED**

Run: `uv run pytest tests/unit/submission/test_rebuild.py -q`

Expected: FAIL because `experiments.submission.rebuild` does not exist.

- [ ] **Step 3: Implement exact cache inventory and geometry validation**

Resolve every expected TIFF below `cache_root/{category}/{split}/tiff`, require no extra TIFFs, decode as finite two-dimensional `float16`, and require its shape to match the corresponding source PNG `(height, width)`. Return predictions in manifest order.

- [ ] **Step 4: Run the focused tests and observe GREEN**

Run: `uv run pytest tests/unit/submission/test_rebuild.py -q`

Expected: all cache-inventory tests pass.

- [ ] **Step 5: Add a RED orchestration test with the real pinned validator boundary**

Inject a narrow `validate(Path)` callable for the unit orchestration test while keeping archive building, thresholding, inspection, and summary real. Assert that the callable receives the extracted archive root, no `GpuLease` is constructed, and the old archive hash is unchanged. The real pinned utility is exercised against the complete 4,090-image archive in Task 4.

- [ ] **Step 6: Implement the cache-only CLI**

The CLI accepts `--data-root`, `--runs-root`, `--champions`, `--source-cache-root`, `--output-root`, and `--official-utils-root`. It refuses an output root equal to or inside the repository or source cache, refuses an existing target archive, calibrates the eight exact seed-42 champions, writes external calibration JSON atomically, builds and verifies the archive, extracts it under a temporary directory, runs `OfficialUtilities.validate`, and writes `submission_summary.json` as `LOCAL-PREFLIGHT-NOT-SUBMITTED`.

- [ ] **Step 7: Run focused, documentation, and static gates**

Run:

```powershell
uv run pytest tests/unit/submission -q
uv run pytest tests/publication tests/release -q
uv run ruff check experiments/submission tests/unit/submission
uv run mypy experiments/submission
```

Expected: all commands exit zero.

- [ ] **Step 8: Update bookkeeping and commit Task 3**

```powershell
git add experiments/submission/rebuild.py experiments/submission/__init__.py tests/unit/submission/test_rebuild.py docs/EXPERIMENT_RUNBOOK.md docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md
git commit -m "feat(submission): rebuild from frozen cache"
```

---

### Task 4: Prove the full 4,090-image local preflight

**Files:**
- Modify: `docs/RELEASE_CHECKLIST.md`
- Modify: `docs/LIMITATIONS.md`
- Modify: `docs/assets/evidence/release-verification.json`
- Modify: `tests/release/test_release.py`
- Modify: `docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md`
- Local only: `D:\mvtec-ad2-submission-thresholded-20260810\`

**Interfaces:**
- Consumes: the exact committed Task 3 source, original archive and source-cache hashes, frozen champion runs, verified dataset, and pinned official utilities.
- Produces: external corrected archive and summary, sanitized committed local-preflight evidence, complete release gates, and no official submission.

- [ ] **Step 1: Write the failing release-evidence test**

Require committed release evidence to preserve the historical official inventory (`4,090 TIFF`, `0 thresholded PNG`, `PRIVATE-NO-GO`) while separately recording a local-only preflight with `4,090` continuous, `4,090` thresholded, eight validation-only calibrations, official validator `PASS`, and `submitted: false`.

- [ ] **Step 2: Run the release test and observe RED**

Run: `uv run pytest tests/release/test_release.py -q`

Expected: FAIL because no corrected local-preflight evidence exists.

- [ ] **Step 3: Run the complete external cache-only rebuild**

Run the new CLI against:

```text
data root: D:\datasets\mvtec-ad-2
runs root: D:\mvtec-ad2-runs
champions: reports/champions.json
source cache: D:\mvtec-ad2-submissions-20260807-171623\prediction-cache
new output: D:\mvtec-ad2-submission-thresholded-20260810
official utilities: D:\mvtec-ad2-official-utils-20260810\extracted\MVTecAD2_public_code_utils
```

Before and after, hash the original archive and require exact equality. Record only sanitized aggregate counts, method identifiers, calibration hashes, archive hash, validator result, source commit, and `submitted: false`; do not commit the corrected archive, thresholds, paths, image identities, or raw validator output.

- [ ] **Step 4: Update truthful documentation and evidence**

Keep the official result and `PRIVATE-NO-GO` unchanged. State that a later local pipeline repair successfully generated a complete thresholded preflight but was not submitted and therefore produced no new official F1 measurement.

- [ ] **Step 5: Run focused and complete non-GPU gates**

Run:

```powershell
uv run pytest tests/unit/submission tests/release tests/publication -q
uv run pytest -m "not gpu" -q
uv run ruff check .
uv run mypy experiments src apps/api scripts
uv run python scripts/verify_experiments.py
uv run python scripts/verify_claims.py
uv run python scripts/verify_public_boundary.py --git-tree HEAD
```

Expected: all commands exit zero; historical official claims remain unchanged.

- [ ] **Step 6: Commit verified local-preflight evidence**

```powershell
git add docs/RELEASE_CHECKLIST.md docs/LIMITATIONS.md docs/assets/evidence/release-verification.json tests/release/test_release.py docs/superpowers/plans/2026-08-10-06-thresholded-submission-pipeline.md
git commit -m "docs(release): record thresholded local preflight"
```

- [ ] **Step 7: Run the exact-HEAD clean export and finalize continuity**

Run `scripts/clean_export.ps1 -Treeish HEAD` to a new external report. Mark the plan `Complete`, update both ignored continuity files, commit only final plan bookkeeping if needed, and require a clean tracked worktree. Do not push without separate authorization.
