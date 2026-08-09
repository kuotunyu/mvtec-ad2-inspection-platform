param(
    [ValidateRange(1, 10)]
    [int]$Repeat = 3
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$before = git -C $repoRoot status --porcelain=v1 --untracked-files=all

for ($iteration = 1; $iteration -le $Repeat; $iteration++) {
    $projectName = "mvtecad2system$iteration"
    $port = 18100 + $iteration
    $tempBase = [IO.Path]::GetFullPath([IO.Path]::Combine([IO.Path]::GetTempPath(), "$projectName-$PID"))
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (-not $tempBase.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing unsafe temporary path: $tempBase"
    }
    New-Item -ItemType Directory -Path $tempBase -Force | Out-Null
    $env:INSPECTION_MODEL_ROOT = Join-Path $tempBase "models"
    $env:INSPECTION_PORT = "$port"
    $env:SOURCE_REVISION = (git -C $repoRoot rev-parse HEAD)
    $env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:$port"
    try {
        Push-Location $repoRoot
        uv run pytest tests/system -q
        uv run python scripts/build_demo_bundle.py --output $env:INSPECTION_MODEL_ROOT
        docker compose -p $projectName up -d --build --wait --wait-timeout 120
        Push-Location (Join-Path $repoRoot "apps/web")
        npx playwright test e2e/docker-workstation.spec.ts --config=playwright.docker.config.ts
        Pop-Location
        Write-Output "System iteration $iteration/$Repeat PASS"
    }
    finally {
        if ((Get-Location).Path -ne $repoRoot) { Pop-Location }
        $savedPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        docker compose -p $projectName down --volumes --remove-orphans 2>$null | Out-Null
        $ErrorActionPreference = $savedPreference
        if (Test-Path -LiteralPath $tempBase) {
            Remove-Item -LiteralPath $tempBase -Recurse -Force
        }
    }
}

$after = git -C $repoRoot status --porcelain=v1 --untracked-files=all
if (Compare-Object $before $after) { throw "System tests changed the worktree" }
Write-Output "Repeated system gate PASS: $Repeat isolated runs"
