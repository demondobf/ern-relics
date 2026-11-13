# Activate the native toolchain in this PowerShell process. No installations or user PATH edits.
#requires -Version 7.4
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'environment.ps1')
$null = Test-WindowsEnvironment
$toolchain = Get-NativeToolchain
Import-Module (Join-Path $toolchain.Installation 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll') -ErrorAction Stop
Enter-VsDevShell -VsInstallPath $toolchain.Installation -SkipAutomaticLocation -DevCmdArguments '-arch=amd64 -host_arch=amd64 -winsdk=10.0.26100.0' | Out-Host
if (-not $env:VSCMD_VER -or $env:VSCMD_ARG_TGT_ARCH -ne 'x64') { throw 'Visual Studio did not initialize the x64 compiler environment.' }
$directories = @((Split-Path -Parent $toolchain.CMake), (Split-Path -Parent $toolchain.Ninja))
$env:PATH = (@($directories) + @($env:PATH -split ';' | Where-Object { $_ -notin $directories })) -join ';'
Write-Host "Native shell ready: MSVC $($toolchain.CompilerVersion), Windows SDK 10.0.26100, bundled CMake and Ninja."
