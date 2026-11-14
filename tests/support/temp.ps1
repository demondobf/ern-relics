# Temporary fixtures for the two PowerShell bootstrap tests. Production output handling is Python.
function New-TemporaryDirectory {
    $path = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ('ern-relics-' + [guid]::NewGuid().ToString('N'))))
    New-Item -ItemType Directory -Path $path | Out-Null
    return $path
}

function Remove-TemporaryDirectory([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $parent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    if ((Split-Path -Parent $absolute) -ne $parent -or (Split-Path -Leaf $absolute) -notmatch '^ern-relics-[0-9a-f]{32}$') {
        throw "Refusing cleanup outside an owned temporary fixture: $absolute"
    }
    if ((Get-Item -LiteralPath $absolute -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Temporary fixture is a reparse point.'
    }
    if (Get-ChildItem -LiteralPath $absolute -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
        throw 'Temporary fixture contains a reparse point.'
    }
    Remove-Item -LiteralPath $absolute -Recurse -Force
}
