# MVTec AD 2 Product Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the durable batch-inspection backend, model-serving boundary, human review workflow, evidence reports, and operational telemetry around the frozen experiment artifacts.

**Architecture:** FastAPI accepts validated local uploads and creates SQLite-backed jobs. A separate worker owns GPU inference through renewable leases, writes content-addressed artifacts atomically, and resumes idempotently after interruption. The API never performs model inference in its request process.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, SQLite WAL, Pillow, python-magic/libmagic fallback, Prometheus client, structlog, pytest, httpx.

## Global Constraints

- Consume the versioned contracts and champion bundles created by Plan 01; do not create a second prediction, threshold, or model-manifest schema.
- The product outcome is `PASS` or `REVIEW`; only a human review may record `ACCEPT`, `REJECT`, or `UNCERTAIN`.
- API requests enqueue work only. A dedicated worker owns model loading and inference.
- Use opaque UUIDs and server-generated filenames. Never trust archive paths, browser names, MIME headers, or client model paths.
- SQLite runs in WAL mode with foreign keys enabled and a configured busy timeout. State transitions are transactional and compare-and-set.
- Persist raw input, anomaly map, overlay, prediction JSON, and report references outside Git in a configured artifact root.
- Every mutation appends an audit event without raw image bytes, secrets, or full exception text.
- No multi-tenancy, RBAC, live camera, automatic final rejection, or Kubernetes in v1.
- Never push, publish, tag, release, upload to Hugging Face, or submit official predictions without explicit user authorization.

---

## Planned File Map

- `src/inspection_platform/settings.py`: fail-closed runtime configuration.
- `src/inspection_platform/db/{engine,models,migrations,repositories}.py`: durable relational state.
- `src/inspection_platform/jobs/{states,service,leases}.py`: job lifecycle and ownership.
- `src/inspection_platform/ingestion/{images,archives,service}.py`: secure batch ingestion.
- `src/inspection_platform/storage/{paths,artifacts}.py`: content-addressed atomic artifacts.
- `src/inspection_platform/registry/{repository,service}.py`: verified frozen bundle registry.
- `src/inspection_platform/inference/{base,anomalib_runtime,mock}.py`: serving boundary.
- `src/inspection_platform/worker/{runner,heartbeat,cli}.py`: resumable worker.
- `src/inspection_platform/reviews/service.py`: human decisions and audit trail.
- `src/inspection_platform/reports/{schemas,builder,render}.py`: JSON, CSV, and HTML evidence.
- `apps/api/{main,dependencies,errors,routes}.py`: HTTP interface.

### Task 1: Create runtime settings and the durable database model

**Files:**
- Create: `src/inspection_platform/settings.py`
- Create: `src/inspection_platform/db/__init__.py`
- Create: `src/inspection_platform/db/engine.py`
- Create: `src/inspection_platform/db/models.py`
- Create: `src/inspection_platform/db/repositories.py`
- Create: `alembic.ini`
- Create: `src/inspection_platform/db/migrations/env.py`
- Create: `src/inspection_platform/db/migrations/versions/0001_initial.py`
- Test: `tests/unit/db/test_database.py`
- Test: `tests/unit/db/test_repositories.py`

**Interfaces:**
- Produces `Settings`, `create_engine_and_session(settings)`, `JobRepository`, `ImageRepository`, `ReviewRepository`, and `AuditRepository`.
- Tables: `jobs`, `inspection_images`, `predictions`, `reviews`, `audit_events`, and `model_bundles`.
- All externally visible identifiers are UUID strings; database timestamps are timezone-aware UTC.

- [x] **Step 1: Write WAL, foreign-key, and repository tests first**

