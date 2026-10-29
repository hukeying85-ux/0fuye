#Requires -Version 5.1
<#
.SYNOPSIS
    One poll cycle of the CGMD desktop hub (designed for a 60 s scheduled task).

.DESCRIPTION
    1. guards against overlapping runs (exclusive lock file);
    2. fetches the configured branch and verifies the origin is the locked
       repository hukeying85-ux/0fuye (any other remote aborts immediately);
    3. reads results/status/cgmd_task.json from the branch;
    4. when status == "pending" (or an abandoned claim), starts
       code/federation/desktop_runner.py inside WSL2, which claims the task,
       runs the Martini 3 pipeline on the GPU and writes the reduced result;
    5. commits only results/status + results/cgmd and pushes back to the same
       branch, then records a heartbeat in state/hub-state.json (and, at most
       once per -HeartbeatMinutes, a tiny results/status/hub_heartbeat.json in
       git so that other clients can see the watcher is alive).

    Absolutely nothing is written to the screen: this script is started by
    wscript.exe (see CgmdPoll.vbs), which has no console at all.

.PARAMETER ConfigPath
    Workstation config, default ..\config\cgmd_hub.local.json

.PARAMETER Force
    Run even when the task is not pending (used by bootstrap validation).

.PARAMETER NoPublish
    Execute the task but never push (leaves the commit local).

.PARAMETER MaxRunMinutes
    Hard wall clock limit for the simulation; 0 means no limit.

.PARAMETER HeartbeatMinutes
    Minimum minutes between two git heart-beats; 0 writes one every cycle,
    -1 disables the git heart-beat (the local state/hub-state.json is kept).

.EXAMPLE
    powershell -NoProfile -File Invoke-CgmdPoll.ps1 -Force
