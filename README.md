# MVTec AD 2 Industrial Inspection Platform

![Synthetic inspection workstation showing anomaly evidence and human review](docs/assets/screenshots/job-evidence.webp)

A local-first industrial anomaly-inspection workstation that turns frozen benchmark evidence into a resumable batch, visual review, and auditable human-decision workflow.

The public portfolio proves three things without redistributing MVTec data: **8 category-specific champions** <!-- claim:8|reports/champions.json|/champions|len --> selected from **56 formal public runs** <!-- claim:56|reports/public_benchmark.json|/runs|len -->, an end-to-end product exercised with visibly synthetic fixtures, and fail-closed boundaries around model identity, uploads, recovery, reports, and deletion. Official submission not performed.

## Product workflow

![Synthetic batch-to-review workflow](docs/assets/workflow.svg)

An operator selects a category and submits a batch. Valid images continue even when another image is corrupt. A dedicated leased worker verifies the selected bundle before inference, stores model evidence as `PASS` or `REVIEW`, and resumes idempotently after an expired lease. A human owns final disposition and every report preserves model and human decisions separately.

The screenshots in this repository are generated only from `fixtures/public-demo`; they contain no MVTec pixels and do not imply production deployment.

## Evidence, not a leaderboard claim

- The frozen champion matrix is in [reports/champions.json](reports/champions.json), with its readable summary in [reports/benchmark.md](reports/benchmark.md).
- Public selection uses image AUROC, pixel AU-PRO, confidence intervals, latency, VRAM, and artifact size under the approved metric contract.
- Per-category winners are PatchCore for `can`, `vial`, `wallplugs`, and `walnuts`; Dinomaly for `fabric`, `fruit_jelly`, `rice`, and `sheet_metal`.
- EfficientAD remains a benchmarked candidate, not a selected champion.
- Private predictions passed the official local validator, but no authenticated server submission has been made. The public status therefore remains a local release candidate, never an official private score.

## Architecture

![Local architecture with React, FastAPI, SQLite, worker, artifact store, and verified registry](docs/assets/architecture.svg)

The API never imports training orchestration at startup. Runtime databases, uploads, artifacts, datasets, checkpoints, and real model bundles live outside Git. Docker uses digest-pinned multi-stage images, a read-only root filesystem, an unprivileged user, persistent runtime volumes, and a read-only model mount.

See [Architecture](docs/ARCHITECTURE.md), [Case study](docs/CASE_STUDY.md), [Model card](docs/MODEL_CARD.md), [Data card](docs/DATA_CARD.md), [Security](docs/SECURITY.md), and [Limitations](docs/LIMITATIONS.md).

## Run the synthetic local demo

Prerequisites are Python, `uv`, Node/npm, Docker Desktop, and a Chromium browser installed for Playwright.

```powershell
uv sync --extra ml --frozen
Push-Location apps/web
npm ci
npx playwright install chromium
Pop-Location

$env:INSPECTION_MODEL_ROOT = "D:\mvtec-ad2-demo-models"
uv run python scripts/build_demo_bundle.py --output $env:INSPECTION_MODEL_ROOT
docker compose up -d --build --wait
```

Open `http://127.0.0.1:8000`. Stop the local services with `docker compose down`; add `--volumes` only when you intentionally want to remove that Compose project's demo database and artifacts.

For exact verification and real-model preparation, follow [Reproducibility](docs/REPRODUCIBILITY.md) and [Remote setup](docs/REMOTE_SETUP.md). No command in those guides pushes, publishes, uploads, or submits by itself.

## Decision semantics

`PASS` means the frozen model score is below its recorded threshold. `REVIEW` means the evidence should be examined by a person. Neither term is a defect type, a root cause, or an automatic reject decision.

## License boundaries

Project source code is available under the [MIT License](LICENSE). MVTec AD 2 data is separately licensed CC BY-NC-SA 4.0 and is not redistributed. Model artifacts trained from that data are treated as research/non-commercial portfolio artifacts; consult [MODEL_CARD.md](docs/MODEL_CARD.md) before any reuse.
