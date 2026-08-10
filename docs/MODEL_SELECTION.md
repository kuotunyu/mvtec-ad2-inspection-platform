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
