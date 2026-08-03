# MVTec AD 2 Inspection Platform Design

Date: 2026-08-04  
Status: Approved design  
Repository: `mvtec-ad2-inspection-platform`

## 1. Objective

Build a product-oriented, single-workstation industrial anomaly-inspection system backed by a reproducible MVTec AD 2 benchmark. A quality engineer submits a batch of product images, receives anomaly scores and localized heatmaps, reviews uncertain items, and exports an auditable report. The benchmark determines which model is deployed for each product category and supplies the evidence behind every public claim.

The primary portfolio targets are Computer Vision Engineer, Machine Learning Engineer, and AI Engineer roles. The differentiator is not another model-training notebook: it is the integration of unknown-defect detection, human review, model governance, resumable GPU experiments, operational evidence, and honest distribution-shift validation.

## 2. Product Boundary

### 2.1 Primary workflow

1. The operator selects one of the eight MVTec AD 2 product categories.
2. The operator uploads PNG/JPEG images or a ZIP archive, or creates an inspection job through the REST API.
3. The service validates and hashes every input, persists the job, and returns immediately.
4. A dedicated worker leases the job and loads the category's frozen champion model.
5. For each valid image, the worker records an anomaly score, anomaly map, overlay, threshold, decision, model version, latency, and evidence hashes.
6. The system emits only `PASS` or `REVIEW`. It never converts an anomaly score directly into a final production rejection.
7. A human reviewer records `ACCEPT`, `REJECT`, or `UNCERTAIN`, plus a reason and optional note.
8. The system exports machine-readable JSON/CSV and a self-contained HTML inspection report.

### 2.2 Explicit non-goals for v1

- Live cameras, video streaming, PLC integration, and claims of real production-line operation.
- Multi-tenancy, enterprise identity, role-based access control, or cloud orchestration.
- Kubernetes, Redis, Celery, or a distributed multi-GPU scheduler.
- LLM-generated inspection conclusions.
- Automatic final reject decisions.
- Commercial-use claims, safety certification, or claims that MVTec performance transfers to a real factory without validation.

## 3. Dataset Acquisition and Governance

### 3.1 Source and integrity

The implementation must use the official MVTec-hosted archive referenced by the upstream Anomalib MVTecAD2 datamodule, not a third-party mirror.

- Archive: `mvtec_ad_2.tar.gz`
- Official archive URL: `https://www.mydrive.ch/shares/150997/701c90d3aea6588f404936e32a674602/download/466712769-1743429042/mvtec_ad_2.tar.gz`
- Expected size: `32,739,596,982` bytes
- SHA-256: `c0ded99ef32bfc8e352d52beb44515e5b292b8598cb963aadfa91ca0763505e4`
- License: CC BY-NC-SA 4.0
- Categories: `can`, `fabric`, `fruit_jelly`, `rice`, `sheet_metal`, `vial`, `wallplugs`, `walnuts`

The downloader must support resumption, verify the exact byte count and SHA-256 before extraction, extract into a directory outside Git, and generate a versioned manifest containing archive provenance, category counts, split counts, extensions, and file hashes required to reproduce an experiment.

### 3.2 Split policy

- `train/good`: model fitting only.
- `validation/good`: preprocessing calibration, conformal threshold calibration, and operational false-review estimation.
- `test_public`: one controlled local comparison after configurations are frozen.
- `test_private`: official hidden-label evaluation after champion selection.
- `test_private_mixed`: official hidden-label lighting-shift evaluation after champion selection.

No public or private test output may influence training, preprocessing, threshold calibration, or hyperparameter selection. Public test results may select a champion from already-frozen candidates. Once selected, the registry is frozen before private submissions are generated.

### 3.3 Public boundary

Raw MVTec images, complete derived image collections, private predictions, and dataset archives must never enter Git or a public Hugging Face repository. Clean-clone tests use deterministic synthetic inspection images. Public qualitative UI fixtures are synthetic. Aggregate benchmark tables and official server summaries may be published if their terms allow it.

## 4. System Architecture

The deployment model is a single GPU inspection workstation.

### 4.1 Components