```python
def test_sqlite_connection_enables_safety_pragmas(session_factory: SessionFactory) -> None:
    with session_factory() as session:
        assert session.scalar(text("PRAGMA journal_mode")) == "wal"
        assert session.scalar(text("PRAGMA foreign_keys")) == 1

def test_job_creation_and_audit_are_atomic(repositories: Repositories) -> None:
    job = repositories.jobs.create(CreateJob(category="can", image_count=2))
    events = repositories.audit.list_for_resource(job.id)
    assert [(event.action, event.resource_id) for event in events] == [("job.created", job.id)]
```

- [x] **Step 2: Run the focused tests and confirm missing modules fail**

Run: `uv run pytest tests/unit/db -q`
Expected: FAIL because settings, tables, and repositories do not exist.

- [x] **Step 3: Implement fail-closed settings and the initial migration**

```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///./runtime/inspection.db"
    artifact_root: Path = Path("./runtime/artifacts")
    model_registry_root: Path = Path("./runtime/models")
    max_upload_bytes: int = 25 * 1024 * 1024
    max_archive_files: int = 2_000
    max_archive_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    lease_seconds: int = 120
    heartbeat_seconds: int = 30
```

Resolve configured roots, create only their immediate directories, reject a root that is a file, and never silently fall back to a user home or repository-wide path. Configure WAL, foreign keys, a 5-second busy timeout, and transaction-scoped repositories.

- [x] **Step 4: Run migrations and database verification**

Run: `uv run alembic upgrade head` with a temporary database URL.
Run: `uv run pytest tests/unit/db -q`
Expected: migration and all database tests pass.

- [ ] **Step 5: Commit the database foundation**

```powershell
git add src/inspection_platform/settings.py src/inspection_platform/db alembic.ini tests/unit/db
git commit -m "feat(backend): add durable inspection database"
```

### Task 2: Enforce the job state machine and renewable worker leases

**Files:**
- Create: `src/inspection_platform/jobs/__init__.py`
- Create: `src/inspection_platform/jobs/states.py`
- Create: `src/inspection_platform/jobs/leases.py`
- Create: `src/inspection_platform/jobs/service.py`
- Test: `tests/unit/jobs/test_states.py`
- Test: `tests/integration/jobs/test_leases.py`

**Interfaces:**
- Produces `JobStatus`, `transition_job(job_id, expected, target)`, `claim_next_job(worker_id, now)`, `renew_lease(job_id: str, worker_id: str, now: datetime) -> bool`, and `recover_expired_leases(now)`.
- Allowed terminal states: `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`, and `CANCELLED`.

- [x] **Step 1: Specify all legal and illegal transitions in tests**

```python
@pytest.mark.parametrize(
    ("source", "target"),
    [("QUEUED", "RUNNING"), ("RUNNING", "COMPLETED"),
     ("RUNNING", "COMPLETED_WITH_ERRORS"), ("RUNNING", "FAILED"),
     ("QUEUED", "CANCELLED"), ("RUNNING", "CANCELLED")],
)
def test_legal_transition(source: JobStatus, target: JobStatus) -> None:
    assert can_transition(source, target)

def test_completed_job_cannot_restart() -> None:
    assert not can_transition(JobStatus.COMPLETED, JobStatus.RUNNING)
```

- [x] **Step 2: Run state tests and confirm failure**

Run: `uv run pytest tests/unit/jobs/test_states.py -q`
Expected: FAIL because the transition table is absent.

- [x] **Step 3: Implement compare-and-set transitions and lease claims**

Claim one queued or expired-running job in a short transaction. Store `worker_id`, `lease_expires_at`, `heartbeat_at`, and `attempt`. A live lease cannot be stolen. An expired lease returns to resumable ownership without resetting completed image rows.

- [x] **Step 4: Prove two workers cannot own the same job**

Run: `uv run pytest tests/integration/jobs/test_leases.py -q`
Expected: both concurrent claimers complete, exactly one receives the job, and expired-lease recovery is idempotent.

- [ ] **Step 5: Commit lifecycle and leases**

```powershell
git add src/inspection_platform/jobs tests/unit/jobs tests/integration/jobs
git commit -m "feat(worker): add leased job state machine"
```

