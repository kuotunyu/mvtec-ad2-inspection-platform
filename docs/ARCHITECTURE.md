# Architecture

The platform separates offline evidence production from online inspection. The only bridge is a versioned, hash-verified contract chain.

![Architecture diagram](assets/architecture.svg)

## Offline plane

The experiment package verifies the official dataset manifest, enforces normal-only training, executes deterministic candidate configurations, computes frozen metrics, selects one champion per category, and emits sanitized aggregate evidence. Real checkpoints and raw predictions remain in external roots.

## Product plane

The React workstation calls a FastAPI boundary for upload, job state, evidence, review, reporting, and deletion. SQLite WAL stores durable state and leases. The worker alone loads model runtimes; it verifies every bundle file before predicting, skips committed image predictions on recovery, and records one terminal audit event.

The artifact store is content-addressed. API paths are identifiers rather than filesystem paths. Explicit deletion resolves database references and unlinks only proven in-root files that are not shared by another job.

## Deployment profiles

- Synthetic CI/demo: deterministic mock bundles and project-generated images; CPU only.
- Local formal serving: external frozen champion bundles on the tested workstation; GPU gate required.
- Public source export: code, aggregate evidence, docs, and synthetic fixtures only.

Docker packages the built frontend with the API and a separate worker. Both run as an unprivileged identity with a read-only root filesystem. The database and artifacts use named volumes; the model registry is an explicit read-only host mount.
