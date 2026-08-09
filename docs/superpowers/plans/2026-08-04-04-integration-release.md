# MVTec AD 2 Integration and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate experiments, backend, worker, and frontend into a reproducible local product; verify crash recovery, security, Docker operation, evidence integrity, public boundaries, and release claims before any publication decision.

**Architecture:** One versioned contract connects offline champion selection to online inference and human review. A synthetic public-demo bundle drives deterministic CI, while real champion bundles remain external and hash-verified. Multi-stage Docker images package the web assets, API, and worker without bundling data or weights; a release verifier recomputes every public claim from sanitized evidence.

**Tech Stack:** Python 3.12, React/Vite, FastAPI, SQLite, Docker/Compose, GitHub Actions, Playwright, CycloneDX SBOM tooling pinned by Python/npm lockfiles, pytest, Ruff, mypy.

## Global Constraints

- Execute only after Plans 01–03 are complete and their focused gates pass.
- Keep the dataset, official test images, weights, checkpoints, raw predictions, databases, and user uploads outside Git and outside release archives/images.
- Use deterministic synthetic fixtures and a clearly labeled mock bundle for CI and screenshots.
- Docker may run CPU smoke tests with the mock bundle. A real GPU smoke is a separate local gate and must not claim portability beyond the tested RTX 4090 environment.
- Official private and private-mixed results validate frozen category champions only. Never tune from them.
- Local release candidate is allowed after public/product gates. `v1.0.0` is allowed only after the official private gate and explicit user authorization.
- If private mixed-lighting evidence materially fails the frozen criterion, publish the honest verdict `NO-GO under lighting shift`; do not hide it or silently recalibrate.
- Never push, open a PR, publish, create/move a tag, create a Release, deploy, upload to Hugging Face, or submit to the official server without explicit user authorization.

---

## Planned File Map

- `fixtures/public-demo/*`: synthetic inputs and sanitized expected outputs.
- `scripts/build_demo_bundle.py`: deterministic mock model bundle.
- `scripts/verify_contract_chain.py`: experiment-to-product contract verification.
- `deploy/docker/{api.Dockerfile,worker.Dockerfile,entrypoint-api.sh,entrypoint-worker.sh}`: non-root images.
- `compose.yaml`: API, worker, and persistent runtime volumes.
- `.dockerignore`: release boundary.
- `tests/system/*`: API/worker/browser and recovery tests.
- `scripts/security_scan.py`, `scripts/verify_public_boundary.py`, `scripts/verify_release.py`: fail-closed gates.
- `.github/workflows/ci.yml`: CPU, frontend, Docker, and publication verification.
- `README.md`, `docs/{ARCHITECTURE,CASE_STUDY,MODEL_CARD,DATA_CARD,SECURITY,LIMITATIONS,REPRODUCIBILITY,REMOTE_SETUP}.md`: portfolio narrative and evidence.

### Task 1: Connect the offline contracts to product inference

**Files:**
- Create: `scripts/build_demo_bundle.py`
- Create: `scripts/verify_contract_chain.py`
- Create: `fixtures/public-demo/manifest.json`
- Create: `fixtures/public-demo/images/*.png`
- Create: `fixtures/public-demo/expected/*.json`
- Test: `tests/ml_integrity/test_contract_chain.py`
- Test: `tests/integration/test_demo_bundle.py`

**Interfaces:**
- `build_demo_bundle(output: Path) -> ModelBundleManifest` creates one explicit synthetic-CI mock bundle per category; mock bundles are never champions.
- `verify_contract_chain(evidence_root, registry_root) -> VerificationReport` proves dataset → run → prediction → metric → selection → bundle → product compatibility.

- [x] **Step 1: Write cross-contract failure tests**

```python
@pytest.mark.parametrize(
    "mutation",
    ["dataset_hash", "metric_contract", "preprocess_hash", "threshold", "weight_hash"],
)
def test_contract_chain_rejects_identity_drift(valid_chain: EvidenceChain, mutation: str) -> None:
    valid_chain.mutate(mutation)
    report = verify_contract_chain(valid_chain.evidence_root, valid_chain.registry_root)
    assert not report.ok
    assert mutation in report.error_codes
```

- [x] **Step 2: Run integrity tests and confirm failure**

Run: `uv run pytest tests/ml_integrity/test_contract_chain.py -q`
Expected: FAIL because the verifier and demo bundle do not exist.

- [x] **Step 3: Create visibly synthetic public demo fixtures**

