#Requires -Version 5.1
<#
.SYNOPSIS
    One command that brings the workstation clone up to date, optionally
    redeploys Arena Desk (code/panel), then runs the full self-check and pushes
    the evidence back into the branch.

.DESCRIPTION
    This is the "sync this to the desktop" button.  It performs, in order:

      1. lock check  - origin must be the locked repository, otherwise exit 5;
      2. fetch       - reports how many commits are incoming on the branch;
      3. hard sync   - checkout + reset --hard origin/<branch> (refuses a dirty
                       tree unless -Force is given);
      4. desk        - with -Desk, runs code/panel/deploy.ps1 -NoOpenWindow and
                       records the JSON it prints (version, exe, tasks);
      5. self-check  - runs runner/Test-CgmdHub.ps1 (17 checks, no GPU work);
      6. publish     - commits results/status/desktop_selfcheck.json plus
                       results/status/desktop_sync.json and pushes the branch.

    Nothing is started in a new window: every child process is launched with
    -NoNewWindow, so the scheduled-task variant stays invisible.

.PARAMETER ConfigPath
    Explicit hub config; defaults to config/cgmd_hub.local.json then the
    template config/cgmd_hub.json.

.PARAMETER RepoPath
    Override the clone location recorded in the config.

.PARAMETER Branch
    Override the branch recorded in the config.

.PARAMETER Desk
    Redeploy Arena Desk from code/panel/deploy.ps1 after the sync.

.PARAMETER SkipAutoHeal
    Pass -SkipAutoHeal to deploy.ps1 (skips the SSH/self-heal pass, faster).

.PARAMETER DeskBootDemo
    Pass -LaunchBootDemo to deploy.ps1 (show the boot animation once).

.PARAMETER NoSelfCheck
    Skip runner/Test-CgmdHub.ps1 (the sync record is still published).

.PARAMETER Notify
    Send the phone beacon with the final verdict.

.PARAMETER Force
    Discard uncommitted local changes before the hard reset.

.PARAMETER DryRun
    Show what would be synced and stop before touching the working tree.

.PARAMETER Quiet
    No console output (scheduled-task friendly).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Sync-Desktop.ps1 -Desk -Notify

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Sync-Desktop.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = '',
    [string]$RepoPath = '',
    [string]$Branch = '',
    [switch]$Desk,
    [switch]$SkipAutoHeal,
    [switch]$DeskBootDemo,
    [switch]$NoSelfCheck,
    [switch]$Notify,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StartedAt = Get-Date

function Say {
    param([string]$Message, [string]$Colour = 'Gray')
    if (-not $Quiet) { Write-Host $Message -ForegroundColor $Colour }
}

function Get-BeijingStamp {
    $utc = [DateTime]::UtcNow
    foreach ($id in @('China Standard Time', 'Asia/Shanghai')) {
        try {
            $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById($id)
            return [System.TimeZoneInfo]::ConvertTimeFromUtc($utc, $tz).ToString('yyyy-MM-ddTHH:mm:sszzz')
        } catch {
            continue
        }
    }
    return $utc.AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        try {
        return ($raw | ConvertFrom-Json)
    } catch {
        # Not JSON (a literal "False" once landed in results/status and made
        # every reader throw).  Treat it as missing, never as fatal.
Say ('  [warn] ignoring a status file that is not JSON: ' + $Path) 'Yellow'
        return $null
    }
    } catch {
        return $null
    }
}

function Get-Property {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    if ($null -eq $prop.Value) { return $Default }
    return $prop.Value
}

function Invoke-Git {
    param([string]$Repo, [string[]]$GitArgs)
    $all = @('-C', $Repo) + $GitArgs
    try {
        $output = & git @all 2>&1
        $code = $LASTEXITCODE
    } catch {
        return [pscustomobject]@{ Code = -1; Output = $_.Exception.Message }
    }
    return [pscustomobject]@{
        Code   = $code
        Output = (($output | ForEach-Object { "$_" }) -join [Environment]::NewLine).Trim()
    }
}

function Send-BeaconLine {
    param([string]$Title, [string]$Message, [string[]]$Tags = @('desktop_computer'), [string]$Topic = '')
    $beacon = Join-Path $PSScriptRoot 'Send-CgmdBeacon.ps1'
    if (-not (Test-Path -LiteralPath $beacon)) { return }
    try {
        & $beacon -Topic $Topic -Title $Title -Message $Message -Tags $Tags -Quiet | Out-Null
    } catch {
        return
    }
}

# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
$cfg = $null
$cfgPath = ''
foreach ($candidate in @($ConfigPath, (Join-Path $script:HubRoot 'config\cgmd_hub.local.json'), (Join-Path $script:HubRoot 'config\cgmd_hub.json'))) {
    if (-not $candidate) { continue }
    if (Test-Path -LiteralPath $candidate) {
        $loaded = Read-JsonFile -Path $candidate
        if ($null -ne $loaded) { $cfg = $loaded; $cfgPath = $candidate; break }
    }
}
if ($null -eq $cfg) {
    Say '  [fail] no hub config; run bootstrap_desktop.ps1 first' 'Red'
    exit 4
}

$repo = $RepoPath
if (-not $repo) { $repo = Get-Property $cfg 'repo_path' 'C:\cgmd\0fuye' }
$branch = $Branch
if (-not $branch) { $branch = Get-Property $cfg 'branch' 'main' }
$lockedRepo = Get-Property $cfg 'locked_repo' 'hukeying85-ux/0fuye'
$topic = Get-Property $cfg 'ntfy_topic' 'arena-beacon-95bc796a66'

if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    Say ('  [fail] no git clone at ' + $repo) 'Red'
    exit 4
}

Say ''
Say '  CGMD-Engine - desktop sync' 'White'
Say ('  repo  : ' + $repo)
Say ('  branch: ' + $branch)
Say ('  config: ' + $cfgPath)
Say ''

# ---------------------------------------------------------------------------
# 1. lock
# ---------------------------------------------------------------------------
$remote = Invoke-Git -Repo $repo -GitArgs @('remote', 'get-url', 'origin')
if ($remote.Code -ne 0) {
    Say '  [fail] origin remote is not configured' 'Red'
    exit 5
}
if ($remote.Output -notmatch [regex]::Escape($lockedRepo)) {
    Say ('  [fail] origin is ' + $remote.Output + ', expected ' + $lockedRepo) 'Red'
    exit 5
}
Say ('  [ok] origin locked to ' + $lockedRepo) 'Green'

# ---------------------------------------------------------------------------
# 2. fetch
# ---------------------------------------------------------------------------
$shaBefore = (Invoke-Git -Repo $repo -GitArgs @('rev-parse', 'HEAD')).Output
$shortBefore = $shaBefore
if ($shortBefore.Length -gt 7) { $shortBefore = $shortBefore.Substring(0, 7) }
$fetch = Invoke-Git -Repo $repo -GitArgs @('fetch', '--quiet', 'origin', $branch)
if ($fetch.Code -ne 0) {
    Say ('  [fail] git fetch failed: ' + $fetch.Output) 'Red'
    exit 8
}
$incoming = Invoke-Git -Repo $repo -GitArgs @('log', '--oneline', ('HEAD..origin/' + $branch))
$incomingLines = @()
if ($incoming.Output) { $incomingLines = @($incoming.Output -split "`r?`n" | Where-Object { $_ }) }
Say ('  [ok] fetched; ' + $incomingLines.Count + ' commit(s) to pull') 'Green'
foreach ($line in $incomingLines) { Say ('        ' + $line) 'DarkGray' }

if ($DryRun) {
    Say ''
    Say '  dry run - working tree left untouched' 'Yellow'
    Say ''
    exit 0
}

# ---------------------------------------------------------------------------
# 3. hard sync
# ---------------------------------------------------------------------------
$dirty = Invoke-Git -Repo $repo -GitArgs @('status', '--porcelain')
if ($dirty.Output) {
    if (-not $Force) {
        Say '  [fail] working tree is dirty; commit, stash or rerun with -Force' 'Red'
        Say ('        ' + ($dirty.Output -replace "`r?`n", '; ')) 'DarkGray'
        exit 8
    }
    Say '  [warn] discarding local changes (-Force)' 'Yellow'
    $null = Invoke-Git -Repo $repo -GitArgs @('reset', '--hard', 'HEAD')
    $null = Invoke-Git -Repo $repo -GitArgs @('clean', '-fd', '--', 'results')
}

$checkout = Invoke-Git -Repo $repo -GitArgs @('checkout', '--quiet', $branch)
if ($checkout.Code -ne 0) {
    Say ('  [fail] could not switch to ' + $branch + ': ' + $checkout.Output) 'Red'
    exit 8
}
$reset = Invoke-Git -Repo $repo -GitArgs @('reset', '--hard', ('origin/' + $branch))
if ($reset.Code -ne 0) {
    Say ('  [fail] reset failed: ' + $reset.Output) 'Red'
    exit 8
}
$shaAfter = (Invoke-Git -Repo $repo -GitArgs @('rev-parse', 'HEAD')).Output
$shortAfter = $shaAfter
if ($shortAfter.Length -gt 7) { $shortAfter = $shortAfter.Substring(0, 7) }
Say ('  [ok] synced ' + $shortBefore + ' -> ' + $shortAfter) 'Green'

