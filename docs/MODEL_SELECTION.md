# Model Selection

Public evidence is the source of truth for category champions. The frozen aggregate is in `reports/public_benchmark.json`; the selected champions are in `reports/champions.json`.

| Category | Champion |
| --- | --- |
| can | PatchCore |
| fabric | Dinomaly |
| fruit_jelly | Dinomaly |
| rice | Dinomaly |
| sheet_metal | Dinomaly |
| vial | PatchCore |
| wallplugs | PatchCore |
| walnuts | PatchCore |

Selection uses the declared quality, uncertainty, latency, artifact-size, and deterministic tie-break policy. Private and private-mixed bundles consume these frozen choices only; they must never be used to tune the selection.

Deployment is pinned to seed 42 of each selected family, with the complete model/config/dataset provenance retained in external run evidence. Operational decisions use the calibrated threshold contract: PASS, REVIEW, or FAIL semantics are explicit and are not inferred from a private score distribution.

## 768 x 768 PatchCore research

A fixed public-only seed-42 study attempted to change only PatchCore input and
resize geometry from 512 x 512 to 768 x 768 for `can` and `wallplugs`. Both
candidate fits exhausted the RTX 4090's 24 GiB VRAM before evaluation, so the
frozen result is `RESOURCE_LIMIT_EXCEEDED`. No private evidence or submission
was used, and the category champions above remain unchanged. Sanitized evidence
is recorded in `reports/high_resolution_patchcore.json`.

The identical unmodified study was later completed on an 80 GiB A100, which
resolved the memory limit without changing the pre-registered design, the seed,
the configs, or the classification rules. Measured training peaks were 43.5 GiB
for `can` and 31.0 GiB for `wallplugs`, so neither fit could ever have completed
on the 24 GiB workstation.

Both categories improved pixel localization substantially. `can` gained 0.0995
AU-PRO and 0.0545 pixel AUROC while image AUROC moved by -0.0123; `wallplugs`
gained 0.1551 AU-PRO and 0.0259 pixel AUROC while image AUROC moved by +0.0104.
Those AU-PRO gains are the largest this project has measured from a geometry
change alone.

The frozen classification is nevertheless `RESOURCE_LIMIT_EXCEEDED`, and it is a
latency failure rather than a memory failure. Inference peaks were 4,669 MiB and
3,383 MiB, far below the 12,288 MiB cap, but GPU p95 latency reached 708.7 ms
for `can` and 508.5 ms for `wallplugs`, both above the pre-declared 500 ms cap.
The rule was applied as written rather than relaxed after seeing a favorable
quality result, so the champion matrix above is unchanged.

That latency cost is structural rather than an artifact of the cloud device. The
memory bank grows about 2.1 times and each query image contributes 2.25 times as
many patches, so nearest-neighbor search performs roughly 4.8 times the distance
computations; the observed ratios were 6.7 and 6.2. Latency and VRAM in this
study were measured on the A100 and are not comparable with the RTX 4090
baseline figures recorded elsewhere in this repository, while the AU-PRO and
AUROC deltas are deterministic and hardware independent.

Sanitized aggregate evidence is in `reports/high_resolution_patchcore_cloud.json`,
and the hardware provenance bound to that report's digest is in
`reports/high_resolution_patchcore_cloud_environment.json`. This is single-seed
evidence. Promotion would require a separately pre-registered multi-seed study
and a serving contract that the candidate can satisfy.

## Resource-informed 640 x 640 frontier

Measured 512 x 512 training footprints ruled out another useful `can` probe,
but left enough margin for one fixed 640 x 640 `wallplugs` run. The candidate
completed on the same RTX 4090 and improved public AU-PRO from 0.5286 to 0.5981
(+0.0695) and pixel AUROC by 0.0166. Image AUROC decreased by 0.0406, GPU p95
latency increased from 82.3 to 166.6 ms, and training peaked at 22,219 MiB.

The frozen public-only classification is `PROMISING` for pixel localization,
not a general model-quality or private-performance claim. It does not replace
the champion above; promotion would require preplanned multi-seed replication.
Sanitized aggregate evidence is in
`reports/patchcore_resolution_frontier.json`.

## Balanced PatchCore follow-up

The preplanned public-only follow-up could not establish a reproducible or
balanced improvement on this workstation. Two independent 640 x 640
`wallplugs` seed-17 attempts were interrupted by system-wide forced reboots at
96,558/187,519 and 151,967/187,519 coreset units, with observed GPU memory near
17.9 GiB. Retrying the same candidate a third time was rejected as unsafe.

The independent 576 x 576 seed-42 probe was then attempted as specified. It
held about 23,964 MiB GPU memory and sustained severe coreset degradation at
12,633/151,890 units, so the isolated worker was stopped through the supervisor
and its lease was released. Stage A and Stage B are therefore both
`RESOURCE_LIMIT_EXCEEDED`; no public candidate metrics exist, no follow-up
seeds ran, and the frozen `wallplugs` champion remains unchanged. Sanitized,
identity-bound aggregate evidence is in
`reports/balanced_patchcore_resource_limit.json`.

## Memory-bounded 640 x 640 PatchCore follow-up

The fixed public-only coreset ladder completed without a resource stop. The
0.01 seed-42 probe improved AU-PRO by 0.0757 and pixel AUROC by 0.0112, but its
205.1 MiB artifact exceeded the 200 MiB cap and image AUROC regressed by 0.0533,
so the preplanned 0.02 rescue ran. The 0.02 seed-42 result passed: AU-PRO
improved by 0.0854, pixel AUROC by 0.0195, image AUROC changed by -0.0302,
public GPU p95 latency was 78.4 ms, and the artifact was 315.0 MiB. Training
peaked at 22,219 MiB on the RTX 4090.

Seeds 17 and 2026 completed with the same 0.02 contract. All three artifacts
and latencies remained below the 350 MiB and 175 ms caps, with zero per-image
failures, but image AUROC deltas were -0.0728 and -0.0626 for the replications.
The three-seed mean image AUROC delta was therefore about -0.0552, below the
frozen -0.04 reproducibility gate. The fixed verdict is
`EFFICIENT_SEED42_ONLY`: the smaller coreset is operationally efficient and
improves public localization, but the general image-level quality gain is not
reproducible. It does not replace the frozen `wallplugs` champion or alter the
official `PRIVATE-NO-GO` state. Sanitized aggregate evidence is in
`reports/memory_bounded_patchcore.json`.
