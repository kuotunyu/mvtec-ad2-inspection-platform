# Reproducibility

## CPU and product gates

From a clean checkout with Python and Node available:

```powershell
uv sync --extra ml --frozen
uv run ruff format --check src apps/api tests scripts
uv run ruff check src apps/api tests scripts
uv run mypy
uv run pytest -m "not gpu and not dataset" -q

Push-Location apps/web
npm ci
npm run api:check
npm run lint
npm run typecheck
npm run test -- --run
npm run build
Pop-Location
```

Build the deterministic registry twice when investigating reproducibility; `tests/integration/test_demo_bundle.py` compares the entire byte tree.

```powershell
$env:INSPECTION_MODEL_ROOT = "D:\mvtec-ad2-demo-models"
uv run python scripts/build_demo_bundle.py --output $env:INSPECTION_MODEL_ROOT
uv run python scripts/verify_contract_chain.py --registry-root $env:INSPECTION_MODEL_ROOT
powershell -ExecutionPolicy Bypass -File scripts/docker_smoke.ps1
powershell -ExecutionPolicy Bypass -File scripts/run_system_tests.ps1 -Repeat 3
```

## Publication gates

```powershell
uv run python scripts/render_docs_assets.py --check
uv run pytest tests/publication -q
uv run python scripts/verify_claims.py
uv run python scripts/security_scan.py --root .
uv run python scripts/verify_public_boundary.py --git-tree HEAD
```

The approved design and four implementation plans are the authoritative execution record. Local continuity files are intentionally excluded from Git.

## Dataset and GPU gates

Dataset and real-GPU commands require the verified external manifest, external run/model roots, the project GPU lease, and the pinned environment. Follow the foundation handoff and private-evaluation runbook. Do not substitute synthetic success for real-model parity, and do not submit or publish without explicit authorization.