# ---------------------------------------------------------------------------
# 4. desk deploy
# ---------------------------------------------------------------------------
$deskResult = $null
$deskOk = $true
$deskSkipped = $true
if ($Desk) {
    $deployScript = Join-Path (Join-Path (Join-Path $repo 'code') 'panel') 'deploy.ps1'
    if (-not (Test-Path -LiteralPath $deployScript)) {
        Say ('  [fail] ' + $deployScript + ' not in this branch') 'Red'
        $deskOk = $false
    } else {
        Say '  deploying Arena Desk (code/panel/deploy.ps1 -NoOpenWindow)' 'Cyan'
        $outFile = Join-Path $script:HubRoot 'state\desk-deploy.out'
        $errFile = Join-Path $script:HubRoot 'state\desk-deploy.err'
        $stateDir = Split-Path -Parent $outFile
        if (-not (Test-Path -LiteralPath $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }
        $deployArgs = '-NoOpenWindow'
        if ($SkipAutoHeal) { $deployArgs += ' -SkipAutoHeal' }
        if ($DeskBootDemo) { $deployArgs += ' -LaunchBootDemo' }
        $argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + $deployScript + '" ' + $deployArgs
        try {
            $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $argLine -NoNewWindow -PassThru `
                -RedirectStandardOutput $outFile -RedirectStandardError $errFile
            if ($proc.WaitForExit(900000)) {
                $deployCode = $proc.ExitCode
            } else {
                & taskkill.exe /F /T /PID $proc.Id 2>&1 | Out-Null
                $deployCode = -1
            }
        } catch {
            $deployCode = -1
        }
        $deskSkipped = $false
        $stdout = ''
        if (Test-Path -LiteralPath $outFile) {
            $stdout = [System.IO.File]::ReadAllText($outFile, [System.Text.Encoding]::UTF8)
        }
        $lines = @($stdout -split "`r?`n")
        for ($i = $lines.Length - 1; $i -ge 0; $i--) {
            $line = $lines[$i].Trim()
            if ($line.StartsWith('{') -and $line.EndsWith('}')) {
                try { $deskResult = $line | ConvertFrom-Json; break } catch { continue }
            }
        }
        if ($null -ne $deskResult) {
            $deskVersion = [string](Get-Property $deskResult 'version' '?')
            $deskExe = [bool](Get-Property $deskResult 'compiled_exe' $false)
            Say ('  [ok] desk deployed: version ' + $deskVersion + ', exe ' + $(if ($deskExe) { 'compiled' } else { 'reused' })) 'Green'
        } elseif ($deployCode -eq 0) {
            Say '  [warn] deploy finished but printed no JSON summary' 'Yellow'
        } else {
            $tail = ''
            if (Test-Path -LiteralPath $errFile) {
                $tail = ([System.IO.File]::ReadAllText($errFile, [System.Text.Encoding]::UTF8)).Trim()
            }
            Say ('  [fail] deploy exit code ' + $deployCode + ' ' + $tail) 'Red'
            $deskOk = $false
        }
    }
}

# ---------------------------------------------------------------------------
# 5. self-check
# ---------------------------------------------------------------------------
$selfCheckCode = -1
$verdict = $null
if (-not $NoSelfCheck) {
    $selfCheck = Join-Path $PSScriptRoot 'Test-CgmdHub.ps1'
    if (-not (Test-Path -LiteralPath $selfCheck)) {
        Say '  [fail] Test-CgmdHub.ps1 missing' 'Red'
        exit 7
    }
    Say '  running the 17-point self-check' 'Cyan'
    & $selfCheck -Quiet
    $selfCheckCode = $LASTEXITCODE
    $verdict = Read-JsonFile -Path (Join-Path (Join-Path (Join-Path $repo 'results') 'status') 'desktop_selfcheck.json')
} else {
    Say '  self-check skipped (NoSelfCheck)' 'Yellow'
}

# ---------------------------------------------------------------------------
# 6. publish the sync record
# ---------------------------------------------------------------------------
$overall = 'unknown'
$summaryText = 'not run'
if ($null -ne $verdict) {
    $overall = [string](Get-Property $verdict 'overall' 'unknown')
    $summary = Get-Property $verdict 'summary' $null
    if ($null -ne $summary) {
        $summaryText = ('{0} pass / {1} warn / {2} fail' -f (Get-Property $summary 'passed' 0), (Get-Property $summary 'warnings' 0), (Get-Property $summary 'failed' 0))
    }
}

$record = [pscustomobject]@{
    schema     = 'cgmd.desksync.v1'
    synced_at  = Get-BeijingStamp
    host       = $env:COMPUTERNAME
    repo       = $repo
    branch     = $branch
    from_sha   = $shaBefore
    to_sha     = $shaAfter
    incoming   = $incomingLines.Count
    desk       = [pscustomobject]@{
        requested = [bool]$Desk
        skipped   = $deskSkipped
        ok        = $deskOk
        version   = [string](Get-Property $deskResult 'version' '')
        exe       = [string](Get-Property $deskResult 'exe_path' '')
        tasks     = (Get-Property $deskResult 'tasks' $null)
    }
    selfcheck  = [pscustomobject]@{
        ran       = (-not $NoSelfCheck)
        overall   = $overall
        exit_code = $selfCheckCode
        summary   = $summaryText
    }
    seconds    = [math]::Round(((Get-Date) - $script:StartedAt).TotalSeconds, 1)
}

$recordPath = Join-Path (Join-Path (Join-Path $repo 'results') 'status') 'desktop_sync.json'
$recordDir = Split-Path -Parent $recordPath
if (-not (Test-Path -LiteralPath $recordDir)) { New-Item -ItemType Directory -Path $recordDir -Force | Out-Null }
[System.IO.File]::WriteAllText($recordPath, ($record | ConvertTo-Json -Depth 8), (New-Object System.Text.UTF8Encoding($false)))

$paths = @('results/status/desktop_sync.json')
if (-not $NoSelfCheck) { $paths += 'results/status/desktop_selfcheck.json' }
$null = Invoke-Git -Repo $repo -GitArgs (@('add', '-A', '--') + $paths)
$status = Invoke-Git -Repo $repo -GitArgs @('status', '--porcelain')
if ($status.Output) {
    $message = ('sync: {0} -> {1} | desk {2} | selfcheck {3}' -f $shortBefore, $shortAfter, $(if ($Desk) { 'yes' } else { 'no' }), $overall)
    $commit = Invoke-Git -Repo $repo -GitArgs @('commit', '-m', $message)
    if ($commit.Code -eq 0) {
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            $push = Invoke-Git -Repo $repo -GitArgs @('push', 'origin', ('HEAD:' + $branch))
            if ($push.Code -eq 0) {
                Say '  [ok] sync record pushed' 'Green'
                break
            }
            $pull = Invoke-Git -Repo $repo -GitArgs @('pull', '--rebase', '--autostash', 'origin', $branch)
            if ($pull.Code -ne 0) {
                Say ('  [warn] push failed: ' + $push.Output) 'Yellow'
                break
            }
        }
    } else {
        Say ('  [warn] commit failed: ' + $commit.Output) 'Yellow'
    }
} else {
    Say '  [ok] nothing new to publish' 'DarkGray'
}

# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------
$exitCode = 0
if (-not $deskOk) { $exitCode = 9 }
if ($selfCheckCode -ne -1) {
    if ($selfCheckCode -eq 7) { $exitCode = 7 }
    elseif ($selfCheckCode -eq 5) { $exitCode = 5 }
    elseif ($selfCheckCode -eq 4) { $exitCode = 4 }
    elseif ($selfCheckCode -eq 6 -and $exitCode -eq 0) { $exitCode = 6 }
}

if ($Notify) {
    $verdictText = 'PASS'
    if ($exitCode -eq 6) { $verdictText = 'WARN' }
    if ($exitCode -ne 0 -and $exitCode -ne 6) { $verdictText = 'FAIL' }
    $message = @()
    $message += ('{0} on {1}' -f $verdictText, $env:COMPUTERNAME)
    $message += ('code {0} -> {1} on {2}' -f $shortBefore, $shortAfter, $branch)
    $message += ('desk ' + $(if ($Desk) { 'redeployed' } else { 'untouched' }) + ' | selfcheck ' + $overall + ' (' + $summaryText + ')')
    $tags = @('white_check_mark')
    if ($exitCode -eq 6) { $tags = @('warning') }
    if ($exitCode -ne 0 -and $exitCode -ne 6) { $tags = @('rotating_light') }
    Send-BeaconLine -Title ('[CGMD] desktop sync ' + $verdictText) -Message ($message -join [Environment]::NewLine) -Tags $tags -Topic $topic
}

Say ''
if ($exitCode -eq 0) {
    Say ('  SYNC + SELF-CHECK OK  (' + $summaryText + ')') 'Green'
} elseif ($exitCode -eq 6) {
    Say ('  SYNC OK, SELF-CHECK HAS WARNINGS  (' + $summaryText + ')') 'Yellow'
} else {
    Say ('  SYNC FINISHED WITH ISSUES  exit ' + $exitCode) 'Red'
}
Say ('  record: ' + $recordPath)
Say ''
exit $exitCode