#>
[CmdletBinding()]
param(
    [string]$ConfigPath,
    [switch]$Force,
    [switch]$NoPublish,
    [int]$MaxRunMinutes = 0,
    [int]$HeartbeatMinutes = 60,
    [int]$StaleLockMinutes = 90,
    [switch]$LogVerbose
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StateDir = Join-Path $script:HubRoot 'state'
$script:LogDir = Join-Path $script:HubRoot 'logs'
$script:LockPath = Join-Path $script:StateDir 'poll.lock'
$script:StatePath = Join-Path $script:StateDir 'hub-state.json'
$script:RunOut = Join-Path $script:StateDir 'last-run.log'
$script:CmdFile = Join-Path $script:StateDir 'last-run.cmd'
$script:Lock = $null
$script:LockPidPath = Join-Path $script:StateDir 'poll.pid'

foreach ($dir in @($script:StateDir, $script:LogDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

function Get-BeijingStamp {
    $utc = [DateTime]::UtcNow
    foreach ($id in @('China Standard Time', 'Asia/Shanghai')) {
        try {
            $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById($id)
            return [System.TimeZoneInfo]::ConvertTimeFromUtc($utc, $tz).ToString('yyyy-MM-ddTHH:mm:sszzz')
        } catch { continue }
    }
    return $utc.AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
}

function Write-HubLog {
    param([string]$Message, [string]$Level = 'INFO')
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = '{0} [{1}] {2}' -f $stamp, $Level, $Message
    $file = Join-Path $script:LogDir ('hub-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))
    try {
        [System.IO.File]::AppendAllText($file, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
    if ($LogVerbose) { Write-Host $line }
}

function Open-PollLock {
    # A single instance at a time, but never at the price of a permanent wedge:
    # a crashed or killed poll used to leave the lock behind and the watcher
    # stayed silent for hours until somebody logged in and removed it by hand.
    param([int]$StaleMinutes = 90)
    try {
        return [System.IO.File]::Open($script:LockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    } catch { }

    $holder = Read-JsonFile -Path $script:LockPidPath
    $holderPid = 0
    if ($null -ne $holder) { $holderPid = [int](Get-Property $holder 'pid' 0) }
    $alive = $false
    if ($holderPid -gt 0) {
        $alive = $null -ne (Get-Process -Id $holderPid -ErrorAction SilentlyContinue)
    }
    $age = 0.0
    try { $age = ((Get-Date) - (Get-Item -LiteralPath $script:LockPath).LastWriteTime).TotalMinutes } catch { }

    if ($alive -and $age -lt $StaleMinutes) {
        return $null
    }
    Write-HubLog ('breaking a stale poll lock: holder pid {0}, alive {1}, age {2:N1} min' -f $holderPid, $alive, $age) 'WARN'
    if ($alive -and $holderPid -gt 0) {
        try { & taskkill.exe /F /T /PID $holderPid 2>&1 | Out-Null } catch { }
        Start-Sleep -Seconds 2
    }
    Remove-Item -LiteralPath $script:LockPath -Force -ErrorAction SilentlyContinue
    try {
        return [System.IO.File]::Open($script:LockPath, 'OpenOrCreate', 'ReadWrite', 'None')
    } catch {
        return $null
    }
}

function Write-PollPid {
    try {
        Write-JsonFile -Path $script:LockPidPath -Data ([ordered]@{
            pid        = $PID
            started_at = Get-BeijingStamp
            script     = 'Invoke-CgmdPoll.ps1'
            host       = $env:COMPUTERNAME
        })
    } catch { }
}

function Clear-PollPid {
    try { Remove-Item -LiteralPath $script:LockPidPath -Force -ErrorAction SilentlyContinue } catch { }
}

function Test-SmokeDue {
    # Self-healing schedule: verify 100 ps whenever the last proof is missing,
    # failed, or simply old.  No request file from a human is involved.
    param([string]$Repo, [double]$IntervalHours = 24, [double]$RetryMinutes = 180)
    $schedule = Read-JsonFile -Path (Join-Path $script:StateDir 'smoke-schedule.json')
    if ($null -ne $schedule) {
        $stamp = [string](Get-Property $schedule 'last_queued_at' '')
        if ($stamp) {
            try {
                $last = [datetimeoffset]::Parse($stamp)
                if (([datetimeoffset]::Now - $last).TotalMinutes -lt $RetryMinutes) { return $false }
            } catch { }
        }
    }
    $report = Read-JsonFile -Path (Join-Path $Repo 'results\status\gmx_smoke.json')
    if ($null -eq $report) { return $true }
    if ([string](Get-Property $report 'status' 'unknown') -ne 'ok') { return $true }
    $generated = [string](Get-Property $report 'generated_at' '')
    if (-not $generated) { return $true }
    try {
        return (([datetimeoffset]::Now - [datetimeoffset]::Parse($generated)).TotalHours -ge $IntervalHours)
    } catch {
        return $true
    }
}

function Invoke-MailboxOnce {
    # Runs the worker in its own process so a broken job cannot take the poll
    # down, then copies its ledger into results/status for remote inspection.
    param([string]$Repo, [string]$Branch, [string]$Ref = '', [int]$MaxJobs = 1)
    $worker = Join-Path $PSScriptRoot 'Invoke-CgmdMailbox.ps1'
    if (-not (Test-Path -LiteralPath $worker)) { return }
    $log = Join-Path $script:StateDir 'mailbox-call.log'
    $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $worker + '" -RepoPath "' + $Repo + '" -MaxJobs ' + $MaxJobs + ' -Quiet'
    if ($Branch) { $line += ' -Branch "' + $Branch + '"' }
    if ($Ref) { $line += ' -Ref "' + $Ref + '"' }
    $code = Invoke-Captured -CommandLine $line -OutFile $log -TimeoutSeconds 2700
    Write-HubLog ('mailbox worker exit ' + $code)
    $last = Read-JsonFile -Path (Join-Path $script:StateDir 'mailbox-last.json')
    if ($null -eq $last) { return }
    $statusDir = Join-Path (Join-Path $Repo 'results') 'status'
    if (-not (Test-Path -LiteralPath $statusDir)) {
        New-Item -ItemType Directory -Path $statusDir -Force | Out-Null
    }
    Write-JsonFile -Path (Join-Path $statusDir 'hub_mailbox.json') -Data $last
    # Publish on every cycle (Publish-Results is a no-op when nothing changed):
    # a remote reader must be able to tell "worker ran, queue empty" from
    # "worker never ran".
    if (-not $NoPublish) {
        $null = Publish-Results -Repo $Repo -Branch $Branch -Message 'mailbox: worker report [desktop hub]'
    }
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Write-JsonFile {
    param([string]$Path, $Data)
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $json = $Data | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-Property {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    if ($null -eq $prop.Value) { return $Default }
    return $prop.Value
}

function Get-HubConfig {
    param([string]$Path)
    $candidates = @()
    if ($Path) { $candidates += $Path }
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.local.json')
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.json')
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $cfg = Read-JsonFile -Path $candidate
            if ($null -ne $cfg) { return $cfg }
        }
    }
    throw 'no hub config found; run bootstrap_desktop.ps1 first'
}

function Invoke-Git {
    param([string]$Repo, [string[]]$GitArgs)
    $all = @('-C', $Repo) + $GitArgs
    $output = & git @all 2>&1
    $code = $LASTEXITCODE
    return [pscustomobject]@{ Code = $code; Output = (($output | ForEach-Object { "$_" }) -join [Environment]::NewLine).Trim() }
}

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $result = & wsl.exe -d $script:Distro -- wslpath -a $WindowsPath 2>&1
    if ($LASTEXITCODE -ne 0) { throw ("wslpath failed: " + ($result -join ' ')) }
    return ("$result").Trim()
}

function Quote-Bash {
    param([string]$Value)
    return "'" + ($Value -replace "'", "'\''") + "'"
}

function Invoke-Captured {
    param([string]$CommandLine, [string]$OutFile, [int]$TimeoutSeconds = 0)
    $content = '@echo off' + [Environment]::NewLine + $CommandLine + ' > "' + $OutFile + '" 2>&1' +
               [Environment]::NewLine + 'echo CGMD_EXIT_CODE=%ERRORLEVEL% >> "' + $OutFile + '"' +
               [Environment]::NewLine
    [System.IO.File]::WriteAllText($script:CmdFile, $content, [System.Text.Encoding]::ASCII)
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /c ""{0}""' -f $script:CmdFile) `
        -NoNewWindow -PassThru
    if ($TimeoutSeconds -gt 0) {
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            Write-HubLog ("run exceeded {0} s, killing pid {1}" -f $TimeoutSeconds, $proc.Id) 'WARN'
            & taskkill.exe /F /T /PID $proc.Id 2>&1 | Out-Null
            return -1
        }
    } else {
        $proc.WaitForExit()
    }
    # Start-Process -PassThru does not reliably expose ExitCode for console
    # programs on PS 5.1 (it came back empty on the workstation), so the wrapper
    # echoes %ERRORLEVEL% into the log and that is what gets read back.
    if (Test-Path -LiteralPath $OutFile) {
        try {
            $text = [System.IO.File]::ReadAllText($OutFile, [System.Text.Encoding]::UTF8)
            $match = [regex]::Match($text, 'CGMD_EXIT_CODE=(-?\d+)')
            if ($match.Success) { return [int]$match.Groups[1].Value }
            if ($text -match 'Fatal error') { return 1 }
        } catch { }
    }
    return $proc.ExitCode
}

function Send-Beacon {
    param([string]$Title, [string]$Message, [string[]]$Tags = @('desktop_computer'), [string]$Topic = '')
    $script = Join-Path $PSScriptRoot 'Send-CgmdBeacon.ps1'
    if (-not (Test-Path -LiteralPath $script)) { return }
    if (-not $Topic) { $Topic = $script:Topic }
    try {
        & $script -Topic $Topic -Title $Title -Message $Message -Tags $Tags -Quiet | Out-Null
    } catch {
        Write-HubLog ("beacon error: " + $_.Exception.Message) 'WARN'
    }
}

function Publish-Results {
    param([string]$Repo, [string]$Branch, [string]$Message)
    $paths = @()
    foreach ($rel in @('results\status', 'results\cgmd')) {
        if (Test-Path -LiteralPath (Join-Path $Repo $rel)) { $paths += $rel }
    }
    if ($paths.Count -eq 0) { return $true }
    $gitArgs = @('add', '-A', '--') + ($paths | ForEach-Object { $_ -replace '\\', '/' })
    $null = Invoke-Git -Repo $Repo -GitArgs $gitArgs
    $status = Invoke-Git -Repo $Repo -GitArgs @('status', '--porcelain')
    if (-not $status.Output) {
        Write-HubLog 'nothing to publish'
        return $true
    }
    $commit = Invoke-Git -Repo $Repo -GitArgs @('commit', '-m', $Message)
    if ($commit.Code -ne 0 -and $commit.Output -notmatch 'nothing to commit') {
        Write-HubLog ("commit failed: " + $commit.Output) 'ERROR'
        return $false
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $push = Invoke-Git -Repo $Repo -GitArgs @('push', 'origin', ('HEAD:' + $Branch))
        if ($push.Code -eq 0) {
            Write-HubLog ("published to {0} (attempt {1})" -f $Branch, $attempt)
            return $true
        }
        Write-HubLog ("push failed (attempt {0}): {1}" -f $attempt, $push.Output) 'WARN'
        $pull = Invoke-Git -Repo $Repo -GitArgs @('pull', '--rebase', '--autostash', 'origin', $Branch)
        if ($pull.Code -ne 0) {
            Write-HubLog ("rebase failed: " + $pull.Output) 'ERROR'
            $null = Invoke-Git -Repo $Repo -GitArgs @('rebase', '--abort')
            return $false
        }
    }
    return $false
}

function Publish-Diagnostics {
    param([string]$Repo, [string]$Branch, [string]$Label = 'poll')
    # Copies the tail of today's hub log plus the last captured call into the
    # repository, so a failure on the workstation is diagnosable from git.
    if ($NoPublish) { return }
    $statusDir = Join-Path (Join-Path $Repo 'results') 'status'
    if (-not (Test-Path -LiteralPath $statusDir)) {
        New-Item -ItemType Directory -Path $statusDir -Force | Out-Null
    }
    $today = Join-Path $script:LogDir ('hub-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))
    $parts = @('# CGMD hub diagnostics (' + $Label + ') at ' + (Get-BeijingStamp))
    if (Test-Path -LiteralPath $today) {
        $parts += '--- hub log (tail 120) ---'
        $parts += @([System.IO.File]::ReadAllLines($today, [System.Text.Encoding]::UTF8) | Select-Object -Last 120)
    }
    $callLog = Join-Path $script:StateDir 'last-run.log'
    if (Test-Path -LiteralPath $callLog) {
        $parts += '--- last call output (tail 120) ---'
        $parts += @([System.IO.File]::ReadAllLines($callLog, [System.Text.Encoding]::UTF8) | Select-Object -Last 120)
    }
    $smokeLog = Join-Path $script:StateDir 'smoke-call.log'
    if (Test-Path -LiteralPath $smokeLog) {
        $parts += '--- last smoke output (tail 120) ---'
        $parts += @([System.IO.File]::ReadAllLines($smokeLog, [System.Text.Encoding]::UTF8) | Select-Object -Last 120)
    }
    $selfCheckLog = Join-Path $script:StateDir 'selfcheck-call.log'
    if (Test-Path -LiteralPath $selfCheckLog) {
        $parts += '--- last selfcheck output (tail 120) ---'
        $parts += @([System.IO.File]::ReadAllLines($selfCheckLog, [System.Text.Encoding]::UTF8) | Select-Object -Last 120)
    }
    $path = Join-Path $statusDir 'desktop_diagnostics.log'
    try {
        [System.IO.File]::WriteAllText($path, ($parts -join [Environment]::NewLine), (New-Object System.Text.UTF8Encoding($false)))
        $null = Publish-Results -Repo $Repo -Branch $Branch -Message ('diag: ' + $Label + ' [desktop hub]')
    } catch {
        Write-HubLog ('diagnostics publish failed: ' + $_.Exception.Message) 'WARN'
    }
}

function Publish-Heartbeat {
    param([string]$Repo, [string]$Branch, [string]$State = 'idle', [string]$TaskId = '', [int]$Minutes = 60)
    # A tiny file in git so that "the workstation watcher is alive" can be
    # checked from any other client (phone, laptop, Arena agent) without SSH.
    if ($NoPublish -or $Minutes -lt 0) { return }
    $rel = 'results/status/hub_heartbeat.json'
    $path = Join-Path (Join-Path (Join-Path $Repo 'results') 'status') 'hub_heartbeat.json'
    $previous = Read-JsonFile -Path $path
    if ($Minutes -gt 0 -and $null -ne $previous) {
        $last = [string](Get-Property $previous 'at' '')
        if ($last) {
            try {
                $parsed = [datetimeoffset]::Parse($last)
                $age = ([datetimeoffset]::Now - $parsed).TotalMinutes
                if ($age -lt $Minutes) { return }
            } catch {
                $null = $_
            }
        }
    }
    $head = (Invoke-Git -Repo $Repo -GitArgs @('rev-parse', '--short', 'HEAD')).Output
    $document = [ordered]@{
        schema     = 'cgmd.heartbeat.v1'
        at         = Get-BeijingStamp
        host       = $env:COMPUTERNAME
        branch     = $Branch
        head       = $head
        state      = $State
        task_id    = $TaskId
        interval_s = Get-Property $script:Config 'poll_seconds' 60
        poll_count = 1 + [int](Get-Property $previous 'poll_count' 0)
        launcher   = 'wscript -> CGMDHub.exe (winexe) -> powershell hidden'
    }
    try {
        Write-JsonFile -Path $path -Data $document
    } catch {
        Write-HubLog ('heart-beat write failed: ' + $_.Exception.Message) 'WARN'
        return
    }
    $null = Publish-Results -Repo $Repo -Branch $Branch -Message ('heartbeat: {0} alive, state {1} [desktop hub]' -f $env:COMPUTERNAME, $State)
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
$startedAt = Get-Date
try {
    $script:Lock = Open-PollLock -StaleMinutes $StaleLockMinutes
    if ($null -eq $script:Lock) {
        Write-HubLog 'another poll is running, exiting' 'WARN'
        exit 0
    }
    Write-PollPid

    $cfg = Get-HubConfig -Path $ConfigPath
    $script:Config = $cfg
    $repo = Get-Property $cfg 'repo_path'
    $branch = Get-Property $cfg 'branch' 'main'
    $script:Distro = Get-Property $cfg 'wsl_distro' 'Ubuntu'
    $script:Topic = Get-Property $cfg 'ntfy_topic' 'arena-beacon-95bc796a66'
    $wslWork = Get-Property $cfg 'wsl_workdir_root' '/home/cgmd/cgmd-runs'
    $gpuId = Get-Property $cfg 'gpu_id' 0
    $lockedRepo = Get-Property $cfg 'locked_repo' 'hukeying85-ux/0fuye'
    $prune = Get-Property $cfg 'prune_raw' $true

    if (-not $repo -or -not (Test-Path -LiteralPath $repo)) {
        Write-HubLog ("repo_path missing or not found: {0}" -f $repo) 'ERROR'
        exit 4
    }

    $remote = Invoke-Git -Repo $repo -GitArgs @('remote', 'get-url', 'origin')
    if ($remote.Code -ne 0) {
        Write-HubLog 'origin remote is not configured' 'ERROR'
        exit 4
    }
    if ($remote.Output -notmatch [regex]::Escape($lockedRepo)) {
        Write-HubLog ("REFUSING to run: origin is '{0}', expected '{1}'" -f $remote.Output, $lockedRepo) 'ERROR'
        exit 5
    }

    Write-HubLog ("poll start branch={0} repo={1}" -f $branch, $repo)

    # --- 1. publish leftovers, then synchronise --------------------------
    $dirty = Invoke-Git -Repo $repo -GitArgs @('status', '--porcelain')
    if ($dirty.Output -and $dirty.Output -match 'results/') {
        Write-HubLog 'publishing leftover results from the previous cycle'
        $null = Publish-Results -Repo $repo -Branch $branch -Message 'cgmd: publish leftover results [desktop hub]'
    }

    $fetch = Invoke-Git -Repo $repo -GitArgs @('fetch', '--quiet', 'origin', $branch)
    if ($fetch.Code -ne 0) {
        Write-HubLog ("fetch failed: " + $fetch.Output) 'WARN'
    } else {
        # Never skip the reset: a dirty tree used to pin the clone to an old
        # commit, so a poller kept running stale code for hours.  Local results
        # were published just above; whatever is left is machine noise.
        $dirty = Invoke-Git -Repo $repo -GitArgs @('status', '--porcelain')
        if ($dirty.Output) {
            Write-HubLog ("discarding local changes before sync: {0}" -f ($dirty.Output -replace "`r?`n", '; ')) 'WARN'
        }
        $null = Invoke-Git -Repo $repo -GitArgs @('checkout', '--quiet', '--force', $branch)
        $sync = Invoke-Git -Repo $repo -GitArgs @('reset', '--hard', ('origin/' + $branch))
        if ($sync.Code -ne 0) {
            Write-HubLog ("sync failed: " + $sync.Output) 'WARN'
        } else {
            Write-HubLog ("synced to origin/{0}" -f $branch)
        }
    }

    $requestFile = Join-Path $repo 'results\status\selfcheck_request.json'

    # --- 1b. mailbox bus: any session, any branch -> this workstation -----
    # Work is queued on a dedicated ref (default hub/mailbox), so a caller
    # never commits to its own branch: the rebase conflicts that used to cost
    # a whole round trip cannot happen.  A mailbox failure must never stop the
    # poll, so everything is wrapped.
    if ([bool](Get-Property $cfg 'mailbox_enabled' $true)) {
        try {
            Invoke-MailboxOnce -Repo $repo -Branch $branch `
                -Ref ([string](Get-Property $cfg 'mailbox_ref' '')) `
                -MaxJobs ([int](Get-Property $cfg 'mailbox_jobs_per_poll' 1))
        } catch {
            Write-HubLog ('mailbox step failed: ' + $_.Exception.Message) 'WARN'
        }
    }

    # --- 1b-2. self-healing 100 ps schedule -------------------------------
    # The operator should never have to ask for the smoke test again: if the
    # last proof is missing, failed or older than smoke_interval_hours, queue
    # it here.  Retries are rate limited so a broken workstation does not spend
    # every cycle on a doomed run.
    if ([bool](Get-Property $cfg 'smoke_auto' $true) -and -not (Test-Path -LiteralPath $requestFile)) {
        if (Test-SmokeDue -Repo $repo `
                -IntervalHours ([double](Get-Property $cfg 'smoke_interval_hours' 24)) `
                -RetryMinutes ([double](Get-Property $cfg 'smoke_retry_minutes' 180))) {
            Write-JsonFile -Path $requestFile -Data ([ordered]@{
                schema       = 'cgmd.selfcheck.request.v1'
                desk         = $false
                smoke        = $true
                how          = 'automatic schedule (self-healing), no human involved'
                requested_at = Get-BeijingStamp
                requested_by = 'hub-scheduler'
                note         = 'periodic 100 ps verification of the workstation'
            })
            Write-JsonFile -Path (Join-Path $script:StateDir 'smoke-schedule.json') -Data ([ordered]@{
                last_queued_at = Get-BeijingStamp
            })
            Write-HubLog 'smoke schedule: queued an automatic 100 ps verification'
        }
    }

    # --- 1c. on-demand self-check / desk deployment -----------------------
    # Any client (Arena agent, laptop, phone) may drop
    # results/status/selfcheck_request.json into the branch.  With desk=false
    # the desktop runs Test-CgmdHub.ps1 (17 checks); with desk=true it runs
    # Sync-Desktop.ps1 -Desk, which pulls the branch tip, redeploys Arena Desk
    # and then checks; with smoke=true it first integrates 100 ps with GROMACS
    # and publishes results/status/gmx_smoke.json.  Either way the report is
    # published and the request file is deleted so the next poll is quiet.
    if (Test-Path -LiteralPath $requestFile) {
        $selfCheckScript = Join-Path $PSScriptRoot 'Test-CgmdHub.ps1'
        $syncScript = Join-Path $PSScriptRoot 'Sync-Desktop.ps1'
        $request = Read-JsonFile -Path $requestFile
        $wantDesk = [bool](Get-Property $request 'desk' $false)
        $wantSmoke = [bool](Get-Property $request 'smoke' $false)

        # --- 1b-1. real GROMACS smoke test (100 ps) -----------------------
        if ($wantSmoke) {
            # A native Windows GROMACS (gmx.exe on PATH) is preferred: it needs
            # no WSL distro, no python and no Martini files.
            $nativeGmx = $null
            foreach ($name in @('gmx.exe', 'gmx')) {
                $found = Get-Command $name -ErrorAction SilentlyContinue
                if ($null -ne $found) { $nativeGmx = $found.Source; break }
            }
            $nativeRunner = Join-Path $PSScriptRoot 'Run-Gmx-Native.ps1'
            if ($nativeGmx -and (Test-Path -LiteralPath $nativeRunner)) {
                Write-HubLog ('smoke requested: native gmx at ' + $nativeGmx + ', running 100 ps in Windows')
                Send-Beacon -Title '[CGMD] gmx smoke test' -Message ('desktop ' + $env:COMPUTERNAME + ' is integrating 100 ps with the Windows GROMACS now') -Tags @('microscope')
                $nativeLog = Join-Path $script:StateDir 'smoke-call.log'
                $nativeLine = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $nativeRunner + '" -Ps 100 -GpuId ' + $gpuId + ' -Quiet'
                $nativeCode = Invoke-Captured -CommandLine $nativeLine -OutFile $nativeLog -TimeoutSeconds 1900
                Write-HubLog ("native smoke finished with exit code {0}" -f $nativeCode)
                if (Test-Path -LiteralPath $nativeLog) {
                    $nativeTail = ([System.IO.File]::ReadAllLines($nativeLog, [System.Text.Encoding]::UTF8) | Select-Object -Last 30) -join [Environment]::NewLine
                    Write-HubLog ("native smoke output (tail):" + [Environment]::NewLine + $nativeTail)
                }
                $nativeReport = Read-JsonFile -Path (Join-Path $repo 'results\status\gmx_smoke.json')
                $nativeMessage = 'native gmx smoke: no report produced'
                $nativeTags = @('rotating_light')
                if ($null -ne $nativeReport) {
                    $nativeStatus = [string](Get-Property $nativeReport 'status' 'unknown')
                    $nativeVersion = ''
                    $nativeSoftware = Get-Property $nativeReport 'software' $null
                    if ($null -ne $nativeSoftware) {
                        $nativeBlock = Get-Property $nativeSoftware 'gromacs' $null
                        if ($null -ne $nativeBlock) { $nativeVersion = [string](Get-Property $nativeBlock 'version' '') }
                    }
                    $nativeMessage = ('gmx {0} (native): {1}, {2} ps integrated' -f $nativeVersion, $nativeStatus, (Get-Property $nativeReport 'ps_completed' 0))
                    $nativeError = [string](Get-Property $nativeReport 'stage_error' '')
                    if ($nativeError) { $nativeMessage += (' | ' + $nativeError) }
                    if ($nativeStatus -eq 'ok') { $nativeTags = @('white_check_mark') }
                }
                Send-Beacon -Title '[CGMD] gmx smoke result' -Message $nativeMessage -Tags $nativeTags
                Publish-Diagnostics -Repo $repo -Branch $branch -Label 'gmx-smoke-native'
                Remove-Item -LiteralPath $requestFile -Force -ErrorAction SilentlyContinue
                if (-not $NoPublish) {
                    $null = Publish-Results -Repo $repo -Branch $branch -Message 'smoke: gmx 100 ps report (native) [desktop hub]'
                }
                Write-HubLog 'native smoke cycle complete'
                Publish-Heartbeat -Repo $repo -Branch $branch -State 'smoke-done' -TaskId 'gmx-smoke' -Minutes $HeartbeatMinutes
                exit 0
            }
            Write-HubLog 'smoke requested: no Windows gmx found, running cgmd.smoke (100 ps) inside WSL2'
            Send-Beacon -Title '[CGMD] gmx smoke test' -Message ('desktop ' + $env:COMPUTERNAME + ' is integrating 100 ps with GROMACS now') -Tags @('microscope')
            $wslRepoSmoke = Convert-ToWslPath -WindowsPath $repo
            $smokeWork = ($wslWork.TrimEnd('/') + '/smoke-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
            $smokeParts = @()
            $smokeParts += ('cd ' + (Quote-Bash $wslRepoSmoke))
            $smokeParts += ('export PYTHONPATH=' + (Quote-Bash ($wslRepoSmoke + ':' + $wslRepoSmoke + '/code/cgmd')) + ' PYTHONIOENCODING=utf-8')
            # `timeout` and stdin from /dev/null: a wedged child must never keep
            # the poll lock for an hour again.
            $smokeParts += ('timeout 1200 python3 -m cgmd.smoke --ps 100 --gpu-id ' + $gpuId +
                            ' --workdir ' + (Quote-Bash $smokeWork) +
                            ' --out results/status/gmx_smoke.json --timeout 900 < /dev/null')
            $smokeCommand = 'wsl.exe -d ' + $script:Distro + ' -- bash -c "' + ($smokeParts -join ' && ') + '"'
            $smokeLog = Join-Path $script:StateDir 'smoke-call.log'
            $smokeCode = Invoke-Captured -CommandLine $smokeCommand -OutFile $smokeLog -TimeoutSeconds 1260
            Write-HubLog ("smoke finished with exit code {0}" -f $smokeCode)
            if (Test-Path -LiteralPath $smokeLog) {
                $smokeTail = ([System.IO.File]::ReadAllLines($smokeLog, [System.Text.Encoding]::UTF8) | Select-Object -Last 30) -join [Environment]::NewLine
                Write-HubLog ("smoke output (tail):" + [Environment]::NewLine + $smokeTail)
            }
            $smokeReport = Read-JsonFile -Path (Join-Path $repo 'results\status\gmx_smoke.json')
            $smokeMessage = 'gmx smoke: no report produced'
            $smokeTags = @('rotating_light')
            if ($null -ne $smokeReport) {
                $smokeStatus = [string](Get-Property $smokeReport 'status' 'unknown')
                $gmxInfo = Get-Property $smokeReport 'software' $null
                $gmxVersion = ''
                if ($null -ne $gmxInfo) {
                    $gmxBlock = Get-Property $gmxInfo 'gromacs' $null
                    if ($null -ne $gmxBlock) { $gmxVersion = [string](Get-Property $gmxBlock 'version' '') }
                }
                $smokePs = Get-Property $smokeReport 'ps_completed' 0
                $smokeMessage = ('gmx {0}: {1}, {2} ps integrated' -f $gmxVersion, $smokeStatus, $smokePs)
                $smokeError = [string](Get-Property $smokeReport 'stage_error' '')
                if ($smokeError) { $smokeMessage += (' | ' + $smokeError) }
                if ($smokeStatus -eq 'ok') { $smokeTags = @('white_check_mark') }
            }
            Send-Beacon -Title '[CGMD] gmx smoke result' -Message $smokeMessage -Tags $smokeTags
            # Never swallow a request without a report: retry up to three polls
            # (so a fix pushed by the operator is picked up) and only then give up.
            $attempts = 1 + [int](Get-Property $request 'attempts' 0)
            if ($null -eq $smokeReport -and $attempts -lt 3) {
                $request | Add-Member -NotePropertyName 'attempts' -NotePropertyValue $attempts -Force
                $request | Add-Member -NotePropertyName 'last_attempt_at' -NotePropertyValue (Get-BeijingStamp) -Force
                Write-JsonFile -Path $requestFile -Data $request
                Write-HubLog ('no smoke report produced; keeping the request for retry {0}/3' -f $attempts) 'WARN'
            } else {
                Remove-Item -LiteralPath $requestFile -Force -ErrorAction SilentlyContinue
            }
            if (-not $NoPublish) {
                $null = Publish-Results -Repo $repo -Branch $branch -Message 'smoke: gmx 100 ps report [desktop hub]'
            }
            Publish-Diagnostics -Repo $repo -Branch $branch -Label 'gmx-smoke'
            Write-HubLog 'smoke cycle complete'
            Publish-Heartbeat -Repo $repo -Branch $branch -State 'smoke-done' -TaskId 'gmx-smoke' -Minutes $HeartbeatMinutes
            exit 0
        }

        $runnerScript = $selfCheckScript
        $runnerArgs = '-Quiet'
        if ($wantDesk -and (Test-Path -LiteralPath $syncScript)) {
            # desk=true means: pull the branch tip, redeploy Arena Desk, then check
            $runnerScript = $syncScript
            $runnerArgs = '-Desk -Quiet'
        }
        if (-not (Test-Path -LiteralPath $runnerScript)) {
            Write-HubLog ('request seen but ' + $runnerScript + ' is missing') 'ERROR'
        } else {
            Write-HubLog ('remote request: desk=' + $wantDesk + ', running ' + (Split-Path -Leaf $runnerScript))
            $requestTitle = '[CGMD] self-check'
            if ($wantDesk) { $requestTitle = '[CGMD] sync + desk deploy' }
            Send-Beacon -Title $requestTitle -Message ('desktop ' + $env:COMPUTERNAME + ' is executing the request now') -Tags @('mag')
            $callLog = Join-Path $script:StateDir 'selfcheck-call.log'
            $callLine = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $runnerScript + '" ' + $runnerArgs
            $code = Invoke-Captured -CommandLine $callLine -OutFile $callLog -TimeoutSeconds 1800
            Write-HubLog ("self-check finished with exit code {0}" -f $code)
            $verdictFile = Join-Path $repo 'results\status\desktop_selfcheck.json'
            $verdict = Read-JsonFile -Path $verdictFile
            $overall = [string](Get-Property $verdict 'overall' 'unknown')
            $summary = Get-Property $verdict 'summary' $null
            $message = ('self-check: ' + $overall)
            if ($null -ne $summary) {
                $message += (' (' + (Get-Property $summary 'passed' 0) + ' pass / ' +
                             (Get-Property $summary 'warnings' 0) + ' warn / ' +
                             (Get-Property $summary 'failed' 0) + ' fail)')
            }
            $verdictTags = @('white_check_mark')
            if ($overall -eq 'warn') { $verdictTags = @('warning') }
            if ($overall -eq 'fail' -or $overall -eq 'unknown') { $verdictTags = @('rotating_light') }
            Send-Beacon -Title '[CGMD] self-check result' -Message $message -Tags $verdictTags
            Remove-Item -LiteralPath $requestFile -Force -ErrorAction SilentlyContinue
            if (-not $NoPublish) {
                $null = Publish-Results -Repo $repo -Branch $branch -Message 'selfcheck: desktop report [desktop hub]'
            }
            Write-HubLog 'self-check cycle complete'
            Publish-Heartbeat -Repo $repo -Branch $branch -State 'request-done' -TaskId 'selfcheck' -Minutes $HeartbeatMinutes
            exit 0
        }
    }

    # --- 2. inspect the task document ------------------------------------
    $taskFile = Join-Path $repo 'results\status\cgmd_task.json'
    $task = Read-JsonFile -Path $taskFile
    if ($null -eq $task) {
        Write-HubLog 'no task document on this branch, nothing to do'
        exit 0
    }
    $taskStatus = [string](Get-Property $task 'status' 'idle')
    $taskId = [string](Get-Property $task 'task_id' 'unknown')
    Write-HubLog ("task {0} status={1}" -f $taskId, $taskStatus)

    if ($taskStatus -ne 'pending' -and -not $Force) {
        Write-HubLog 'task is not pending, idling'
        Publish-Heartbeat -Repo $repo -Branch $branch -State 'idle' -TaskId $taskId -Minutes $HeartbeatMinutes
        exit 0
    }

    # --- 3. run the pipeline inside WSL2 ---------------------------------
    $wslRepo = Convert-ToWslPath -WindowsPath $repo
    $parts = @()
    $parts += ('cd ' + (Quote-Bash $wslRepo))
    $parts += ('export PYTHONPATH=' + (Quote-Bash ($wslRepo + ':' + $wslRepo + '/code/cgmd')) + ' PYTHONIOENCODING=utf-8')
    $parts += ('python3 code/federation/desktop_runner.py run')
    $parts += ('--task-file results/status/cgmd_task.json')
    $parts += ('--repo ' + (Quote-Bash $wslRepo))
    $parts += ('--workdir-root ' + (Quote-Bash $wslWork))
    $parts += ('--gpu-id ' + $gpuId)
    if ($prune) { $parts += '--prune-raw' }
    if ($Force) { $parts += '--force' }
    $bashScript = $parts -join ' && '
    # NOTE: cmd.exe only honours double quotes, so the bash script (which uses
    # single quotes internally) is handed to wsl.exe wrapped in double quotes.
    $wslCommand = 'wsl.exe -d ' + $script:Distro + ' -- bash -lc "' + $bashScript + '"'

    if (Test-Path -LiteralPath $script:RunOut) { Remove-Item -LiteralPath $script:RunOut -Force }
    Write-HubLog 'starting desktop_runner.py in WSL2'
    Send-Beacon -Title '[CGMD] hub claim' -Message ("desktop started task {0}" -f $taskId) -Tags @('rocket')

    $timeout = 0
    if ($MaxRunMinutes -gt 0) { $timeout = $MaxRunMinutes * 60 }
    $exit = Invoke-Captured -CommandLine $wslCommand -OutFile $script:RunOut -TimeoutSeconds $timeout

    $runnerJson = $null
    if (Test-Path -LiteralPath $script:RunOut) {
        $lines = [System.IO.File]::ReadAllLines($script:RunOut, [System.Text.Encoding]::UTF8)
        for ($i = $lines.Length - 1; $i -ge 0; $i--) {
            $line = $lines[$i].Trim()
            if ($line.StartsWith('{') -and $line.EndsWith('}')) {
                try { $runnerJson = $line | ConvertFrom-Json; break } catch { continue }
            }
        }
        foreach ($line in $lines) {
            if ($line -match '^CGMD_EXIT_CODE=(-?\d+)$') { $exit = [int]$Matches[1] }
        }
        $tail = ($lines | Select-Object -Last 40) -join [Environment]::NewLine
        Write-HubLog ("runner output (tail):" + [Environment]::NewLine + $tail)
    }
    Write-HubLog ("runner finished with exit code {0}" -f $exit)

    # --- 4. publish the reduced results ----------------------------------
    $ok = $false
    if ($null -ne $runnerJson) { $ok = [bool](Get-Property $runnerJson 'ok' $false) }
    if ($NoPublish) {
        Write-HubLog 'NoPublish set, skipping git publish'
    } else {
        $message = 'cgmd: {0} {1} [desktop hub]' -f $taskId, $taskStatus
        if ($null -ne $runnerJson) {
            $message = 'cgmd: {0} {1} [desktop hub]' -f $taskId, (Get-Property $runnerJson 'status' 'unknown')
        }
        $published = Publish-Results -Repo $repo -Branch $branch -Message $message
        if (-not $published) {
            Write-HubLog 'publish failed, will retry next cycle' 'ERROR'
            Send-Beacon -Title '[CGMD] publish failed' -Message ("git push failed for task {0}; retrying next cycle" -f $taskId) -Tags @('warning')
        }
    }

    # --- 5. heartbeat -----------------------------------------------------
    $previous = Read-JsonFile -Path $script:StatePath
    $heartbeat = [ordered]@{
        last_poll_at       = Get-BeijingStamp
        last_poll_seconds  = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
        task_id            = $taskId
        task_status_before = $taskStatus
        runner_exit_code   = $exit
        runner_ok          = $ok
        runner_result      = $runnerJson
        repo               = $repo
        branch             = $branch
        wsl_distro         = $script:Distro
        gpu_id             = $gpuId
        poll_count         = 1 + [int](Get-Property $previous 'poll_count' 0)
    }
    Write-JsonFile -Path $script:StatePath -Data $heartbeat
    Publish-Heartbeat -Repo $repo -Branch $branch -State 'task-done' -TaskId $taskId -Minutes $HeartbeatMinutes
    Write-HubLog 'poll finished'
    if ($null -ne $runnerJson) {
        $status = Get-Property $runnerJson 'status' 'unknown'
        $summary = Get-Property $runnerJson 'summary' ''
        Send-Beacon -Title '[CGMD] hub done' -Message ("task {0} -> {1}{2}result: {3}" -f $taskId, $status, [Environment]::NewLine, $summary) -Tags @('white_check_mark')
    }

    if ($exit -eq 3) { exit 3 }
    if ($exit -eq -1) { exit 6 }
    if ($exit -ne 0 -and -not $ok) { exit 1 }
    exit 0
}
catch {
    Write-HubLog ("unhandled error: " + $_.Exception.Message + ' | ' + $_.ScriptStackTrace) 'ERROR'
    try {
        if ($repo -and (Test-Path -LiteralPath $repo)) {
            Publish-Diagnostics -Repo $repo -Branch $branch -Label ('error: ' + $_.Exception.Message)
        }
    } catch { }
    Send-Beacon -Title '[CGMD] hub error' -Message ("poll error: " + $_.Exception.Message) -Tags @('rotating_light')
    exit 9
}
finally {
    Clear-PollPid
    if ($null -ne $script:Lock) {
        try { $script:Lock.Dispose() } catch { }
        try {
            if (Test-Path -LiteralPath $script:LockPath) { Remove-Item -LiteralPath $script:LockPath -Force }
        } catch { }
    }
}
