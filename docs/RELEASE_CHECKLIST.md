# Release Checklist

## Candidate classification

- Candidate: `0.1.0-rc.1`
- Status: `PRIVATE-NO-GO`
- Verified source: `f902c7b50cd79a2fdd954af4d23c46af4c488bc7`
- Official submission performed: Yes, exactly once
- Official private status: `DONE`

The public benchmark, product, Docker, security, documentation, clean-export, and eight-category real GPU serving gates pass. The frozen official result does not support a v1 release, and it does not grant permission to publish.

## Completed local gates

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
7. Request separate authorization for any commit of official aggregates and again for push, tag, GitHub Release, deployment, or model publication.

## Publication boundary

- [x] Official submission authorized and completed.
- [x] Official result sanitized and independently checked.
- [x] Mixed-lighting criterion classified truthfully as `PRIVATE-NO-GO`.
- [x] Thresholded cache-only repair passed local preflight and remains unsubmitted.
- [x] Publication explicitly authorized.

The authorized scope is the Public source repository `kuotunyu/mvtec-ad2-inspection-platform` and its initial `main` push. Tags, GitHub Releases, deployments, model publication, and additional official submissions remain separately authorized actions.
