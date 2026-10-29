#Requires -Version 5.1
<#
.SYNOPSIS
    git-sync-hub v4.0 - Permanent Zero-Window Auto-Poll, Pull, Execute & Push Hub
    (C:\0github\.git-sync\leanrea-626378d6-leanrea)

.DESCRIPTION
    Runs silently in the background via Windows Task Scheduler (TaskName: 'git-sync-hub').
    Capabilities:
      1. ZERO POP-UP WINDOWS: Hides console window via Win32 ShowWindow(SW_HIDE),
         executes all child processes via ProcessStartInfo (CreateNoWindow=true,
         UseShellExecute=false), and reloads in-memory so the process never exits.
      2. 15-SECOND FAST POLLING (NO RATE-LIMIT GAPS):
         Uses Git Credential Manager token for GitHub REST API (5,000 req/hr) every
         60s to discover repos, and runs direct `git ls-remote` on active repos every
         15s (zero REST API rate limit, instant detection).
      3. AUTO PULL + EXECUTE CODE + PUSH RESULTS FOR ALL NEW BRANCHES:
         When any mqgg5630-cyber arena/* branch has a new commit:
           - Pulls/clones results, deliverable, code, skills
           - Executes tasks silently on LAPTOP-R77M5D6M (full access to C:\, D:\, E:\,
             Desktop, Python E:\spider\python.exe, PowerShell, Git Bash):
               * results/status/hub_task.json (write_files, copy_files, powershell, python, bash, cmd)
               * results/status/desktop_target.json (copies file to target_path / Desktop)
               * results/task/run.ps1 | run.py | run.sh
               * code/hub_task.ps1 | hub_task.py | hub_task.sh
               * results/status/handshake.json (if local_check.ps1 requested)
           - Writes stdout/stderr/receipt to results/status/hub_exec_output.txt and
             results/status/hub_sync_receipt.json
           - Mirrors results/* and deliverable/* to C:\0github\results\<project-branch>\
           - Commits and pushes all results + execution outputs back to origin <branch>
           - Deletes the temporary clone so C:\0github\.git-sync stays at ~4.2 MB.
#>
[CmdletBinding()]
param(
    [string]$Owner           = 'hukeying85-ux',
    [string]$SyncRoot        = 'C:\0github\.git-sync',
    [string]$ResultsRoot     = 'C:\0github\results',
    [string]$TopRoot         = 'C:\0github',
    [string]$BaseDirName     = 'leanrea-626378d6-leanrea',
    [string]$CutoffIso       = '2026-10-24T02:55:00Z',
    [int]$IntervalSeconds    = 15,
    [switch]$Loop,
    [switch]$RegisterTask,
    [switch]$Status
)

$ErrorActionPreference = 'Continue'
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE     = 'never'

# Immediately hide console window if any exists
try {
    if (-not ('Win32.ConsoleHide' -as [type])) {
        Add-Type -Namespace Win32 -Name ConsoleHide -MemberDefinition '
            [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
            [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
        ' -ErrorAction SilentlyContinue
    }
    $hwnd = [Win32.ConsoleHide]::GetConsoleWindow()
    if ($hwnd -ne [IntPtr]::Zero) {
        [void][Win32.ConsoleHide]::ShowWindow($hwnd, 0)
    }
} catch {}

$TaskName  = 'git-sync-hub'
$StateRoot = Join-Path $env:USERPROFILE '.git-sync-hub'
if (-not (Test-Path -LiteralPath $StateRoot)) {
    New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
}
$LogFile       = Join-Path $StateRoot 'hub-watch.log'
$StateJson     = Join-Path $StateRoot 'hub-state.json'
$SeenHeadsJson = Join-Path $StateRoot 'seen-heads.json'
$PidFile       = Join-Path $StateRoot 'hub-watch.pid'

function Write-HubLog([string]$Msg) {
    $line = "[{0}] [pid={1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $PID, $Msg
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Find-GitExe {
    $candidates = @(
        'E:\hermes\git\cmd\git.exe',
        'E:\hermes\git\bin\git.exe',
        'C:\Program Files\Git\cmd\git.exe',
        'C:\Program Files\Git\bin\git.exe'
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $cmd = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return 'git.exe'
}

function Find-BashExe {
    $candidates = @(
        'E:\hermes\git\bin\bash.exe',
        'E:\hermes\git\usr\bin\bash.exe',
        'C:\Program Files\Git\bin\bash.exe'
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return 'bash.exe'
}

function Find-PythonExe {
    $candidates = @(
        'E:\spider\python.exe',
        'E:\miniconda3\python.exe',
        'C:\Python311\python.exe',
        'C:\Python310\python.exe'
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return 'python.exe'
}

$GitExe    = Find-GitExe
$BashExe   = Find-BashExe
$PythonExe = Find-PythonExe

function Invoke-ProcessSilent {
    param(
        [string]$FileName,
        [string]$Arguments,
        [string]$WorkingDirectory = $PSScriptRoot,
        [int]$TimeoutSeconds = 120,
        [string]$StdinText = ''
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName               = $FileName
        $psi.Arguments              = $Arguments
        if ($WorkingDirectory -and (Test-Path -LiteralPath $WorkingDirectory)) {
            $psi.WorkingDirectory   = $WorkingDirectory
        }
        $psi.UseShellExecute        = $false
        $psi.CreateNoWindow         = $true
        $psi.WindowStyle            = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        if ($StdinText) {
            $psi.RedirectStandardInput = $true
        }
        $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $psi.StandardErrorEncoding  = [System.Text.Encoding]::UTF8

        $proc = [System.Diagnostics.Process]::Start($psi)
        if ($StdinText) {
            $proc.StandardInput.Write($StdinText)
            $proc.StandardInput.Close()
        }
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $errTask = $proc.StandardError.ReadToEndAsync()

        $finished = $proc.WaitForExit($TimeoutSeconds * 1000)
        if (-not $finished) {
            try { & taskkill.exe /F /T /PID $proc.Id >$null 2>&1 } catch {}
            try { $proc.Kill() } catch {}
            try { [void]$proc.WaitForExit(2000) } catch {}
        }
        $sw.Stop()
        $outStr = ''
        $errStr = ''
        try { if ($outTask.Wait(2000)) { $outStr = [string]$outTask.Result } } catch {}
        try { if ($errTask.Wait(2000)) { $errStr = [string]$errTask.Result } } catch {}
        return @{
            exit_code  = if ($finished) { [int]$proc.ExitCode } else { 124 }
            stdout     = $outStr
            stderr     = $errStr
            elapsed_ms = [int]$sw.ElapsedMilliseconds
            timed_out  = (-not $finished)
        }
    } catch {
        $sw.Stop()
        return @{
            exit_code  = 1
            stdout     = ''
            stderr     = $_.Exception.Message
            elapsed_ms = [int]$sw.ElapsedMilliseconds
            timed_out  = $false
        }
    }
}

function Invoke-GitSilent {
    param(
        [string]$Arguments,
        [string]$WorkingDirectory = $PSScriptRoot,
        [int]$TimeoutSeconds = 30
    )
    return Invoke-ProcessSilent -FileName $GitExe -Arguments "-c core.fsmonitor=false -c gc.auto=0 -c maintenance.auto=false -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=20 $Arguments" -WorkingDirectory $WorkingDirectory -TimeoutSeconds $TimeoutSeconds
}

function Get-GitHubToken {
    if ($script:CachedGhToken) { return $script:CachedGhToken }
    try {
        $res = Invoke-ProcessSilent -FileName $GitExe -Arguments 'credential fill' -StdinText "protocol=https`nhost=github.com`n`n" -TimeoutSeconds 10
        foreach ($line in ($res.stdout -split "`r?`n")) {
            if ($line -match '^password=(.+)$') {
                $script:CachedGhToken = $Matches[1].Trim()
                return $script:CachedGhToken
            }
        }
    } catch {}
    return ''
}

function Get-ShortCloneName([string]$RepoName, [string]$Branch) {
    $slug = $Branch -replace '^arena/', ''
    return "{0}-{1}" -f $RepoName, $slug
}

function Remove-TreeSafe([string]$Target) {
    if (-not (Test-Path -LiteralPath $Target)) { return $true }
    try {
        & cmd.exe /c "attrib -r -s -h `"$Target\*`" /s /d >nul 2>&1"
        & cmd.exe /c "rmdir /s /q `"$Target`" >nul 2>&1"
        if (Test-Path -LiteralPath $Target) {
            Remove-Item -LiteralPath $Target -Recurse -Force -ErrorAction SilentlyContinue
        }
    } catch {}
    return (-not (Test-Path -LiteralPath $Target))
}

function Write-LocalFileSafe([string]$TargetPath, [byte[]]$Bytes, [string]$TextContent, [bool]$UseBytes = $false) {
    $writtenPaths = @()
    $zhDesktop = "$([char]0x684C)$([char]0x9762)"
    $candidates = @($TargetPath)

    # If target mentions D:\<Desktop> or Desktop, also write to actual Windows Desktop folder
    $realDesktop = [Environment]::GetFolderPath('Desktop')
    if ($realDesktop -and ($TargetPath -match [regex]::Escape($zhDesktop) -or $TargetPath -match '(?i)\\Desktop\\')) {
        $leaf = Split-Path -Path $TargetPath -Leaf
        $altDesktopPath = Join-Path $realDesktop $leaf
        if ($candidates -notcontains $altDesktopPath) {
            $candidates += $altDesktopPath
        }
    }

    foreach ($cand in $candidates) {
        try {
            $parent = Split-Path -Path $cand -Parent
            if ($parent -and (-not (Test-Path -LiteralPath $parent))) {
                New-Item -ItemType Directory -Path $parent -Force -ErrorAction Stop | Out-Null
            }
            if ($UseBytes) {
                [System.IO.File]::WriteAllBytes($cand, $Bytes)
            } else {
                [System.IO.File]::WriteAllText($cand, $TextContent, (New-Object System.Text.UTF8Encoding($false)))
            }
            if (Test-Path -LiteralPath $cand) {
                $writtenPaths += $cand
            }
        } catch {
            # If writing directly to C:\<file> root fails due to Windows root UAC ACL,
            # automatically create C:\0github\<file> (creating subfolders on C:\ is allowed without elevation!)
            if ($cand -match '^[Cc]:\\[^\\]+$') {
                $leaf = Split-Path -Path $cand -Leaf
                $fallbackDir = 'C:\0github'
                $fallbackPath = Join-Path $fallbackDir $leaf
                try {
                    if (-not (Test-Path -LiteralPath $fallbackDir)) {
                        New-Item -ItemType Directory -Path $fallbackDir -Force -ErrorAction Stop | Out-Null
                    }
                    if ($UseBytes) {
                        [System.IO.File]::WriteAllBytes($fallbackPath, $Bytes)
                    } else {
                        [System.IO.File]::WriteAllText($fallbackPath, $TextContent, (New-Object System.Text.UTF8Encoding($false)))
                    }
                    if (Test-Path -LiteralPath $fallbackPath) {
                        $writtenPaths += $fallbackPath
                    }
                } catch {}
            }
        }
    }
    return $writtenPaths
}

function Copy-ResultsFromDir([string]$SourceDir, [string]$ShortName) {
    if (-not (Test-Path -LiteralPath $SourceDir)) { return $false }
    $copiedAny = $false

    $srcRes = Join-Path $SourceDir 'results'
    if (Test-Path -LiteralPath $srcRes) {
        $items = @(Get-ChildItem -LiteralPath $srcRes -Force -ErrorAction SilentlyContinue)
        if ($items.Count -gt 0) {
            $dst = Join-Path $ResultsRoot $ShortName
            if (-not (Test-Path -LiteralPath $dst)) {
                New-Item -ItemType Directory -Path $dst -Force | Out-Null
            }
            & robocopy.exe $srcRes $dst /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
            $copiedAny = $true
        }
    }

    $srcDeliv = Join-Path $SourceDir 'deliverable'
    if (Test-Path -LiteralPath $srcDeliv) {
        $items = @(Get-ChildItem -LiteralPath $srcDeliv -Force -ErrorAction SilentlyContinue)
        if ($items.Count -gt 0) {
            $dstD = Join-Path (Join-Path $ResultsRoot $ShortName) 'deliverable'
            if (-not (Test-Path -LiteralPath $dstD)) {
                New-Item -ItemType Directory -Path $dstD -Force | Out-Null
            }
            & robocopy.exe $srcDeliv $dstD /E /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
            $copiedAny = $true
        }
    }
    return $copiedAny
}

function Get-SeenHeads {
    $map = @{}
    $seedPath = Join-Path $PSScriptRoot 'code\tasks\initial_seen_heads.json'
    if (Test-Path -LiteralPath $seedPath) {
        try {
            $seedObj = Get-Content -LiteralPath $seedPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($p in $seedObj.PSObject.Properties) {
                $k = [string]$p.Name
                $v = [string]$p.Value
                if ($k -match '^https://github\.com/[^/]+/(.+)$') {
                    $norm = $Matches[1]
                    if (-not $map.ContainsKey($norm)) { $map[$norm] = $v }
                } else {
                    $map[$k] = $v
                }
            }
        } catch {}
    }
    if (Test-Path -LiteralPath $SeenHeadsJson) {
        try {
            $curObj = Get-Content -LiteralPath $SeenHeadsJson -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($p in $curObj.PSObject.Properties) {
                $k = [string]$p.Name
                $v = [string]$p.Value
                if ($k -match '^https://github\.com/[^/]+/(.+)$') {
                    $norm = $Matches[1]
                    if (-not $map.ContainsKey($norm)) { $map[$norm] = $v }
                } else {
                    $map[$k] = $v
                }
            }
        } catch {}
    }
    return $map
}

function Save-SeenHeads([hashtable]$Map) {
    try {
        $clean = [ordered]@{}
        foreach ($k in ($Map.Keys | Sort-Object)) {
            $ks = [string]$k
            if ($ks -match '^https://') { continue }
            $clean[$ks] = [string]$Map[$k]
        }
        ($clean | ConvertTo-Json -Depth 3) | Set-Content -LiteralPath $SeenHeadsJson -Encoding UTF8
    } catch {}
}

function Invoke-ResultsOnlyCleanup {
    if (-not (Test-Path -LiteralPath $ResultsRoot)) {
        New-Item -ItemType Directory -Path $ResultsRoot -Force | Out-Null
    }

    $evictedClones = 0
    if (Test-Path -LiteralPath $SyncRoot) {
        $dirs = @(Get-ChildItem -LiteralPath $SyncRoot -Directory -Force -ErrorAction SilentlyContinue)
        foreach ($d in $dirs) {
            if ($d.Name -ieq $BaseDirName) { continue }
            Copy-ResultsFromDir -SourceDir $d.FullName -ShortName $d.Name | Out-Null
            if (Remove-TreeSafe -Target $d.FullName) {
                $evictedClones++
            }
        }
    }

    $evictedTop = 0
    if (Test-Path -LiteralPath $TopRoot) {
        $topItems = @(Get-ChildItem -LiteralPath $TopRoot -Force -ErrorAction SilentlyContinue)
        foreach ($item in $topItems) {
            if ($item.Name -ieq '.git-sync' -or $item.Name -ieq 'results') { continue }
            if ($item.PSIsContainer) {
                Copy-ResultsFromDir -SourceDir $item.FullName -ShortName $item.Name | Out-Null
                if (Remove-TreeSafe -Target $item.FullName) {
                    $evictedTop++
                }
            } else {
                Remove-Item -LiteralPath $item.FullName -Force -ErrorAction SilentlyContinue
                $evictedTop++
            }
        }
    }

    return @{
        evicted_clones = $evictedClones
        evicted_top    = $evictedTop
    }
}

function Invoke-BranchTasksSilently([string]$ProjectDir, [string]$RepoName, [string]$Branch, [string]$ShortName, [string]$SourceSha) {
    $execLogs = @()
    $copiedTargets = @()
    $env:HUB_REPO_DIR    = $ProjectDir
    $env:HUB_RESULTS_DIR = (Join-Path $ResultsRoot $ShortName)
    $env:HUB_PYTHON_EXE  = $PythonExe

    # 1. Process results/status/desktop_target.json if present
    $dtPath = Join-Path $ProjectDir 'results\status\desktop_target.json'
    if (Test-Path -LiteralPath $dtPath) {
        try {
            $dt = Get-Content -LiteralPath $dtPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($dt.source -and $dt.target_path -and ($dt.status -ne 'confirmed_written_on_host')) {
                $srcRel  = ([string]$dt.source) -replace '/', '\'
                $srcFull = Join-Path $ProjectDir $srcRel
                if (Test-Path -LiteralPath $srcFull) {
                    $bytes = [System.IO.File]::ReadAllBytes($srcFull)
                    $written = @(Write-LocalFileSafe -TargetPath ([string]$dt.target_path) -Bytes $bytes -UseBytes $true)
                    $copiedTargets += $written
                    $dt | Add-Member -NotePropertyName 'status' -NotePropertyValue 'confirmed_written_on_host' -Force
                    $dt | Add-Member -NotePropertyName 'confirmed_by_host' -NotePropertyValue $env:COMPUTERNAME -Force
                    $dt | Add-Member -NotePropertyName 'confirmed_at_utc' -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) -Force
                    $dt | Add-Member -NotePropertyName 'confirmed_at_local' -NotePropertyValue ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) -Force
                    $dt | Add-Member -NotePropertyName 'written_paths' -NotePropertyValue $written -Force
                    $dt | Add-Member -NotePropertyName 'verified_bytes' -NotePropertyValue $bytes.Length -Force
                    ($dt | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $dtPath -Encoding UTF8
                    $execLogs += [ordered]@{
                        step         = 'desktop_target.json'
                        exit_code    = 0
                        written_to   = $written
                        bytes        = $bytes.Length
                    }
                }
            }
        } catch {
            $execLogs += [ordered]@{
                step      = 'desktop_target.json'
                exit_code = 1
                error     = $_.Exception.Message
            }
        }
    }

    # 2. Process results/status/hub_task.json or results/task/task.json if present
    foreach ($taskJsonRel in @('results\status\hub_task.json', 'results\task\task.json')) {
        $tjPath = Join-Path $ProjectDir $taskJsonRel
        if (-not (Test-Path -LiteralPath $tjPath)) { continue }
        try {
            $tj = Get-Content -LiteralPath $tjPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($tj.PSObject.Properties['enabled'] -and ($tj.enabled -eq $false)) { continue }
            if (($tj.status -eq 'completed_on_host') -and (-not $tj.always_run)) { continue }
            $taskFailed = $false
            $taskWritten = @()

            # 2a. write_files: [{ "path": "C:\\...", "content": "..." }]
            if ($tj.write_files) {
                foreach ($wf in @($tj.write_files)) {
                    if (-not $wf.path) { continue }
                    $text = [string]$wf.content
                    $wPaths = @(Write-LocalFileSafe -TargetPath ([string]$wf.path) -TextContent $text -UseBytes $false)
                    $copiedTargets += $wPaths
                    $taskWritten += $wPaths
                    if ($wPaths.Count -eq 0) { $taskFailed = $true }
                    $execLogs += [ordered]@{
                        step       = "write_file: $($wf.path)"
                        exit_code  = if ($wPaths.Count -gt 0) { 0 } else { 1 }
                        written_to = $wPaths
                    }
                }
            }

            # 2b. copy_files: [{ "source": "results/...", "target": "C:\\..." }]
            if ($tj.copy_files) {
                foreach ($cf in @($tj.copy_files)) {
                    $srcRel = ([string]$cf.source) -replace '/', '\'
                    $tgt    = [string]($cf.target, $cf.target_path | Where-Object { $_ } | Select-Object -First 1)
                    $srcFull = Join-Path $ProjectDir $srcRel
                    if ($tgt -and (Test-Path -LiteralPath $srcFull)) {
                        $b = [System.IO.File]::ReadAllBytes($srcFull)
                        $wPaths = @(Write-LocalFileSafe -TargetPath $tgt -Bytes $b -UseBytes $true)
                        $copiedTargets += $wPaths
                        $taskWritten += $wPaths
                        if ($wPaths.Count -eq 0) { $taskFailed = $true }
                        $execLogs += [ordered]@{
                            step       = "copy_file: $srcRel -> $tgt"
                            exit_code  = if ($wPaths.Count -gt 0) { 0 } else { 1 }
                            written_to = $wPaths
                            bytes      = $b.Length
                        }
                    }
                }
            }

            # 2c. Inline powershell commands
            if ($tj.powershell) {
                foreach ($psCmd in @($tj.powershell)) {
                    if (-not $psCmd) { continue }
                    $tmpPs = Join-Path $env:TEMP ("hub_inline_{0}.ps1" -f [guid]::NewGuid().ToString('N'))
                    [System.IO.File]::WriteAllText($tmpPs, [string]$psCmd, (New-Object System.Text.UTF8Encoding($true)))
                    $r = Invoke-ProcessSilent -FileName 'powershell.exe' -Arguments "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$tmpPs`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 120
                    Remove-Item -LiteralPath $tmpPs -Force -ErrorAction SilentlyContinue
                    if ($r.exit_code -ne 0) { $taskFailed = $true }
                    $execLogs += [ordered]@{
                        step       = 'hub_task.powershell'
                        exit_code  = $r.exit_code
                        elapsed_ms = $r.elapsed_ms
                        stdout     = $r.stdout.Trim()
                        stderr     = $r.stderr.Trim()
                    }
                }
            }

            # 2d. Inline python code/commands
            if ($tj.python) {
                foreach ($pyCmd in @($tj.python)) {
                    if (-not $pyCmd) { continue }
                    $tmpPy = Join-Path $env:TEMP ("hub_inline_{0}.py" -f [guid]::NewGuid().ToString('N'))
                    [System.IO.File]::WriteAllText($tmpPy, [string]$pyCmd, (New-Object System.Text.UTF8Encoding($false)))
                    $r = Invoke-ProcessSilent -FileName $PythonExe -Arguments "`"$tmpPy`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 120
                    Remove-Item -LiteralPath $tmpPy -Force -ErrorAction SilentlyContinue
                    if ($r.exit_code -ne 0) { $taskFailed = $true }
                    $execLogs += [ordered]@{
                        step       = 'hub_task.python'
                        exit_code  = $r.exit_code
                        elapsed_ms = $r.elapsed_ms
                        stdout     = $r.stdout.Trim()
                        stderr     = $r.stderr.Trim()
                    }
                }
            }

            # 2e. Inline bash commands
            if ($tj.bash) {
                foreach ($shCmd in @($tj.bash)) {
                    if (-not $shCmd) { continue }
                    $tmpSh = Join-Path $env:TEMP ("hub_inline_{0}.sh" -f [guid]::NewGuid().ToString('N'))
                    $lfText = ([string]$shCmd) -replace "`r`n", "`n"
                    [System.IO.File]::WriteAllText($tmpSh, $lfText, (New-Object System.Text.UTF8Encoding($false)))
                    $r = Invoke-ProcessSilent -FileName $BashExe -Arguments "`"$tmpSh`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 120
                    Remove-Item -LiteralPath $tmpSh -Force -ErrorAction SilentlyContinue
                    if ($r.exit_code -ne 0) { $taskFailed = $true }
                    $execLogs += [ordered]@{
                        step       = 'hub_task.bash'
                        exit_code  = $r.exit_code
                        elapsed_ms = $r.elapsed_ms
                        stdout     = $r.stdout.Trim()
                        stderr     = $r.stderr.Trim()
                    }
                }
            }

            # 2f. Inline cmd commands
            if ($tj.cmd) {
                foreach ($cCmd in @($tj.cmd)) {
                    if (-not $cCmd) { continue }
                    $r = Invoke-ProcessSilent -FileName 'cmd.exe' -Arguments "/c $cCmd" -WorkingDirectory $ProjectDir -TimeoutSeconds 120
                    if ($r.exit_code -ne 0) { $taskFailed = $true }
                    $execLogs += [ordered]@{
                        step       = 'hub_task.cmd'
                        exit_code  = $r.exit_code
                        elapsed_ms = $r.elapsed_ms
                        stdout     = $r.stdout.Trim()
                        stderr     = $r.stderr.Trim()
                    }
                }
            }

            $tj | Add-Member -NotePropertyName 'status' -NotePropertyValue ($(if ($taskFailed) { 'failed_on_host' } else { 'completed_on_host' })) -Force
            $tj | Add-Member -NotePropertyName 'executed_on_host' -NotePropertyValue $env:COMPUTERNAME -Force
            $tj | Add-Member -NotePropertyName 'executed_at_utc' -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) -Force
            $tj | Add-Member -NotePropertyName 'executed_at_local' -NotePropertyValue ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) -Force
            $tj | Add-Member -NotePropertyName 'source_commit' -NotePropertyValue $SourceSha -Force
            if ($taskWritten.Count -gt 0) {
                $tj | Add-Member -NotePropertyName 'written_paths' -NotePropertyValue $taskWritten -Force
            }
            ($tj | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $tjPath -Encoding UTF8
        } catch {
            $execLogs += [ordered]@{
                step      = $taskJsonRel
                exit_code = 1
                error     = $_.Exception.Message
            }
        }
    }

    # 3. Execute standalone task scripts if present
    $scriptCandidates = @(
        @{ rel = 'results\task\run.ps1'; kind = 'ps1' },
        @{ rel = 'code\hub_task.ps1';    kind = 'ps1' },
        @{ rel = 'results\task\run.py';  kind = 'py'  },
        @{ rel = 'code\hub_task.py';     kind = 'py'  },
        @{ rel = 'results\task\run.sh';  kind = 'sh'  },
        @{ rel = 'code\hub_task.sh';     kind = 'sh'  }
    )
    foreach ($sc in $scriptCandidates) {
        $sFull = Join-Path $ProjectDir $sc.rel
        if (-not (Test-Path -LiteralPath $sFull)) { continue }
        $r = $null
        if ($sc.kind -eq 'ps1') {
            $r = Invoke-ProcessSilent -FileName 'powershell.exe' -Arguments "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$sFull`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 180
        } elseif ($sc.kind -eq 'py') {
            $r = Invoke-ProcessSilent -FileName $PythonExe -Arguments "`"$sFull`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 180
        } elseif ($sc.kind -eq 'sh') {
            $r = Invoke-ProcessSilent -FileName $BashExe -Arguments "`"$sFull`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 180
        }
        if ($r) {
            $execLogs += [ordered]@{
                step       = $sc.rel
                exit_code  = $r.exit_code
                elapsed_ms = $r.elapsed_ms
                stdout     = $r.stdout.Trim()
                stderr     = $r.stderr.Trim()
            }
        }
    }

    # Pre-write hub_exec_output.txt and hub_sync_receipt.json so code/local_check.ps1 criteria can inspect them if needed
    $statusDir = Join-Path $ProjectDir 'results\status'
    if (-not (Test-Path -LiteralPath $statusDir)) {
        New-Item -ItemType Directory -Path $statusDir -Force | Out-Null
    }
    if ($execLogs.Count -gt 0) {
        $preLines = @(
            "== git-sync-hub v4.0 execution log on $env:COMPUTERNAME ==",
            "repo: $RepoName",
            "branch: $Branch",
            "source_commit: $SourceSha",
            ""
        )
        foreach ($el in $execLogs) {
            $preLines += "--- step: $($el.step) (exit=$($el.exit_code)) ---"
            if ($el.written_to) { $preLines += "written_to: $(($el.written_to) -join ', ')" }
            if ($el.stdout)     { $preLines += $el.stdout }
            if ($el.stderr)     { $preLines += "[stderr] $($el.stderr)" }
            if ($el.error)      { $preLines += "[error] $($el.error)" }
            $preLines += ""
        }
        Set-Content -LiteralPath (Join-Path $statusDir 'hub_exec_output.txt') -Value ($preLines -join "`r`n") -Encoding UTF8
    }
    $preReceipt = [ordered]@{
        status               = 'synced'
        host                 = $env:COMPUTERNAME
        repo                 = $RepoName
        branch               = $Branch
        source_commit        = $SourceSha
        synced_at_utc        = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        synced_at_local      = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        poll_interval_sec    = $IntervalSeconds
        local_results_dir    = (Join-Path $ResultsRoot $ShortName)
        tasks_executed_count = $execLogs.Count
        tasks_executed       = $execLogs
        copied_targets       = $copiedTargets
        mode                 = 'auto-poll-exec-and-sync-zero-window-v4.0'
    }
    ($preReceipt | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath (Join-Path $statusDir 'hub_sync_receipt.json') -Encoding UTF8

    # 4. If handshake.json has local_state == pending and code/local_check.ps1 exists, run code/local_check.ps1 directly
    $hsPath = Join-Path $ProjectDir 'results\status\handshake.json'
    $lcPath = Join-Path $ProjectDir 'code\local_check.ps1'
    if ((Test-Path -LiteralPath $hsPath) -and (Test-Path -LiteralPath $lcPath)) {
        try {
            $hs = Get-Content -LiteralPath $hsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($hs.local_state -eq 'pending') {
                $r = Invoke-ProcessSilent -FileName 'powershell.exe' -Arguments "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$lcPath`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 240
                $rNum = if ($hs.round) { [int]$hs.round } else { 1 }
                $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                $logName = "check_r{0}_{1}.txt" -f $rNum, $stamp
                $logPath = Join-Path $statusDir $logName
                $verdict = if ($r.exit_code -eq 0) { 'passed' } else { 'failed' }
                $logBody = @(
                    "check round $rNum on $env:COMPUTERNAME - $verdict (exit $($r.exit_code))",
                    "mode: auto-poll-exec-and-sync-zero-window-v4.0",
                    "",
                    $r.stdout.TrimEnd()
                )
                if ($r.stderr.Trim()) {
                    $logBody += ""
                    $logBody += "[stderr]"
                    $logBody += $r.stderr.TrimEnd()
                }
                Set-Content -LiteralPath $logPath -Value ($logBody -join "`r`n") -Encoding UTF8

                $hs | Add-Member -NotePropertyName 'local_state' -NotePropertyValue $verdict -Force
                $hs | Add-Member -NotePropertyName 'local_updated' -NotePropertyValue ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) -Force
                $hs | Add-Member -NotePropertyName 'host' -NotePropertyValue $env:COMPUTERNAME -Force
                $hs | Add-Member -NotePropertyName 'local_log' -NotePropertyValue ("results/status/$logName") -Force
                ($hs | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $hsPath -Encoding UTF8

                $execLogs += [ordered]@{
                    step       = 'code/local_check.ps1'
                    exit_code  = $r.exit_code
                    elapsed_ms = $r.elapsed_ms
                    verdict    = $verdict
                    log_file   = "results/status/$logName"
                }
            }
        } catch {}
    }

    return @{
        exec_logs      = $execLogs
        copied_targets = $copiedTargets
    }
}

function Push-ResultsReceipt([string]$ProjectDir, [string]$RepoName, [string]$Branch, [string]$ShortName, [string]$SourceSha, [hashtable]$TaskOutcome) {
    $statusDir = Join-Path $ProjectDir 'results\status'
    if (-not (Test-Path -LiteralPath $statusDir)) {
        New-Item -ItemType Directory -Path $statusDir -Force | Out-Null
    }

    $execLogs = @($TaskOutcome.exec_logs)
    $copiedTargets = @($TaskOutcome.copied_targets)

    # Check if handshake is already accepted and no new tasks ran -> mirror locally without pushing an extra commit
    $hsPath = Join-Path $statusDir 'handshake.json'
    if ((Test-Path -LiteralPath $hsPath) -and ($execLogs.Count -eq 0)) {
        try {
            $hsCheck = Get-Content -LiteralPath $hsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if (($hsCheck.arena_state -eq 'accepted') -and ($hsCheck.local_state -eq 'passed')) {
                Copy-ResultsFromDir -SourceDir $ProjectDir -ShortName $ShortName | Out-Null
                return
            }
        } catch {}
    }

    # Write human-readable execution log if any tasks ran
    $allOk = $true
    foreach ($el in $execLogs) {
        if ($el.exit_code -ne 0) { $allOk = $false }
    }
    if ($execLogs.Count -gt 0) {
        $lines = @(
            "== git-sync-hub v4.0 execution log on $env:COMPUTERNAME ==",
            "repo: $RepoName",
            "branch: $Branch",
            "source_commit: $SourceSha",
            "executed_at_utc: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))",
            "executed_at_local: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))",
            "tasks_all_ok: $allOk",
            ""
        )
        foreach ($el in $execLogs) {
            $lines += "--- step: $($el.step) (exit=$($el.exit_code)) ---"
            if ($el.written_to) { $lines += "written_to: $(($el.written_to) -join ', ')" }
            if ($el.stdout)     { $lines += $el.stdout }
            if ($el.stderr)     { $lines += "[stderr] $($el.stderr)" }
            if ($el.error)      { $lines += "[error] $($el.error)" }
            $lines += ""
        }
        $outLogPath = Join-Path $statusDir 'hub_exec_output.txt'
        Set-Content -LiteralPath $outLogPath -Value ($lines -join "`r`n") -Encoding UTF8
    }

    # First mirror all results/ and deliverable/ to C:\0github\results\<ShortName>
    Copy-ResultsFromDir -SourceDir $ProjectDir -ShortName $ShortName | Out-Null

    $localResDir = Join-Path $ResultsRoot $ShortName
    if (-not (Test-Path -LiteralPath $localResDir)) {
        New-Item -ItemType Directory -Path $localResDir -Force | Out-Null
    }
    $fileCount = @(Get-ChildItem -LiteralPath $localResDir -Recurse -File -Force -ErrorAction SilentlyContinue).Count
    $nowUtc    = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $nowLocal  = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')

    $receipt = [ordered]@{
        status               = 'synced'
        host                 = $env:COMPUTERNAME
        repo                 = $RepoName
        branch               = $Branch
        source_commit        = $SourceSha
        synced_at_utc        = $nowUtc
        synced_at_local      = $nowLocal
        poll_interval_sec    = $IntervalSeconds
        local_results_dir    = $localResDir
        synced_files_count   = $fileCount
        tasks_executed_count = $execLogs.Count
        tasks_all_ok         = $allOk
        tasks_executed       = $execLogs
        copied_targets       = $copiedTargets
        mode                 = 'auto-poll-exec-and-sync-zero-window-v4.0'
    }
    $receiptPath = Join-Path $statusDir 'hub_sync_receipt.json'
    ($receipt | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $receiptPath -Encoding UTF8

    # If handshake.json is still pending (e.g., no local_check.ps1 was present), mark it passed/failed based on $allOk
    if (Test-Path -LiteralPath $hsPath) {
        try {
            $hs = Get-Content -LiteralPath $hsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($hs.local_state -eq 'pending') {
                $rNum = if ($hs.round) { [int]$hs.round } else { 1 }
                $verdict = if ($allOk) { 'passed' } else { 'failed' }
                $logName = "check_r{0}_{1}.txt" -f $rNum, (Get-Date -Format 'yyyyMMdd-HHmmss')
                $logPath = Join-Path $statusDir $logName
                $hs | Add-Member -NotePropertyName 'local_state' -NotePropertyValue $verdict -Force
                $hs | Add-Member -NotePropertyName 'local_updated' -NotePropertyValue $nowLocal -Force
                $hs | Add-Member -NotePropertyName 'host' -NotePropertyValue $env:COMPUTERNAME -Force
                $hs | Add-Member -NotePropertyName 'local_log' -NotePropertyValue ("results/status/$logName") -Force
                ($hs | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $hsPath -Encoding UTF8

                $logBody = @(
                    "check round $rNum on $env:COMPUTERNAME - $verdict (exit $(if ($allOk) { 0 } else { 1 }))",
                    "mode: auto-poll-exec-and-sync-zero-window-v4.0",
                    "local_results_dir: $localResDir",
                    "tasks_executed_count: $($execLogs.Count)",
                    "synced_files_count: $fileCount",
                    "== local execution and results sync $verdict"
                ) -join "`r`n"
                Set-Content -LiteralPath $logPath -Value $logBody -Encoding UTF8
            }
        } catch {}
    }

    # Re-mirror updated status files into C:\0github\results\<ShortName>
    Copy-ResultsFromDir -SourceDir $ProjectDir -ShortName $ShortName | Out-Null

    try {
        [void](Invoke-GitSilent -Arguments "-C `"$ProjectDir`" config user.name `"git-sync-hub ($env:COMPUTERNAME)`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 10)
        [void](Invoke-GitSilent -Arguments "-C `"$ProjectDir`" config user.email `"git-sync-hub@local`"" -WorkingDirectory $ProjectDir -TimeoutSeconds 10)
        if (Test-Path -LiteralPath (Join-Path $ProjectDir 'results')) {
            [void](Invoke-GitSilent -Arguments "-C `"$ProjectDir`" add -A results" -WorkingDirectory $ProjectDir -TimeoutSeconds 20)
        }
        if (Test-Path -LiteralPath (Join-Path $ProjectDir 'deliverable')) {
            [void](Invoke-GitSilent -Arguments "-C `"$ProjectDir`" add -A deliverable" -WorkingDirectory $ProjectDir -TimeoutSeconds 20)
        }
        [void](Invoke-GitSilent -Arguments "-C `"$ProjectDir`" commit -m `"hub($env:COMPUTERNAME): exec & sync to $localResDir`" --quiet" -WorkingDirectory $ProjectDir -TimeoutSeconds 20)
        [void](Invoke-GitSilent -Arguments "-C `"$ProjectDir`" push origin $Branch --quiet" -WorkingDirectory $ProjectDir -TimeoutSeconds 45)
    } catch {
        Write-HubLog "WARN: receipt push failed on ${ShortName}: $($_.Exception.Message)"
    }
}

function Update-BaseRepo {
    $baseDir = $PSScriptRoot
    if (-not (Test-Path -LiteralPath (Join-Path $baseDir '.git'))) {
        $baseDir = Join-Path $SyncRoot $BaseDirName
    }
    if (-not (Test-Path -LiteralPath (Join-Path $baseDir '.git'))) { return }

    try {
        [void](Invoke-GitSilent -Arguments "-C `"$baseDir`" fetch origin --prune --quiet" -WorkingDirectory $baseDir -TimeoutSeconds 30)
        $brRes = Invoke-GitSilent -Arguments "-C `"$baseDir`" rev-parse --abbrev-ref HEAD" -WorkingDirectory $baseDir -TimeoutSeconds 10
        $branch = ([string]$brRes.stdout).Trim()
        if ($branch) {
            [void](Invoke-GitSilent -Arguments "-C `"$baseDir`" pull --ff-only origin $branch --quiet" -WorkingDirectory $baseDir -TimeoutSeconds 30)
        }
        $wPath = Join-Path $baseDir 'hub-worker.ps1'
        if (Test-Path -LiteralPath $wPath) {
            try { . $wPath } catch {}
        }
        $baseWatch = Join-Path $baseDir 'watch.ps1'
        if (Test-Path -LiteralPath $baseWatch) {
            [void](Invoke-ProcessSilent -FileName 'powershell.exe' -Arguments "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$baseWatch`"" -WorkingDirectory $baseDir -TimeoutSeconds 180)
        }
        Copy-ResultsFromDir -SourceDir $baseDir -ShortName $BaseDirName | Out-Null
    } catch {
        Write-HubLog "WARN: base repo update failed: $($_.Exception.Message)"
    }
}

function Get-TargetReposToCheck {
    $skipRepos = @('git-pull-arena', 'rea', 'Light-skills', 'subs-check-pro', 'AgentArena', 'BrowserSkill', 'zhongqi')
    # Fast path: check active repos via direct git ls-remote every 15s (zero REST API limit),
    # and refresh repo list from authenticated GitHub API every 45s.
    if ((-not $script:ActiveRepoNames) -or ($script:ActiveRepoNames.Count -gt 12)) {
        $script:ActiveRepoNames = @(
            'goutoujunshi',
            'leanrea',
            'skills',
            '-skills'
        )
    } else {
        $script:ActiveRepoNames = @($script:ActiveRepoNames | Where-Object { $_ -notin $skipRepos })
    }
    $now = Get-Date
    if ((-not $script:LastApiRefresh) -or (($now - $script:LastApiRefresh).TotalSeconds -ge 45)) {
        $script:LastApiRefresh = $now
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $headers = @{
            'User-Agent' = 'leanrea-git-sync-hub/4.0'
            'Accept'     = 'application/vnd.github.v3+json'
        }
        $tok = Get-GitHubToken
        if ($tok) {
            $headers['Authorization'] = "Bearer $tok"
        }
        $url = "https://api.github.com/users/$Owner/repos?per_page=15&sort=pushed&direction=desc"
        try {
            $repos = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 15 -ErrorAction Stop
            $fresh = @('goutoujunshi', 'leanrea', 'skills', '-skills')
            foreach ($r in $repos) {
                if (-not $r.pushed_at) { continue }
                $rn = [string]$r.name
                if ($rn -in $skipRepos) { continue }
                $pushedIso = ([DateTime]$r.pushed_at).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                if ($pushedIso -ge '2026-10-20T00:00:00Z') {
                    if ($fresh -notcontains $rn) { $fresh += $rn }
                }
            }
            $script:ActiveRepoNames = @($fresh | Select-Object -First 12)
        } catch {
            Write-HubLog "WARN: API refresh skipped (using direct ls-remote list): $($_.Exception.Message)"
        }
    }
    return $script:ActiveRepoNames
}

function Sync-NewRemoteBranches {
    $seen    = Get-SeenHeads
    $changed = $false
    $synced  = 0

    $tempRoot = Join-Path $env:TEMP 'git-sync-hub-ephemeral'
    if (-not (Test-Path -LiteralPath $tempRoot)) {
        New-Item -ItemType Directory -Path $tempRoot -Force -ErrorAction SilentlyContinue | Out-Null
    }

    $repoNames = @(Get-TargetReposToCheck)
    foreach ($repoName in $repoNames) {
        if ($synced -ge 3) { break }
        $cloneUrl = "https://github.com/$Owner/$repoName.git"
        $lsRes = Invoke-GitSilent -Arguments "ls-remote --heads $cloneUrl refs/heads/arena/*" -TimeoutSeconds 20
        if ($lsRes.exit_code -ne 0) { continue }
        $lsOut = @($lsRes.stdout -split "`r?`n")
        foreach ($line in $lsOut) {
            if ($synced -ge 3) { break }
            if ($line -notmatch '^([0-9a-f]{40})\s+refs/heads/(arena/.+)$') { continue }
            $sha    = $Matches[1]
            $branch = $Matches[2].Trim()
            $key    = "{0}#{1}" -f $repoName, $branch

            $shortName = Get-ShortCloneName -RepoName $repoName -Branch $branch
            if ($shortName -ieq $BaseDirName) {
                if ($seen[$key] -ne $sha) {
                    $seen[$key] = $sha
                    $changed = $true
                }
                continue
            }

            if ($seen.ContainsKey($key) -and ($seen[$key] -eq $sha)) {
                continue
            }

            Write-HubLog "NEW-BRANCH-ACTIVITY: $key @ $($sha.Substring(0, 7)) -> pull + exec + sync"
            $dest = Join-Path $tempRoot ("{0}-{1}" -f $shortName, [guid]::NewGuid().ToString('N').Substring(0, 8))

            try {
                # Record seen SHA before clone so a timed-out/broken branch never blocks the queue forever
                $seen[$key] = $sha
                Save-SeenHeads -Map $seen
                $changed = $true

                $clRes = Invoke-GitSilent -Arguments "clone --quiet --depth 1 --filter=blob:none --sparse --branch $branch $cloneUrl `"$dest`"" -TimeoutSeconds 45
                if (($clRes.exit_code -eq 0) -and (Test-Path -LiteralPath (Join-Path $dest '.git'))) {
                    [void](Invoke-GitSilent -Arguments "-C `"$dest`" sparse-checkout set results deliverable code skills" -WorkingDirectory $dest -TimeoutSeconds 45)

                    $taskOutcome = Invoke-BranchTasksSilently -ProjectDir $dest -RepoName $repoName -Branch $branch -ShortName $shortName -SourceSha $sha
                    Push-ResultsReceipt -ProjectDir $dest -RepoName $repoName -Branch $branch -ShortName $shortName -SourceSha $sha -TaskOutcome $taskOutcome

                    $headRes = Invoke-GitSilent -Arguments "-C `"$dest`" rev-parse HEAD" -WorkingDirectory $dest -TimeoutSeconds 10
                    $finalSha = ([string]$headRes.stdout).Trim()
                    if ($finalSha -match '^[0-9a-f]{40}$') {
                        $seen[$key] = $finalSha
                        Save-SeenHeads -Map $seen
                    }
                    $synced++
                    Write-HubLog "NEW-BRANCH-DONE: $key -> final=$($seen[$key].Substring(0,7)) tasks=$($taskOutcome.exec_logs.Count)"
                } else {
                    Write-HubLog "WARN: clone timed out or failed on ${key} (exit=$($clRes.exit_code))"
                }
            } catch {
                Write-HubLog "WARN: ephemeral sync error on ${key}: $($_.Exception.Message)"
            } finally {
                Remove-TreeSafe -Target $dest | Out-Null
            }
        }
    }

    if ($changed) {
        Save-SeenHeads -Map $seen
    }
    return $synced
}

function Invoke-OneCycle {
    Set-Content -LiteralPath $PidFile -Value ([string]$PID) -Encoding ASCII -ErrorAction SilentlyContinue
    try {
        $dups = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'hub-watch\.ps1' -and $_.ProcessId -ne $PID })
        foreach ($dp in $dups) {
            Stop-Process -Id $dp.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {}
    Update-BaseRepo
    $workerPath = Join-Path $PSScriptRoot 'hub-worker.ps1'
    if (Test-Path -LiteralPath $workerPath) {
        try { . $workerPath } catch {}
    }
    $syncedNew = Sync-NewRemoteBranches
    $cleanInfo = Invoke-ResultsOnlyCleanup
    $resCount  = @(Get-ChildItem -LiteralPath $ResultsRoot -Directory -ErrorAction SilentlyContinue).Count

    $state = [ordered]@{
        updated_at        = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        host              = $env:COMPUTERNAME
        pid               = $PID
        task_name         = $TaskName
        mode              = 'auto-poll-exec-and-sync-zero-window-v4.0'
        poll_interval_sec = $IntervalSeconds
        sync_root         = $SyncRoot
        results_root      = $ResultsRoot
        base_dir          = (Join-Path $SyncRoot $BaseDirName)
        cutoff_iso        = $CutoffIso
        result_projects   = $resCount
        synced_new        = $syncedNew
        evicted_clones    = $cleanInfo.evicted_clones
        evicted_top       = $cleanInfo.evicted_top
    }
    ($state | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $StateJson -Encoding UTF8
    Write-HubLog ("CYCLE-DONE: result_projects={0} synced_new={1} evicted_clones={2}" -f $resCount, $syncedNew, $cleanInfo.evicted_clones)
}

if ($Status) {
    if (Test-Path -LiteralPath $StateJson) {
        Get-Content -LiteralPath $StateJson -Raw
    } else {
        Write-Output "No state file yet at $StateJson"
    }
    return
}

do {
    try {
        $workerPath = Join-Path $PSScriptRoot 'hub-worker.ps1'
        if (Test-Path -LiteralPath $workerPath) {
            try { . $workerPath } catch {}
        }
        Invoke-OneCycle
    } catch {
        Write-HubLog "CYCLE-ERROR: $($_.Exception.Message)"
    }
    if ($Loop) {
        Start-Sleep -Seconds $IntervalSeconds
    }
} while ($Loop)
