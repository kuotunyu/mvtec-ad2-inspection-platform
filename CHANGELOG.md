# Changelog

## 0.1.0-rc.1 - 2026-08-11

Status: `PRIVATE-NO-GO`. The product and public release-candidate gates remain verified, but the frozen official private gate does not support a v1 release. This source snapshot is published as a GitHub pre-release, not as a v1 or production release.

### Published snapshot

- Annotated tag [`v0.1.0-rc.1`](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.0-rc.1) points to source commit `82918727d6d9ed7c6555556d73b24b3acb2e7b9b`.
- The GitHub pre-release was published on 2026-08-11 as a source-only portfolio snapshot with no custom release assets.
- GitHub-generated source archives contain no MVTec data, model weights, checkpoints, private predictions, raw server responses, or credentials.

### Added

- Reproducible eight-category MVTec AD 2 experiment pipeline with frozen PatchCore and Dinomaly champions.
- Local-first FastAPI, SQLite, leased worker, content-addressed evidence, deterministic reports, and React review workstation.
- Digest-pinned non-root Docker images, clean-export packaging, CycloneDX SBOMs, public-boundary scanning, and browser acceptance gates.
- Hash-bound public benchmark, champion, serving, and release-candidate evidence.

### Verified

- All eight real champion bundles served successfully on the recorded RTX 4090 environment from source `f902c7b50cd79a2fdd954af4d23c46af4c488bc7`.
- The committed-source clean export passed Python, frontend, accessibility, packaging, SBOM, Docker, security, documentation, and end-to-end browser gates.
- The combined frozen private prediction archive contains both official private splits and passes the official local validator.
- The one authorized official submission reached `DONE`; sanitized private and mixed-lighting aggregates are hash-bound in the release evidence.
- The submitted archive contained no thresholded PNGs, so official ClassF1 and SegF1 are zero and explicitly treated as unavailable thresholded-map evidence.

### Publication boundary

- No second official submission was performed or is planned. Deployment and model publication remain unauthorized and unperformed.
- The one-time authorization for the `v0.1.0-rc.1` annotated tag and source-only GitHub pre-release was exercised without deployment or model publication.
- Any future tag, Release, deployment, model publication, or additional official submission requires new explicit authorization.
