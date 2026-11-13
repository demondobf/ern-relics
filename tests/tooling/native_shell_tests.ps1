$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $projectRoot 'tests/support/temp.ps1')
$fixture = New-TemporaryDirectory
$savedPath = $env:PATH
$savedVersion = $env:VSCMD_VER
$savedArchitecture = $env:VSCMD_ARG_TGT_ARCH
$savedSdk = $env:WindowsSDKVersion
$caller = (Get-Location).Path

# Exercise the activation script without loading or installing Visual Studio.
function Import-Module {
    param($Name, $ErrorAction)
    if ($Name -ne (Join-Path $fixture 'Visual Studio/Common7/Tools/Microsoft.VisualStudio.DevShell.dll')) {
        throw 'Activation selected a module from another Visual Studio installation.'
    }
}
function Enter-VsDevShell {
    param($VsInstallPath, [switch]$SkipAutomaticLocation, $DevCmdArguments)
    if ($VsInstallPath -ne (Join-Path $fixture 'Visual Studio') -or -not $SkipAutomaticLocation -or
        $DevCmdArguments -cne '-arch=amd64 -host_arch=amd64 -winsdk=10.0.26100.0') {
        throw 'Activation did not select x64 tools, the pinned SDK, and the caller directory.'
    }
    $env:VSCMD_VER = 'fixture'
    $env:VSCMD_ARG_TGT_ARCH = 'x64'
    $env:WindowsSDKVersion = '10.0.26100.0\'
}
try {
    $setup = Join-Path $fixture 'tools/setup'
    New-Item -ItemType Directory -Path $setup -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot 'tools/setup/shell.ps1') -Destination $setup
    [IO.File]::WriteAllText((Join-Path $setup 'environment.ps1'), @'
function Test-WindowsEnvironment {}
function Get-NativeToolchain {
    [pscustomobject]@{
        Installation = Join-Path $fixture 'Visual Studio'
        CMake = Join-Path $fixture 'CMake bin/cmake.exe'
        Ninja = Join-Path $fixture 'Ninja bin/ninja.exe'
        CompilerVersion = '19.44'
    }
}
'@)
    foreach ($attempt in 1..2) {
        & (Join-Path $setup 'shell.ps1')
        if ((Get-Location).Path -ne $caller -or $env:VSCMD_ARG_TGT_ARCH -ne 'x64' -or $env:WindowsSDKVersion -ne '10.0.26100.0\') {
            throw 'Activation failed to update the current process or changed the caller directory.'
        }
        $entries = @($env:PATH -split ';')
        foreach ($directory in @('CMake bin', 'Ninja bin')) {
            if (@($entries | Where-Object { $_ -eq (Join-Path $fixture $directory) }).Count -ne 1) {
                throw 'Repeated activation must keep one PATH entry for each bundled tool.'
            }
        }
        if ($entries[0] -ne (Join-Path $fixture 'CMake bin') -or $entries[1] -ne (Join-Path $fixture 'Ninja bin')) {
            throw 'Activation must prefer the selected bundled CMake and Ninja.'
        }
    }
} finally {
    $env:PATH = $savedPath
    $env:VSCMD_VER = $savedVersion
    $env:VSCMD_ARG_TGT_ARCH = $savedArchitecture
    $env:WindowsSDKVersion = $savedSdk
    Remove-TemporaryDirectory $fixture
}
Write-Host 'PASS: native shell activation selects one x64 toolchain and SDK, preserves the caller directory, and avoids duplicate PATH entries.'
