#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$root = if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'server.py'))) {
    $PSScriptRoot
} else {
    # The reference laptop had an E: drive; the workstation does not.  Walk the
    # drives that exist instead of assuming one.
    $found = $null
    foreach ($drv in @('C:\', 'D:\', 'E:\', 'F:\', 'G:\')) {
        if (-not (Test-Path -LiteralPath $drv)) { continue }
        $candidate = Join-Path $drv '0apps\ArenaDesk'
        if (Test-Path -LiteralPath (Join-Path $candidate 'ArenaDesk.exe')) { $found = $candidate; break }
        if (-not $found -and (Test-Path -LiteralPath $candidate)) { $found = $candidate }
    }
    if ($found) { $found } else { 'C:\0apps\ArenaDesk' }
}
$exe = Join-Path $root 'ArenaDesk.exe'
if (Test-Path -LiteralPath $exe) {
    Start-Process -FilePath $exe -WorkingDirectory $root
    exit 0
}
$t = Get-ScheduledTask -TaskName 'arena-desk-panel' -TaskPath '\' -ErrorAction SilentlyContinue
if ($t -and [string]$t.State -ne 'Running') {
    Start-ScheduledTask -TaskName 'arena-desk-panel' -TaskPath '\'
}
for ($i = 0; $i -lt 15; $i++) {
    try {
        $r = Invoke-WebRequest 'http://127.0.0.1:18765/api/bootstrap' -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            $edge = @(
                "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
                "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
            ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
            if ($edge) {
                $prof = Join-Path $root 'data\desktop-window-profile'
                New-Item -ItemType Directory -Force -Path $prof | Out-Null
                Start-Process -FilePath $edge -ArgumentList @('--app="http://127.0.0.1:18765/"', ('--user-data-dir="' + $prof + '"'), '--window-size=1440,900')
            } else {
                Start-Process 'http://127.0.0.1:18765/'
            }
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 1
}
throw 'Panel service did not become ready; permanent hub was not modified.'
