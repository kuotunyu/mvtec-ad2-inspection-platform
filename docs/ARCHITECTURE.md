# Architecture

The platform separates offline evidence production from online inspection. The only bridge is a versioned, hash-verified contract chain.

![Architecture diagram](assets/architecture.svg)

## Offline plane

The experiment package verifies the official dataset manifest, enforces normal-only training, executes deterministic candidate configurations, computes frozen metrics, selects one champion per category, and emits sanitized aggregate evidence. Real checkpoints and raw predictions remain in external roots.

## Product plane

The React workstation calls a FastAPI boundary for upload, job state, evidence, review, reporting, and deletion. SQLite WAL stores durable state, worker liveness, and leases. Ingestion commits the job, audit row, images, and initial image errors in one transaction, so workers never observe a partially registered batch. The worker alone loads model runtimes; it verifies every bundle file before predicting, renews ownership from a separate heartbeat thread during long inference, skips committed image predictions on recovery, and records one terminal audit event.

Each successful image transaction records the score, frozen threshold, decision, bundle identity, raw-map hash, display anomaly-map hash, overlay hash, and distinct database-resolved `source`, `anomaly-map`, and `overlay` routes. The artifact store is content-addressed. A reentrant cross-process store lock is held from blob publication through its database commit and by every physical unlink; reusing an existing digest also refreshes its retention reservation. API paths are identifiers rather than filesystem paths. Explicit or scheduled retention resolves database references and unlinks only proven in-root files that are not shared by another active job.

The system-status API derives queue, review, error, and worker heartbeat state from durable records; unavailable state stays unknown in the frontend instead of becoming a synthetic zero. Atomic claims plus worker, attempt-generation, state, and unexpired-lease fences guard every prediction publication and terminal transition. Prediction, review revision, and audit dedupe constraints enforce idempotency at the database boundary, not only in worker control flow. Application startup upgrades recognized legacy schemas through Alembic, reconciles duplicate prediction evidence, preserves conflicting review history by assigning deterministic revisions, backfills audit idempotency keys, and refuses unknown partial schemas.

## Deployment profiles

- Synthetic CI/demo: deterministic mock bundles and project-generated images; CPU only.
- Local formal serving: external frozen champion bundles on the tested workstation; GPU gate required.
- Public source export: code, aggregate evidence, docs, and synthetic fixtures only.

Docker packages the built frontend with the API and a separate worker. Both run as an unprivileged identity with a read-only root filesystem. The database and artifacts use named volumes; the model registry is an explicit read-only host mount. Multipart parsing and validated-upload staging share a dedicated disk-backed spool volume through `TMPDIR` and `INSPECTION_SPOOL_ROOT`, while the unrelated container `/tmp` remains a small tmpfs. API startup requires free spool capacity for two maximum-size request copies plus one maximum image, so the declared upload contract cannot silently exceed container storage. `compose.yaml` is the CPU synthetic profile. `compose.gpu.yaml` replaces only the worker build with the ML extra, sets `cuda:0`, and requests the NVIDIA runtime for formal local serving.
