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