Generate geometric metal-like shapes, scratches, dents, and clean controls from fixed seeds. Add a small visible `SYNTHETIC DEMO` mark outside the evaluated object region. Manifest each image hash, generator version, seed, intended mock outcome, and CC0 project-generated status. No MVTec pixel may be used as source or texture.

- [x] **Step 4: Build the mock bundle and contract-chain verifier**

The mock bundle has the same manifest shape as a real champion but records `runtime_kind="mock"`, `model_family=null`, `evaluation_scope="synthetic-ci-only"`, and no public benchmark score. In demo mode the verifier accepts only that restricted mock form; in normal mode it rejects any active bundle that was not selected by the frozen public artifact. It follows hashes in both directions and rejects dangling evidence.

- [x] **Step 5: Run deterministic and tamper gates**

Run: `uv run python scripts/build_demo_bundle.py --output "$env:INSPECTION_MODEL_ROOT"` twice and compare manifests.
Run: `uv run pytest tests/ml_integrity/test_contract_chain.py tests/integration/test_demo_bundle.py -q`
Expected: byte-stable manifests and all valid/tampered cases pass.

- [x] **Step 6: Commit only synthetic fixtures and tooling**

```powershell
git add scripts/build_demo_bundle.py scripts/verify_contract_chain.py fixtures/public-demo tests/ml_integrity/test_contract_chain.py tests/integration/test_demo_bundle.py
git commit -m "test(system): add synthetic evidence fixtures"
```

### Task 2: Package non-root API and worker containers

**Files:**
- Create: `.dockerignore`
- Create: `deploy/docker/api.Dockerfile`
- Create: `deploy/docker/worker.Dockerfile`
- Create: `deploy/docker/entrypoint-api.sh`
- Create: `deploy/docker/entrypoint-worker.sh`
- Create: `compose.yaml`
- Create: `tests/container/test_image_contract.py`
- Create: `scripts/docker_smoke.ps1`

**Interfaces:**
- API image serves built frontend and `/api`; worker image runs `inspection-worker serve`.
- Compose mounts named runtime volumes and an explicit read-only model registry; no data or model downloads happen at container startup.

- [x] **Step 1: Write static container-contract tests**

```python
def test_images_run_as_non_root(dockerfiles: list[Path]) -> None:
    for dockerfile in dockerfiles:
        assert re.search(r"^USER\s+(?!0\b|root\b)\S+", dockerfile.read_text(), re.MULTILINE)

def test_context_excludes_private_material() -> None:
    rules = Path(".dockerignore").read_text()
    for required in ["data", "runtime", "artifacts", "checkpoints", ".env", "*.pt", "*.ckpt"]:
        assert required in rules
```

- [x] **Step 2: Run container tests and confirm failure**

Run: `uv run pytest tests/container/test_image_contract.py -q`
Expected: FAIL because Docker files do not exist.

- [x] **Step 3: Implement deterministic multi-stage images**

Pin base images by digest after checking supported upstream versions. Build frontend with `npm ci`, Python wheels with the frozen lock, copy only runtime files, create an unprivileged UID, add read-only filesystem compatibility, and include OCI labels for source revision and license. Do not place CUDA, training extras, Git history, or developer caches in the API image.

- [x] **Step 4: Define health-aware Compose services**

API waits for migrations and exposes liveness/readiness. Worker waits for database readiness and the registry mount. Use init, stop grace periods, bounded log rotation, and restart-on-failure. SQLite and artifacts use persistent named volumes; API and worker share only required volumes.

- [x] **Step 5: Build and run the CPU smoke**

Run: `powershell -ExecutionPolicy Bypass -File scripts/docker_smoke.ps1`
Expected: clean-context builds succeed, images run non-root, API becomes ready, worker heartbeat appears, a synthetic job completes, JSON report hashes verify, containers stop cleanly, and no repository files change.

- [x] **Step 6: Inspect image contents and commit packaging**

Run: `uv run pytest tests/container/test_image_contract.py -q`
Run: scan both image file lists for `.git`, `.env`, MVTec names, checkpoints, raw runs, source maps, and local paths.
Expected: none found.

```powershell
git add .dockerignore deploy/docker compose.yaml tests/container scripts/docker_smoke.ps1
git commit -m "build(container): package inspection services"
```

### Task 3: Prove the complete workflow and crash recovery

**Files:**
- Create: `tests/system/test_full_workflow.py`
- Create: `tests/system/test_worker_recovery.py`
- Create: `tests/system/test_partial_failure.py`
- Create: `tests/system/test_report_roundtrip.py`
- Create: `apps/web/e2e/docker-workstation.spec.ts`
- Create: `scripts/run_system_tests.ps1`

