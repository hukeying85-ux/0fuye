#Requires -Version 5.1
<#
.SYNOPSIS
    Register (or re-register) the silent 60 s polling task in Task Scheduler.

.DESCRIPTION
    The task action is `wscript.exe CgmdPoll.vbs`, i.e. a GUI-subsystem host:
    it never allocates a console, so no black window can ever flash - not at
    logon, not every minute, not when a 1 us simulation finishes.

    Settings applied on purpose:
      * repetition every -IntervalSeconds forever (default 60 s)
      * StartWhenAvailable          - catch up after sleep / reboot
      * MultipleInstances = Ignore  - overlapping runs are already locked out
      * ExecutionTimeLimit = 0      - a microsecond run may take days
      * DisallowStartIfOnBatteries = false, StopIfGoingOnBatteries = false
      * RunLevel = Limited          - no UAC prompt, no elevation needed

.PARAMETER TaskName
    Scheduled task name, default CGMD-Hub-Poll.

.PARAMETER IntervalSeconds
    Polling period, default 60.

.PARAMETER UseWrapperExe
    Start the compiled CGMDHub.exe instead of wscript.exe (both are silent).

.EXAMPLE
    .\Register-CgmdHubTask.ps1 -IntervalSeconds 60
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'CGMD-Hub-Poll',
    [int]$IntervalSeconds = 60,
    [switch]$UseWrapperExe,
    [string]$WscriptPath = '',
    [switch]$SkipFirstRun
)

$ErrorActionPreference = 'Stop'
$hubRoot = Split-Path -Parent $PSScriptRoot
$runnerDir = $PSScriptRoot
$logDir = Join-Path $hubRoot 'logs'
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir ('register-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))

function Write-RegLog {
    param([string]$Message)
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    try {
        [System.IO.File]::AppendAllText($logFile, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

$pollScript = Join-Path $runnerDir 'Invoke-CgmdPoll.ps1'
$vbsScript = Join-Path $runnerDir 'CgmdPoll.vbs'
$wrapperExe = Join-Path $runnerDir 'CGMDHub.exe'

if (-not (Test-Path -LiteralPath $pollScript)) { throw "missing $pollScript" }
if (-not (Test-Path -LiteralPath $vbsScript)) { throw "missing $vbsScript" }

if (-not $WscriptPath) {
    $WscriptPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
}
if (-not (Test-Path -LiteralPath $WscriptPath)) { $WscriptPath = 'wscript.exe' }

# --- choose a silent action ------------------------------------------------
if ($UseWrapperExe) {
    if (-not (Test-Path -LiteralPath $wrapperExe)) {
        throw "CGMDHub.exe not built yet; run Build-SilentLauncher.ps1 or omit -UseWrapperExe"
    }
    $action = New-ScheduledTaskAction -Execute $wrapperExe -Argument ('--script "{0}"' -f $pollScript)
    Write-RegLog ("action: {0}" -f $wrapperExe)
} else {
    $action = New-ScheduledTaskAction -Execute $WscriptPath -Argument ('"{0}"' -f $vbsScript)
    Write-RegLog ("action: {0} `"{1}`"" -f $WscriptPath, $vbsScript)
}

# --- trigger: start now, repeat forever -------------------------------------
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1))
try {
    $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
        -RepetitionInterval (New-TimeSpan -Seconds $IntervalSeconds) `
        -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
} catch {
    $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
        -RepetitionInterval (New-TimeSpan -Seconds $IntervalSeconds) `
        -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition
}

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances Ignore -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
$settings.DisallowStartIfOnBatteries = $false
$settings.StopIfGoingOnBatteries = $false

$principal = New-ScheduledTaskPrincipal -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
    -LogonType Interactive -RunLevel Limited

$description = 'CGMD-Engine desktop hub: silent git poll every {0}s, GPU task execution in WSL2, phone beacon.' -f $IntervalSeconds

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Write-RegLog ("existing task '{0}' found, replacing" -f $TaskName)
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description $description | Out-Null

Write-RegLog ("registered task '{0}' (every {1}s, logon type Interactive, run level Limited)" -f $TaskName, $IntervalSeconds)

# --- immediate validation run (hidden) --------------------------------------
if (-not $SkipFirstRun) {
    Write-RegLog 'starting one silent validation poll now'
    if (Test-Path -LiteralPath $wrapperExe) {
        Start-Process -FilePath $wrapperExe -ArgumentList ('--script "{0}"' -f $pollScript) -WindowStyle Hidden | Out-Null
    } else {
        Start-Process -FilePath $WscriptPath -ArgumentList ('"{0}"' -f $vbsScript) -WindowStyle Hidden | Out-Null
    }
    Write-RegLog 'validation poll launched (check logs\hub-*.log in ~30 s)'
}

Write-RegLog ('done. verify with: Get-ScheduledTask -TaskName {0} | Get-ScheduledTaskInfo' -f $TaskName)
