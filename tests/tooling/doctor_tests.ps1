param([string]$Python)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Python) { $Python = Join-Path $projectRoot '.venv/Scripts/python.exe' }
$uvExecutable = (Get-Command uv -CommandType Application -ErrorAction Stop).Source
. (Join-Path $projectRoot 'tests/support/temp.ps1')
$temporaryRoot = New-TemporaryDirectory
$savedPath = $env:PATH
$savedUserProfile = $env:USERPROFILE
$savedProgramFilesX86 = ${env:ProgramFiles(x86)}
$savedUvCache = $env:UV_CACHE_DIR
$savedUvEnvironment = $env:UV_PROJECT_ENVIRONMENT
$env:UV_PROJECT_ENVIRONMENT = $null
$mockVswhere = $null

function New-DoctorFixture([string]$Name, [switch]$MissingUv, [switch]$IncompleteLLVM, [string]$UvVersion = '0.13.7') {
    $root = Join-Path $temporaryRoot $Name
    New-Item -ItemType Directory -Path (Join-Path $root 'tools/setup') -Force | Out-Null
    foreach ($file in @('tools/setup/doctor.ps1', 'tools/setup/environment.ps1', 'pyproject.toml', 'uv.lock', '.python-version')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination (Join-Path $root $file)
    }
    [IO.File]::WriteAllText((Join-Path $root 'sources.lock.json'), '[]')
    # Stub machine-only dependencies. Environment checks run the real uv executable.
    $toolchain = Join-Path $root 'tools/setup/environment.ps1'
    Add-Content -LiteralPath $toolchain -Value @'
function Get-GitVersion { 'fixture Git' }
function Get-NativeToolchain { [pscustomobject]@{ Installation = 'fixture Visual Studio'; CompilerVersion = '19.44.0' } }
function Get-SevenZip { 'fixture 7-Zip' }
'@
    if (-not $MissingUv) {
        $wrapper = @'
function uv {
    if ($args[0] -eq '--version') { 'uv FIXTURE_VERSION'; $global:LASTEXITCODE = 0; return }
    foreach ($flag in @('--check', '--locked', '--offline', '--no-python-downloads', '--no-cache')) {
        if ($args -notcontains $flag) { throw "Doctor must pass $flag to uv." }
    }
    & $uvExecutable @args
}
'@
        Add-Content -LiteralPath $toolchain -Value ($wrapper.Replace('FIXTURE_VERSION', $UvVersion))
    }
    if (-not $IncompleteLLVM) {
        Add-Content -LiteralPath $toolchain -Value "function Get-PinnedClangTidy { 'fixture LLVM' }"
    }
    return $root
}
function Invoke-Doctor([string]$Root) {
    $output = & (Join-Path $Root 'tools/setup/doctor.ps1') *>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Text = $output -join "`n" }
}
function Get-FixtureSnapshot([string]$Root) {
    return (Get-ChildItem -LiteralPath $Root -Recurse -Force | Sort-Object FullName | ForEach-Object {
        if ($_.PSIsContainer) { $_.FullName } else {
            "$($_.FullName):$($_.LastWriteTimeUtc.Ticks):$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash)"
        }
    }) -join "`n"
}

