#Requires -Version 5.1
<#
.SYNOPSIS
    Compile SilentLauncher.cs into CGMDHub.exe (/target:winexe, no console).

.DESCRIPTION
    Uses the C# compiler that ships with .NET Framework 4.x on every Windows 10
    and Windows 11 machine (no Visual Studio, no SDK download, no network).

    The resulting CGMDHub.exe is a GUI-subsystem executable: Windows itself
    guarantees that launching it never creates a console window.  It starts
    PowerShell with -WindowStyle Hidden, CreateNoWindow = true and redirects the
    child's output into logs\hub-runner.log.

.PARAMETER Force
    Rebuild even when CGMDHub.exe is newer than the source file.

.EXAMPLE
    .\Build-SilentLauncher.ps1 -Force
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [string]$CscPath = ''
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'SilentLauncher.cs'
$target = Join-Path $PSScriptRoot 'CGMDHub.exe'

if (-not (Test-Path -LiteralPath $source)) { throw "missing $source" }

if ((-not $Force) -and (Test-Path -LiteralPath $target)) {
    $srcTime = (Get-Item -LiteralPath $source).LastWriteTimeUtc
    $exeTime = (Get-Item -LiteralPath $target).LastWriteTimeUtc
    if ($exeTime -gt $srcTime) {
        Write-Host 'CGMDHub.exe is up to date (use -Force to rebuild)'
        return $target
    }
}

if (-not $CscPath) {
    $candidates = @(
        (Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $env:SystemRoot 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { $CscPath = $candidate; break }
    }
}

if (-not $CscPath) {
    Write-Warning 'csc.exe not found; the hub still works through wscript.exe (also windowless).'
    return $null
}

Write-Host ("compiling {0} -> {1}" -f $source, $target)
$arguments = @('/nologo', '/target:winexe', '/optimize+', ('/out:' + $target), $source)
$output = & $CscPath @arguments 2>&1
if ($LASTEXITCODE -ne 0) {
    throw ("csc failed: " + (($output | ForEach-Object { "$_" }) -join ' | '))
}

if (Test-Path -LiteralPath $target) {
    Write-Host 'CGMDHub.exe built successfully (GUI subsystem, zero console window)'
} else {
    throw 'csc reported success but CGMDHub.exe is missing'
}
return $target
