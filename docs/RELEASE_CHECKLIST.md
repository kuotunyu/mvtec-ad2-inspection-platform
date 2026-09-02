# Release Checklist

## v0.1.2 source-only maintenance release

- Software version: `0.1.2`
- Source scope: maintenance update to the reproducible portfolio artifact and local inspection-workstation contract, adding the completed 768 x 768 study evidence, its hardware provenance, and the hosted-GPU research tooling
- Model-validation status: `PRIVATE-NO-GO`
- External publication evidence: The `v0.1.2` Git tag and corresponding [GitHub Release](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.2) are the authoritative record of publication identity, source commit, and date.
- Release assets: GitHub-generated source archives only; no custom dataset, weights, checkpoints, predictions, drift scores, or private evidence
- Current source-lock evidence: [`docs/assets/evidence/source-release.json`](assets/evidence/source-release.json), separate from the historical exact-candidate GPU evidence

The 2026-09-03 authorization covers the version-maintenance commits, branch and PR publication, protected integration to `main`, one annotated `v0.1.2` tag, and the matching source-only GitHub Release. It does not authorize a deployment, hosted service, model publication, real-score retrieval, retraining, threshold changes, an additional official submission, or access to private predictions and raw official responses.

The maintenance changes do not alter frozen model selection, preprocessing, thresholds, prediction semantics, or official conclusions. The 768 x 768 study completed on an 80 GiB cloud GPU is single-seed, `test_public`-only evidence whose frozen verdict is `RESOURCE_LIMIT_EXCEEDED` on the 500 ms serving cap, so it promotes no champion. No exact-candidate real-GPU serving gate was rerun, so `v0.1.2` makes no new GPU compatibility or model-quality claim; `v0.1.0` remains the last release with recorded 8/8 exact-candidate GPU serving evidence. Before the tag is pushed, the exact source candidate must pass version consistency, Python and frontend verification, Docker and browser system tests, package/archive verification, publication/security tests, claims verification, and the Git public-boundary gate.

## v0.1.1 source-only maintenance release

- Software version: `0.1.1`
- Source scope: maintenance update to the reproducible portfolio artifact and local inspection-workstation contract
- Model-validation status: `PRIVATE-NO-GO`
- External publication evidence: The `v0.1.1` Git tag and corresponding [GitHub Release](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.1) are the authoritative record of publication identity, source commit, and date.
- Release assets: GitHub-generated source archives only; no custom dataset, weights, checkpoints, predictions, drift scores, or private evidence
- Current source-lock evidence: [`docs/assets/evidence/source-release.json`](assets/evidence/source-release.json), separate from the historical exact-candidate GPU evidence

The 2026-08-30 authorization covers the version-maintenance commits, branch and PR publication, protected integration to `main`, one annotated `v0.1.1` tag, and the matching source-only GitHub Release. It does not authorize a deployment, hosted service, model publication, real-score retrieval, retraining, threshold changes, an additional official submission, or access to private predictions and raw official responses.

The maintenance changes do not alter frozen model selection, preprocessing, thresholds, prediction semantics, or official conclusions. No exact-candidate real-GPU serving gate was rerun, so `v0.1.1` makes no new GPU compatibility or model-quality claim. `v0.1.0` remains the last release with recorded 8/8 exact-candidate GPU serving evidence. Before the tag is pushed, the exact source candidate must pass version consistency, Python and frontend verification, Docker and browser system tests, package/archive verification, publication/security tests, claims verification, and the Git public-boundary gate.

## v0.1.0 stable source contract and exact-candidate GPU evidence

- Software version: `0.1.0`
- Source scope: reproducible portfolio artifact and local inspection-workstation contract
- Model-validation status: `PRIVATE-NO-GO`
- External publication evidence: The `v0.1.0` Git tag and corresponding [GitHub Release](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.0) are the authoritative record of publication identity, source commit, and date.
- Exact-candidate GPU requirement: All eight frozen bundles must pass against the final candidate SHA before stable publication.

Source acceptance and external publication are separate: this checklist defines the stable software contract without asserting that the external tag or Release exists, and it does not record the exact-candidate GPU gate as passed until that gate runs against the final SHA. Stable describes the reproducible portfolio artifact and local workstation contract, not production deployment or private model quality. Historical result manifests remain immutable evidence of the RC-era evaluation sources; they are not rewritten to impersonate final stable evidence.

## Historical published RC snapshot

- Historical real-GPU evidence source: `f902c7b50cd79a2fdd954af4d23c46af4c488bc7`
- Published source snapshot: `82918727d6d9ed7c6555556d73b24b3acb2e7b9b`
- Annotated tag: `v0.1.0-rc.1`
- GitHub pre-release: [source-only portfolio snapshot](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.0-rc.1)
- Published at: `2026-08-11T12:08:34Z`
- Custom release assets: None; only GitHub-generated source archives are available.
- Official submission performed: Yes, exactly once
- Official private status: `DONE`

The RC public benchmark, product, Docker, security, documentation, clean-export, and eight-category real GPU serving gates passed. The frozen official result did not support a v1 release. The authorized RC publication is therefore labeled as a source-only `PRIVATE-NO-GO` pre-release, not a production release.

