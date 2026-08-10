# High-Resolution PatchCore Research Design

**Status:** Approved for autonomous execution

## Context

The frozen PatchCore configuration uses 512 x 512 inputs. PatchCore is the
selected public champion for `can`, `vial`, `wallplugs`, and `walnuts`, but the
seed-42 public AU-PRO values for `can` and `wallplugs` are only about 0.311 and
0.529. Their completed 512 x 512 training runs took about 25 and 12 minutes on
the current RTX 4090, so they provide a useful bounded test of whether retaining
more spatial detail has enough benefit to justify the added cost.

This is exploratory public-only research. It must not use the official private
score, private images, private predictions, or the remaining submission quota.

## Fixed question

Does changing only PatchCore input and resize geometry from 512 x 512 to
768 x 768 materially improve comparable public AU-PRO for `can` and
`wallplugs` at seed 42?

## Frozen study

- Categories: `can`, `wallplugs`.
- Family and backbone: PatchCore with `wide_resnet50_2`.
- Seed: 42.
- Baseline: the existing completed 512 x 512 screening run for the same
  category, family, seed, dataset manifest, and public evaluation contract.
- Candidate: 768 x 768 input and resize.
- Controlled variables: layers `layer2` and `layer3`, coreset ratio `0.1`, nine
  neighbors, ImageNet normalization, bilinear interpolation, float32 model
  precision, batch size one, and all metric code remain unchanged.
- Evaluation geometry remains 256 x 256 so the candidate is directly
  comparable to the frozen public benchmark.
- Primary metric: public pixel AU-PRO with the repository's frozen FPR limit
  (`0.3`).
- Secondary evidence: public image AUROC, pixel AUROC, GPU p95 latency, peak
  VRAM, checkpoint size, failure rate, and wall-clock run duration.

The category choice was made before observing any 768 x 768 result. `vial` is
already strong at about 0.925 public AU-PRO, while `walnuts` has a substantially
longer 512 x 512 run. Testing the two lower-AU-PRO champions yields more
information per GPU-hour.

## Result classification

Classification is descriptive and cannot change the frozen champions:

- `PROMISING`: neither category loses more than 0.02 AU-PRO and at least one
  gains at least 0.02.
- `MIXED`: at least one category gains at least 0.02 but another loses more
  than 0.02.
- `NO_CLEAR_GAIN`: neither of the preceding rules applies.
- `RESOURCE_LIMIT_EXCEEDED`: any run fails, peak VRAM exceeds 12,288 MiB, GPU
  p95 latency exceeds 500 ms, or per-image failure rate is nonzero.

Even a `PROMISING` result is exploratory. Promotion would require a separately
planned replication at seeds 17 and 2026 plus the normal champion-selection and
release gates.

## Architecture

A dedicated research module will:

1. fail closed unless the candidate config differs from the frozen PatchCore
   config only in the two 768 x 768 geometry fields;
2. construct exactly two hash-identified seed-42 `RunSpec` objects;
3. reuse the existing process-isolated worker, supervisor, resumability,
   checksum contracts, and exclusive GPU lease;
4. evaluate only `test_public` through the existing public metric pipeline;
5. compare against the immutable committed public benchmark; and
6. write an external identity-bound report containing only aggregate public
   metrics, hashes, resource measurements, and run identities.

Raw maps, checkpoints, logs, thresholds, and image-level records remain under a
new external run root. A later sanitized committed report may contain only the
same aggregate public evidence.

## Safety and stop conditions

- Inspect the shared GPU lease and compute-process diagnostic before starting.
- Use `D:\mvtec-ad2-highres-patchcore-20260810` as the new external root.
- Never reuse or mutate the frozen `D:\mvtec-ad2-runs` evidence.
- A normal model or test failure is diagnosed and retried according to the
  existing supervisor rules; it is not a reason to request user input.
- Stop for conflicting GPU ownership, dataset/checksum corruption, an
  unrecoverable resource limit, required credentials, an official upload, or a
  new publication authorization.
- Do not push, tag, release, deploy, publish a model, or submit to MVTec.
