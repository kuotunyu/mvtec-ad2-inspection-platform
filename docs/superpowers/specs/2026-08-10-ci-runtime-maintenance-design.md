# CI Runtime Maintenance Design

**Status:** Approved by delegated autonomous-maintenance authorization

## Context

GitHub Actions run `31354617495` passed all five jobs for commit `44e65bc`,
but every job emitted a hosted-runner annotation because the pinned official
Actions still declared the deprecated Node.js 20 runtime. PowerShell initially
rendered one public limitations sentence as a corrupted em-dash sequence, but
byte-level UTF-8 inspection later confirmed the tracked text was already
correct; no documentation-byte repair is required.

This maintenance must preserve the existing CI matrix, least-privilege
permissions, immutable SHA pinning, release evidence, product behavior, and
sole-contributor history.

## Considered approaches

1. **Upgrade each official Action to its latest stable Node.js 24 release and
   pin its immutable commit SHA.** This removes the known runtime cause while
   retaining supply-chain pinning. This is the selected approach.
2. Upgrade only to the first Node.js 24 major. This reduces major-version
   movement but knowingly leaves later official fixes behind and creates a
   second near-term maintenance pass.
3. Ignore the annotations because CI is green. This preserves current bytes but
   leaves a time-bounded hosted-runner compatibility risk and noisy evidence.

## Frozen action set

The GitHub API and each tagged `action.yml` were inspected on 2026-08-10. All
four selected releases declare `runs.using: node24`:

| Action | Release | Immutable commit SHA |
| --- | --- | --- |
| `actions/checkout` | `v7.0.1` | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | `v7.0.0` | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/setup-node` | `v7.0.0` | `820762786026740c76f36085b0efc47a31fe5020` |
| `actions/upload-artifact` | `v7.0.1` | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |

## Changes

- Replace every matching `uses:` entry in `.github/workflows/ci.yml` with the
  frozen SHA and exact release comment above.
- Add a release-contract test that requires the exact action-to-SHA mapping,
  so a mutable tag, rollback, partial upgrade, or unreviewed replacement fails.
- Extend the public-boundary verifier to reject UTF-8 public text containing
  Unicode replacement characters or private-use code points, while preserving
  the already-correct limitations bytes.

No job, command, permission, cache key, tool version, trigger, concurrency
setting, product dependency, or product behavior changes.

## Verification and boundaries

- Observe focused test failures against the current workflow and a controlled
  corrupt-text fixture before editing production files.
- Run focused release/publication tests, Ruff, format, mypy, the complete
  non-GPU suite, claims, security, and public-boundary verification.
- Run an exact committed clean export after implementation.
- Commit only as `kuotunyu` with no contributor trailers.
- Do not push, tag, release, deploy, publish a model, or submit to MVTec. A
  future explicitly authorized push and GitHub-hosted CI run are required to
  prove the remote annotations are gone.
