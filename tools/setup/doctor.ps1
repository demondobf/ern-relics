# Check installed dependencies without syncing, downloading, or changing PATH.
#requires -Version 7.4
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $PSScriptRoot 'environment.ps1')
$repairs = [Collections.Generic.List[string]]::new()

function Test-Dependency([string]$Name, [scriptblock]$Check, [string]$Repair) {
    try {
        $detail = & $Check
        Write-Host "[ok] ${Name}: $detail"
    } catch {
        $repairs.Add($Repair)
        Write-Host "[fail] ${Name}: $($_.Exception.Message)"
    }
}

Test-Dependency 'Windows' { Test-WindowsEnvironment } 'Use PowerShell 7.4 or newer on 64-bit Windows.'
Test-Dependency 'Git' { Get-GitVersion } 'Install Git and reopen the terminal.'
Test-Dependency 'uv' { Get-UvVersion } 'Resolve the uv version or PATH problem above; reopen the terminal or parent app if needed.'
Test-Dependency 'Visual Studio' {
    $toolchain = Get-NativeToolchain
    "MSVC $($toolchain.CompilerVersion), CMake, Ninja, Windows SDK; $($toolchain.Installation)"
} 'Import .vsconfig into one supported Visual Studio installation using Visual Studio Installer.'
Test-Dependency 'AddressSanitizer for asan preset' { Get-ASanRuntime } 'Add C++ AddressSanitizer to the selected Visual Studio installation before using the asan preset.'
Test-Dependency '7-Zip for LLVM setup' { Get-SevenZip } 'Install 7-Zip to extract LLVM.'

$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
Test-Dependency 'Python and locked packages' {
    # uv --check creates .venv/.lock if absent; require uv initialization first.
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $projectRoot '.venv/.lock') -PathType Leaf)) {
        throw 'Python environment is missing or not initialized by uv. Run uv sync --locked.'
    }
    # Check only: no environment or lockfile changes, network, downloads, or persistent cache.
    $previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
    try {
        # Check this repository's .venv even when the caller selects another uv environment.
        $env:UV_PROJECT_ENVIRONMENT = Join-Path $projectRoot '.venv'
        $result = & uv sync --project $projectRoot --check --locked --offline --no-python-downloads --no-cache 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment
    }
    if ($exitCode -ne 0) { throw "${result}. Run uv sync --locked." }
    'Project environment matches uv.lock'
} 'Run uv sync --locked.'
$llvmRepair = if (Test-Path -LiteralPath (Get-LocalLLVMDirectory)) {
    "Remove the incomplete .tools/llvm/$(Get-PinnedLLVMVersion) directory, then run uv run --no-sync python -m tools.setup.llvm."
} else { 'Run uv run --no-sync python -m tools.setup.llvm.' }
Test-Dependency 'LLVM analyzer and builtin headers' { Get-PinnedClangTidy } $llvmRepair
foreach ($dependency in (Get-Content -Raw -LiteralPath (Join-Path $projectRoot 'sources.lock.json') | ConvertFrom-Json)) {
    $directory = Join-Path $projectRoot "third_party/$($dependency.Name)"
    $repair = if (Test-Path -LiteralPath (Join-Path $directory '.git')) {
        'Review native checkout problems above, then run uv run --no-sync python -m tools.setup.sources.'
    } else { 'Run uv run --no-sync python -m tools.setup.sources.' }
    Test-Dependency $dependency.Name {
        if (-not (Test-Path -LiteralPath (Join-Path $directory '.git'))) { throw 'Missing checkout. Run uv run --no-sync python -m tools.setup.sources.' }
        $origin = & git -C $directory remote get-url origin
        if ($LASTEXITCODE -ne 0 -or $origin -ne $dependency.Url) { throw 'Dependency origin differs from sources.lock.json.' }
        $head = & git -C $directory rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or $head -ne $dependency.Commit) { throw 'Dependency commit differs. Run uv run --no-sync python -m tools.setup.sources.' }
        $changes = & git --no-optional-locks -C $directory status --porcelain
        if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Dependency has local changes or cannot be inspected.' }
        $head
    } $repair
}
if ($repairs.Count) {
    Write-Host "`nNext steps:"
    $repairs | Select-Object -Unique | ForEach-Object { Write-Host "- $_" }
    exit 1
}
Write-Host 'Dependencies are ready. Activate tools/setup/shell.ps1, then run uv run --no-sync python -m tools.check.'