### Task 3: Build secure image and archive ingestion with atomic storage

**Files:**
- Create: `src/inspection_platform/storage/__init__.py`
- Create: `src/inspection_platform/storage/paths.py`
- Create: `src/inspection_platform/storage/artifacts.py`
- Create: `src/inspection_platform/ingestion/__init__.py`
- Create: `src/inspection_platform/ingestion/images.py`
- Create: `src/inspection_platform/ingestion/archives.py`
- Create: `src/inspection_platform/ingestion/service.py`
- Test: `tests/unit/ingestion/test_images.py`
- Test: `tests/unit/ingestion/test_archives.py`
- Test: `tests/integration/ingestion/test_service.py`

**Interfaces:**
- Produces `validate_image(stream, limits) -> ValidatedImage`, `iterate_safe_archive(stream, limits)`, `ArtifactStore.put_stream(stream: BinaryIO, media_type: str) -> ArtifactRef`, and `IngestionService.create_job(category: str, uploads: Sequence[UploadStream]) -> JobRead`.
- Accept PNG, JPEG, and WebP only after successful decoder verification and re-open.

- [ ] **Step 1: Write adversarial ingestion tests**

```python
@pytest.mark.parametrize("name", ["../x.png", "/tmp/x.png", "a/../../x.png"])
def test_archive_rejects_path_escape(name: str, archive_factory: ArchiveFactory) -> None:
    with pytest.raises(UnsafeUploadError):
        list(iterate_safe_archive(archive_factory.zip_with(name)))

def test_image_rejects_header_only_spoof() -> None:
    with pytest.raises(InvalidImageError):
        validate_image(BytesIO(b"\x89PNG\r\n\x1a\nnot-an-image"), DEFAULT_LIMITS)
```

- [ ] **Step 2: Run ingestion tests and confirm failure**

Run: `uv run pytest tests/unit/ingestion -q`
Expected: FAIL because validation and storage are absent.

- [ ] **Step 3: Implement bounded streaming, decode verification, and safe archives**

Reject encrypted archives, symlinks, duplicate normalized paths, nested archives, excessive compression ratios, too many files, excessive declared or streamed bytes, and unsupported members. Store files under `sha256[:2]/sha256` using a sibling temporary file, flush/fsync, and atomic replace. Record the browser filename only as escaped display metadata.

- [ ] **Step 4: Make job creation atomic across storage and database references**

If database creation fails, remove only newly created unreferenced temporary artifacts. Never recursively delete a configured root. If two identical images arrive, deduplicate bytes while creating two job image records.

- [ ] **Step 5: Run security and integration tests**

Run: `uv run pytest tests/unit/ingestion tests/integration/ingestion -q`
Expected: all valid image, zip, tar, limit, duplicate, rollback, and deduplication cases pass.

- [ ] **Step 6: Commit secure ingestion**

```powershell
git add src/inspection_platform/storage src/inspection_platform/ingestion tests/unit/ingestion tests/integration/ingestion
git commit -m "feat(ingestion): secure batch image uploads"
```

### Task 4: Load only verified frozen model bundles

**Files:**
- Create: `src/inspection_platform/registry/__init__.py`
- Create: `src/inspection_platform/registry/repository.py`
- Create: `src/inspection_platform/registry/service.py`
- Create: `src/inspection_platform/inference/__init__.py`
- Create: `src/inspection_platform/inference/base.py`
- Create: `src/inspection_platform/inference/anomalib_runtime.py`
- Create: `src/inspection_platform/inference/mock.py`
- Test: `tests/unit/registry/test_registry.py`
- Test: `tests/unit/inference/test_mock.py`
- Test: `tests/integration/inference/test_bundle_loading.py`

