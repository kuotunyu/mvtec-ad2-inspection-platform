# Case Study

## The engineering question

An anomaly benchmark is not yet an inspection product. The difficult part was preserving experimental identity while adding uploads, durable work, evidence visualization, human review, recovery, packaging, and honest publication boundaries.

## What was built

The offline plane completed **56 formal public runs** <!-- claim:56|reports/public_benchmark.json|/runs|len --> and froze **8 category-specific champions** <!-- claim:8|reports/champions.json|/champions|len -->. The product plane consumes manifests with dataset, preprocessing, threshold, prediction-contract, and file hashes. A mismatch stops inference rather than silently loading a nearby model.

The workstation supports mixed batches: a corrupt input becomes an image-level error while valid inputs continue. Worker leases make restart safe; existing predictions are not duplicated and terminal audit history remains idempotent. JSON is canonical, while CSV and HTML are deterministic renderings with spreadsheet and markup neutralization.

## Why the model matrix is per category

The candidate families trade off representation, latency, memory, and regional localization differently by product category. Selection therefore uses frozen category evidence and confidence intervals instead of declaring one family universally best. The full aggregate evidence is [recomputable](../reports/champions.json); the readable benchmark is [here](../reports/benchmark.md).

## What the result does not claim

The UI routes model evidence to `PASS` or `REVIEW`; a person records `ACCEPT`, `REJECT`, or `UNCERTAIN`. It does not infer defect type or root cause. Public measurements are tied to the recorded local hardware/software environment and are not production guarantees.

Private prediction packaging and the official local validator completed before one authorized official submission. The server result is preserved as sanitized aggregate evidence and classified `PRIVATE-NO-GO`: AucPro_0.05 is 31.24 on `private` and 29.81 on `private_mixed`. The archive did not include thresholded PNGs, so zero official ClassF1 and SegF1 values are reported as a packaging limitation, not hidden or repaired with a second submission.
