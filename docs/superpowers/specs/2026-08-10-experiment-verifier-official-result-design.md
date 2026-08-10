# Official Result-Aware Experiment Verifier Design

## Problem

The repository contains a reviewed, sanitized official MVTec AD 2 result and
an integrity manifest, but `scripts/verify_experiments.py` only recognizes an
external local-submission summary. A normal checkout therefore reports
`PENDING EXTERNAL SUBMISSION` after the official submission has completed.

## Decision

Keep verification status separate from release classification:

- return `PASS` when the committed official result is present, complete, and
  hash-bound by `docs/assets/evidence/manifest.json`;
- preserve `PRIVATE-NO-GO` or `V1-CANDIDATE` inside the evidence as the release
  verdict rather than returning it as the verifier status;
- retain `PENDING EXTERNAL SUBMISSION` when neither complete committed official
  evidence nor a passing external local-submission summary exists;
- fail closed for malformed, unmanifested, hash-mismatched, incomplete, or
  unknown-verdict committed official evidence.

The existing external-summary path remains supported for pre-submission local
handoff verification. No network access, private evidence, credentials, or
submission action is added.

## Verification

Focused tests cover pending, legacy summary PASS, committed official PASS, and
all fail-closed integrity cases. The runbook will explain the distinction
between verifier status and release verdict. Full non-GPU release gates and an
exact-HEAD clean export remain required before completion.
