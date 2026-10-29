$ErrorActionPreference='Stop'
$root='E:\0apps\ArenaDesk'
$rows=Get-Content "$root\data\install-state.json" -Raw | ConvertFrom-Json
$pet=$rows | Where-Object {$_.name -eq 'desktop-pet'} | Select-Object -Last 1
if ($pet.status -ne 'installed' -or -not (Test-Path $pet.exe)) { throw 'Pet download not verified' }
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$p=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$a=New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "E:\0apps\ArenaDesk\launch_pet.ps1"' -WorkingDirectory $root
$t=New-ScheduledTaskTrigger -AtLogOn -User $user
Register-ScheduledTask -TaskName 'arena-desktop-pet' -TaskPath '\' -Action $a -Trigger $t -Principal $p -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName 'arena-desktop-pet' -TaskPath '\'
Start-Sleep -Seconds 10
& "$root\control.ps1" -Action hide -Name 'arena-desktop-pet'
& "$root\control.ps1" -Action show -Name 'arena-desktop-pet'
& "$root\open_dsh.ps1"
& "$root\control.ps1" -Action snapshot
