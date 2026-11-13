#requires -Version 7.4
# Shared, read-only dependency checks for setup scripts, doctor, and builds.
function Test-WindowsEnvironment {
    if (-not $IsWindows -or -not [Environment]::Is64BitOperatingSystem) { throw 'Use 64-bit Windows.' }
    return "64-bit Windows; PowerShell $($PSVersionTable.PSVersion)"
}

function Get-GitVersion {
    $version = & git --version
    if ($LASTEXITCODE -ne 0) { throw 'Install Git and reopen the terminal.' }
    return $version
}

function Get-UvVersion {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        $installed = Join-Path $env:USERPROFILE '.local/bin/uv.exe'
        if (Test-Path -LiteralPath $installed) { throw "Installed at $installed but absent from this process PATH. Restart the terminal or its parent app." }
        throw 'Install uv and reopen the terminal.'
    }
    $project = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../../pyproject.toml')
    if ($project -notmatch 'required-version = ">=(\d+\.\d+\.\d+)"') { throw 'Cannot read the uv minimum version.' }
    $minimum = [version]$Matches[1]
    $version = & uv --version
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^uv (\d+\.\d+\.\d+)' -or [version]$Matches[1] -lt $minimum) {
        throw "uv $minimum or newer required; found $version"
    }
    return $version
}

function Get-PinnedLLVMVersion {
    $project = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../../pyproject.toml')
    if ($project -notmatch '"clang-format==(\d+\.\d+\.\d+)"') { throw 'Cannot read the clang-format pin in pyproject.toml.' }
    return $Matches[1]
}

function Get-LocalLLVMDirectory {
    return [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../../.tools/llvm/$(Get-PinnedLLVMVersion)"))
}

function Get-SevenZip {
    $command = Get-Command 7z -CommandType Application -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $installed = Join-Path $env:ProgramFiles '7-Zip/7z.exe'
    if (Test-Path -LiteralPath $installed) { return $installed }
    throw 'Install 7-Zip to extract LLVM, then run uv run --no-sync python -m tools.setup.llvm.'
}

function Get-NativeToolchain {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Install Visual Studio C++ Build Tools and the Windows SDK.' }
    # Shell activation needs the core tools together. CMake validates ASan only
    # when its preset is selected; doctor reports that capability separately.
    $components = (Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../../.vsconfig') | ConvertFrom-Json).components |
        Where-Object { $_ -notlike 'Microsoft.VisualStudio.Workload.*' -and $_ -ne 'Microsoft.VisualStudio.Component.VC.ASAN' }
    $installation = & $vswhere -latest -products '*' -version '[17.14,19.0)' -requires $components -property installationPath
    if ($LASTEXITCODE -ne 0 -or -not $installation) {
        $labels = @{
            'Microsoft.VisualStudio.Component.VC.Tools.x86.x64' = 'MSVC C++ tools'
            'Microsoft.VisualStudio.Component.VC.CMake.Project' = 'CMake and Ninja'
            'Microsoft.VisualStudio.Component.Windows11SDK.26100' = 'Windows SDK 10.0.26100'
        }
        $required = $components | ForEach-Object { if ($labels.ContainsKey($_)) { $labels[$_] } else { $_ } }
        throw "Visual Studio 2022 17.14 or Visual Studio 2026 must include all required components in one installation: $($required -join ', '). Import .vsconfig into Visual Studio Installer."
    }
    $default = (Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt')).Trim()
    $compiler = Join-Path $installation "VC/Tools/MSVC/$default/bin/Hostx64/x64/cl.exe"
    $compilerVersion = (Get-Item -LiteralPath $compiler).VersionInfo.FileVersion
    if ($compilerVersion -notmatch '^(\d+\.\d+\.\d+)' -or [version]$Matches[1] -lt [version]'19.44.0') { throw "MSVC 19.44 or newer required; found $compilerVersion" }
    $cmake = Join-Path $installation 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    if (-not (Test-Path -LiteralPath $cmake)) { throw 'Visual Studio CMake is missing. Import .vsconfig into Visual Studio Installer.' }
    $ninja = Join-Path $installation 'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
    if (-not (Test-Path -LiteralPath $ninja)) { throw 'Visual Studio Ninja is missing. Import .vsconfig into Visual Studio Installer.' }
    $cmakeVersion = & $cmake --version
    if ($LASTEXITCODE -ne 0 -or ($cmakeVersion -join "`n") -notmatch 'cmake version (\d+\.\d+\.\d+)' -or [version]$Matches[1] -lt [version]'3.25.0') {
        throw "Install CMake 3.25 or newer. Found: $cmakeVersion"
    }
    $ninjaVersion = & $ninja --version
    if ($LASTEXITCODE -ne 0 -or $ninjaVersion -notmatch '^(\d+\.\d+\.\d+)' -or [version]$Matches[1] -lt [version]'1.11.0') {
        throw "Install Ninja 1.11 or newer. Found: $ninjaVersion"
    }
    [pscustomobject]@{
        Installation = $installation
        CMake = $cmake
        Ninja = $ninja
        CompilerVersion = $compilerVersion
        Compiler = $compiler
    }
}

function Get-ASanRuntime($Toolchain = (Get-NativeToolchain)) {
    $runtime = Join-Path (Split-Path -Parent $Toolchain.Compiler) 'clang_rt.asan_dynamic-x86_64.dll'
    if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) {
        throw 'AddressSanitizer is missing from the selected compiler. Add the C++ AddressSanitizer component in Visual Studio Installer to use the asan preset.'
    }
    return $runtime
}

function Get-PinnedClangTidy([string]$Directory = (Get-LocalLLVMDirectory)) {
    $expected = Get-PinnedLLVMVersion
    $tidy = Join-Path $Directory 'bin/clang-tidy.exe'
    $header = Join-Path $Directory "lib/clang/$($expected.Split('.')[0])/include/stddef.h"
    if (-not (Test-Path -LiteralPath $tidy -PathType Leaf) -or -not (Test-Path -LiteralPath $header -PathType Leaf)) {
        throw "LLVM $expected is missing or incomplete. Remove .tools/llvm/$expected if present, then run uv run --no-sync python -m tools.setup.llvm."
    }
    $version = & $tidy --version
    if ($LASTEXITCODE -ne 0 -or ($version -join "`n") -notmatch "\bLLVM version $([regex]::Escape($expected))\b") {
        throw "LLVM does not match version $expected. Remove .tools/llvm/$expected, then run uv run --no-sync python -m tools.setup.llvm."
    }
    return $tidy
}