**Interfaces:**
- `InferenceRuntime.load(bundle: ModelBundleManifest) -> LoadedModel`.
- `LoadedModel.predict(image: NDArrayUInt8) -> PredictionRecord`.
- `ModelRegistry.activate(category, bundle_id)` verifies every file hash and enforces one active bundle per category. Normal mode accepts only a public-selected frozen champion; explicit demo mode accepts only `runtime_kind="mock"`, `model_family=None`, and `evaluation_scope="synthetic-ci-only"`.

- [ ] **Step 1: Write tampering and compatibility tests**

```python
def test_registry_rejects_tampered_weight(valid_bundle: BundleFixture) -> None:
    valid_bundle.weight.write_bytes(b"tampered")
    with pytest.raises(BundleIntegrityError, match="sha256"):
        registry.register(valid_bundle.manifest_path)

def test_runtime_rejects_prediction_contract_mismatch(valid_bundle: BundleFixture) -> None:
    valid_bundle.manifest.prediction_contract_version = "9.0.0"
    with pytest.raises(IncompatibleBundleError):
        runtime.load(valid_bundle.manifest)
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `uv run pytest tests/unit/registry tests/unit/inference -q`
Expected: FAIL because registry and runtime boundaries do not exist.

- [ ] **Step 3: Implement verification-first registration and a deterministic mock**

The mock runtime must return the same score and anomaly-map dimensions for the same image hash and bundle identity. It exists for CI and public synthetic demos and must label outputs `runtime="mock"`; never imply it is a trained model.

- [ ] **Step 4: Implement the Anomalib serving adapter without training imports in API startup**

Load a bundle lazily in the worker, validate category, preprocessing, threshold, weights, device, and library compatibility before setting it active. Normalize the adapter output into the Plan 01 `PredictionRecord` and preserve raw score before threshold comparison.

- [ ] **Step 5: Verify clean-process loading**

Run: `uv run pytest tests/integration/inference/test_bundle_loading.py -q`
Expected: valid mock and fixture bundles load; tampered, incompatible, wrong-category, and missing-file bundles fail closed.

- [ ] **Step 6: Commit the model-serving boundary**

```powershell
git add src/inspection_platform/registry src/inspection_platform/inference tests/unit/registry tests/unit/inference tests/integration/inference
git commit -m "feat(inference): serve verified champion bundles"
```

### Task 5: Implement the resumable inspection worker

**Files:**
- Create: `src/inspection_platform/worker/__init__.py`
- Create: `src/inspection_platform/worker/heartbeat.py`
- Create: `src/inspection_platform/worker/runner.py`
- Create: `src/inspection_platform/worker/cli.py`
- Test: `tests/unit/worker/test_runner.py`
- Test: `tests/integration/worker/test_recovery.py`

**Interfaces:**
- Produces `WorkerRunner.run_once() -> WorkResult`, `WorkerRunner.serve(stop_event)`, and CLI `inspection-worker serve`.
- One image result is committed only after all referenced artifacts exist and their hashes match.

- [ ] **Step 1: Write idempotency, cancellation, and crash tests**

```python
def test_resume_skips_completed_images(worker_fixture: WorkerFixture) -> None:
    worker_fixture.complete_first_image_then_expire_lease()
    worker_fixture.new_worker.run_once()
    assert worker_fixture.runtime.calls_by_image == {"first": 1, "second": 1}

def test_one_bad_image_yields_partial_completion(worker_fixture: WorkerFixture) -> None:
    worker_fixture.runtime.fail_on("broken")
    result = worker_fixture.worker.run_once()
    assert result.status is JobStatus.COMPLETED_WITH_ERRORS
    assert result.succeeded == 1 and result.failed == 1
