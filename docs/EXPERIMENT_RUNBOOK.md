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

The verifier prints `PASS`, `FAIL`, or `PENDING EXTERNAL SUBMISSION`. A clean
checkout reports `PASS` only when the committed official result is complete and
matches its evidence-manifest hash, or when an explicitly supplied external
local-submission summary passed validation. `PASS` means the evidence contract
is valid; the independent release verdict can still be `PRIVATE-NO-GO`.
Pending remains correct before either form of evidence exists.

## Reproduce the foundation

1. Acquire the official archive into an external data root and build the dataset manifest.
2. Run the CPU smoke and marked GPU smoke for the three frozen adapters.
3. Expand the immutable screening/replication queue and run it through the GPU lease supervisor.
4. Freeze public contenders and champions from the committed evidence reports.
5. Build private and private-mixed bundles only from frozen seed-42 champions. The local official validator must pass before any separately authorized submission.

Resume by reusing the external evidence root and cache. Never delete or overwrite a completed artifact to make a run appear successful. Quarantine incompatible or truncated evidence and investigate the recorded failure.

## Rebuild thresholded private outputs from the frozen cache

Use the cache-only command when continuous private TIFFs already exist and only the validation-calibrated binary PNG tree must be rebuilt:

```powershell
uv run python -m experiments.submission.rebuild `
  --data-root D:\datasets\mvtec-ad-2 `
  --runs-root D:\mvtec-ad2-runs `
  --champions reports\champions.json `
  --source-cache-root D:\mvtec-ad2-submissions-20260807-171623\prediction-cache `
  --output-root D:\mvtec-ad2-submission-thresholded-20260810 `
  --official-utils-root D:\mvtec-ad2-official-utils-20260810\extracted\MVTecAD2_public_code_utils
```

The output root must be new and outside both the repository and source cache. The command verifies the exact frozen seed-42 champion identities, calibrates from hash-bound validation maps, checks every cached TIFF against the source geometry, writes both archive trees, runs the checksum-pinned official validator, and records `LOCAL-PREFLIGHT-NOT-SUBMITTED`. It does not acquire the GPU lease, run inference, or contact the benchmark server.

## Run the fixed high-resolution PatchCore study

The approved public-only study changes only PatchCore input and resize geometry from 512 x 512 to 768 x 768 for `can` and `wallplugs` at seed 42. It uses a new external run root, the shared GPU lease, the frozen public metric pipeline, and never reads or submits private evidence.

```powershell
uv run python -m experiments.high_resolution_patchcore `
  --data-root D:\datasets\mvtec-ad-2 `
  --dataset-manifest D:\datasets\mvtec-ad-2.manifest.json `
  --runs-root D:\mvtec-ad2-highres-patchcore-20260810 `
  --candidate-config experiments\configs\research\patchcore-768.yaml `
  --baseline-public-benchmark reports\public_benchmark.json `
  --gpu-lock D:\.mvtec-ad2-gpu.lock
```

Add `--dry-run` to verify the two run identities without acquiring the GPU lease. Completed runs and public predictions are hash-verified and reused after interruption; incompatible or corrupt evidence fails closed. The aggregate report remains under the external run root until reviewed and sanitized.

## Boundaries

No command in this repository pushes, submits to the MVTec server, uploads to a model hub, or accepts credentials. Official private submission remains an explicit human authorization step.

## Run the resource-informed PatchCore frontier probe

After the 768 x 768 resource-limit result, the fixed frontier study runs only
the 640 x 640 `wallplugs` candidate whose measured 512 x 512 training footprint
leaves a credible fit margin:

```powershell
uv run python -m experiments.patchcore_resolution_frontier `
  --data-root D:\datasets\mvtec-ad-2 `
  --dataset-manifest D:\datasets\mvtec-ad-2.manifest.json `
  --runs-root D:\mvtec-ad2-patchcore-frontier-20260810 `
  --candidate-config experiments\configs\research\patchcore-640.yaml `
  --baseline-public-benchmark reports\public_benchmark.json `
  --gpu-lock D:\.mvtec-ad2-gpu.lock
```

Use `--dry-run` for identity/config/path validation without acquiring the GPU.
The study reads only public data and cannot change frozen champions or submit an
archive.
