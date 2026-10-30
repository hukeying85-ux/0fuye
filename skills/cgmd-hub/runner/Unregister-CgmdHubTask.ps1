#Requires -Version 5.1
<#
.SYNOPSIS
    Stop and remove the CGMD desktop hub scheduled task.

.DESCRIPTION
    Removes the polling task and terminates a run that is still in flight.
    Nothing else on the machine is touched: no global git config, no other
    scheduled task, no user account change.

.PARAMETER TaskName
    Scheduled task name, default CGMD-Hub-Poll.

.PARAMETER KeepStateFiles
    Keep state/ and logs/ (default: they are kept, this switch is a no-op
    documented for symmetry with future options).
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'CGMD-Hub-Poll',
    [switch]$KeepStateFiles
)

$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host ("no task named '{0}' - nothing to do" -f $TaskName)
    return
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host ("removed scheduled task '{0}'" -f $TaskName)

$pollers = @()
try {
    $pollers = Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'Invoke-CgmdPoll' }
} catch {
    $pollers = @()
}
foreach ($process in $pollers) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host ("stopped poller process {0}" -f $process.ProcessId)
    } catch { }
}

Write-Host 'done. the repository, git credentials and WSL environment were left untouched.'
