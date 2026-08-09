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

Public selection evidence is complete. Private and private-mixed predictions were packaged after freezing and passed the official local validator. Official authenticated submission was not performed; private performance is therefore `not evaluated` publicly.

## Failure modes

Lighting shift, texture drift, unseen product variants, contamination of nominal training data, resize artifacts, and category mistakes can change scores. Spatial maps are visual evidence, not segmentation ground truth. Latency and memory results are specific to the recorded RTX workstation. Tampered or incomplete bundles are rejected before inference.

## License and provenance

Manifests bind file hashes, dataset identity, prediction contract, preprocessing, and thresholds. MVTec AD 2 is CC BY-NC-SA 4.0; real trained artifacts are restricted to research/non-commercial portfolio use and are not bundled in this repository or CPU images.
