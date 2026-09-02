# Limitations

- The system detects anomalous evidence; it does not identify defect type, root cause, severity, or repair action.
- `PASS` and `REVIEW` are model outcomes. Final acceptance or rejection is a human responsibility.
- Public benchmark measurements do not guarantee factory performance, and the recorded latency/VRAM applies only to the tested workstation environment.
- Lighting, camera, pose, scale, material, background, and product-lot shifts can invalidate calibration.
- The anomaly-score drift component is an offline evidence generator, not a daemon, dashboard, alerting service, retraining system, or production monitor. Its PSI severity bands are heuristics rather than calibrated acceptance gates, and the report separately exposes whether sample size is adequate for interpretation.
- The repository contains no publishable standard-versus-lighting per-sample score distributions, so it commits no measured drift report. Drift tests use synthetic canonical prediction artifacts to verify the detector and report contract only; they do not establish observed MVTec AD 2 or factory drift.
- MVTec AD 2 is a research dataset with non-commercial terms and is not redistributed.
- Synthetic demo results prove product plumbing, determinism, recovery, accessibility, and boundary handling—not real model quality.
- The default deployment is a trusted single-user workstation. Authentication, TLS termination, centralized authorization, and multi-tenant isolation are outside scope.
- The frozen official private gate is `PRIVATE-NO-GO`; no retuning or second submission was performed after seeing the result.
- The submitted archive contained no thresholded PNGs. Official ClassF1 and SegF1 are therefore zero and are not interpreted as measured thresholded-map performance.
- A later cache-only repair produced 4,090 matching binary PNGs and passed local preflight, but it was not submitted and therefore provides no new official F1 measurement.
- A fixed 768 x 768 PatchCore study for `can` and `wallplugs` failed during fitting with CUDA out-of-memory on a 24 GiB RTX 4090. The identical unmodified study later completed on an 80 GiB A100, where training peaked at 43.5 GiB and 31.0 GiB.
- That completed 768 x 768 study improved public pixel localization on both categories, by 0.0995 AU-PRO for `can` and 0.1551 for `wallplugs`, with image AUROC roughly unchanged. Its frozen verdict is still `RESOURCE_LIMIT_EXCEEDED` because GPU p95 latency of 708.7 ms and 508.5 ms exceeded the pre-declared 500 ms serving cap. It is single-seed public-only evidence, it does not change any champion, and it does not support a high-resolution quality claim.
- Latency and VRAM in the cloud study were measured on an A100 and are not comparable with the RTX 4090 figures recorded elsewhere. The quality deltas are deterministic and hardware independent; the latency increase is structural, since the memory bank and the query patch count both grow with the input geometry.
- A later public-only 640 x 640 `wallplugs` PatchCore probe improved AU-PRO but reduced image AUROC, doubled p95 latency, and used 22,219 MiB during training. This is exploratory single-seed evidence, not a promoted champion or evidence of private improvement.
- The balanced follow-up could not safely complete its planned replications: two 640 x 640 attempts ended in system interruptions, and the isolated 576 x 576 worker was stopped after sustained resource degradation. These runs provide resource-limit evidence, not comparable quality metrics.
- A memory-bounded 640 x 640 coreset study completed three seeds and reduced artifact and inference costs, but the image-AUROC regression failed its predeclared reproducibility gate. Its `EFFICIENT_SEED42_ONLY` verdict does not change the champion matrix or official private result.
