# Experiment Runbook

This repository records the reproducible MVTec AD 2 foundation workflow. Keep the dataset, checkpoints, predictions, leases, and submission archives outside Git.

All commands below use explicit environment variables for licensed data and runtime artifacts. Set each referenced variable to an absolute path outside the checkout before running a study; the repository does not assume a workstation drive letter or create a private-data root inside Git.

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
  --data-root $env:MVTECAD2_DATA_ROOT `
  --runs-root $env:MVTECAD2_RUNS_ROOT `
  --champions reports\champions.json `
  --source-cache-root $env:MVTECAD2_PREDICTION_CACHE_ROOT `
  --output-root $env:MVTECAD2_SUBMISSION_OUTPUT_ROOT `
  --official-utils-root $env:MVTECAD2_OFFICIAL_UTILS_ROOT
```

The output root must be new and outside both the repository and source cache. The command verifies the exact frozen seed-42 champion identities, calibrates from hash-bound validation maps, checks every cached TIFF against the source geometry, writes both archive trees, runs the checksum-pinned official validator, and records `LOCAL-PREFLIGHT-NOT-SUBMITTED`. It does not acquire the GPU lease, run inference, or contact the benchmark server.

## Run the fixed high-resolution PatchCore study

The approved public-only study changes only PatchCore input and resize geometry from 512 x 512 to 768 x 768 for `can` and `wallplugs` at seed 42. It uses a new external run root, the shared GPU lease, the frozen public metric pipeline, and never reads or submits private evidence.

```powershell
uv run python -m experiments.high_resolution_patchcore `
  --data-root $env:MVTECAD2_DATA_ROOT `
  --dataset-manifest $env:MVTECAD2_DATASET_MANIFEST `
  --runs-root $env:MVTECAD2_HIGHRES_RUNS_ROOT `
  --candidate-config experiments\configs\research\patchcore-768.yaml `
  --baseline-public-benchmark reports\public_benchmark.json `
  --gpu-lock $env:MVTECAD2_GPU_LOCK
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
  --data-root $env:MVTECAD2_DATA_ROOT `
  --dataset-manifest $env:MVTECAD2_DATASET_MANIFEST `
  --runs-root $env:MVTECAD2_FRONTIER_RUNS_ROOT `
  --candidate-config experiments\configs\research\patchcore-640.yaml `
  --baseline-public-benchmark reports\public_benchmark.json `
  --gpu-lock $env:MVTECAD2_GPU_LOCK
```

Use `--dry-run` for identity/config/path validation without acquiring the GPU.
The study reads only public data and cannot change frozen champions or submit an
archive.

## Run the balanced PatchCore overnight study

The fixed public-only follow-up reproduces 640 x 640 `wallplugs` at seeds 17
and 2026, then runs the 576 x 576 seed-42 balance probe. Seeds 17 and 2026 at
576 x 576 run only when the committed seed-42 gate passes:

```powershell
uv run python -m experiments.balanced_patchcore_study `
  --data-root $env:MVTECAD2_DATA_ROOT `
  --dataset-manifest $env:MVTECAD2_DATASET_MANIFEST `
  --runs-root $env:MVTECAD2_BALANCED_RUNS_ROOT `
  --config-640 experiments\configs\research\patchcore-640.yaml `
  --config-576 experiments\configs\research\patchcore-576.yaml `
  --gpu-lock $env:MVTECAD2_GPU_LOCK
```

Use `--dry-run` first. Rerunning the identical formal command resumes verified
completed identities. Raw evidence stays under the external root; the command
does not read private evidence, submit, push, tag, release, deploy, or publish.

## Run the memory-bounded PatchCore study

The fixed public-only ladder tests 640 x 640 PatchCore with a 0.01 coreset at
seed 42 first. It tries the 0.02 rescue only after a resource-safe quality miss,
and replicates seeds 17 and 2026 only for the first ratio that passes the frozen
seed-42 gate. A child-only resource guard may stop this command's worker after
three consecutive unsafe samples; it never terminates an unrelated process.

```powershell
uv run python -m experiments.memory_bounded_patchcore `
  --data-root $env:MVTECAD2_DATA_ROOT `
  --dataset-manifest $env:MVTECAD2_DATASET_MANIFEST `
  --runs-root $env:MVTECAD2_MEMORY_BOUNDED_RUNS_ROOT `
  --config-001 experiments\configs\research\patchcore-640-coreset-001.yaml `
  --config-002 experiments\configs\research\patchcore-640-coreset-002.yaml `
  --gpu-lock $env:MVTECAD2_GPU_LOCK
```

Run the identical command with `--dry-run` first to validate source, dataset,
config, reference, and ordered run identities without creating the run root or
acquiring the GPU lease. After interruption, resume only with the identical
formal command; completed identities are hash-verified and reused. Raw outputs
remain under the external root. The study cannot change frozen champions or
read private evidence, submit, push, tag, release, deploy, or publish.

## Complete the high-resolution study on a cloud GPU

The fixed 768 x 768 study exhausted the local 24 GiB GPU during coreset fitting.
In Anomalib 2.5, PatchCore holds every training embedding on the device and then
concatenates the store into a memory bank, so the training peak is about twice
the embedding total. That is roughly 46 GB for `can` and 33 GB for `wallplugs`
at 768 x 768, which needs a GPU with at least 60 GB.

[`notebooks/colab_high_resolution_patchcore.ipynb`](../notebooks/colab_high_resolution_patchcore.ipynb)
runs the identical unmodified study on such a GPU. It refuses to continue unless
the device reports at least 60,000 MiB, the cloned worktree is clean, the staged
dataset manifest matches the frozen digest, and a subprocess confirms that torch
sees the GPU. Torch is never imported in the notebook kernel, because the GPU
lease treats any other CUDA-holding Python process as a conflict.

Only `train/good`, `validation/good`, and `test_public` are staged. The private
splits are never read by this study and must not be copied to cloud storage.

Regenerate the notebook from its source of truth after editing the generator,
and verify that the committed copy is current:

```powershell
uv run python scripts/build_study_notebook.py
uv run python scripts/build_study_notebook.py --check
```

After the run, record the hardware provenance beside the study report. The
sidecar binds the report's canonical digest to the GPU identity and the
per-category training peak, and it refuses to write any filesystem path:

```powershell
uv run python scripts/capture_study_environment.py `
  --study-report $env:MVTECAD2_HIGHRES_RUNS_ROOT\evidence\high-resolution-patchcore.json `
  --runs-root $env:MVTECAD2_HIGHRES_RUNS_ROOT `
  --output $env:MVTECAD2_HIGHRES_RUNS_ROOT\evidence\cloud-environment.json
```

Quality deltas for AU-PRO, image AUROC, and pixel AUROC are deterministic and
remain comparable with the frozen 512 x 512 baseline. Latency and VRAM recorded
by a cloud run describe different hardware from every other performance figure
in this repository and must not be compared with the RTX 4090 baseline.
