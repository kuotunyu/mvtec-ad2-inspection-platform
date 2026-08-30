# Contributing

Thank you for improving this source-only industrial inspection portfolio. Keep changes focused,
reviewable, and consistent with the repository's evidence boundaries.

## Start here

- Follow [Reproducibility](docs/REPRODUCIBILITY.md) for supported environments and verification.
- Read [Security](docs/SECURITY.md) before changing uploads, archives, paths, logs, or reports.
- Read the [Release checklist](docs/RELEASE_CHECKLIST.md) before changing versions or publication
  surfaces.

Do not duplicate those commands in this file; the linked documents are the sources of truth.

## Change workflow

1. Make one focused change and add the smallest test that proves it.
2. Run the relevant targeted test before the complete required gates.
3. Describe behavior, evidence, and limitations without overstating model quality.
4. Use the pull-request template to record exact verification results and boundary impact.

## Evidence and public boundary

Never commit datasets, weights, checkpoints, raw anomaly scores, private predictions, official raw
responses, credentials, `.env` files, runtime databases, uploads, or private absolute paths.

- Label synthetic fixtures and synthetic results explicitly.
- Keep public aggregate evidence distinct from private evidence.
- Support model-quality claims with committed machine-readable evidence and its contract.
- Preserve the frozen `PRIVATE-NO-GO` conclusion unless separately authorized official evidence
  changes it.
- Treat the MVTec AD 2 dataset and trained artifacts according to their separate non-commercial
  license boundary.
