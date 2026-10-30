param(
    [ValidateSet('snapshot','start','stop','hide','show','open')][string]$Action='snapshot',
    [string]$Name=''
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$allowed=@('arena-desktop-pet','arena-desk-open','arena-desk-boot-demo','arena-dsh-web')
$readonlyPeers=@('git-sync-hub','arena-desk-panel','jev-chat-monitor','jev-chat-analyze')
if ($Action -ne 'snapshot' -and $Name -notin $allowed) { throw 'Protected or unknown task' }
if ($Action -eq 'snapshot') {
    $rows=@()
    foreach ($n in ($readonlyPeers+$allowed)) {
        $t=Get-ScheduledTask -TaskName $n -TaskPath '\' -ErrorAction SilentlyContinue
        if ($t) {
            $i=Get-ScheduledTaskInfo -TaskName $n -TaskPath '\'
            $rows+=@{name=$n;state=[string]$t.State;last_result=$i.LastTaskResult;limit=$t.Settings.ExecutionTimeLimit;protected=($n -in $readonlyPeers)}
        } else { $rows+=@{name=$n;state='NotInstalled';protected=($n -in $readonlyPeers)} }
    }
    ConvertTo-Json -InputObject $rows -Depth 4 -Compress
    exit 0
}
if ($Action -eq 'open') {
    if ($Name -ne 'arena-dsh-web') { throw 'Only DSH can be opened' }
    & (Join-Path $PSScriptRoot 'open_dsh.ps1')
} elseif ($Action -in @('hide','show')) {
    if ($Name -ne 'arena-desktop-pet') { throw 'Only pet windows may be hidden' }
    Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class PetWindows {
 public delegate bool EnumProc(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
 [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h, int n);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
'@
    $ids=@(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like 'E:\0apps\DSHPet\*' -and $_.Name -eq 'dsh-pet-standalone-webm.exe' } | ForEach-Object { [uint32]$_.ProcessId })
    $file='E:\0apps\ArenaDesk\data\hidden-pet.json'
    if ($ids.Count -eq 0) { throw 'Desktop pet is not running' }
    $flag='E:\0apps\ArenaDesk\data\pet-hidden.flag'
    if ($Action -eq 'hide') {
        $script:windows=New-Object System.Collections.Generic.List[long]
        $callback=[PetWindows+EnumProc]{param($h,$l)
            [uint32]$proc=0; [void][PetWindows]::GetWindowThreadProcessId($h,[ref]$proc)
            if ($proc -in $ids -and [PetWindows]::IsWindowVisible($h)) {
                $script:windows.Add($h.ToInt64()); [void][PetWindows]::ShowWindowAsync($h,0)
            }; return $true
        }
        [void][PetWindows]::EnumWindows($callback,[IntPtr]::Zero)
        if ($script:windows.Count -gt 0) { ConvertTo-Json -InputObject @($script:windows.ToArray()) | Set-Content $file -Encoding UTF8; Set-Content $flag 'hidden' -Encoding ASCII }
    } elseif (Test-Path $file) {
        $handles=Get-Content $file -Raw | ConvertFrom-Json
        foreach ($v in $handles) {
            $h=[IntPtr][long]$v; [uint32]$proc=0; [void][PetWindows]::GetWindowThreadProcessId($h,[ref]$proc)
            if ($proc -in $ids) { [void][PetWindows]::ShowWindowAsync($h,5) }
        }
        Remove-Item $flag -ErrorAction SilentlyContinue
    }
} elseif ($Action -eq 'start') {
    Enable-ScheduledTask -TaskName $Name -TaskPath '\' | Out-Null
    Start-ScheduledTask -TaskName $Name -TaskPath '\'
} else {
    # Disable future automatic launches AND stop the existing task instance.
    Disable-ScheduledTask -TaskName $Name -TaskPath '\' | Out-Null
    Stop-ScheduledTask -TaskName $Name -TaskPath '\'
    # Some historical wrappers detached pythonw. Match only exact owned scripts.
    $scriptName=switch ($Name) { 'jev-chat-monitor' {'run_with_recorder.py'} 'jev-chat-analyze' {'auto_analyze.py'} default {''} }
    if ($scriptName) {
        Get-CimInstance Win32_Process | Where-Object {
            $_.ExecutablePath -eq 'E:\0apps\jev-chat-windows\venv\Scripts\pythonw.exe' -and
            $_.CommandLine -match ('[\\/]' + [regex]::Escape($scriptName) + '("|\s|$)')
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
    }
}
@{ok=$true;action=$Action;task=$Name} | ConvertTo-Json -Compress