try {
    $missingPath = New-DoctorFixture 'missing-uv-path' -MissingUv
    $env:USERPROFILE = Join-Path $temporaryRoot 'user'
    $env:PATH = $temporaryRoot
    $uvDirectory = Join-Path $env:USERPROFILE '.local/bin'
    New-Item -ItemType Directory -Path $uvDirectory -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $uvDirectory 'uv.exe'), 'Installed but must not execute')
    $snapshot = Get-FixtureSnapshot $missingPath
    $result = Invoke-Doctor $missingPath
    if ($result.ExitCode -ne 1 -or $result.Text -notlike '*absent from this process PATH*' -or $result.Text -notlike '*Next steps:*') {
        throw "Doctor failed to explain the missing uv PATH entry: $($result.Text)"
    }
    if ((Get-FixtureSnapshot $missingPath) -ne $snapshot) { throw 'Doctor modified the checkout while checking PATH.' }
    $env:PATH = $savedPath
    $env:USERPROFILE = $savedUserProfile

    $oldUv = New-DoctorFixture 'outdated-uv' -UvVersion '0.0.1'
    $result = Invoke-Doctor $oldUv
    if ($result.ExitCode -ne 1 -or $result.Text -notlike '*uv * or newer required; found uv 0.0.1*' -or $result.Text -notlike '*Next steps:*uv version or PATH problem*') {
        throw "Doctor missed an outdated uv or its repair: $($result.Text)"
    }

    $packages = New-DoctorFixture 'python-packages'
    & $Python -I -B -m venv --without-pip (Join-Path $packages '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create the isolated doctor Python fixture.' }
    $sitePackages = Join-Path $packages '.venv/Lib/site-packages'
    Get-ChildItem -LiteralPath (Join-Path $projectRoot '.venv/Lib/site-packages') -Force |
        Copy-Item -Destination $sitePackages -Recurse
    $env:UV_CACHE_DIR = Join-Path $packages 'persistent-cache'
    New-Item -ItemType Directory -Path $env:UV_CACHE_DIR | Out-Null
    [IO.File]::WriteAllText((Join-Path $env:UV_CACHE_DIR 'sentinel.txt'), 'Doctor must not touch this cache')
    $snapshot = Get-FixtureSnapshot $packages
    $result = Invoke-Doctor $packages
    if ($result.ExitCode -ne 1 -or $result.Text -notlike '*not initialized by uv*') {
        throw "Doctor missed an environment without uv initialization: $($result.Text)"
    }
    if ((Get-FixtureSnapshot $packages) -ne $snapshot) { throw 'Doctor created an environment lock or modified an uninitialized environment.' }
    $setupOutput = & $uvExecutable sync --project $packages --locked --offline --no-python-downloads --no-cache 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Cannot initialize the offline fixture: $setupOutput" }
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $packages 'alternate-environment'
    $snapshot = Get-FixtureSnapshot $packages
    $result = Invoke-Doctor $packages
    if ($result.ExitCode -ne 0 -or $result.Text -notlike '*Dependencies are ready*') {
        throw "Doctor rejected a matching environment: $($result.Text)"
    }
    if ((Get-FixtureSnapshot $packages) -ne $snapshot) { throw 'Doctor modified a synchronized environment, lockfile, or persistent cache.' }
    if ($env:UV_PROJECT_ENVIRONMENT -ne (Join-Path $packages 'alternate-environment')) { throw 'Doctor changed the caller uv environment selection.' }
    $metadata = Get-ChildItem -LiteralPath $sitePackages -Directory -Filter 'ruff-*.dist-info' | Select-Object -First 1
    if (-not $metadata) { throw 'The doctor fixture needs the installed project ruff package.' }
    $metadataFile = Join-Path $metadata.FullName 'METADATA'
    [IO.File]::WriteAllText($metadataFile, ((Get-Content -Raw -LiteralPath $metadataFile) -replace '(?m)^Version: [^\r\n]+', 'Version: 0.0.1'))
    Rename-Item -LiteralPath $metadata.FullName -NewName 'ruff-0.0.1.dist-info'
    $snapshot = Get-FixtureSnapshot $packages
    $result = Invoke-Doctor $packages
    if ($result.ExitCode -ne 1 -or $result.Text -notlike '*ruff*0.0.1*' -or $result.Text -notlike '*Next steps:*uv sync --locked*') {
        throw "Doctor missed an outdated package or its repair: $($result.Text)"
    }
    if ((Get-FixtureSnapshot $packages) -ne $snapshot) { throw 'Doctor modified the outdated environment, lockfile, or persistent cache.' }

    $incomplete = New-DoctorFixture 'incomplete-llvm' -IncompleteLLVM
    . (Join-Path $incomplete 'tools/setup/environment.ps1')
    $cache = Get-LocalLLVMDirectory
    New-Item -ItemType Directory -Path (Join-Path $cache 'bin') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $cache 'lib/clang') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $cache 'bin/clang-tidy.exe'), 'Must not execute without builtin headers')
    $snapshot = Get-FixtureSnapshot $incomplete
    $result = Invoke-Doctor $incomplete
    if ($result.ExitCode -ne 1 -or $result.Text -notlike '*LLVM analyzer and builtin headers:*missing or incomplete*' -or $result.Text -notlike '*Next steps:*Remove the incomplete .tools/llvm/*tools.setup.llvm*') {
        throw "Doctor missed an incomplete LLVM cache or its repair: $($result.Text)"
    }
    if ((Get-FixtureSnapshot $incomplete) -ne $snapshot) { throw 'Doctor modified the incomplete LLVM cache.' }

    # Two partial Visual Studio installations must not combine into one valid toolchain.
    $native = New-DoctorFixture 'split-visual-studio'
    Copy-Item -LiteralPath (Join-Path $projectRoot '.vsconfig') -Destination $native
    Copy-Item -LiteralPath (Join-Path $projectRoot 'tools/setup/environment.ps1') -Destination (Join-Path $native 'tools/setup/environment.ps1')
    . (Join-Path $native 'tools/setup/environment.ps1')
    ${env:ProgramFiles(x86)} = Join-Path $native 'Program Files (x86)'
    $mockVswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    New-Item -ItemType Directory -Path (Split-Path -Parent $mockVswhere) -Force | Out-Null
    [IO.File]::WriteAllText($mockVswhere, 'Must use the mocked discovery command')
    $selectionState = [pscustomobject]@{ Required = @() }
    Set-Item -Path "Function:$mockVswhere" -Value {
        param([switch]$latest, $products, $version, [string[]]$requires, $property)
        $selectionState.Required = $requires
        $global:LASTEXITCODE = 0
        $partialInstalls = @(
            @('Microsoft.VisualStudio.Component.VC.Tools.x86.x64', 'Microsoft.VisualStudio.Component.Windows11SDK.26100'),
            @('Microsoft.VisualStudio.Component.VC.CMake.Project', 'Microsoft.VisualStudio.Component.VC.ASAN')
        )
        foreach ($components in $partialInstalls) {
            if (-not @($requires | Where-Object { $_ -notin $components }).Count) { return 'partial Visual Studio' }
        }
    }
    try {
        $null = Get-NativeToolchain
        throw 'Shared native validation accepted split Visual Studio components.'
    } catch {
        if ($_.Exception.Message -notlike '*all required components in one installation*MSVC C++ tools*CMake and Ninja*Windows SDK*AddressSanitizer*') { throw }
    }
    $expected = (Get-Content -Raw -LiteralPath (Join-Path $native '.vsconfig') | ConvertFrom-Json).components |
        Where-Object { $_ -notlike 'Microsoft.VisualStudio.Workload.*' }
    if (Compare-Object $expected $selectionState.Required) { throw 'Native validation did not request all concrete .vsconfig components together.' }
} finally {
    $env:PATH = $savedPath
    $env:USERPROFILE = $savedUserProfile
    ${env:ProgramFiles(x86)} = $savedProgramFilesX86
    $env:UV_CACHE_DIR = $savedUvCache
    $env:UV_PROJECT_ENVIRONMENT = $savedUvEnvironment
    if ($mockVswhere) { Remove-Item -LiteralPath "Function:$mockVswhere" -ErrorAction SilentlyContinue }
    Remove-TemporaryDirectory $temporaryRoot
}
Write-Host 'PASS: doctor checks uv environments offline without changing files or cache; reports setup failures and requires one complete Visual Studio installation.'
