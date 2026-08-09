# GitHub Public Repository Publication Design

**Date:** 2026-08-09

**Status:** Approved for specification

**Target:** `kuotunyu/mvtec-ad2-inspection-platform`

**Visibility:** Public

## 1. Purpose

Publish the completed MVTec AD 2 Industrial Inspection Platform as a concise,
evidence-backed portfolio repository. The public landing page should be primarily
Traditional Chinese (`zh-TW`) while retaining standard technical terms in their
original form.

The publication must preserve the existing result classification:
`PRIVATE-NO-GO`. It is a truthful engineering and research case study, not a
leaderboard or production-deployment claim.

## 2. Public presentation

### 2.1 Repository identity

- Owner: `kuotunyu`
- Repository: `mvtec-ad2-inspection-platform`
- Default branch: `main`
- Visibility: Public
- Description: `以 MVTec AD 2 建構的可重現工業異常檢測與人工覆核平台（研究／作品集用途）`
- Website: unset
- Issues: enabled
- Wiki and Projects: disabled to keep the public surface focused

Recommended topics:

- `computer-vision`
- `anomaly-detection`
- `industrial-inspection`
- `mvtec-ad`
- `patchcore`
- `fastapi`
- `react`
- `docker`
- `mlops`
- `human-in-the-loop`

GitHub's About panel is populated by the description, topics, and optional
website. No separate About document is required.

### 2.2 README language and structure

Keep the technical project title in English. Rewrite the README body primarily
in concise Traditional Chinese, retaining original terms such as MVTec AD 2,
PatchCore, Dinomaly, FastAPI, React, Docker, AU-PRO, and `PRIVATE-NO-GO`.

The README remains the public front door and should cover, in this order:

1. One-paragraph project summary and synthetic hero image.
2. Honest headline evidence and the `PRIVATE-NO-GO` classification.
3. Product workflow and human-review semantics.
4. Public benchmark and official sanitized aggregate evidence.
5. Compact serving-performance table.
6. Architecture and documentation links.
7. Synthetic local-demo instructions.
8. License and data-publication boundaries.

Existing machine-verifiable claim comments, evidence links, hashes, and
synthetic-media disclosures must remain intact. Detailed technical documents may
remain English because they are already verified source material; the README is
the `zh-TW` presentation layer and must not duplicate or reinterpret their
contracts.

## 3. Publication boundary

The public repository may contain:

- Source code, tests, CI configuration, and documentation.
- Synthetic fixtures, screenshots, and diagrams.
- Reviewed aggregate benchmark artifacts and sanitized official results already
  committed under the approved evidence contract.
- Reproduction instructions that obtain licensed data outside Git.

It must not contain:

- MVTec source images or masks.
- Private benchmark images, identifiers, anomaly maps, or raw predictions.
- Datasets, model weights, checkpoints, uploads, runtime databases, or run
  directories.
- Official raw responses, private screenshots, workstation paths, credentials,
  tokens, cookies, or other secrets.

The MIT license applies to project source code only. MVTec data and derived model
artifacts retain their separately documented licensing and research-use
constraints.

## 4. Contributor identity guarantee

The GitHub Contributors surface must contain only `kuotunyu`.

Before every publication commit and before pushing:

1. Audit every reachable commit author and committer.
2. Require the sole identity to be
   `kuotunyu <61350295+kuotunyu@users.noreply.github.com>`.
3. Reject `Co-authored-by`, `Signed-off-by`, or other contributor trailers that
   name another identity.
4. Create no bot-authored, agent-authored, generated, merge, or CI commits.

After pushing, verify repository metadata and the GitHub contributors endpoint.
GitHub may calculate its Contributors graph asynchronously, so local history is
the authoritative immediate identity check and the remote endpoint must be
rechecked when populated.

## 5. Publication sequence

1. Implement the concise `zh-TW` README without changing evidence semantics.
2. Mark publication authorization in `docs/RELEASE_CHECKLIST.md`; retain the
   release classification as `PRIVATE-NO-GO`.
3. Run focused publication, claim, release, security, and public-boundary gates.
4. Commit the tracked presentation changes locally using only the approved
   `kuotunyu` identity.
5. Run the complete required release verification against a clean committed
   export and confirm a clean worktree.
6. Repeat the full-history identity and trailer audit.
7. Create the Public GitHub repository, configure `origin`, and push `main`.
8. Apply the approved description and topics; leave Website unset.
9. Verify visibility, default branch, metadata, remote commit identity,
   Contributors, and GitHub Actions results.
10. Update the excluded local continuity files with the publication outcome.

Repository creation and the initial `main` push are authorized by the user's
2026-08-09 request. A tag, GitHub Release, deployment, model publication,
additional official benchmark submission, or second remote requires separate
authorization.

## 6. Verification and failure handling

The publication is complete only when:

- README claims resolve against committed evidence.
- Publication, release, security, and public-boundary checks pass.
- The complete clean-export release gate passes from the publication commit.
- `git status` is clean apart from intentionally excluded local continuity files.
- The remote is Public, its default branch is `main`, and its metadata matches
  this design.
- The pushed history contains only the approved `kuotunyu` author and committer
  identity and no foreign contributor trailers.
- GitHub Actions passes, or any failure is diagnosed and corrected through the
  normal TDD and verification workflow before completion is claimed.

If the repository name becomes unavailable, GitHub authentication expires, a
secret or private artifact is detected, the remote identity audit differs from
the local history, or GitHub requires a materially different publication scope,
stop before pushing further and report the exact blocker.

## 7. Non-goals

This publication does not:

- Reclassify the candidate as v1-ready.
- Retune or rerun models based on official private results.
- Perform a second official submission.
- Publish model bundles or licensed datasets.
- Create a tag, GitHub Release, deployment, website, package publication, or
  Hugging Face repository.
- Translate every detailed engineering document into Traditional Chinese.
