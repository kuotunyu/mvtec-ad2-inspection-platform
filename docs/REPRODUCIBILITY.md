# Reproducibility

## Synthetic quick check

The shortest public check requires no MVTec data, real weights, or GPU:

```powershell
uv sync --frozen
powershell -ExecutionPolicy Bypass -File scripts/docker_smoke.ps1
```

The script builds deterministic synthetic bundles in a temporary directory, starts the non-root API and worker containers, completes an inspection, verifies the image boundary, and removes its isolated database, artifact, and upload-spool volumes. Docker must have enough free storage for the configured multipart limit; with defaults the startup floor is `2 * 2 GiB + 25 MiB`.

## Python and frontend gates

From a clean checkout with Python 3.12, Node 24, `uv`, and Playwright Chromium available:

```powershell
uv sync --frozen --extra ml
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m "not gpu and not dataset" -q

npm ci --prefix apps/web
npm --prefix apps/web exec -- playwright install chromium
npm --prefix apps/web run verify
npm --prefix apps/web run e2e
```

When an API route or schema changes, regenerate the committed contract before running the gates. `tests/api` fails if `apps/web/openapi.json` drifts from the application, and `api:check` fails if the generated client drifts from the schema:

```powershell
uv run python scripts/export_openapi.py --output apps/web/openapi.json
npm --prefix apps/web run api:generate
```

Build the deterministic registry twice when investigating reproducibility; `tests/integration/test_demo_bundle.py` compares the entire byte tree.

```powershell
$env:INSPECTION_MODEL_ROOT = Join-Path ([IO.Path]::GetTempPath()) "mvtec-ad2-demo-models"
uv run python scripts/build_demo_bundle.py --output $env:INSPECTION_MODEL_ROOT
uv run python scripts/verify_contract_chain.py --registry-root $env:INSPECTION_MODEL_ROOT
powershell -ExecutionPolicy Bypass -File scripts/docker_smoke.ps1
powershell -ExecutionPolicy Bypass -File scripts/run_system_tests.ps1 -Repeat 3
```

## Publication gates

```powershell
uv run python scripts/render_docs_assets.py --check-manifest
uv run pytest tests/publication tests/release tests/security -q
uv run python scripts/verify_claims.py
uv run python scripts/security_scan.py --root .
uv run python scripts/verify_public_boundary.py --git-tree HEAD

uv build --out-dir dist
$releaseReport = Join-Path ([IO.Path]::GetTempPath()) "mvtec-ad2-release-python.json"
$releaseArgs = @("run", "python", "scripts/verify_release.py", "--source", ".", "--output", $releaseReport)
Get-ChildItem dist -File | Where-Object Name -Match '\.(?:whl|tar\.gz)$' | ForEach-Object {
    $releaseArgs += @("--archive", $_.FullName)
}
& uv @releaseArgs
```

The committed implementation, tests, evidence artifacts, release checklist, and Git history
are the authoritative execution record. Local agent plans and continuity notes are
intentionally excluded from the public repository.

## Dataset and GPU gates

Dataset and real-GPU commands require the verified external manifest, external run/model roots, the project GPU lease, and the pinned environment. Follow [EXPERIMENT_RUNBOOK.md](EXPERIMENT_RUNBOOK.md). Do not substitute synthetic success for real-model parity, and do not submit or publish without explicit authorization.
