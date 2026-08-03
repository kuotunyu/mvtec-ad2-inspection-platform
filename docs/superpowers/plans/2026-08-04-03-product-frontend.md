# MVTec AD 2 Product Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished, accessible inspection workstation that makes batch progress, anomaly evidence, human review, model provenance, and limitations understandable to an interviewer in one guided workflow.

**Architecture:** A React single-page application consumes only the generated FastAPI OpenAPI contract. TanStack Query owns server state and polling; page-local state owns display controls. The interface is responsive but optimized for a desktop review station, with keyboard-safe review actions and no inference logic in the browser.

**Tech Stack:** React 19, TypeScript strict mode, Vite, React Router, TanStack Query, generated OpenAPI client, Vitest, Testing Library, MSW, Playwright, axe-core, CSS Modules/design tokens.

## Global Constraints

- Use the `apps/web/openapi.json` generated in Plan 02 and fail CI when the client is stale.
- Display only `PASS` and `REVIEW` as model outcomes. `ACCEPT`, `REJECT`, and `UNCERTAIN` are visibly labeled human decisions.
- Never turn anomaly heatmaps into claims of defect classification, root cause, clinical certainty, or automated final rejection.
- Preserve partial success: one failed image must not hide usable results from the rest of a batch.
- Every action remains keyboard accessible; color is never the only status cue; dialogs manage focus.
- Preview untrusted image bytes only through backend artifact URLs. Escape names and notes; never inject report HTML into the DOM.
- Use synthetic fixtures for screenshots and public demos. Do not commit MVTec images or derived raw private predictions.
- Avoid a generic admin-template appearance. The visual language should resemble an industrial evidence workstation, not a marketing dashboard.
- Never deploy, publish, tag, release, or create a remote without explicit user authorization.

---

## Planned File Map

- `apps/web/package.json`, `apps/web/package-lock.json`, `apps/web/vite.config.ts`, `apps/web/tsconfig*.json`: deterministic frontend build.
- `apps/web/src/api/{generated,client,queries}.ts`: typed HTTP boundary.
- `apps/web/src/app/{App,router,providers}.tsx`: application shell.
- `apps/web/src/styles/{tokens,global}.css`: visual system.
- `apps/web/src/components/*`: status, evidence, progress, heatmap, and confirmation primitives.
- `apps/web/src/pages/{Dashboard,NewInspection,JobDetail,ReviewQueue,ModelEvidence}.tsx`: five product surfaces.
- `apps/web/src/test/*`: MSW handlers, fixtures, and render helpers.
- `apps/web/e2e/*`: browser workflow and accessibility checks.

