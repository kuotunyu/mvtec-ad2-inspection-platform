# Model Card

## Intended use

The category-specific models provide anomaly evidence for a local research/non-commercial inspection workflow. They support human review and portfolio reproducibility. They are not safety-certified quality-control systems and must not autonomously reject production material.

## Candidate families and frozen matrix

PatchCore, EfficientAD, and Dinomaly were evaluated under the same dataset and metric contracts. The frozen winners are:

| Category | Selected family |
|---|---|
| can | PatchCore |
| fabric | Dinomaly |
| fruit jelly | Dinomaly |
| rice | Dinomaly |
| sheet metal | Dinomaly |
| vial | PatchCore |
| wallplugs | PatchCore |
| walnuts | PatchCore |

This matrix contains **8 category-specific champions** <!-- claim:8|reports/champions.json|/champions|len -->. Exact scores, bootstrap intervals, latency, VRAM, artifact sizes, run identities, and selection reasons remain in [champions.json](../reports/champions.json) and [benchmark.md](../reports/benchmark.md), avoiding hand-copied values here.

## Calibration and decisions

Each serving bundle records preprocessing identity and its frozen threshold. The model emits a score and spatial evidence; the product maps that evidence only to `PASS` or `REVIEW`. Human disposition is stored separately with optimistic revision control.

## Evaluation status

Public selection evidence is complete. The one frozen combined archive passed the local validator and completed official evaluation without retuning or resubmission. Official AucPro_0.05 averages are **31.24** <!-- claim:31.24|docs/assets/evidence/official-private-result.json|/metrics/private/auc_pro_0_05/average|.2f --> on `private` and **29.81** <!-- claim:29.81|docs/assets/evidence/official-private-result.json|/metrics/private_mixed/auc_pro_0_05/average|.2f --> on `private_mixed`; the release verdict is `PRIVATE-NO-GO`.

The archive contained no thresholded PNGs, so official ClassF1 and SegF1 are zero and are not treated as measured thresholded-map performance. This packaging limitation is preserved in the sanitized [official result](assets/evidence/official-private-result.json), and no second submission was performed.

Post-freeze PatchCore studies tested higher resolutions and smaller coresets against fixed public-only gates. They produced useful resource and localization evidence, but no multi-seed result justified replacing the frozen matrix. Their `RESOURCE_LIMIT_EXCEEDED`, `PROMISING`, and `EFFICIENT_SEED42_ONLY` classifications are research outcomes rather than deployed model versions; see [MODEL_SELECTION.md](MODEL_SELECTION.md).

## Failure modes

Lighting shift, texture drift, unseen product variants, contamination of nominal training data, resize artifacts, and category mistakes can change scores. Spatial maps are visual evidence, not segmentation ground truth. Latency and memory results are specific to the recorded RTX workstation. Tampered or incomplete bundles are rejected before inference.

## License and provenance

Manifests bind file hashes, dataset identity, prediction contract, preprocessing, and thresholds. MVTec AD 2 is CC BY-NC-SA 4.0; real trained artifacts are restricted to research/non-commercial portfolio use and are not bundled in this repository or CPU images.
