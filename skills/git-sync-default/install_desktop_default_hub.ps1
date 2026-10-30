#Requires -Version 5.1
$ErrorActionPreference = 'Continue'
$hubRoot = 'C:\0github\.git-sync\desktop-base'
New-Item -ItemType Directory -Force -Path $hubRoot, 'C:\0github\results', 'C:\cgmd' | Out-Null
$csc = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
$srCs = Join-Path $PSScriptRoot 'ArenaSilentRun.cs'
$srExe = Join-Path $hubRoot 'ArenaSilentRun.exe'
if ((Test-Path $csc) -and (Test-Path $srCs)) { & $csc /nologo /target:winexe /optimize+ /out:$srExe $srCs | Out-Null }
$hwSrc = Join-Path $PSScriptRoot 'hub-watch-desktop.ps1'
$hwDst = Join-Path $hubRoot 'hub-watch.ps1'
if (Test-Path -LiteralPath $hwSrc) {
    Copy-Item -LiteralPath $hwSrc -Destination $hwDst -Force
    $act = if (Test-Path $srExe) { New-ScheduledTaskAction -Execute $srExe -Argument ('"' + $hwDst + '" -Loop -IntervalSeconds 15') -WorkingDirectory $hubRoot } else { New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $hwDst + '" -Loop -IntervalSeconds 15') -WorkingDirectory $hubRoot }
    $trg = New-ScheduledTaskTrigger -AtLogOn
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\' -Action $act -Trigger $trg -Settings $set -Force | Out-Null
    Start-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\' -ErrorAction SilentlyContinue
}
$cgBootstrap = Join-Path (Split-Path $PSScriptRoot -Parent) 'cgmd-hub\bootstrap_desktop.ps1'
if (Test-Path -LiteralPath $cgBootstrap) {
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $cgBootstrap -SkipCredentials -SkipWslSetup -SkipFirstPoll
}
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$panelDeploy = Join-Path $repoRoot 'code\panel\deploy.ps1'
if (Test-Path -LiteralPath $panelDeploy) {
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $panelDeploy -OpenMainWindow -SkipAutoHeal
}
