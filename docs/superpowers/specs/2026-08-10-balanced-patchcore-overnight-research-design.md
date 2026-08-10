# Balanced PatchCore Overnight Research Design

**Status:** Approved for autonomous execution

## Context and objective

The public-only 640 x 640 `wallplugs` PatchCore seed-42 probe improved AU-PRO
from 0.5286 to 0.5981 (+0.0695) and pixel AUROC by 0.0166, but image AUROC
fell by 0.0406. Its 22,219 MiB observed training peak is close to the 24 GiB
RTX 4090 limit. The 768 x 768 study already failed with CUDA OOM and will not
be repeated.

The objective is to determine whether the 640 localization gain is reproducible
and whether 576 x 576 offers a better localization/image-level trade-off. This
is exploratory public-only research. It cannot change the frozen champions,
release verdict, or submission state.

## Fixed study

The study is limited to the `wallplugs` PatchCore champion and keeps the frozen
backbone, feature layers, coreset ratio, neighbor count, normalization,
interpolation, batch size, precision, metric implementation, and 256 x 256
evaluation geometry unchanged.

### Stage A: reproduce the 640 x 640 result

- Reuse the completed seed-42 candidate as immutable evidence.
- Run new 640 x 640 candidates at seeds 17 and 2026.
- Compare every candidate with the matching immutable 512 x 512 PatchCore
  baseline for the same seed and evaluation contract.
- Report all three per-seed deltas plus their arithmetic means. Do not hide a
  failed or adverse seed.

Stage A is `REPRODUCIBLE_LOCALIZATION_GAIN` only when all runs complete, mean
AU-PRO delta is at least +0.02, at least two of three AU-PRO deltas are
positive, public evaluation p95 latency is at most 500 ms for every seed, and
the per-image failure rate is zero. It is `MIXED` when at least one seed gains
+0.02 but those aggregate conditions are not met, `NO_CLEAR_GAIN` when neither
rule applies, and `RESOURCE_LIMIT_EXCEEDED` on a run or resource-contract
failure. Image and pixel AUROC remain mandatory reported secondary metrics.

### Stage B: test the 576 x 576 balance point

- Run one 576 x 576 candidate at seed 42.
- Its advance gate requires AU-PRO delta at least +0.02, image AUROC delta no
  worse than -0.01, pixel AUROC delta no worse than -0.005, p95 latency at most
  500 ms, and zero per-image failures.
- Only when that gate passes, run seeds 17 and 2026 at 576 x 576 and compare
  each with its matching 512 x 512 baseline.
- The three-seed result is `BALANCED_PROMISING` only when all runs complete,
  mean AU-PRO delta is at least +0.02, mean image AUROC delta is no worse than
  -0.01, no individual image AUROC delta is worse than -0.03, mean pixel AUROC
  delta is non-negative, every p95 latency is at most 500 ms, and all
  per-image failure rates are zero.
- A completed result that misses the aggregate gate is `MIXED` or
  `NO_CLEAR_GAIN`; a run or resource-contract failure is
  `RESOURCE_LIMIT_EXCEEDED`.

The Stage B advance decision is fixed before observing any 576 result. Failure
to advance is a completed scientific outcome, not a reason to invent another
candidate during the same study.

## Architecture and evidence

A dedicated research module and resumable supervisor entry point will:

1. fail closed unless candidate configs differ from the frozen PatchCore
   baseline only in geometry and the declared seed;
2. bind every run to dataset, source, config, baseline, and evaluation hashes;
3. inspect the shared GPU lease and compute processes before acquiring the
   exclusive lease;
4. execute candidates sequentially in isolated worker processes;
5. evaluate only `test_public` with the existing metric pipeline;
6. preserve checkpoints, raw maps, logs, and image-level records outside Git;
7. atomically checkpoint stage and run state so interruption resumes from the
   latest completed run; and
8. produce one sanitized aggregate report containing identities, aggregate
   metrics, deltas, timings, resource measurements, failures, and the fixed
   verdict.

The new external root must be unique and located under `D:\`; the implementation
plan will select its exact timestamped name. Existing frozen run roots and
committed evidence are read-only.

## Error handling and autonomous continuation

- A candidate failure is captured with sanitized diagnostics and does not erase
  earlier completed evidence.
- Retry only failures already classified as transient by the existing
  supervisor contract. Do not retry deterministic CUDA OOM indefinitely.
- If Stage A fails, still attempt the independent seed-42 Stage B probe when
  the GPU and dataset integrity checks remain healthy.
- If Stage B seed 42 misses its advance gate, record that result and skip its
  replication seeds as designed.
- Stop only for conflicting GPU ownership, dataset or checksum corruption,
  repeated infrastructure failure that prevents trustworthy work, required
  credentials, or an action outside the authorized boundary.

## Testing and verification

Use test-driven development for the study specification, config-difference
guard, conditional Stage B expansion, resumability, classifications, and
sanitized report contract. Before committing reviewed aggregate evidence, run
the focused research tests and the repository's required Python, frontend,
typing, formatting, claims, security, public-boundary, package, Docker, system,
and browser release gates on the exact committed source as required by the
existing plans.

## Authorization boundaries

- Never read or derive decisions from official private metrics, private
  predictions, or private images.
- Do not change or promote a frozen champion in this study.
- Do not create a second MVTec submission.
- Do not push, tag, create a GitHub Release, deploy, or publish a model.
- Only sanitized aggregate public evidence may be committed; all large or raw
  artifacts remain external.

Expected GPU time is approximately 2-3 hours when Stage B stops after seed 42,
or 3-6 hours when all five new candidates run. Full verification may extend
elapsed time to roughly 6-8 hours and is primarily CPU, disk, and Docker work.