- **React and TypeScript frontend**: dashboard, batch submission, job detail, review queue, and model-evidence views.
- **FastAPI service**: REST API, upload validation, job/review operations, report access, health, readiness, and metrics.
- **SQLite in WAL mode**: jobs, images, reviews, model registry, leases, and append-only audit events.
- **Dedicated inspection worker**: one formal GPU job at a time, lease and heartbeat recovery, image-level failure isolation, and idempotent resume.
- **Filesystem artifact store**: uploaded images, normalized inputs, anomaly maps, overlays, reports, checkpoints, and run evidence, partitioned by immutable identifiers.
- **Model registry**: per-category champion, model family, artifact revision, SHA-256, dataset/config/code hashes, threshold, and validation evidence.
- **Hugging Face artifact source**: optional public model artifacts at pinned revisions; raw data is excluded.

The benchmark/training package and the serving package share typed artifact contracts but remain independent. The product must be able to load a frozen model bundle without importing the training orchestration code.

### 4.2 Job state machine

Allowed states are:

`QUEUED -> RUNNING -> COMPLETED | COMPLETED_WITH_ERRORS | FAILED | CANCELLED`

Workers acquire time-limited leases and refresh a heartbeat. An expired lease returns an unfinished job to the queue. Completed image records are immutable and skipped during resume when all input, model, config, and output hashes match. A failure in one image does not discard successful results from the rest of the batch.

### 4.3 Runtime profiles

- **Local GPU profile**: formal training, benchmarking, and RTX 4090 inference.
- **Docker CPU review profile**: clean-clone product demonstration using synthetic fixtures and a verified downloadable model artifact or deterministic mock when network access is disabled.
- **CI profile**: unit, integration, frontend, security, contract, and container smoke tests without MVTec data or a GPU.

## 5. Model and Benchmark Design

### 5.1 Candidate families

The benchmark compares exactly three complementary Anomalib 2.5.0 model families:

- **PatchCore**: memory-bank baseline and localization reference.
- **EfficientAD**: latency and deployment candidate.
- **Dinomaly**: DINOv2 feature-reconstruction quality candidate.

The implementation may correct a verified compatibility defect, but it may not silently replace a model family or change its evaluation contract after observing test results. Every justified deviation is recorded in the experiment registry.

### 5.2 Experiment stages

1. Run one tiny GPU smoke test per model on `sheet_metal`.
2. Freeze dataset, preprocessing, training, calibration, and metric contracts.
3. Run all three models across all eight categories with seed `42`.
4. Select the two leading contenders independently for each category using the predeclared public-test comparison. A model that is weak on the macro average is not eliminated from a category where it performs well.
5. Run each category's two contenders with seeds `17`, `42`, and `2026`.
6. Compute category-level and macro results with bootstrap 95% confidence intervals.
7. Select and freeze one champion per category.
8. Generate official-format predictions for `test_private` and `test_private_mixed`.
9. Submit once the user supplies the required official evaluation-server interaction.

The `42` contender run from stage 3 is reused in stage 5 when its artifacts and hashes are valid. It is not retrained merely to inflate run counts.

### 5.3 Metrics

Quality metrics:

- Image-level AUROC and AUPR.
- Pixel-level AU-PRO integrated to false-positive rate 0.30.
- Pixel-level AUROC and AUPR.
- Per-category values, macro means, and bootstrap 95% confidence intervals.

Operating-point metrics:

- Validation-normal false-review rate.
- Public-normal false-review rate.
- Public anomaly recall, precision, and F1.
- Expected review count per 1,000 normal images.

Engineering metrics:

- GPU and CPU latency p50/p95.
- Throughput at batch size 1 and the product's bounded batch setting.
- Cold-start time, peak VRAM, artifact size, and per-image failure rate.

### 5.4 Threshold policy

Each model/category threshold is calibrated only on the normal validation set using a finite-sample conformal upper quantile targeting a nominal 1% false-review rate. The artifact records the calibration sample count, quantile rule, achieved validation rate, and warning that coverage is not guaranteed under distribution shift.

For `n` validation scores and `alpha = 0.01`, sort scores in ascending order and use order statistic `k = min(n, ceil((n + 1) * (1 - alpha)))` as the threshold. Ties at the threshold map to `REVIEW`. Any change to this formula creates a new threshold-policy version and invalidates earlier model bundles.

The product maps scores below the frozen threshold to `PASS` and scores at or above it to `REVIEW`. Thresholds are versioned registry fields, not mutable UI preferences. A reviewer may explore alternate thresholds in an analysis view, but exploratory values cannot overwrite the production registry.

### 5.5 Champion selection

Champion selection is lexicographic and auditable, not an opaque weighted score:

