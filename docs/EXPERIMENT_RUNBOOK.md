# Experiment Runbook

This repository records the reproducible MVTec AD 2 foundation workflow. Keep the dataset, checkpoints, predictions, leases, and submission archives outside Git.

## Verify a checkout

```powershell
uv run python scripts/verify_experiments.py
uv run pytest -m "not gpu and not dataset" -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src experiments scripts
```

The verifier prints `PASS`, `FAIL`, or `PENDING EXTERNAL SUBMISSION`. The pending state is correct until an authorized official server result exists; it is never converted to success automatically.

## Reproduce the foundation

1. Acquire the official archive into an external data root and build the dataset manifest.
2. Run the CPU smoke and marked GPU smoke for the three frozen adapters.
3. Expand the immutable screening/replication queue and run it through the GPU lease supervisor.
4. Freeze public contenders and champions from the committed evidence reports.
5. Build private and private-mixed bundles only from frozen seed-42 champions. The local official validator must pass before any separately authorized submission.

Resume by reusing the external evidence root and cache. Never delete or overwrite a completed artifact to make a run appear successful. Quarantine incompatible or truncated evidence and investigate the recorded failure.

## Boundaries

No command in this repository pushes, submits to the MVTec server, uploads to a model hub, or accepts credentials. Official private submission remains an explicit human authorization step.