```

- [ ] **Step 2: Run worker tests and confirm failure**

Run: `uv run pytest tests/unit/worker -q`
Expected: FAIL because the runner does not exist.

- [ ] **Step 3: Implement per-image atomic inference and heartbeat renewal**

Load the category champion once per job, decode the stored input, predict, render an anomaly map and alpha overlay, write content-addressed artifacts, then insert the prediction record transactionally. Renew the lease on a separate bounded heartbeat loop. Check cancellation between images.

- [ ] **Step 4: Distinguish image failure from job failure**

A corrupt individual input becomes an image-level error and permits `COMPLETED_WITH_ERRORS`. Bundle integrity failure, incompatible runtime, lost lease, or unavailable storage fails the job. Store exception class and a stable error code; do not persist model tracebacks or filesystem paths in public responses.

- [ ] **Step 5: Verify recovery and concurrency**

Run: `uv run pytest tests/unit/worker tests/integration/worker -q`
Expected: crash/restart, expired lease, cancellation, partial completion, and repeated `run_once` tests pass without duplicate predictions.

- [ ] **Step 6: Commit the worker**

```powershell
git add src/inspection_platform/worker tests/unit/worker tests/integration/worker
git commit -m "feat(worker): run resumable batch inference"
```

### Task 6: Expose the typed FastAPI contract

**Files:**
- Create: `apps/api/__init__.py`
- Create: `apps/api/main.py`
- Create: `apps/api/dependencies.py`
- Create: `apps/api/errors.py`
- Create: `apps/api/routes/health.py`
- Create: `apps/api/routes/jobs.py`
- Create: `apps/api/routes/reviews.py`
- Create: `apps/api/routes/models.py`
- Create: `apps/api/schemas.py`
- Test: `tests/api/test_health.py`
- Test: `tests/api/test_jobs.py`
- Test: `tests/api/test_reviews.py`
- Test: `tests/api/test_models.py`

**Interfaces:**
- `POST /api/v1/jobs`, `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}`, `POST /api/v1/jobs/{id}/cancel`.
- `GET /api/v1/jobs/{id}/images/{image_id}`, artifact endpoints, review queue and review mutation endpoints.
- `GET /api/v1/models`, `GET /api/v1/evidence`, `GET /api/health/live`, and `GET /api/health/ready`.

- [ ] **Step 1: Write OpenAPI-facing behavior tests**

```python
def test_create_job_returns_202(client: TestClient, png_bytes: bytes) -> None:
    response = client.post("/api/v1/jobs", files=[("files", ("part.png", png_bytes, "image/png"))], data={"category": "can"})
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"

