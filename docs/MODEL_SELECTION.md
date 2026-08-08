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
