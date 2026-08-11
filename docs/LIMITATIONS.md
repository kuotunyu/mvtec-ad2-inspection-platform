# Limitations

- The system detects anomalous evidence; it does not identify defect type, root cause, severity, or repair action.
- `PASS` and `REVIEW` are model outcomes. Final acceptance or rejection is a human responsibility.
- Public benchmark measurements do not guarantee factory performance, and the recorded latency/VRAM applies only to the tested workstation environment.
- Lighting, camera, pose, scale, material, background, and product-lot shifts can invalidate calibration.
- MVTec AD 2 is a research dataset with non-commercial terms and is not redistributed.
- Synthetic demo results prove product plumbing, determinism, recovery, accessibility, and boundary handling—not real model quality.
- The default deployment is a trusted single-user workstation. Authentication, TLS termination, centralized authorization, and multi-tenant isolation are outside scope.
- The frozen official private gate is `PRIVATE-NO-GO`; no retuning or second submission was performed after seeing the result.
- The submitted archive contained no thresholded PNGs. Official ClassF1 and SegF1 are therefore zero and are not interpreted as measured thresholded-map performance.
- A later cache-only repair produced 4,090 matching binary PNGs and passed local preflight, but it was not submitted and therefore provides no new official F1 measurement.
- A fixed 768 x 768 PatchCore study for `can` and `wallplugs` failed during fitting with CUDA out-of-memory on a 24 GiB RTX 4090. It produced no comparable public metrics, did not change any champion, and does not support a high-resolution quality claim.
- A later public-only 640 x 640 `wallplugs` PatchCore probe improved AU-PRO but reduced image AUROC, doubled p95 latency, and used 22,219 MiB during training. This is exploratory single-seed evidence, not a promoted champion or evidence of private improvement.
- The balanced follow-up could not safely complete its planned replications: two 640 x 640 attempts ended in system interruptions, and the isolated 576 x 576 worker was stopped after sustained resource degradation. These runs provide resource-limit evidence, not comparable quality metrics.
- A memory-bounded 640 x 640 coreset study completed three seeds and reduced artifact and inference costs, but the image-AUROC regression failed its predeclared reproducibility gate. Its `EFFICIENT_SEED42_ONLY` verdict does not change the champion matrix or official private result.
