# GitHub Public Repository Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Active

**Goal:** Publish `kuotunyu/mvtec-ad2-inspection-platform` as a Public, concise Traditional Chinese portfolio repository with verified evidence boundaries and `kuotunyu` as its sole contributor.

**Architecture:** Treat the README and release checklist as the tracked publication contract, guarded by focused pytest assertions and the existing claim/security/public-boundary verifiers. Verify the final committed tree locally before creating the remote, then use authenticated GitHub CLI operations only for the explicitly authorized repository creation, metadata, and `main` push. Verify the remote independently through GitHub API and Actions before claiming completion.

**Tech Stack:** Markdown, pytest, existing Python release verifiers, PowerShell, Git, GitHub CLI, GitHub Actions

## Global Constraints

- Target exactly `kuotunyu/mvtec-ad2-inspection-platform`, visibility Public, default branch `main`.
- Use the description `以 MVTec AD 2 建構的可重現工業異常檢測與人工覆核平台（研究／作品集用途）`; leave Website unset.
- Keep README primarily concise Traditional Chinese while retaining established technical terms in English.
- Preserve the truthful `PRIVATE-NO-GO` classification and all machine-verifiable claim comments.
- Never publish MVTec data, private images or identifiers, raw predictions, weights, checkpoints, runtime data, credentials, or raw official responses.
- Every commit author and committer must be `kuotunyu <61350295+kuotunyu@users.noreply.github.com>` with no contributor trailers.
- Work on `main` in the existing repository; do not use a subagent, worktree, amend, squash, rebase, or merge commit.
- Do not create a tag, GitHub Release, deployment, website, model publication, second remote, or second official submission.

## Planning compatibility

This plan introduced the first legitimate active checklist after Plans 01–04
were completed. The release bookkeeping regression was verified RED against the
new unchecked steps, then updated to skip only plans declaring
`**Status:** Active`; completed plans remain subject to the zero-unchecked-step
invariant. Task 3 must change this plan to `**Status:** Complete` after every
step is objectively complete.

---

### Task 1: Localize and lock the public presentation

**Files:**
- Modify: `tests/publication/test_docs.py`
- Modify: `README.md`
- Modify: `docs/RELEASE_CHECKLIST.md`
- Modify: `docs/superpowers/plans/2026-08-10-05-github-publication.md`

**Interfaces:**
- Consumes: committed aggregate evidence referenced by the existing README claim comments; approved publication design at `docs/superpowers/specs/2026-08-09-github-publication-design.md`.
- Produces: a Traditional Chinese public front door and an automated publication contract consumed by CI and the release verifier.

- [x] **Step 1: Add the failing publication-contract test**

Append this test to `tests/publication/test_docs.py`:

```python
def test_public_readme_is_zh_tw_front_door_and_publication_is_authorized() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    for required in (
        "## 專案重點",
        "## 產品流程",
        "## 官方 private gate",
        "## 已驗證的本機 serving 效能",
        "## 執行 synthetic local demo",
        "PRIVATE-NO-GO",
        "MVTec 原始資料",
    ):
        assert required in readme

    checklist = Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    assert "- [x] Publication explicitly authorized." in checklist
    assert "Publication remains outside this authorized result-import task." not in checklist
```

- [x] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
uv run pytest tests/publication/test_docs.py::test_public_readme_is_zh_tw_front_door_and_publication_is_authorized -q
```

Expected: FAIL because the current README headings are English and publication authorization remains unchecked.

- [x] **Step 3: Rewrite the README as the concise Traditional Chinese front door**

Keep the title, synthetic hero image, workflow image, architecture image, serving table, evidence links, commands, and every `<!-- claim:... -->` comment. Use these exact headings:

```markdown
# MVTec AD 2 Industrial Inspection Platform

## 專案重點
## 產品流程
## 證據，而非 leaderboard 宣稱
## 官方 private gate
## 已驗證的本機 serving 效能
## 架構
## 執行 synthetic local demo
## 判定語意
## License 與資料邊界
```

The opening summary must state that this is a local-first industrial anomaly-inspection and human-review platform, that public visuals use `fixtures/public-demo`, and that the frozen official result is `PRIVATE-NO-GO`. Translate explanatory prose and table column labels to concise Traditional Chinese without changing any metric, family selection, command, path, claim annotation, or warning. The final boundary section must explicitly say that the repository does not redistribute `MVTec 原始資料`.

- [x] **Step 4: Record the explicit publication authorization**

In `docs/RELEASE_CHECKLIST.md`, change:

```markdown
- [ ] Publication explicitly authorized.

Publication remains outside this authorized result-import task.
```

to:

```markdown
- [x] Publication explicitly authorized.

