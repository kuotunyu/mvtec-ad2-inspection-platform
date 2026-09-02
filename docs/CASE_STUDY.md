# Case Study

## The engineering question

An anomaly benchmark is not yet an inspection product. The difficult part was preserving experimental identity while adding uploads, durable work, evidence visualization, human review, recovery, packaging, and honest publication boundaries.

## What was built

The offline plane completed **56 formal public runs** <!-- claim:56|reports/public_benchmark.json|/runs|len --> and froze **8 category-specific champions** <!-- claim:8|reports/champions.json|/champions|len -->. The product plane consumes manifests with dataset, preprocessing, threshold, prediction-contract, and file hashes. A mismatch stops inference rather than silently loading a nearby model.

The workstation supports mixed batches: a corrupt input becomes an image-level error while valid inputs continue. Worker leases make restart safe; existing predictions are not duplicated and terminal audit history remains idempotent. JSON is canonical, while CSV and HTML are deterministic renderings with spreadsheet and markup neutralization.

## Why the model matrix is per category

The candidate families trade off representation, latency, memory, and regional localization differently by product category. Selection therefore uses frozen category evidence and confidence intervals instead of declaring one family universally best. The full aggregate evidence is [recomputable](../reports/champions.json); the readable benchmark is [here](../reports/benchmark.md).

## Research under a fixed memory budget

The post-freeze PatchCore studies treated resource limits as experimental evidence rather than failed runs to hide. Fixed 768 x 768 probes exhausted a 24 GiB RTX 4090 during fitting. A 640 x 640 `wallplugs` frontier probe then improved localization but regressed image AUROC and increased latency, so it was not promoted.

The 768 x 768 study was later completed on an 80 GiB cloud GPU with the identical study code, seed, and configuration. Measured training peaks of 43.5 GiB and 31.0 GiB confirmed the original device could never have held either fit. The quality hypothesis held: `can` gained 0.0995 AU-PRO and `wallplugs` 0.1551, this project's largest gain from a geometry change alone, with image AUROC roughly unchanged. The candidate was refused anyway, because GPU p95 latency of 708.7 ms and 508.5 ms exceeded a 500 ms serving cap written into the classification rules before any result existed. That is a latency failure rather than a memory failure, and the cost is structural: the memory bank and the query patch count both grow with the input geometry, giving roughly 4.8 times the nearest-neighbor distance computations. Applying the rule as written instead of relaxing it after a favorable result is the point of the exercise.

The final public-only coreset ladder kept the 640 x 640 geometry and reduced the memory-bank ratio. The 0.02 seed-42 candidate improved AU-PRO by **0.0854** <!-- claim:0.0854|reports/memory_bounded_patchcore.json|/probes/1/comparison/au_pro_delta|.4f --> with **78.4 ms** GPU p95 <!-- claim:78.4|reports/memory_bounded_patchcore.json|/probes/1/comparison/candidate/gpu_p95_latency_ms|.1f --> and a **330,255,411-byte** artifact <!-- claim:330,255,411|reports/memory_bounded_patchcore.json|/probes/1/comparison/candidate/artifact_size_bytes|,d -->. Replications at seeds 17 and 2026 retained the localization gain but regressed image AUROC enough to fail the predeclared reproducibility gate. The verdict is therefore `EFFICIENT_SEED42_ONLY`, not a new champion. The exact ordered procedure and sanitized evidence are in [MODEL_SELECTION.md](MODEL_SELECTION.md) and [memory_bounded_patchcore.json](../reports/memory_bounded_patchcore.json).

## What the result does not claim

The UI routes model evidence to `PASS` or `REVIEW`; a person records `ACCEPT`, `REJECT`, or `UNCERTAIN`. It does not infer defect type or root cause. Public measurements are tied to the recorded local hardware/software environment and are not production guarantees.

Private prediction packaging and the official local validator completed before one authorized official submission. The server result is preserved as sanitized aggregate evidence and classified `PRIVATE-NO-GO`: AucPro_0.05 is 31.24 on `private` and 29.81 on `private_mixed`. The archive did not include thresholded PNGs, so zero official ClassF1 and SegF1 values are reported as a packaging limitation, not hidden or repaired with a second submission.