- [x] **Step 1: Write the full product acceptance test**

Start isolated API and worker processes with temporary roots and the mock bundle. Upload a batch containing synthetic pass, synthetic review, and corrupt input; assert `COMPLETED_WITH_ERRORS`, valid evidence for good inputs, one image error, human review revision, and byte-valid report downloads.

- [x] **Step 2: Add failure injection at durable boundaries**

Kill the worker after artifact write but before database commit, after database commit, and during heartbeat. Restart it and assert no duplicate predictions, no orphan reference, no state regression, and one final audit history. Simulate unavailable artifact storage and tampered bundle; both fail closed with stable error codes.

- [x] **Step 3: Add a real browser-to-container test**

The browser creates the batch, watches progress, opens source/map/overlay, resolves the review, downloads JSON, and visits Model & Evidence. Capture no screenshots from MVTec data. Assert network responses contain no local absolute paths or tracebacks.

- [x] **Step 4: Run repeated clean system gates**

Run: `powershell -ExecutionPolicy Bypass -File scripts/run_system_tests.ps1 -Repeat 3`
Expected: three isolated runs pass; each cleans only its named temporary containers/volumes and leaves the worktree unchanged.

- [x] **Step 5: Commit system verification**

```powershell
git add tests/system apps/web/e2e/docker-workstation.spec.ts scripts/run_system_tests.ps1
git commit -m "test(system): verify resilient inspection workflow"
```

### Task 4: Harden security, privacy, provenance, and deletion boundaries

**Files:**
- Create: `scripts/security_scan.py`
- Create: `scripts/verify_public_boundary.py`
- Create: `tests/security/test_api_boundaries.py`
- Create: `tests/security/test_archive_bombs.py`
- Create: `tests/security/test_logs.py`
- Create: `tests/security/test_deletion_scope.py`
- Create: `docs/SECURITY.md`

**Interfaces:**
- `security_scan.py --root PATH` emits a machine-readable report and nonzero exit on high-severity findings.
- `verify_public_boundary.py --git-tree HEAD` inspects tracked files and built distributions/images.

- [x] **Step 1: Add adversarial API and archive tests**

Cover path traversal, symlinks, decompression bombs, polyglot files, malformed images, oversize bodies, Unicode filename tricks, duplicate keys, invalid UUIDs, HTML/CSV injection, request-ID log injection, cancelled upload, and concurrent review conflicts.

- [x] **Step 2: Add log and error-boundary assertions**

Capture logs from upload, inference exception, review note, bundle failure, and request validation. Reject raw image bytes, notes, full external exceptions, filesystem roots, cookies, authorization values, environment secrets, or unsanitized line breaks. Public errors expose stable code, safe message, and request ID only.

- [x] **Step 3: Add deletion-scope tests**

Resolve every target through database references and verify its final absolute path remains under the configured artifact root. Test symlink substitution and repeated deletion. Never use wildcard or recursive deletion against a configured root.

- [x] **Step 4: Implement repository, archive, and image scanners**

Scan tracked files, wheel, sdist, frontend dist, Docker contexts, and image inventories for secrets, large binaries, MVTec/raw-prediction patterns, runtime databases, `.env`, checkpoints, absolute Windows/Linux paths, unsafe license claims, and unpinned remote scripts.

- [x] **Step 5: Run the security gate**

Run: `uv run pytest tests/security -q`
Run: `uv run python scripts/security_scan.py --root .`
Run: `uv run python scripts/verify_public_boundary.py --git-tree HEAD`
Expected: all adversarial tests pass and scanners report zero high-severity violations.

- [x] **Step 6: Commit hardening**

```powershell
git add scripts/security_scan.py scripts/verify_public_boundary.py tests/security docs/SECURITY.md
git commit -m "fix(security): harden public inspection boundaries"
```

### Task 5: Create recomputable portfolio documentation

