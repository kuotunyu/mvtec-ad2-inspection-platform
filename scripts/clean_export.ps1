param(
    [string]$ReportPath,
    [string]$Treeish = "HEAD"
)

$ErrorActionPreference = "Stop"
function Invoke-NativeChecked {
    param([string]$Command, [string[]]$Arguments, [string]$Label)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE" }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$revision = & git -C $repoRoot rev-parse $Treeish
if ($LASTEXITCODE -ne 0 -or -not $revision) { throw "Unable to resolve source tree: $Treeish" }

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$leaf = "m2ce-$PID-$([Guid]::NewGuid().ToString('N').Substring(0, 8))"
$tempBase = [IO.Path]::GetFullPath([IO.Path]::Combine($tempRoot, $leaf))
if (-not $tempBase.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
    -not ([IO.Path]::GetFileName($tempBase)).StartsWith("m2ce-")) {
    throw "Refusing unsafe temporary path: $tempBase"
}
$exportRoot = Join-Path $tempBase "source"
$archivePath = Join-Path $tempBase "source.tar"
$verificationPath = Join-Path $tempBase "release-verification.json"
$pythonSbom = Join-Path $tempBase "sbom-python.cdx.json"
$nodeSbom = Join-Path $tempBase "sbom-node.cdx.json"
$wheelVenv = Join-Path $tempBase "wheel-smoke"
$projectSuffix = $PID.ToString()

New-Item -ItemType Directory -Path $exportRoot -Force | Out-Null
try {
    Invoke-NativeChecked "git" @("-C", $repoRoot, "archive", "--format=tar", "--output=$archivePath", $Treeish) "git archive"
    Invoke-NativeChecked "tar" @("-xf", $archivePath, "-C", $exportRoot) "archive extraction"
    Remove-Item -LiteralPath $archivePath -Force

    $env:SOURCE_REVISION = $revision
    Push-Location $exportRoot
    try {
        Invoke-NativeChecked "uv" @("sync", "--frozen", "--extra", "ml") "Python dependency install"
        Invoke-NativeChecked "uv" @("run", "ruff", "format", "--check", ".") "Ruff format"
        Invoke-NativeChecked "uv" @("run", "ruff", "check", ".") "Ruff lint"
        Invoke-NativeChecked "uv" @("run", "mypy") "mypy"
        Invoke-NativeChecked "uv" @("run", "pytest", "-m", "not gpu and not dataset", "-q") "pytest"

        Invoke-NativeChecked "npm" @("ci", "--prefix", "apps/web") "frontend dependency install"
        Invoke-NativeChecked "npm" @("--prefix", "apps/web", "run", "verify") "frontend verification"
        Invoke-NativeChecked "npm" @("--prefix", "apps/web", "run", "e2e") "frontend browser tests"
        Invoke-NativeChecked "uv" @("run", "python", "scripts/render_docs_assets.py", "--check") "documentation assets"
        Invoke-NativeChecked "uv" @("run", "python", "scripts/verify_claims.py") "documentation claims"

        Invoke-NativeChecked "uv" @("build", "--out-dir", "dist") "distribution build"
        $archives = @(
            Get-ChildItem -LiteralPath (Join-Path $exportRoot "dist") -File |
                Where-Object Name -Match '\.(?:whl|tar\.gz)$'
        )
        if ($archives.Count -lt 2) { throw "Expected wheel and source distribution" }

        Invoke-NativeChecked "uv" @("venv", $wheelVenv) "wheel smoke environment"
        $wheelPython = if ([IO.Path]::DirectorySeparatorChar -eq '\') {
            Join-Path $wheelVenv "Scripts/python.exe"
        } else {
            Join-Path $wheelVenv "bin/python"
        }
        $wheel = $archives | Where-Object Extension -eq ".whl" | Select-Object -First 1
        if (-not $wheel) { throw "Wheel artifact missing" }
        Invoke-NativeChecked "uv" @("pip", "install", "--python", $wheelPython, $wheel.FullName) "wheel install"
        Invoke-NativeChecked $wheelPython @("-c", "import experiments, inspection_platform; print('wheel smoke PASS')") "wheel import"

        Invoke-NativeChecked "uv" @("run", "cyclonedx-py", "environment", $wheelPython, "--output-reproducible", "--output-format", "JSON", "--output-file", $pythonSbom, "--pyproject", "pyproject.toml") "Python SBOM"
        Invoke-NativeChecked "npm" @("--prefix", "apps/web", "exec", "--", "cyclonedx-npm", "--package-lock-only", "--output-reproducible", "--output-format", "JSON", "--output-file", $nodeSbom, (Join-Path $exportRoot "apps/web/package.json")) "Node SBOM"
        if (-not (Test-Path -LiteralPath $pythonSbom) -or -not (Test-Path -LiteralPath $nodeSbom)) {
            throw "SBOM generation failed"
        }

        $verifyArguments = @("run", "python", "scripts/verify_release.py", "--source", ".", "--output", $verificationPath)
        foreach ($artifact in $archives) { $verifyArguments += @("--archive", $artifact.FullName) }
        Invoke-NativeChecked "uv" $verifyArguments "release verifier"

        Invoke-NativeChecked "powershell" @("-ExecutionPolicy", "Bypass", "-File", "scripts/docker_smoke.ps1", "-ProjectName", "mvtecad2export$projectSuffix", "-Port", "18280") "Docker smoke"
        Invoke-NativeChecked "powershell" @("-ExecutionPolicy", "Bypass", "-File", "scripts/run_system_tests.ps1", "-Repeat", "1") "system workflow"
    }
    finally {
        Pop-Location
    }

    if ($ReportPath) {
        $resolvedReport = [IO.Path]::GetFullPath($ReportPath)
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($resolvedReport)) -Force | Out-Null
        Copy-Item -LiteralPath $verificationPath -Destination $resolvedReport -Force
    }
    Write-Output "Clean export PASS: $revision"
    Write-Output "Python SBOM and Node SBOM generated and validated in isolated workspace"
}
finally {
    if (Test-Path -LiteralPath $tempBase) {
        $resolved = [IO.Path]::GetFullPath($tempBase)
        if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
            ([IO.Path]::GetFileName($resolved)).StartsWith("m2ce-")) {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        } else {
            throw "Refusing unsafe cleanup path: $resolved"
        }
    }
}