1. Rank by pixel AU-PRO on the frozen public run.
2. Compare each challenger with the leading candidate using a paired bootstrap 95% confidence interval for the AU-PRO difference. If the interval excludes zero, retain the higher-AU-PRO model; if it includes zero, treat localization quality as unresolved.
3. When localization quality is unresolved, apply the same paired-bootstrap rule to image AUROC.
4. If image quality is also unresolved, prefer lower GPU p95 latency measured by the frozen benchmark contract.
5. If GPU p95 latency differs by less than 5%, prefer lower peak VRAM; if peak VRAM differs by less than 5%, prefer the smaller serialized artifact.
6. Select independently per category.

Private results validate the frozen selection; they never select it. A material lighting-shift failure produces an explicit `NO-GO under lighting shift` limitation rather than post-hoc tuning or result removal.

## 6. Unattended GPU Supervisor

Formal runs execute sequentially under a resumable supervisor.

- Acquire an exclusive project GPU lock and check for known compute workloads without treating ordinary desktop graphics processes as conflicts.
- Run one atomic model/category/seed unit at a time.
- Record code SHA, config hash, dataset manifest hash, environment lock, model revision, timestamps, latency, VRAM, and exit status.
- Emit JSONL heartbeat records with progress, GPU utilization, peak memory, temperature, free disk, and current checkpoint.
- Skip completed units only when their full evidence contract matches.
- Resume supported model checkpoints; never overwrite an incompatible run directory.
- Permit one predefined batch-size reduction after a verified OOM. A second OOM fails that unit.
- Stop on checksum mismatch, NaN/Inf, corrupt artifact, invalid metric shape, insufficient disk, or repeated OOM.
- Do not change model, resolution, threshold, seed, or evaluation rules in response to disappointing test results.
- A 12-hour window is an observation interval, not a forced termination. The supervisor may continue beyond it or stop gracefully after an atomic unit.

## 7. Product Interface

### 7.1 Screens

1. **Dashboard**: recent jobs, PASS/REVIEW counts, pending reviews, failures, active model versions, and latency summaries.
2. **New Inspection**: category, batch name, drag-and-drop images/ZIP, validation feedback, and job creation.
3. **Job Detail**: progress, filterable image gallery, score, threshold, heatmap, overlay, model evidence, and errors.
4. **Review Queue**: keyboard-efficient review of flagged images with `ACCEPT`, `REJECT`, `UNCERTAIN`, reason, and note.
5. **Model & Evidence**: per-category champion, candidate comparison, confidence intervals, latency/VRAM/artifact data, hashes, and official-evaluation state.

The visual language is a restrained industrial workstation, not a chat interface or a generic neon AI dashboard. Desktop is primary; the core workflow must remain usable at 1280-pixel width and tablet width. Status cannot rely on red/green color alone.

### 7.2 Reports

Every report includes batch identity, timestamps, category, model bundle and hashes, threshold policy, per-image result, review decision, errors, aggregate counts, latency summary, and limitations. JSON is the canonical representation. CSV and HTML are deterministic renderings of the same versioned schema.

## 8. Security, Retention, and Observability

- Decode and validate image content; do not trust extensions or MIME headers alone.
- Generate server-side filenames and reject path traversal, archive bombs, unsupported formats, excessive dimensions, and configured size/count limits.
- Hash inputs for provenance and duplicate detection.
- Keep runtime artifacts outside the source tree.
- Default upload retention is seven days; explicit deletion removes the batch's runtime files and records an audit tombstone.
- Structured logs contain identifiers, shapes, timings, statuses, and error types, not image bytes or extracted content.
- Expose distinct liveness, readiness, and Prometheus-compatible metrics endpoints.
- Record queue depth, job and image outcomes, latency, worker heartbeat, model loads, and GPU memory.
- Reject model bundles whose revision, checksum, schema, preprocessing, or threshold metadata does not match the registry.

## 9. Verification Strategy

### 9.1 Automated tests

- Unit tests for validation, state machines, leases, threshold calibration, manifests, registry contracts, and reports.
- ML-integrity tests for normal-only training, split isolation, mask alignment, deterministic configs, and metric parity with official utilities.
- API integration tests for upload, lifecycle, retry, cancel, review, report, and deletion flows.
- Failure-injection tests for worker crashes, expired leases, duplicate jobs, corrupt model bundles, partial batches, malicious archives, and disk errors.
- Frontend component tests for loading, empty, partial-error, and completed states.
- Playwright end-to-end coverage of submit, inspect, review, and export.
- Clean source-export and Docker CPU smoke tests.
- GPU smoke, full benchmark, and model-bundle inference parity gates outside CI.

### 9.2 Claim verification

