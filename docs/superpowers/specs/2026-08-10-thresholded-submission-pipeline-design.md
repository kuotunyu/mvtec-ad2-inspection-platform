# Thresholded Submission Pipeline Design

**Status:** Approved

## Context

The first authorized MVTec AD 2 archive contained all 4,090 continuous
`float16` TIFF anomaly maps but no thresholded PNGs. The pinned official
utility accepted that archive because thresholded outputs are optional, while
warning that threshold-dependent metrics require binary images. The official
server therefore returned zero ClassF1 and SegF1 values that are not valid
measurements of this method's thresholded performance.

This design adds a fail-closed thresholded-output path and proves it locally.
It does not revise the recorded official result, retune on private data, use
the remaining evaluation budget, or authorize another upload.

## Goals

- Calibrate one segmentation threshold per frozen category champion using
  only its anomaly-free `validation/good` anomaly maps.
- Use the official baseline rule `mean + 3 * population standard deviation`
  over finite validation pixels, computed with bounded memory.
- Produce one single-channel PNG with values exactly `{0, 255}` for every
  continuous TIFF prediction and preserve the source image geometry.
- Require exact, duplicate-free identity parity for both continuous and
  thresholded trees before an archive can pass the project verifier.
- Rebuild a corrected local archive from the existing external prediction
  cache without running private inference again.
- Preserve calibration provenance and sanitized counts in an external summary.

## Non-goals

- No official upload or authenticated benchmark action.
- No mutation or replacement of the previously submitted 9.8 GB archive.
- No use of private labels, server metrics, image identifiers, or raw private
  predictions in Git.
- No model-family, champion, preprocessing, checkpoint, or seed change.
- No claim that adding thresholded PNGs fixes the low private AucPro_0.05
  result or makes the candidate release-ready.
- No public model, tag, GitHub Release, or deployment.

## Approaches considered

### Selected: streaming validation-pixel baseline

Read each hash-verified validation anomaly map once, combine its pixel count,
mean, and squared-deviation accumulator in `float64`, and freeze
`threshold = mean + 3 * std` per category. This matches the baseline described
by the pinned official validator, remains independent of private outputs, and
uses bounded memory.

### Rejected: reuse the existing image-level conformal threshold

The current threshold artifact is calibrated over one maximum anomaly score
per validation image. It controls an image-level review decision; it is not a
segmentation-threshold contract and can be excessively conservative when
applied to every pixel.

### Deferred: optimize a threshold against public defect masks

Optimizing F1 on `test_public` could improve that public metric, but would add
a separate research choice and overfitting surface. The first repair should
implement the official anomaly-free validation baseline. Alternative
calibration belongs in the later, separately evidenced robustness experiment.

## Architecture

### Calibration module

Create `experiments/submission/thresholds.py` with an immutable
`SubmissionThreshold` contract and a `calibrate_submission_threshold(run_dir)`
entry point. The calibrator:

1. requires a completed seed-42 champion run;
2. reads `predictions/validation.json` and its referenced anomaly maps;
3. verifies every map's recorded SHA-256 before using it;
4. rejects missing, non-2D, empty, or non-finite arrays;
5. combines per-map population statistics without concatenating the maps; and
6. records category, run identity, method, pixel count, mean, standard
   deviation, threshold, and validation-artifact hash.

The resulting contract is written outside Git beside the rebuilt submission.

### Dual-output builder

`SubmissionBuilder.build` receives an exact category-to-threshold mapping.
For each verified TIFF it copies the continuous map and writes a mode-`L` PNG
at the matching path below `anomaly_images_thresholded`. A pixel is anomalous
only when its finite continuous score is strictly greater than the frozen
threshold; the output value is `255`, otherwise `0`.

The builder rejects an incomplete threshold mapping before creating an
archive. It writes through a temporary staging directory and replaces only the
new output archive and sidecar in the separately selected output root.

### Inspection and verification

Archive inspection reports continuous and thresholded identities separately.
Project verification requires both sets to equal the private manifest, checks
that there are no duplicates, and validates sampled/generated image contracts
through real TIFF/Pillow decoding. The sanitized summary schema records both
counts plus calibration identities; it never records private image names or
filesystem paths.

### Cache-only rebuild

Add a cache-only command path that reads the existing external
`prediction-cache/<category>/<split>/tiff` files. It validates every expected
identity and source geometry, calibrates thresholds from the frozen champion
runs, builds into a new external root, invokes the checksum-pinned official
utility, and writes a summary. It does not acquire the GPU lease because it
does not perform inference.

The existing formal inference path uses the same calibrator and dual-output
builder for any future candidate, but no future private prediction generation
or upload is part of this task.

## Failure handling and safety

- Any missing threshold, map, calibration artifact, hash mismatch, dimension
  mismatch, invalid value, duplicate identity, or wrong PNG value aborts the
  build.
- Outputs remain outside the repository and outside Docker build contexts.
- The original submission root is read-only input; the corrected archive uses
  a new root such as `D:\mvtec-ad2-submission-thresholded-20260810`.
- Temporary files are scoped beneath the new output root and cleaned normally;
  no recursive delete targets an existing artifact root.
- The official utility is accepted only at SHA-256
  `fda9b379affbbde8b4d4fc1fe6ac52aaff981f347f3424e6b6de027457549f15`.

## Testing and verification

- TDD unit tests for streaming statistics, exact threshold rule, hash failure,
  invalid arrays, binary PNG output, strict comparison, missing thresholds,
  and exact dual-tree identities.
- Focused submission and metric tests, Ruff, and strict mypy.
- Cache-only integration using controlled synthetic TIFF inputs and the real
  pinned official validator.
- Full non-GPU suite and release/public-boundary gates.
- One external full-manifest rebuild from the existing 4,090-map cache,
  followed by project verification and the pinned official validator.
- The corrected local archive and summary remain external and are explicitly
  marked `LOCAL-PREFLIGHT-NOT-SUBMITTED`.

## Acceptance criteria

- A corrected local archive contains exactly 4,090 TIFFs and 4,090 matching
  PNGs.
- Every PNG is single-channel, source-sized, and contains only `0` and `255`.
- All eight category calibrations are validation-only and hash-bound to their
  frozen seed-42 champion runs.
- The project verifier and pinned official validator both pass.
- No official request is made, the old archive is unchanged, Git contains no
  private data or predictions, and the release verdict remains
  `PRIVATE-NO-GO`.
