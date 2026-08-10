# PatchCore Resolution Frontier Research Design

**Status:** Approved for autonomous execution

## Context and decision

The public-only 768 x 768 PatchCore study failed with CUDA OOM for both `can`
and `wallplugs`. The completed 512 x 512 training records provide a better
resource model than the evaluation-only VRAM metric:

- `can`: 19,873 MiB, giving an estimated 90%-of-24-GiB geometry ceiling near
  534 px;
- `wallplugs`: 14,161 MiB, projecting about 22,127 MiB at 640 px under
  quadratic patch-count scaling.

Another higher-resolution `can` run is therefore predictably wasteful. A
single 640 x 640 `wallplugs` run is the only bounded geometry probe with a
credible chance to fit and a useful quality question: its frozen 512 baseline
has public AU-PRO 0.5286.

## Fixed study

- Category: `wallplugs` only.
- Seed: 42.
- Baseline: the immutable 512 x 512 PatchCore screening run.
- Candidate: 640 x 640 input and resize.
- All other model, preprocessing, metric, and evaluation fields remain exactly
  equal to the frozen PatchCore config; public evaluation remains 256 x 256.
- Primary metric: public AU-PRO delta.
- Secondary metrics: image/pixel AUROC, evaluation VRAM and latency, artifact
  size, failure rate, fit duration, and observed training peak VRAM.
- External root: `D:\mvtec-ad2-patchcore-frontier-20260810`.

The result is `PROMISING` only for an AU-PRO gain of at least 0.02 with public
evaluation VRAM at most 12,288 MiB, p95 latency at most 500 ms, and zero
per-image failures. A smaller change is `NO_CLEAR_GAIN`; a loss below -0.02 is
`REGRESSION`; any run failure or resource breach is
`RESOURCE_LIMIT_EXCEEDED`.

## Boundaries

The runner uses the existing process-isolated supervisor, exclusive GPU lease,
frozen public evaluator, checksums, resumability, and fail-closed evidence
contracts. It must not read official private metrics or predictions, change a
champion, consume another submission, or perform a push/publication action.
Raw outputs stay external; only reviewed aggregate public evidence may later be
committed.
