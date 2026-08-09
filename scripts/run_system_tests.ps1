param(
    [ValidateRange(1, 10)]
    [int]$Repeat = 3
)

$ErrorActionPreference = "Stop"
function Invoke-NativeChecked {
    param([string]$Command, [string[]]$Arguments, [string]$Label)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$isGitWorktree = Test-Path -LiteralPath (Join-Path $repoRoot ".git")
[string[]]$before = if ($isGitWorktree) { @(git -C $repoRoot status --porcelain=v1 --untracked-files=all) } else { @() }
$sourceRevision = $env:SOURCE_REVISION
if (-not $sourceRevision) {
    if (-not $isGitWorktree) { throw "SOURCE_REVISION is required outside a Git worktree" }
    $sourceRevision = git -C $repoRoot rev-parse HEAD
}

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
    $env:SOURCE_REVISION = $sourceRevision
    $env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:$port"
    $env:INSPECTION_DOCKER_E2E = "1"
    try {
        Push-Location $repoRoot
        Invoke-NativeChecked "uv" @("run", "pytest", "tests/system", "-q") "system tests"
        Invoke-NativeChecked "uv" @("run", "python", "scripts/build_demo_bundle.py", "--output", $env:INSPECTION_MODEL_ROOT) "demo bundle build"
        Invoke-NativeChecked "docker" @("compose", "-p", $projectName, "up", "-d", "--build", "--wait", "--wait-timeout", "120") "Docker system startup"
        Push-Location (Join-Path $repoRoot "apps/web")
        Invoke-NativeChecked "npx" @("playwright", "test", "e2e/docker-workstation.spec.ts", "--config=playwright.docker.config.ts") "Docker browser workflow"
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
        Remove-Item Env:INSPECTION_DOCKER_E2E -ErrorAction SilentlyContinue
    }
}

if ($isGitWorktree) {
    [string[]]$after = @(git -C $repoRoot status --porcelain=v1 --untracked-files=all)
    if (Compare-Object -ReferenceObject $before -DifferenceObject $after) { throw "System tests changed the worktree" }
}
Write-Output "Repeated system gate PASS: $Repeat isolated runs"
