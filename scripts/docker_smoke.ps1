param(
    [string]$ProjectName = "mvtecad2smoke",
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"
function Invoke-NativeChecked {
    param([string]$Command, [string[]]$Arguments, [string]$Label)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$isGitWorktree = Test-Path -LiteralPath (Join-Path $repoRoot ".git")
$before = if ($isGitWorktree) { git -C $repoRoot status --porcelain=v1 --untracked-files=all } else { $null }
$tempBase = [IO.Path]::GetFullPath([IO.Path]::Combine([IO.Path]::GetTempPath(), "$ProjectName-$PID"))
if (-not $tempBase.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe temporary path: $tempBase"
}
New-Item -ItemType Directory -Path $tempBase -Force | Out-Null
$env:INSPECTION_MODEL_ROOT = Join-Path $tempBase "models"
$env:INSPECTION_PORT = "$Port"
if (-not $env:SOURCE_REVISION) {
    if (-not $isGitWorktree) { throw "SOURCE_REVISION is required outside a Git worktree" }
    $env:SOURCE_REVISION = git -C $repoRoot rev-parse HEAD
}

try {
    Push-Location $repoRoot
    Invoke-NativeChecked "uv" @("run", "python", "scripts/build_demo_bundle.py", "--output", $env:INSPECTION_MODEL_ROOT) "demo bundle build"
    Invoke-NativeChecked "docker" @("compose", "-p", $ProjectName, "build", "--pull") "Docker image build"
    Invoke-NativeChecked "docker" @("compose", "-p", $ProjectName, "up", "-d", "--wait", "--wait-timeout", "120") "Docker startup"

    $apiUser = Invoke-NativeChecked "docker" @("inspect", "$ProjectName-api-1", "--format", "{{.Config.User}}") "API identity inspection"
    $workerUser = Invoke-NativeChecked "docker" @("inspect", "$ProjectName-worker-1", "--format", "{{.Config.User}}") "worker identity inspection"
    if ($apiUser -match '^(0|root)(:|$)' -or $workerUser -match '^(0|root)(:|$)') {
        throw "Container unexpectedly runs as root"
    }

    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health/ready"
    if ($health.status -ne "ready") { throw "API readiness failed" }
    $homeResponse = Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing
    if ($homeResponse.StatusCode -ne 200) { throw "Frontend was not served" }

    $fixture = Join-Path $tempBase "clean-control.png"
    Copy-Item -LiteralPath (Join-Path $repoRoot "fixtures/public-demo/images/clean-control.png") -Destination $fixture
    $response = Invoke-NativeChecked "curl.exe" @("--fail", "--silent", "--show-error", "-F", "category=can", "-F", "files=@$fixture;type=image/png", "http://127.0.0.1:$Port/api/v1/jobs") "synthetic upload"
    $job = $response | ConvertFrom-Json
    $deadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 500
        $detail = Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/jobs/$($job.id)"
    } while ($detail.status -notin @("COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED") -and (Get-Date) -lt $deadline)
    if ($detail.status -ne "COMPLETED") { throw "Synthetic job did not complete: $($detail.status)" }
    if ($detail.images.Count -ne 1 -or -not $detail.images[0].model_outcome) {
        throw "Synthetic evidence is incomplete"
    }

    $workerLogs = Invoke-NativeChecked "docker" @("compose", "-p", $ProjectName, "logs", "worker") "worker log inspection"
    if ($workerLogs -notmatch "worker heartbeat") { throw "Worker heartbeat was not logged" }

    foreach ($image in @("$ProjectName-api", "$ProjectName-worker")) {
        $inventory = Invoke-NativeChecked "docker" @("run", "--rm", "--entrypoint", "sh", $image, "-c", "find /app -type f -print") "image inventory"
        if ($inventory -match '(\.git|\.env|MVTec_AD_2|checkpoints|\.pt$|\.ckpt$|sourceMappingURL)') {
            throw "Private or developer material found in $image"
        }
    }
    Write-Output "Docker smoke PASS: non-root API/worker, ready frontend, completed synthetic job"
}
finally {
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker compose -p $ProjectName down --volumes --remove-orphans 2>$null | Out-Null
    $ErrorActionPreference = $savedPreference
    Pop-Location
    if (Test-Path -LiteralPath $tempBase) {
        Remove-Item -LiteralPath $tempBase -Recurse -Force
    }
}

if ($isGitWorktree) {
    $after = git -C $repoRoot status --porcelain=v1 --untracked-files=all
    if (Compare-Object $before $after) { throw "Docker smoke changed the worktree" }
}