### Task 1: Establish the typed frontend and API boundary

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/package-lock.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/tsconfig.app.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/index.html`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/vite-env.d.ts`
- Create: `apps/web/src/api/generated.ts`
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/scripts/generate-client.mjs`
- Test: `apps/web/src/api/client.test.ts`

**Interfaces:**
- Produces `api`, typed request/response shapes from OpenAPI, `ApiError`, and `requestId` propagation.
- Scripts: `npm run api:generate`, `api:check`, `typecheck`, `lint`, `test`, `build`, and `e2e`.

- [ ] **Step 1: Write client behavior tests before the client**

```tsx
it("maps the backend error envelope and keeps the request id", async () => {
  server.use(http.get("/api/v1/jobs", () => HttpResponse.json(
    { code: "database_busy", message: "Try again", request_id: "req-123" },
    { status: 503 },
  )));
  await expect(api.listJobs()).rejects.toMatchObject({
    code: "database_busy", requestId: "req-123", status: 503,
  });
});
```

- [ ] **Step 2: Run the client test and confirm the missing project fails**

Run: `cd apps/web; npm test -- --run src/api/client.test.ts`
Expected: FAIL because package configuration and client do not exist.

- [ ] **Step 3: Create strict TypeScript configuration and deterministic generation**

Generate types from `apps/web/openapi.json`; do not hand-maintain duplicate API interfaces. Generation writes to a temporary file and atomically replaces `generated.ts`. `api:check` regenerates and fails on a diff.

- [ ] **Step 4: Implement the HTTP wrapper**

Use same-origin `/api`, JSON parsing with content-type validation, abort signals, and multipart upload progress where supported. Do not retry mutations automatically. Retry idempotent reads only for transient network failures with a small bounded backoff.

- [ ] **Step 5: Run frontend foundation gates**

Run: `cd apps/web; npm ci`
Run: `cd apps/web; npm run api:check`
Run: `cd apps/web; npm run typecheck`
Run: `cd apps/web; npm test -- --run src/api/client.test.ts`
Expected: all pass.

- [ ] **Step 6: Commit the frontend foundation**

```powershell
git add apps/web
git commit -m "build(frontend): establish typed web client"
```

### Task 2: Create the workstation shell and accessible design system

**Files:**
- Create: `apps/web/src/app/App.tsx`
- Create: `apps/web/src/app/router.tsx`
- Create: `apps/web/src/app/providers.tsx`
- Create: `apps/web/src/styles/tokens.css`
- Create: `apps/web/src/styles/global.css`
- Create: `apps/web/src/components/AppShell.tsx`
- Create: `apps/web/src/components/StatusBadge.tsx`
- Create: `apps/web/src/components/EmptyState.tsx`
- Create: `apps/web/src/components/ErrorPanel.tsx`
- Test: `apps/web/src/app/App.test.tsx`
- Test: `apps/web/src/components/StatusBadge.test.tsx`

**Interfaces:**
- Routes: `/`, `/inspect`, `/jobs/:jobId`, `/review`, `/evidence`.
- `StatusBadge` requires both text and icon semantics for job, model, and human statuses.

- [ ] **Step 1: Write navigation and semantic-status tests**

```tsx
it("does not communicate review state by color alone", () => {
  render(<StatusBadge kind="model" value="REVIEW" />);
  expect(screen.getByText("Model: review required")).toBeVisible();
  expect(screen.getByTestId("status-icon")).toHaveAttribute("aria-hidden", "true");
});
```

- [ ] **Step 2: Run shell tests and confirm failure**

Run: `cd apps/web; npm test -- --run src/app/App.test.tsx src/components/StatusBadge.test.tsx`
Expected: FAIL because shell and components do not exist.

- [ ] **Step 3: Implement the industrial visual system**

Use a restrained graphite/slate surface palette, high-contrast light content panels, amber for review attention, cyan for model evidence, and red only for actual errors or human rejection. Use a compact sans-serif for controls and a monospaced numeric face for scores and hashes. Provide visible focus rings, reduced-motion support, 44-pixel interaction targets, and a skip link.

- [ ] **Step 4: Implement the responsive application shell**

Desktop uses persistent left navigation and a wide evidence canvas; narrow screens use a focus-managed menu. Show backend readiness and worker heartbeat as operational state, not decorative uptime. Route errors to a useful recovery page.

- [ ] **Step 5: Verify shell behavior and accessibility**

Run: `cd apps/web; npm test -- --run src/app src/components/StatusBadge.test.tsx`
Expected: navigation, active route, keyboard focus, reduced motion, and semantic status tests pass.

- [ ] **Step 6: Commit the shell**

```powershell
git add apps/web/src/app apps/web/src/styles apps/web/src/components
git commit -m "feat(frontend): add inspection workstation shell"
```

### Task 3: Build Dashboard and New Inspection

**Files:**
- Create: `apps/web/src/pages/Dashboard.tsx`
- Create: `apps/web/src/pages/NewInspection.tsx`
- Create: `apps/web/src/components/JobTable.tsx`
- Create: `apps/web/src/components/UploadDropzone.tsx`
- Create: `apps/web/src/components/UploadManifest.tsx`
- Create: `apps/web/src/api/queries.ts`
- Test: `apps/web/src/pages/Dashboard.test.tsx`
- Test: `apps/web/src/pages/NewInspection.test.tsx`

**Interfaces:**
- Dashboard displays queue summary, recent jobs, partial failures, review backlog, and active category champions.
- New Inspection accepts a category and image files or one archive, validates obvious client limits, then creates a server job.

- [ ] **Step 1: Write user-flow tests**

```tsx
it("creates a job and navigates to progress", async () => {
  renderApp("/inspect");
  await user.selectOptions(screen.getByLabelText("Component category"), "can");
  await user.upload(screen.getByLabelText("Inspection files"), [pngFile("a.png"), pngFile("b.png")]);
  await user.click(screen.getByRole("button", { name: "Start inspection" }));
  expect(await screen.findByText("2 images queued")).toBeVisible();
  expect(location.pathname).toMatch(/^\/jobs\//);
});
```

- [ ] **Step 2: Run page tests and confirm failure**

Run: `cd apps/web; npm test -- --run src/pages/Dashboard.test.tsx src/pages/NewInspection.test.tsx`
Expected: FAIL because both pages are absent.

- [ ] **Step 3: Implement honest dashboard summaries**

Separate system queue, model `REVIEW`, human unresolved, and errors. Never label the model review count as defects. Use explicit empty/loading/error states, bounded polling while jobs are active, and `aria-live="polite"` only for concise progress updates.

- [ ] **Step 4: Implement accessible batch upload**

Support drag/drop and standard file input. Show filename, size, local validation result, remove action, and total size. Treat client validation as convenience; surface backend rejections per file. Disable double submission and provide a retry path that does not create a hidden duplicate.

- [ ] **Step 5: Run page and accessibility tests**

Run: `cd apps/web; npm test -- --run src/pages/Dashboard.test.tsx src/pages/NewInspection.test.tsx`
Expected: loading, empty, partial error, upload, duplicate submit, keyboard, and screen-reader status cases pass.

- [ ] **Step 6: Commit Dashboard and ingestion UI**

```powershell
git add apps/web/src/pages apps/web/src/components/JobTable.tsx apps/web/src/components/UploadDropzone.tsx apps/web/src/components/UploadManifest.tsx apps/web/src/api/queries.ts
git commit -m "feat(frontend): add batch inspection intake"
```

### Task 4: Build Job Detail and anomaly evidence comparison

**Files:**
- Create: `apps/web/src/pages/JobDetail.tsx`
- Create: `apps/web/src/components/JobProgress.tsx`
- Create: `apps/web/src/components/ImageResultGrid.tsx`
- Create: `apps/web/src/components/ImageEvidenceDialog.tsx`
- Create: `apps/web/src/components/HeatmapCompare.tsx`
- Create: `apps/web/src/components/ScoreGauge.tsx`
- Test: `apps/web/src/pages/JobDetail.test.tsx`
- Test: `apps/web/src/components/HeatmapCompare.test.tsx`

**Interfaces:**
- Shows job status, completed/error counts, model bundle identity, threshold, per-image score/outcome, source/map/overlay comparison, and report downloads.
- `HeatmapCompare` supports side-by-side and keyboard-controlled reveal slider without drawing conclusions beyond the API record.

- [ ] **Step 1: Write progress and evidence tests**

```tsx
it("keeps successful results visible when one image failed", async () => {
  renderApp("/jobs/job-partial");
  expect(await screen.findByText("Completed with 1 image error")).toBeVisible();
  expect(screen.getByRole("img", { name: "Anomaly overlay for part-01" })).toBeVisible();
  expect(screen.getByText("Could not decode part-02")).toBeVisible();
});
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd apps/web; npm test -- --run src/pages/JobDetail.test.tsx src/components/HeatmapCompare.test.tsx`
Expected: FAIL because the evidence page is absent.

- [ ] **Step 3: Implement bounded progress polling and terminal refresh**

Poll while `QUEUED` or `RUNNING`, slow the interval when the tab is hidden, stop on terminal state, and allow manual refresh. Use the server revision to avoid stale status replacement.

- [ ] **Step 4: Implement the evidence gallery and dialog**

Cards display exact score, exact threshold, textual outcome, processing duration, and human state. The dialog provides original/map/overlay views, opacity control, accessible labels, previous/next navigation, artifact hashes, and a direct route into review. Preserve natural aspect ratio and never crop evidence by default.

- [ ] **Step 5: Verify partial, cancelled, and failed jobs**

Run: `cd apps/web; npm test -- --run src/pages/JobDetail.test.tsx src/components`
Expected: terminal states, missing artifacts, stale polling, slider keyboard control, and accessible dialog tests pass.

- [ ] **Step 6: Commit job evidence UI**

```powershell
git add apps/web/src/pages/JobDetail.tsx apps/web/src/components
git commit -m "feat(frontend): visualize inspection evidence"
```

### Task 5: Build the human Review Queue

**Files:**
- Create: `apps/web/src/pages/ReviewQueue.tsx`
- Create: `apps/web/src/components/ReviewWorkspace.tsx`
- Create: `apps/web/src/components/DecisionBar.tsx`
- Create: `apps/web/src/components/ReviewHistory.tsx`
- Test: `apps/web/src/pages/ReviewQueue.test.tsx`
- Test: `apps/web/src/components/DecisionBar.test.tsx`
- Test: `apps/web/src/components/ReviewHistory.test.tsx`

**Interfaces:**
- Filters unresolved model `REVIEW` items by category, age, and job.
- Saves one of `ACCEPT`, `REJECT`, `UNCERTAIN` with optional note and expected revision.
- Keyboard shortcuts work only inside the focused review workspace and require visible confirmation before mutation.

- [ ] **Step 1: Write safe decision tests**

```tsx
it("does not submit a keyboard decision before confirmation", async () => {
  renderApp("/review");
  await user.keyboard("r");
  expect(screen.getByRole("dialog", { name: "Confirm human rejection" })).toBeVisible();
  expect(reviewRequests()).toHaveLength(0);
});

it("refreshes after a revision conflict", async () => {
  renderApp("/review?fixture=conflict");
  await chooseAndConfirm("Uncertain");
  expect(await screen.findByText("This item was reviewed elsewhere")).toBeVisible();
});
```

- [ ] **Step 2: Run review tests and confirm failure**

Run: `cd apps/web; npm test -- --run src/pages/ReviewQueue.test.tsx src/components/DecisionBar.test.tsx`
Expected: FAIL because review components do not exist.

- [ ] **Step 3: Implement a deliberate review workflow**

Keep evidence visible beside actions. Display `Model outcome` and `Human decision` in separate panels. Require confirmation with the target filename and selected action; restore focus after close. Notes are plain text with length guidance. After success, keep a short undo-free receipt and advance only when the user requests it or enables an explicit preference.

- [ ] **Step 4: Implement conflict, offline, and retry states**

On `409`, retain the unsaved note, fetch current history, and ask the user to reassess. On a network error, do not optimistically label the item reviewed. Ensure repeated confirmation cannot create duplicate revisions.

- [ ] **Step 5: Run review and accessibility gates**

Run: `cd apps/web; npm test -- --run src/pages/ReviewQueue.test.tsx src/components/DecisionBar.test.tsx src/components/ReviewHistory.test.tsx`
Expected: decision, confirmation, shortcut scope, focus, conflict, retry, and history tests pass.

- [ ] **Step 6: Commit human review UI**

```powershell
git add apps/web/src/pages/ReviewQueue.tsx apps/web/src/components/ReviewWorkspace.tsx apps/web/src/components/DecisionBar.tsx apps/web/src/components/ReviewHistory.tsx apps/web/src/pages/ReviewQueue.test.tsx apps/web/src/components/DecisionBar.test.tsx
git commit -m "feat(frontend): add human anomaly review"
```

### Task 6: Build Model & Evidence and truthful benchmark presentation

**Files:**
- Create: `apps/web/src/pages/ModelEvidence.tsx`
- Create: `apps/web/src/components/ChampionMatrix.tsx`
- Create: `apps/web/src/components/MetricDefinition.tsx`
- Create: `apps/web/src/components/ProvenancePanel.tsx`
- Create: `apps/web/src/components/LimitationsPanel.tsx`
- Test: `apps/web/src/pages/ModelEvidence.test.tsx`
- Test: `apps/web/src/components/ChampionMatrix.test.tsx`

**Interfaces:**
- Shows one champion per category, bundle/hash/version, threshold provenance, public metric confidence intervals, private validation status, runtime profile, and explicit limitations.
- Metric labels include scope and direction, such as `Pixel AU-PRO (FPR ≤ 0.30, higher is better)`.

- [ ] **Step 1: Write claims and missing-evidence tests**

```tsx
it("labels an unevaluated private gate instead of inferring success", async () => {
  renderApp("/evidence?fixture=public-only");
  expect(await screen.findByText("Private evaluation: not submitted")).toBeVisible();
  expect(screen.queryByText(/production.ready/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run evidence tests and confirm failure**

Run: `cd apps/web; npm test -- --run src/pages/ModelEvidence.test.tsx src/components/ChampionMatrix.test.tsx`
Expected: FAIL because the evidence page is absent.

- [ ] **Step 3: Implement provenance-first evidence presentation**

Present category rows rather than a single global winner. Put confidence intervals next to estimates. Mark `GO`, `NO-GO under lighting shift`, or `not evaluated` only from the backend evidence contract. Link downloadable machine-readable evidence and reveal code/config/dataset/model identities without exposing local paths.

- [ ] **Step 4: Add limitations beside metrics**

State noncommercial dataset constraints, no defect-type classification, no automatic final rejection, threshold calibration scope, public selection/private validation separation, and hardware-specific latency. Keep limitations visible without requiring a modal.

- [ ] **Step 5: Verify evidence rendering**

Run: `cd apps/web; npm test -- --run src/pages/ModelEvidence.test.tsx src/components/ChampionMatrix.test.tsx`
Expected: public-only, private pass, mixed-lighting no-go, missing artifact, and responsive table cases pass.

- [ ] **Step 6: Commit model evidence UI**

```powershell
git add apps/web/src/pages/ModelEvidence.tsx apps/web/src/components/ChampionMatrix.tsx apps/web/src/components/MetricDefinition.tsx apps/web/src/components/ProvenancePanel.tsx apps/web/src/components/LimitationsPanel.tsx apps/web/src/pages/ModelEvidence.test.tsx apps/web/src/components/ChampionMatrix.test.tsx
git commit -m "feat(frontend): present model evidence and limits"
```

### Task 7: Verify the frontend as a release candidate

**Files:**
- Create: `apps/web/src/test/server.ts`
- Create: `apps/web/src/test/fixtures.ts`
- Create: `apps/web/src/test/render.tsx`
- Create: `apps/web/e2e/workstation.spec.ts`
- Create: `apps/web/e2e/accessibility.spec.ts`
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/scripts/verify-public-assets.mjs`

- [ ] **Step 1: Centralize deterministic synthetic fixtures**

Fixtures cover queued, running, complete, partial-error, failed, cancelled, unresolved review, resolved review, public-only evidence, private pass, and lighting-shift no-go. Images are visibly synthetic geometric parts and contain no MVTec pixels.

- [ ] **Step 2: Add a complete browser workflow test**

Use Playwright to create a synthetic batch, observe progress, inspect source/map/overlay, resolve one review with confirmation, download a report, and inspect the active champion. Assert the UI never calls a model outcome a final rejection.

- [ ] **Step 3: Add automated accessibility checks**

Run axe on all five pages in representative states, keyboard-traverse upload and review, verify focus restoration, and test at 200% zoom plus a 390-pixel viewport.

- [ ] **Step 4: Scan built assets for prohibited material**

`verify-public-assets.mjs` rejects MVTec category image hashes, common local absolute paths, secrets, source maps in production, oversized committed binaries, and unexpected remote analytics URLs.

- [ ] **Step 5: Run the clean frontend gate**

Run: `cd apps/web; npm ci`
Run: `cd apps/web; npm run api:check`
Run: `cd apps/web; npm run lint`
Run: `cd apps/web; npm run typecheck`
Run: `cd apps/web; npm test -- --run --coverage`
Run: `cd apps/web; npm run build`
Run: `cd apps/web; npm run verify:public-assets`
Run: `cd apps/web; npm run e2e` against the Plan 02 mock backend.
Expected: every command passes with no console errors, failed requests, accessibility violations, or prohibited assets.

- [ ] **Step 6: Commit frontend verification**

```powershell
git add apps/web
git commit -m "test(frontend): verify inspection workstation"
```