def test_review_requires_expected_revision(client: TestClient, reviewable_image: ImageRead) -> None:
    response = client.post(
        f"/api/v1/reviews/{reviewable_image.id}",
        json={"decision": "REJECT", "expected_revision": 99},
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run API tests and confirm failure**

Run: `uv run pytest tests/api -q`
Expected: FAIL because the application routes do not exist.

- [ ] **Step 3: Implement routes, pagination, and stable error envelopes**

Use bounded page sizes and structured errors `{code, message, request_id}`. Sanitize incoming request IDs or replace them with generated UUIDs. Artifact endpoints resolve database references and never accept filesystem paths. Health liveness checks process response; readiness checks database, artifact root, and active model manifests but does not load every GPU model.

- [ ] **Step 4: Export and verify the OpenAPI document**

Run: `uv run python scripts/export_openapi.py --output apps/web/openapi.json` after creating the script beside the API work.
Run: `uv run pytest tests/api -q`
Expected: API tests pass and OpenAPI contains the documented v1 routes with no internal path fields.

- [ ] **Step 5: Commit the API**

```powershell
git add apps/api scripts/export_openapi.py apps/web/openapi.json tests/api
git commit -m "feat(api): expose inspection and review workflows"
```

### Task 7: Add human review, reports, audit retention, and metrics

**Files:**
- Create: `src/inspection_platform/reviews/__init__.py`
- Create: `src/inspection_platform/reviews/service.py`
- Create: `src/inspection_platform/reports/__init__.py`
- Create: `src/inspection_platform/reports/schemas.py`
- Create: `src/inspection_platform/reports/builder.py`
- Create: `src/inspection_platform/reports/render.py`
- Create: `src/inspection_platform/observability.py`
- Create: `src/inspection_platform/retention.py`
- Test: `tests/unit/reviews/test_service.py`
- Test: `tests/unit/reports/test_reports.py`
- Test: `tests/unit/test_retention.py`
- Test: `tests/api/test_metrics.py`

**Interfaces:**
- `ReviewService.decide(image_id, decision, note, expected_revision, actor) -> ReviewRead`.
- `ReportBuilder.build(job_id) -> InspectionReport`; deterministic JSON is canonical evidence and CSV/HTML are projections.
- `RetentionService.delete_job(job_id) -> DeletionReceipt` deletes only referenced artifacts after a transactional tombstone.

- [ ] **Step 1: Write review concurrency and report determinism tests**

```python
def test_review_append_only_history_and_revision(review_service: ReviewService) -> None:
    first = review_service.decide(IMAGE_ID, "UNCERTAIN", "needs another look", 0, "local-reviewer")
    second = review_service.decide(IMAGE_ID, "REJECT", "visible scratch", first.revision, "local-reviewer")
    assert second.revision == 2
    assert [x.decision for x in review_service.history(IMAGE_ID)] == ["UNCERTAIN", "REJECT"]

def test_report_json_is_byte_stable(report_builder: ReportBuilder) -> None:
    assert report_builder.render_json(JOB_ID) == report_builder.render_json(JOB_ID)
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `uv run pytest tests/unit/reviews tests/unit/reports -q`
Expected: FAIL because review and report services do not exist.

- [ ] **Step 3: Implement optimistic review revisions and evidence reports**

Include job identity, category, bundle identity/hash, threshold method/value, input hashes, scores, PASS/REVIEW outcomes, artifact hashes, human-review history, runtime identity, and generation timestamp. Escape all display fields in HTML. CSV uses fixed columns and RFC 4180 quoting.

- [ ] **Step 4: Implement bounded metrics and safe retention**

Expose job counts, queue age, image outcomes, inference latency, job duration, worker heartbeat age, and error-code counts. Do not use raw job/image IDs as metric labels. Retention deletes only database-resolved files under the verified artifact root, records a receipt, and is retry-safe.

- [ ] **Step 5: Run report, retention, and metric gates**

Run: `uv run pytest tests/unit/reviews tests/unit/reports tests/unit/test_retention.py tests/api/test_metrics.py -q`
Expected: all tests pass, including XSS strings, CSV formulas, concurrent reviews, missing artifacts, and repeat deletion.

- [ ] **Step 6: Commit product evidence and operations**

```powershell
git add src/inspection_platform/reviews src/inspection_platform/reports src/inspection_platform/observability.py src/inspection_platform/retention.py tests
git commit -m "feat(product): add review and evidence reporting"
```

### Task 8: Verify the backend as one clean system

**Files:**
- Create: `tests/integration/test_backend_workflow.py`
- Create: `scripts/verify_backend.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add an end-to-end backend test using the deterministic mock runtime**

The test creates a mixed batch, lets the worker complete it, records a human review, downloads JSON/CSV/HTML reports, restarts API and worker processes against the same database, and proves state and hashes remain stable.

- [ ] **Step 2: Run all CPU backend tests**

Run: `uv run pytest tests/unit tests/api tests/integration -m "not gpu and not dataset and not slow" --cov=inspection_platform --cov-report=term-missing --cov-fail-under=85`
Expected: PASS with at least 85% project coverage.

- [ ] **Step 3: Run static quality and schema gates**

Run: `uv run ruff format --check .`
Run: `uv run ruff check .`
Run: `uv run mypy src experiments scripts`
Run: `uv run python scripts/verify_backend.py`
Expected: all pass; verifier checks migration head, OpenAPI export freshness, stable error codes, and absence of path fields.

- [ ] **Step 4: Commit backend verification**

```powershell
git add tests/integration/test_backend_workflow.py scripts/verify_backend.py pyproject.toml uv.lock
git commit -m "test(backend): verify durable inspection workflow"
```