The authorized scope is the Public source repository `kuotunyu/mvtec-ad2-inspection-platform` and its initial `main` push. Tags, GitHub Releases, deployments, model publication, and additional official submissions remain separately authorized actions.
```

Do not change the `PRIVATE-NO-GO` candidate status or official metrics.

- [x] **Step 5: Run focused GREEN verification**

Run:

```powershell
uv run pytest tests/publication/test_docs.py tests/publication/test_claims.py tests/release/test_release.py -q
uv run python scripts/verify_claims.py
uv run python scripts/render_docs_assets.py --check
```

Expected: all tests pass, all numeric claims resolve, and all generated documentation assets remain unchanged.

- [x] **Step 6: Stage the exact Task 1 files and verify the staged public tree**

Run:

```powershell
git add -- README.md docs/RELEASE_CHECKLIST.md tests/publication/test_docs.py docs/superpowers/plans/2026-08-10-05-github-publication.md
git diff --cached --check
$publicationTree = git write-tree
uv run python scripts/security_scan.py --root .
uv run python scripts/verify_public_boundary.py --git-tree $publicationTree
git diff --cached --name-only
```

Expected: zero formatting/security/public-boundary findings; the staged list contains only the four declared files.

- [x] **Step 7: Audit identity and commit Task 1**

Run the full-history author, committer, and contributor-trailer audit. Then commit with the approved identity:

```powershell
$env:GIT_AUTHOR_NAME = "kuotunyu"
$env:GIT_AUTHOR_EMAIL = "61350295+kuotunyu@users.noreply.github.com"
$env:GIT_COMMITTER_NAME = "kuotunyu"
$env:GIT_COMMITTER_EMAIL = "61350295+kuotunyu@users.noreply.github.com"
git commit -m "docs: localize public repository presentation"
```

Expected: one non-merge commit with only `kuotunyu` as author and committer and no contributor trailer.

---

### Task 2: Verify the committed publication candidate

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-05-github-publication.md`
- Local only: `D:\mvtec-ad2-release\github-publication-<short-sha>.json`

**Interfaces:**
- Consumes: Task 1 committed README, release checklist, tests, and existing release automation.
- Produces: clean-export and history evidence proving that the exact candidate is safe to publish.

- [ ] **Step 1: Run the complete non-GPU local gates**

Run:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m "not gpu and not dataset" -q
npm --prefix apps/web run verify
npm --prefix apps/web run e2e
uv run python scripts/verify_claims.py
uv run python scripts/security_scan.py --root .
uv run python scripts/verify_public_boundary.py --git-tree HEAD
```

Expected: every command passes. No GPU is required.

- [ ] **Step 2: Run the clean committed export gate**

Run:

```powershell
$shortSha = git rev-parse --short HEAD
powershell -ExecutionPolicy Bypass -File scripts/clean_export.ps1 -Treeish HEAD -ReportPath "D:\mvtec-ad2-release\github-publication-$shortSha.json"
```

Expected: clean export PASS for the exact committed SHA, including package builds, SBOM, Docker smoke, and real browser system workflow. No formal model GPU run is required.

- [ ] **Step 3: Repeat the publication identity audit**

Run:

```powershell
git log --format='%an <%ae>' | Sort-Object -Unique
git log --format='%cn <%ce>' | Sort-Object -Unique
git log --format='%B%x00' | Select-String -Pattern '^(Co-authored-by|Signed-off-by|Reviewed-by|Acked-by|Tested-by):' -CaseSensitive:$false
git status --short
git remote -v
```

Expected: the author and committer outputs each contain only the approved `kuotunyu` identity; the trailer query and worktree status are empty; no remote exists before publication.

- [ ] **Step 4: Mark Task 2 complete and commit its tracked bookkeeping**

Mark Task 2 steps complete, stage only this plan, run `git diff --cached --check`, repeat the identity audit, and commit:

```powershell
git add -- docs/superpowers/plans/2026-08-10-05-github-publication.md
git commit -m "docs: verify GitHub publication candidate"
```

Expected: a clean worktree and a `kuotunyu`-only commit. Run focused publication/release tests once more because this commit changes only plan bookkeeping.

---

### Task 3: Create, configure, push, and verify the Public repository

**Files:**
- Modify: `docs/superpowers/plans/2026-08-10-05-github-publication.md`
- Local only: `.codex-local/PROJECT_STATUS.md`
- Local only: `.codex-local/WORKLOG.md`

**Interfaces:**
- Consumes: Task 2 verified clean committed history, active `gh` authentication for `kuotunyu`, and the approved GitHub metadata.
- Produces: the Public GitHub repository, `origin`, pushed `main`, passing GitHub Actions, verified remote metadata, and continuity records.

- [ ] **Step 1: Reconfirm the action-time preconditions**

Run:

```powershell
gh auth status
gh repo view kuotunyu/mvtec-ad2-inspection-platform --json nameWithOwner 2>$null
git status --short
git remote -v
```

Expected: authenticated as `kuotunyu`; repository lookup returns not found; worktree and remote list are empty. Never print or store the authentication token.

- [ ] **Step 2: Create the Public repository and initial push**

Run:

```powershell
gh repo create kuotunyu/mvtec-ad2-inspection-platform --public --source . --remote origin --push --description "以 MVTec AD 2 建構的可重現工業異常檢測與人工覆核平台（研究／作品集用途）" --disable-wiki
```

Expected: repository creation succeeds, `origin` points to `https://github.com/kuotunyu/mvtec-ad2-inspection-platform.git`, and local `main` tracks `origin/main`.

