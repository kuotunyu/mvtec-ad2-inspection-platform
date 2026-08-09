# Remote Setup

This project does not require a remote service for local verification. Keep the repository, official dataset, runtime state, and model artifacts as separate trust zones.

## Clean machine

1. Clone the source repository without copying local runtime folders.
2. Install Python, `uv`, Node/npm, Docker Desktop, and Playwright Chromium.
3. Install dependencies only from `uv.lock` and `apps/web/package-lock.json`.
4. Build a synthetic registry into an external directory and set `INSPECTION_MODEL_ROOT` to it.
5. Run the public-boundary, security, CPU, frontend, Docker, and system gates from [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Formal workstation

Place the licensed dataset, run evidence, checkpoints, champion bundles, SQLite runtime database, uploads, and generated reports outside the checkout. Verify the dataset and bundle hashes before acquiring the project GPU lease. Never copy MVTec images or real model files into the Docker build context.

## Optional hosting or artifact publication

No deployment, Hugging Face upload, Git push, tag, Release, PR, or official MVTec submission is performed by setup scripts. Those actions require a separate explicit authorization and, where applicable, credentials. Any public model artifact must use a pinned immutable revision, carry its own license/provenance statement, and preserve the non-commercial dataset boundary.

## Official private handoff

The frozen external upload is `private_submission.tar.gz` with SHA-256 `25780c9e0c0a234454fa2e6a9a7d75f274d27d0434ad089549e19b0b0906ffb9`. It combines `test_private` and `test_private_mixed` for the eight identically named official categories and passed the local official validator. Official submission performed: Yes, exactly once. No second submission was performed.

No retuning is allowed after submission. Raw official evidence remains outside Git; the reviewed sanitized aggregate is [official-private-result.json](assets/evidence/official-private-result.json). The result is `PRIVATE-NO-GO`, and the complete release gates must remain green before any separately authorized publication action. See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for the evidence and publication boundary.
