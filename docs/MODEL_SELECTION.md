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