- [ ] **Step 3: Apply the focused About metadata**

Run:

```powershell
gh repo edit kuotunyu/mvtec-ad2-inspection-platform --enable-issues=true --enable-wiki=false --enable-projects=false --default-branch main --description "以 MVTec AD 2 建構的可重現工業異常檢測與人工覆核平台（研究／作品集用途）" --add-topic computer-vision --add-topic anomaly-detection --add-topic industrial-inspection --add-topic mvtec-ad --add-topic patchcore --add-topic fastapi --add-topic react --add-topic docker --add-topic mlops --add-topic human-in-the-loop
```

Expected: command succeeds and no Website is configured.

- [ ] **Step 4: Verify the remote metadata and sole-contributor history**

Run:

```powershell
gh repo view kuotunyu/mvtec-ad2-inspection-platform --json nameWithOwner,visibility,defaultBranchRef,description,homepageUrl,repositoryTopics,url
gh api repos/kuotunyu/mvtec-ad2-inspection-platform/commits --paginate --jq '.[].commit | [.author.name,.author.email,.committer.name,.committer.email] | @tsv'
gh api repos/kuotunyu/mvtec-ad2-inspection-platform/contributors --paginate --jq '.[].login'
```

Expected: Public, `main`, exact description, empty homepage, exactly the approved ten topics, commit identities only `kuotunyu`, and the contributors endpoint either reports only `kuotunyu` or is temporarily empty while GitHub computes it. Any different identity is a blocker.

- [ ] **Step 5: Wait for the initial GitHub Actions run**

Find the push workflow for the current remote SHA and wait for it:

```powershell
$remoteSha = git rev-parse HEAD
$run = gh run list --repo kuotunyu/mvtec-ad2-inspection-platform --commit $remoteSha --event push --limit 1 --json databaseId,status,conclusion,url | ConvertFrom-Json
gh run watch $run.databaseId --repo kuotunyu/mvtec-ad2-inspection-platform --exit-status
gh run view $run.databaseId --repo kuotunyu/mvtec-ad2-inspection-platform --json status,conclusion,jobs,url
```

Expected: workflow conclusion `success`, including `python`, `frontend`, `publication`, `docker`, and `system`. Diagnose failures with `systematic-debugging`; apply fixes with TDD and repeat local gates before pushing again.

- [ ] **Step 6: Record publication completion and push the bookkeeping commit**

Mark every Task 3 checkbox complete and change this plan's status from `Active` to `Complete`. Overwrite `.codex-local/PROJECT_STATUS.md` and append one compact `.codex-local/WORKLOG.md` entry with the remote URL, commit SHA, exact objective verification results, and any failure reason; keep both excluded. Stage only this plan, audit identity and trailers, then commit and push:

```powershell
git add -- docs/superpowers/plans/2026-08-10-05-github-publication.md
git commit -m "docs: record GitHub repository publication"
git push origin main
```

Expected: push succeeds; `.codex-local` and `AGENTS.md` remain excluded and do not appear in `git status`.

- [ ] **Step 7: Perform final remote and clean-export verification**

Run focused publication/release tests, `scripts/verify_claims.py`, security scan, `verify_public_boundary.py --git-tree HEAD`, and a final `scripts/clean_export.ps1 -Treeish HEAD` report at `D:\mvtec-ad2-release\github-publication-final-<short-sha>.json`. Wait for the final push GitHub Actions run and require `success`. Recheck:

```powershell
git status --short
git rev-parse HEAD
git rev-parse origin/main
gh api repos/kuotunyu/mvtec-ad2-inspection-platform/contributors --paginate --jq '.[].login'
gh repo view kuotunyu/mvtec-ad2-inspection-platform --json visibility,defaultBranchRef,description,homepageUrl,repositoryTopics,url
```

Expected: clean worktree; local HEAD equals `origin/main`; the only populated contributor is `kuotunyu`; metadata matches the design; final local and GitHub Actions gates pass.
