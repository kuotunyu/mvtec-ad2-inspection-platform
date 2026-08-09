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