The champion comparison uses exactly three seeds. Its paired bootstrap intervals are descriptive, without multiplicity correction, and `test_public` participated in iterative model selection rather than serving as an independent final holdout. A source-code stable release can certify the reproducible portfolio artifact and workstation contract, but it cannot change the independent `PRIVATE-NO-GO` model verdict or imply production model quality.

## Historical RC gates

- [x] Experiment verifier passes against the completed official submission handoff.
- [x] Backend verifier passes.
- [x] Frontend API, lint, type, unit, build, asset, accessibility, and browser gates pass.
- [x] Dataset-to-product contract chain passes for all eight categories.
- [x] Security and Git public-boundary scans report zero findings.
- [x] Eight real champion bundles pass clean-process GPU serving from the verified source SHA.
- [x] Clean committed export passes tests, package builds, wheel import, CycloneDX SBOM generation, Docker smoke, and the real browser system workflow.
- [x] Release evidence records LF-canonical lock hashes plus dataset, champion, registry, bundle, metric, Docker, GPU, and source identities.

## Frozen official submission handoff

The upload set is already generated outside Git and must remain unchanged:

- Upload file: `private_submission.tar.gz`
- Upload SHA-256: `25780c9e0c0a234454fa2e6a9a7d75f274d27d0434ad089549e19b0b0906ffb9`
- Checksum sidecar: `private_submission.tar.gz.sha256`
- Redacted local summary: `submission_summary.json`
- Expected images: 4,090
- Expected splits in the combined archive: `test_private` and `test_private_mixed`
- Expected category mapping: `can`, `fabric`, `fruit_jelly`, `rice`, `sheet_metal`, `vial`, `wallplugs`, and `walnuts`, each mapped to the identically named official category.
- Exact bundle and manifest hashes: `docs/assets/evidence/release-verification.json` under `model_bundles`.

No retuning rule: after the frozen archive is submitted, no private or mixed-lighting result may change preprocessing, thresholds, model families, seeds, checkpoints, or champion selection. A material mixed-lighting failure must be reported as `PRIVATE-NO-GO`, not hidden or recalibrated.

The single official submission reached `DONE`. Sanitized AucPro_0.05 averages are 31.24 for `private` and 29.81 for `private_mixed`. Direct archive inventory found 4,090 TIFF anomaly maps and zero thresholded PNGs; official ClassF1 and SegF1 are therefore zero and are not interpreted as measured thresholded-map performance. No second submission was performed.

## Thresholded local preflight

After the official result, a cache-only pipeline repair generated a separate local archive with 4,090 continuous float16 TIFF maps and 4,090 matching binary PNG maps. All eight thresholds use finite anomaly-free `validation/good` pixels and the frozen `mean + 3 * population standard deviation` method. The project verifier and checksum-pinned official validator both passed.

This corrected archive was not submitted. It does not change the historical official archive, official scores, one-submission count, or `PRIVATE-NO-GO` classification, and it provides no new official F1 measurement. Sanitized hashes and counts are recorded under `thresholded_local_preflight` in `docs/assets/evidence/release-verification.json`; the archive, calibrations, paths, identities, and raw validator output remain outside Git.

## Authorized capture and import procedure

Do not perform these actions without explicit authorization and the required official account or credentials.

1. Recompute the archive SHA-256 and compare it byte-for-byte with the value above.
2. Upload the one frozen combined archive once through the official MVTec evaluation interface; do not regenerate it after seeing results.
3. Capture the server timestamp, submitted archive hash, per-split/per-category sanitized aggregate scores, and the unedited official response. Keep screenshots, downloads, raw responses, and private predictions outside Git.
4. Verify the local handoff with `uv run python scripts/verify_experiments.py --submission-summary <external-summary>`.
5. Import only a reviewed, sanitized aggregate artifact; never import private image identifiers, maps, labels, workstation paths, credentials, or raw responses.
6. Run `uv run python scripts/verify_claims.py`, the publication/security tests, and the full clean-export gate. Classify the result as `PRIVATE-NO-GO` or `V1-CANDIDATE` according to the frozen criteria.
7. Request separate authorization for any commit of official aggregates and again for push, tag, GitHub Release, deployment, or model publication. The one-time `v0.1.0-rc.1` tag and source-only pre-release authorization recorded below does not authorize any future publication action.

## Historical RC publication closure

- [x] Official submission authorized and completed.
- [x] Official result sanitized and independently checked.
- [x] Mixed-lighting criterion classified truthfully as `PRIVATE-NO-GO`.
- [x] Thresholded cache-only repair passed local preflight and remains unsubmitted.
- [x] Publication explicitly authorized.
- [x] Annotated tag `v0.1.0-rc.1` published at source commit `82918727d6d9ed7c6555556d73b24b3acb2e7b9b`.
- [x] Source-only GitHub pre-release published with `PRIVATE-NO-GO` labeling and no custom assets.
- [x] No deployment, model publication, or additional official submission performed.

The completed historical RC authorization covered the public source repository `kuotunyu/mvtec-ad2-inspection-platform`, its `main` history through the RC snapshot, the annotated tag `v0.1.0-rc.1`, and the matching source-only GitHub pre-release. This is an RC closure record, not authorization for any later publication scope; deployment, model publication, additional official submissions, and later tags or Releases require their own authorization records rather than inheriting the historical RC authorization.