README tables and model-evidence UI must be generated or verified against committed machine-readable aggregate artifacts. Approximate metrics, manually copied headline numbers, unverifiable speed claims, and private raw predictions fail the release verifier.

## 10. Release and Publication

### 10.1 Release states

**Local Release Candidate** requires:

- Dataset integrity and public-boundary checks.
- Frozen public benchmark and champion registry.
- Real-model local product flow.
- Synthetic clean-clone Docker flow.
- Backend, frontend, end-to-end, security, packaging, and documentation gates.
- Clean worktree and reproducible evidence bundles.

**v1.0 Release-ready** additionally requires:

- Official `test_private` and `test_private_mixed` evaluation.
- Public claims synchronized to official results.
- Explicit `NO-GO` disclosure for any material lighting-shift failure.

### 10.2 Licensing and repositories

Project source code and model artifacts have separate license statements. Public model cards state that training used CC BY-NC-SA 4.0 MVTec AD 2 data and limit the artifact to research/non-commercial portfolio use. The project does not claim that a model trained on MVTec data is commercially deployable.

The implementation session may create local commits authored and committed by `kuotunyu <61350295+kuotunyu@users.noreply.github.com>`. It must not create or modify GitHub repositories, Hugging Face repositories, tags, releases, or official benchmark submissions without explicit user authorization.

## 11. Planned Repository Boundaries

```text
apps/
  api/                 FastAPI routes and service composition
  web/                 React and TypeScript workstation
src/inspection_platform/
  contracts/           Versioned schemas shared across subsystems
  ingestion/           Upload and archive validation
  jobs/                State machine, leases, and orchestration
  inference/           Serving-only model interface
  registry/            Frozen model bundle resolution
  reviews/             Human decisions and audit events
  reports/             JSON canonical report and renderers
experiments/
  configs/             Frozen model/category/seed configurations
  data/                Downloader and dataset manifest logic
  metrics/             Official-compatible evaluation and bootstrap
  orchestration/       Resumable unattended supervisor
  submission/          Official-format private prediction bundles
deploy/
  docker/              CPU review profile
docs/
  architecture/        System and experiment documentation
  assets/              Synthetic UI media and aggregate charts
  superpowers/specs/   Approved designs
tests/
  unit/ integration/ ml_integrity/ e2e/ security/
```

Training dependencies must not leak into the CPU product image. Large data, weights, uploads, checkpoints, and runtime outputs live outside the repository and are guarded by both ignore rules and automated tracked-file scans.

## 12. Implementation Authority and Stop Conditions

After the implementation plan is approved, the implementation session may scaffold the repository, download and verify the official dataset outside Git, install pinned dependencies, implement and test the system, create local commits, and start formal GPU work only after all smoke gates pass and the RTX 4090 is not occupied by another formal workload.

It must stop and report rather than improvise when:

- Official source integrity cannot be verified.
- A license or external-service term blocks the intended publication.
- Official benchmark access requires user identity or authentication.
- A design change would alter the research question, split policy, model families, release gates, or public scope.
- Existing unrecognized user work overlaps the new repository.

## 13. Success Criteria

The repository succeeds when a reviewer can:

1. Understand the product and research question from the first README screen.
2. Run CI-equivalent tests and a synthetic CPU product flow from a clean source export.
3. Inspect machine-readable evidence for every metric and public claim.
4. Reproduce dataset acquisition and formal experiments with resumable commands.
5. See why each category's champion was selected and what trade-offs were accepted.
6. Complete a real batch inspection and human-review workflow using a frozen model bundle.
7. Distinguish local public evidence from official private and lighting-shift evidence.
8. See explicit limitations rather than inflated production or commercial claims.

## 14. Primary Sources

- MVTec AD 2 dataset and license: <https://www.mvtec.com/research-teaching/datasets/mvtec-ad-2>
- MVTec AD 2 paper: <https://arxiv.org/abs/2503.21622>
- MVTec evaluation server: <https://benchmark.mvtec.com/>
- Anomalib project: <https://github.com/open-edge-platform/anomalib>
- Anomalib MVTecAD2 datamodule: <https://github.com/open-edge-platform/anomalib/blob/main/src/anomalib/data/datamodules/image/mvtecad2.py>
- PatchCore reference: <https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/patchcore.html>
- EfficientAD reference: <https://anomalib.readthedocs.io/en/stable/markdown/guides/reference/models/image/efficient_ad.html>
- Dinomaly reference: <https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/dinomaly.html>