**Files:**
- Create: `README.md`
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/CASE_STUDY.md`
- Create: `docs/MODEL_CARD.md`
- Modify: `docs/DATA_CARD.md`
- Create: `docs/LIMITATIONS.md`
- Create: `docs/REPRODUCIBILITY.md`
- Create: `docs/REMOTE_SETUP.md`
- Create: `docs/assets/architecture.svg`
- Create: `docs/assets/workflow.svg`
- Create: `docs/assets/screenshots/*.webp`
- Create: `scripts/render_docs_assets.py`
- Create: `scripts/verify_claims.py`
- Test: `tests/publication/test_docs.py`
- Test: `tests/publication/test_claims.py`

- [x] **Step 1: Write documentation-verifier tests before public prose**

```python
def test_every_numeric_claim_resolves_to_sanitized_evidence(public_docs: list[Path]) -> None:
    claims = extract_metric_claims(public_docs)
    assert claims
    assert all(claim.resolves_and_matches() for claim in claims)

def test_docs_never_call_review_a_defect(public_docs: list[Path]) -> None:
    forbidden = re.compile(r"(?:detected|confirmed) defect", re.IGNORECASE)
    assert not any(forbidden.search(path.read_text()) for path in public_docs)
```

- [x] **Step 2: Run publication tests and confirm failure**

Run: `uv run pytest tests/publication -q`
Expected: FAIL because documentation and verifier do not exist.

- [x] **Step 3: Write the README around one interview narrative**

Opening: a product screenshot using synthetic fixtures, one-sentence problem, and three honest proof points. Then show the batch-to-review workflow, architecture, public benchmark and confidence intervals, frozen champion matrix, private status, resilience/security evidence, local demo, reproducibility, limitations, and interview talking points. Do not lead with an exhaustive tool list.

- [x] **Step 4: Document model and data governance**

MODEL_CARD distinguishes PatchCore, EfficientAD, Dinomaly, per-category champions, calibration, private gate, operational decision semantics, and failure modes. DATA_CARD records the official source URL, archive byte count/hash, eight categories, split policy, CC BY-NC-SA 4.0 restriction, and explicit statement that data is not redistributed. SECURITY includes threat model, accepted risks, retention, and local single-user scope.

- [x] **Step 5: Generate diagrams and screenshots reproducibly**

Render architecture and workflow from text-controlled sources. Capture the five UI pages only with the synthetic demo bundle and stable viewport. Store generation commands and asset hashes. Ensure screenshot alternative text describes the workflow and does not imply real production deployment.

- [x] **Step 6: Bind public claims to evidence**

`verify_claims.py` maps every metric table cell, latency, VRAM, artifact size, test count, and evaluation status to a sanitized artifact by key and hash. Missing/private-not-run values render `not evaluated`, never zero or success. Limit copied raw experiment detail to non-sensitive aggregate evidence.

- [x] **Step 7: Run documentation gates and commit**

Run: `uv run python scripts/render_docs_assets.py --check`
Run: `uv run pytest tests/publication -q`
Run: `uv run python scripts/verify_claims.py`
Expected: all links, assets, licenses, numeric claims, and prohibited-phrase checks pass.

```powershell
git add README.md docs scripts/render_docs_assets.py scripts/verify_claims.py tests/publication
git commit -m "docs: present industrial inspection evidence"
```

### Task 6: Add reproducible CI and clean-export verification

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `scripts/clean_export.ps1`
- Create: `scripts/verify_release.py`
- Create: `tests/release/test_release.py`
- Modify: `pyproject.toml`
- Modify: `apps/web/package.json`

**Interfaces:**
- CI jobs: `python`, `frontend`, `publication`, `docker`, and `system`.
- `verify_release.py --source PATH` creates a JSON release-verification report from a committed export directory.

- [x] **Step 1: Write clean-export failure tests**

Cover untracked private files beside package code, stale OpenAPI client, dirty generated assets, uncommitted numeric claims, forbidden archive entries, missing license, mutable model references, and oversized binaries.

- [x] **Step 2: Implement CI with least privilege and pinned actions**

Use read-only contents permission, commit-SHA-pinned actions, dependency caches keyed by lockfiles, no secrets for pull-request tests, timeouts, concurrency cancellation, and uploaded verification reports. CI uses only synthetic fixtures and the mock bundle; GPU and official dataset jobs remain documented local gates.

- [x] **Step 3: Implement a committed-snapshot export**

Export tracked files from `HEAD` into a fresh temporary directory, install Python and frontend dependencies from locks, run unit/API/integration/apps/web/publication tests, build distributions and images, inspect their contents, run the mock system smoke, and remove only the verified temporary directory/container names.

- [x] **Step 4: Run the complete local CPU release gate**

Run: `powershell -ExecutionPolicy Bypass -File scripts/clean_export.ps1`
Expected: a fresh committed export passes installs, quality, tests, frontend build, Python build, wheel smoke, sdist scan, Docker build/health, system workflow, claims, and public-boundary verification.

- [x] **Step 5: Commit CI and release verification**

```powershell
git add .github scripts/clean_export.ps1 scripts/verify_release.py tests/release pyproject.toml uv.lock apps/web/package.json apps/web/package-lock.json
git commit -m "ci: verify clean portfolio release"
```

### Task 7: Run real local GPU serving and performance gates

**Files:**
- Create: `scripts/gpu_product_smoke.py`
- Create: `scripts/benchmark_serving.py`
- Create: `tests/gpu/test_real_bundle_serving.py`
- Create: `docs/assets/evidence/serving-benchmark.json`

- [x] **Step 1: Wait for exclusive access to the RTX 4090**

Check the shared GPU lock from Plan 01 and system process utilization. Do not interrupt another formal experiment. Acquire the lock with project/run identity and record GPU model, driver, CUDA, PyTorch, Anomalib, power mode, and code SHA.

- [x] **Step 2: Smoke every category champion through the product runtime**

For each of eight frozen bundles, load the model in a clean worker process, infer a permitted local test input, verify prediction/map/overlay/report contracts, release GPU memory, and prove another category can load. Do not commit input images or raw private outputs.

- [x] **Step 3: Benchmark serving behavior**

Measure cold start, warmup, per-image p50/p95 latency at batch size 1, sustained throughput, peak allocated/reserved VRAM, CPU fallback latency where supported, artifact size, and process RSS. Use fixed repetitions and report setup separately from inference. A GPU out-of-memory or incompatible export is a release blocker for that bundle.

- [x] **Step 4: Sanitize and verify the serving artifact**

Write aggregate results only, including environment/config identities and confidence intervals where meaningful. Reject local paths, raw image identifiers, and private labels. Bind the artifact hash into the evidence endpoint and docs verifier.

- [x] **Step 5: Run regression gates and commit sanitized evidence**

Run: `uv run pytest tests/gpu/test_real_bundle_serving.py -m gpu -q`
Run: `uv run python scripts/benchmark_serving.py --registry "$env:INSPECTION_MODEL_ROOT" --output docs/assets/evidence/serving-benchmark.json`
Run: `uv run python scripts/verify_claims.py`
Expected: all category bundles pass and the sanitized artifact matches documentation.

```powershell
git add scripts/gpu_product_smoke.py scripts/benchmark_serving.py tests/gpu/test_real_bundle_serving.py docs/assets/evidence/serving-benchmark.json
git commit -m "perf(inference): publish serving evidence"
```

### Task 8: Freeze the local release candidate and prepare the authorized private gate

**Files:**
- Create: `CHANGELOG.md`
- Create: `docs/RELEASE_CHECKLIST.md`
- Create: `docs/assets/evidence/release-verification.json`
- Modify: `docs/REMOTE_SETUP.md`

- [x] **Step 1: Recompute every required gate from committed `HEAD`**

Run the Plan 01 experiment verifier, Plan 02 backend gate, Plan 03 frontend gate, contract-chain verifier, security/public-boundary scanners, GPU product smoke, and clean-export release gate. Do not reuse a pass from a different SHA.

- [x] **Step 2: Classify the candidate truthfully**

The allowed local statuses are:

- `BLOCKED`: a correctness, safety, reproducibility, or evidence gate failed.
- `PUBLIC-RC`: public benchmark, product, Docker, security, documentation, and GPU serving gates pass; official private evaluation is not completed.
- `PRIVATE-NO-GO`: frozen private or mixed-lighting criterion materially fails.
- `V1-CANDIDATE`: all gates, including the frozen official private validation, pass.

- [x] **Step 3: Prepare but do not execute the official submission handoff**

Document exact bundle hashes, official upload files, expected category mapping, no-retuning rule, capture procedure, and result-import verifier. Stop and request explicit user authorization before any official server submission. After results return, import them once, preserve raw external evidence outside Git, commit only sanitized aggregates, and rerun claims verification.

- [x] **Step 4: Write the release verification artifact and changelog**

Include `HEAD`, lock hashes, dataset manifest hash, champion matrix hash, model bundle hashes, sanitized metric artifacts, test summaries, Docker image identities, public scan result, GPU environment, private status, known limitations, and next authorized action.

- [x] **Step 5: Commit the local candidate without publishing**

```powershell
git add CHANGELOG.md docs/RELEASE_CHECKLIST.md docs/REMOTE_SETUP.md docs/assets/evidence/release-verification.json
git commit -m "chore(release): freeze local inspection candidate"
```

- [x] **Step 6: Stop at the publication boundary**

Confirm the worktree is clean and summarize commits, verification evidence, candidate status, unresolved limitations, disk/GPU artifacts, and exact next decision. Do not push, create a remote, open a PR, create or move a tag, create a GitHub Release, deploy, upload to Hugging Face, or submit official predictions.
