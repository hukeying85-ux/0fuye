#Requires -Version 5.1
<#
.SYNOPSIS
    Claim jobs from the git mailbox and answer them on this workstation.

.DESCRIPTION
    The mailbox is a dedicated branch (default hub/mailbox) with

        inbox/<id>.json    request  (cgmd.mailbox.request.v1)
        outbox/<id>.json   result   (cgmd.mailbox.result.v1)

    Any agent session, on any branch, from any machine, can queue work with

        python3 -m core.hub_mailbox send --kind smoke --wait

    and this script (called by Invoke-CgmdPoll.ps1 every cycle) claims the job,
    runs it here on the Windows GROMACS / GPU, and publishes the answer back.
    Nothing is ever written to the caller's branch, so no rebase conflicts.

    Supported kinds: ping, selfcheck, smoke, sync, gmx, shell (opt-in).

.PARAMETER RepoPath
    Checkout of the hub (default C:\cgmd\0fuye from the config).

.PARAMETER Ref
    Mailbox branch, default hub/mailbox.

.PARAMETER MaxJobs
    How many jobs to run in this cycle (default 1: keep the poll responsive).

.PARAMETER MaxJobSeconds
    Hard ceiling per job; the request may ask for less, never for more.

.PARAMETER AllowShell
    Permit the shell kind.  Off by default: it is a remote code execution
    feature and has to be switched on deliberately.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Invoke-CgmdMailbox.ps1 -MaxJobs 2
#>
[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$Branch = '',
    [string]$ConfigPath = '',
    [string]$Ref = '',
    [int]$MaxJobs = 1,
    [int]$MaxJobSeconds = 3600,
    [switch]$AllowShell,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StateDir = Join-Path $script:HubRoot 'state'
$script:LogDir = Join-Path $script:HubRoot 'logs'
$script:ScriptDir = $PSScriptRoot
$script:Worktree = Join-Path $script:StateDir 'mailbox'
$script:LedgerPath = Join-Path $script:StateDir 'mailbox-ledger.json'
$script:AttemptsPath = Join-Path $script:StateDir 'mailbox-attempts.json'
$script:MaxAttempts = 3
$script:LastPath = Join-Path $script:StateDir 'mailbox-last.json'
$script:Stopped = $false
$script:PeerJobs = @()
$script:PeerInfo = @()

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

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    try {
        $file = Join-Path $script:LogDir ('mailbox-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))
        [System.IO.File]::AppendAllText($file, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
    if (-not $Quiet) { Write-Host $line }
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    try {
        return ($raw | ConvertFrom-Json)
    } catch {
        # Not JSON (a literal "False" once landed in results/status and made
        # every reader throw).  Treat it as missing, never as fatal.
        Write-HubLog ('ignoring a status file that is not JSON: ' + $Path) 'WARN'
        return $null
    }
}

function Write-JsonFile {
    param([string]$Path, $Data)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, ($Data | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding($false)))
}

function Get-Property {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) {
            $value = $Object[$Name]
            if ($null -eq $value) { return $Default }
            return $value
        }
        return $Default
    }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    if ($null -eq $prop.Value) { return $Default }
    return $prop.Value
}

function Invoke-Git {
    param([string]$Directory, [string[]]$GitArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & git -C $Directory @GitArgs 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{ Code = $code; Output = $output.Trim() }
}

function Get-HubConfig {
    $candidates = @()
    if ($ConfigPath) { $candidates += $ConfigPath }
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.local.json')
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.json')
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return (Read-JsonFile -Path $candidate) }
    }
    return $null
}

function Get-HubConfigPath {
    $candidates = @()
    if ($ConfigPath) { $candidates += $ConfigPath }
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.local.json')
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.json')
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return (Join-Path $script:HubRoot 'config\cgmd_hub.local.json')
}

function Set-HubConfigValue {
    param([string]$Name, $Value)
    $path = Get-HubConfigPath
    $data = Read-JsonFile -Path $path
    $dict = [ordered]@{}
    if ($null -ne $data) {
        if ($data -is [System.Collections.IDictionary]) {
            foreach ($key in $data.Keys) { $dict[$key] = $data[$key] }
        } else {
            foreach ($prop in $data.PSObject.Properties) { $dict[$prop.Name] = $prop.Value }
        }
    }
    $dict[$Name] = $Value
    Write-JsonFile -Path $path -Data $dict
    return $path
}

# Other projects cannot push into this repo's mailbox: an Arena session token is
# scoped to the one repository the session belongs to (403 for every other repo).
# So the desk pulls *their* mailbox anonymously and answers into its own outbox.
# A peer is "owner/repo" or "owner/repo#ref" (default ref hub/mailbox).
function Get-PeerRepos {
    $value = Get-Property $script:Config 'peer_repos' @()
    $out = @()
    foreach ($item in @($value)) {
        $text = [string]$item
        if (-not $text) { continue }
        $ref = $Ref
        $base = $text
        if ($text.Contains('#')) {
            $parts = $text.Split('#')
            $base = $parts[0]
            if ($parts.Count -gt 1 -and $parts[1]) { $ref = $parts[1] }
        }
        $url = $base
        if ($base -notmatch '^[a-zA-Z][a-zA-Z0-9+.-]*://' -and $base -match '^[^/]+/[^/]+$') {
            $url = 'https://github.com/' + $base + '.git'
        }
        $out += [pscustomobject]@{ Label = $text; Url = $url; Ref = $ref }
    }
    return $out
}

function Fetch-PeerRef {
    param([string]$Url, [string]$PeerRef, [string]$Tracking)
    $previous = $env:GIT_TERMINAL_PROMPT
    $env:GIT_TERMINAL_PROMPT = '0'
    try {
        # Anonymous first: every peer repository is public, and the desk's own
        # stored credential belongs to one repo only.  A private peer then gets
        # a second chance with whatever helper the machine already has.
        $spec = ('+refs/heads/{0}:{1}/{0}' -f $PeerRef, $Tracking)
        $anon = Invoke-Git -Directory $RepoPath -GitArgs @('-c', 'credential.helper=', 'fetch', '--quiet', '--no-tags', $Url, $spec)
        if ($anon.Code -eq 0) { return $anon }
        $retry = Invoke-Git -Directory $RepoPath -GitArgs @('fetch', '--quiet', '--no-tags', $Url, $spec)
        if ($retry.Code -eq 0) { return $retry }
        return $retry
    } finally {
        $env:GIT_TERMINAL_PROMPT = $previous
    }
}

function Invoke-PeerCycle {
    param([int]$Budget = 1, $Ledger = $null)
    $answers = @()
    $peers = @(Get-PeerRepos)
    if ($peers.Count -eq 0) { return @() }
    $outboxDir = Join-Path $script:Worktree 'outbox'
    if (-not (Test-Path -LiteralPath $outboxDir)) {
        New-Item -ItemType Directory -Path $outboxDir -Force | Out-Null
    }
    $index = 0
    foreach ($peer in $peers) {
        $index++
        $label = [string]$peer.Label
        $entry = [ordered]@{ peer = $label; status = 'skipped'; ran = 0; note = '' }
        try {
            # A peer that has never queued anything has no mailbox branch yet:
            # that is "waiting", not an error, and must not spam the log.
            $ls = Invoke-Git -Directory $RepoPath -GitArgs @('-c', 'credential.helper=', 'ls-remote',
                '--heads', $peer.Url, ('refs/heads/' + $peer.Ref))
            if ($ls.Code -ne 0) {
                $entry.status = 'unreachable'
                $entry.note = ([string]$ls.Output).Trim()
                if ($entry.note.Length -gt 200) { $entry.note = $entry.note.Substring(0, 200) }
                $script:PeerInfo += $entry
                Write-Log ('peer {0} unreachable: {1}' -f $label, $entry.note) 'WARN'
                continue
            }
            if ($ls.Output -notmatch [regex]::Escape('refs/heads/' + $peer.Ref)) {
                $entry.status = 'waiting'
                $entry.note = 'no mailbox branch yet (appears on the first send)'
                $script:PeerInfo += $entry
                continue
            }
            $tracking = ('refs/remotes/peer-{0}' -f $index)
            $fetch = Fetch-PeerRef -Url $peer.Url -PeerRef $peer.Ref -Tracking $tracking
            if ($fetch.Code -ne 0) {
                $entry.status = 'unreachable'
                $entry.note = ([string]$fetch.Output).Trim()
                if ($entry.note.Length -gt 200) { $entry.note = $entry.note.Substring(0, 200) }
                $script:PeerInfo += $entry
                Write-Log ('peer {0} unreachable: {1}' -f $label, $entry.note) 'WARN'
                continue
            }
            $refPath = $tracking + '/' + $peer.Ref
            $tree = Invoke-Git -Directory $RepoPath -GitArgs @('ls-tree', '-r', '--name-only', $refPath, 'inbox/')
            $names = @()
            if ($tree.Code -eq 0 -and $tree.Output) {
                $names = @(($tree.Output -split "`r?`n") | Where-Object { $_ -match '^inbox/.+\.json$' } | Sort-Object)
            }
            if ($names.Count -eq 0) {
                $entry.status = 'empty'
                $script:PeerInfo += $entry
                continue
            }
            foreach ($name in $names) {
                if ($entry.ran -ge $Budget) { break }
                $jobId = [System.IO.Path]::GetFileNameWithoutExtension($name)
                $answerPath = Join-Path $outboxDir ($jobId + '.json')
                if (Test-Path -LiteralPath $answerPath) { continue }
                if ($null -ne $Ledger -and $Ledger.Contains($jobId)) { continue }
                $raw = Invoke-Git -Directory $RepoPath -GitArgs @('show', ($refPath + ':' + $name))
                if ($raw.Code -ne 0) { continue }
                $request = $null
                try { $request = $raw.Output | ConvertFrom-Json } catch { $request = $null }
                $started = Get-Date
                $outcome = $null
                try {
                    if ($null -eq $request) {
                        $outcome = [ordered]@{ status = 'error'; summary = 'peer request JSON could not be parsed' }
                    } else {
                        $outcome = Invoke-Job -Request $request
                    }
                } catch {
                    $outcome = [ordered]@{ status = 'error'; summary = ('peer job crashed: ' + $_.Exception.Message) }
                }
                $finished = Get-Date
                $answer = [ordered]@{
                    schema       = 'cgmd.mailbox.result.v1'
                    id           = $jobId
                    kind         = [string](Get-Property $request 'kind' 'unknown')
                    status       = [string](Get-Property $outcome 'status' 'error')
                    summary      = [string](Get-Property $outcome 'summary' '')
                    detail       = Get-Property $outcome 'detail' $null
                    logs_tail    = @(Get-Property $outcome 'logs_tail' @())
                    note         = [string](Get-Property $request 'note' '')
                    requested_by = [string](Get-Property $request 'from' 'peer')
                    peer         = $label
                    worker       = $env:COMPUTERNAME
                    started_at   = $started.ToUniversalTime().AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
                    finished_at  = $finished.ToUniversalTime().AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
                    seconds      = [math]::Round(($finished - $started).TotalSeconds, 2)
                }
                Write-JsonFile -Path $answerPath -Data $answer
                $answers += $answer
                $entry.ran = $entry.ran + 1
                Write-Log ('peer {0} job {1} ({2}) -> {3}: {4}' -f $label, $jobId, $answer['kind'], $answer['status'], $answer['summary'])
                if ($null -ne $Ledger) {
                    $Ledger[$jobId] = [ordered]@{ kind = $answer['kind']; status = $answer['status'];
                                                  finished_at = $answer['finished_at']; summary = $answer['summary'] }
                }
            }
            if ($entry.ran -eq 0 -and $entry.status -eq 'skipped') {
                $entry.status = 'idle'
                $entry.note = ('{0} request(s) seen, all already answered' -f $names.Count)
            } elseif ($entry.ran -gt 0) {
                $entry.status = 'ran'
            }
        } catch {
            $entry.status = 'error'
            $entry.note = $_.Exception.Message
            Write-Log ('peer {0} cycle failed: {1}' -f $label, $_.Exception.Message) 'WARN'
        }
        $script:PeerInfo += $entry
    }
    return $answers
}

function Invoke-Captured {
    param([string]$CommandLine, [string]$OutFile = '', [int]$TimeoutSeconds = 600, [string]$WorkingDirectory = '')
    if (-not $OutFile) {
        $OutFile = Join-Path $script:StateDir ('mailbox-{0}.log' -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
    }
    $cmdFile = [System.IO.Path]::ChangeExtension($OutFile, '.cmd')
    $body = '@echo off' + [Environment]::NewLine + $CommandLine + ' > "' + $OutFile + '" 2>&1' + [Environment]::NewLine +
            ('echo CGMD_EXIT_CODE=%ERRORLEVEL% >> "' + $OutFile + '"')
    [System.IO.File]::WriteAllText($cmdFile, $body, [System.Text.Encoding]::ASCII)
    $working = $WorkingDirectory
    if (-not $working) { $working = $script:StateDir }
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /c "{0}"' -f $cmdFile) `
        -NoNewWindow -PassThru -WorkingDirectory $working
    if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
        & taskkill.exe /F /T /PID $proc.Id 2>&1 | Out-Null
        return 124
    }
    $text = ''
    try { $text = [System.IO.File]::ReadAllText($OutFile, [System.Text.Encoding]::UTF8) } catch { }
    $match = [regex]::Match($text, 'CGMD_EXIT_CODE=(-?\d+)')
    $code = 0
    if ($match.Success) { $code = [int]$match.Groups[1].Value }
    elseif ($text -match 'Fatal error|error:') { $code = 1 }
    return $code
}

function Get-Tail {
    param([string]$Path, [int]$Count = 20)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    try {
        return @([System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8) |
                 Where-Object { $_ -ne '' } | Select-Object -Last $Count)
    } catch {
        return @()
    }
}

# ---------------------------------------------------------------------------
# the mailbox worktree (a real checkout of the mailbox branch, so the same
# UTF-8 helpers as the rest of the hub can be used)
# ---------------------------------------------------------------------------
function Initialize-Mailbox {
    $fetch = Invoke-Git -Directory $RepoPath -GitArgs @('fetch', '--quiet', 'origin',
        ('+refs/heads/{0}:refs/remotes/origin/{0}' -f $Ref))
    if ($fetch.Code -ne 0) {
        if (-not (Test-Path -LiteralPath (Join-Path $script:Worktree '.git'))) {
            $script:InitNote = 'branch does not exist'
            Write-Log ('mailbox branch {0} does not exist yet, nothing to do' -f $Ref)
            return $false
        }
        $script:InitNote = ('fetch failed: ' + $fetch.Output)
        Write-Log ('mailbox fetch failed: ' + $fetch.Output) 'WARN'
        return $false
    }
    $tracking = 'origin/' + $Ref
    if (Test-Path -LiteralPath (Join-Path $script:Worktree '.git')) {
        $null = Invoke-Git -Directory $script:Worktree -GitArgs @('fetch', '--quiet', 'origin')
        $reset = Invoke-Git -Directory $script:Worktree -GitArgs @('reset', '--hard', '--quiet', $tracking)
        if ($reset.Code -ne 0) {
            Write-Log ('mailbox worktree reset failed: ' + $reset.Output) 'WARN'
        }
        return $true
    }
    if (Test-Path -LiteralPath $script:Worktree) {
        Remove-Item -LiteralPath $script:Worktree -Recurse -Force -ErrorAction SilentlyContinue
    }
    # A half-finished earlier attempt leaves a registration behind and every
    # later add then fails with "missing but already registered worktree".
    $null = Invoke-Git -Directory $RepoPath -GitArgs @('worktree', 'remove', '--force', $script:Worktree)
    $null = Invoke-Git -Directory $RepoPath -GitArgs @('worktree', 'prune')
    $add = Invoke-Git -Directory $RepoPath -GitArgs @('worktree', 'add', '--force', '-B', 'hub-mailbox',
        $script:Worktree, $tracking)
    if ($add.Code -ne 0) {
        $script:InitNote = ('worktree add failed: ' + $add.Output)
        Write-Log ('mailbox worktree add failed: ' + $add.Output) 'ERROR'
        return $false
    }
    Write-Log ('mailbox worktree ready at ' + $script:Worktree)
    return $true
}

function New-MailboxBranch {
    param([switch]$Force)
    # Nobody has queued anything yet, so open the queue ourselves.  Without
    # this the branch only appears after the first client, and a client that
    # cannot push (read-only token, CI, a phone) could never start.
    $readme = @(
        '# CGMD mailbox',
        '',
        'Queue work for the workstation from any session, branch or machine:',
        '',
        '    python3 -m core.hub_mailbox run --kind smoke --timeout 1800',
        '',
        '* inbox/<id>.json   request  (cgmd.mailbox.request.v1)',
        '* outbox/<id>.json  result   (cgmd.mailbox.result.v1)',
        '',
        'The desk claims at most mailbox_jobs_per_poll jobs per cycle (60 s),',
        'answers them here and never touches the caller branch.',
        ''
    ) -join [Environment]::NewLine
    $temp = Join-Path $script:StateDir 'mailbox-README.md'
    [System.IO.File]::WriteAllText($temp, $readme, (New-Object System.Text.UTF8Encoding($false)))
    $blob = (Invoke-Git -Directory $RepoPath -GitArgs @('hash-object', '-w', $temp)).Output
    if (-not $blob) { return $false }
    # mktree is fed from a file with LF endings: piping a string through
    # PowerShell 5.1 appends CR and produced a file literally called
    # "README.md`r" the first time this ran.
    $entryFile = Join-Path $script:StateDir 'mailbox-mktree.txt'
    $entry = '100644 blob ' + $blob + "`tREADME.md`n"
    [System.IO.File]::WriteAllText($entryFile, $entry, (New-Object System.Text.ASCIIEncoding))
    $treeOut = Join-Path $script:StateDir 'mailbox-mktree.out'
    $cmd = 'git -C "' + $RepoPath + '" mktree < "' + $entryFile + '"'
    $null = Invoke-Captured -CommandLine $cmd -OutFile $treeOut -TimeoutSeconds 60
    $tree = ''
    try {
        $lines = @([System.IO.File]::ReadAllLines($treeOut, [System.Text.Encoding]::UTF8))
        if ($lines.Count -gt 0) { $tree = $lines[0].Trim() }
    } catch { }
    if (-not $tree -or $tree.Length -lt 8) { Write-Log ('mktree failed: ' + $tree) 'WARN'; return $false }
    $commit = (Invoke-Git -Directory $RepoPath -GitArgs @('-c', 'user.name=CGMD-Desk',
        '-c', 'user.email=hukeying85-ux@users.noreply.github.com',
        'commit-tree', $tree, '-m', 'mailbox: open the queue')).Output
    if (-not $commit) { return $false }
    $pushArgs = @('push', '--quiet')
    if ($Force) { $pushArgs += '--force' }
    $pushArgs += @('origin', ($commit + ':refs/heads/' + $Ref))
    $push = Invoke-Git -Directory $RepoPath -GitArgs $pushArgs
    if ($push.Code -ne 0) {
        $script:InitNote = 'branch push failed: ' + $push.Output
        Write-Log ('mailbox branch creation failed: ' + $push.Output) 'WARN'
        return $false
    }
    Write-Log ('created the mailbox branch ' + $Ref + ' (' + $commit.Substring(0, 8) + ')')
    return $true
}

function Get-MailboxBranchExists {
    $remote = Invoke-Git -Directory $RepoPath -GitArgs @('ls-remote', '--heads', 'origin', $Ref)
    if ($remote.Code -ne 0) { return $false }
    return ($remote.Output -match [regex]::Escape('refs/heads/' + $Ref))
}

function Add-SelfTestRequest {
    # Weekly proof that the bus works end to end on this machine, with nobody
    # asking for it: queue a ping from the desk itself and let the normal path
    # answer it.
    $marker = Join-Path $script:StateDir 'mailbox-selftest.json'
    $previous = Read-JsonFile -Path $marker
    if ($null -ne $previous) {
        $stamp = [string](Get-Property $previous 'last_at' '')
        if ($stamp) {
            try {
                if (([datetimeoffset]::Now - [datetimeoffset]::Parse($stamp)).TotalDays -lt 7) { return $false }
            } catch { }
        }
    }
    $inbox = Join-Path $script:Worktree 'inbox'
    if (-not (Test-Path -LiteralPath $inbox)) { New-Item -ItemType Directory -Path $inbox -Force | Out-Null }
    $jobId = 'selftest-' + (Get-Date -Format 'yyyyMMddTHHmmss')
    $request = [ordered]@{
        schema     = 'cgmd.mailbox.request.v1'
        id         = $jobId
        kind       = 'ping'
        args       = [ordered]@{ selftest = $true }
        note       = 'weekly self test of the mailbox bus'
        from       = 'desk-self-test'
        host       = $env:COMPUTERNAME
        created_at = Get-BeijingStamp
        timeout_s  = 120
    }
    Write-JsonFile -Path (Join-Path $inbox ($jobId + '.json')) -Data $request
    Write-JsonFile -Path $marker -Data ([ordered]@{ last_at = Get-BeijingStamp; last_id = $jobId })
    Write-Log ('queued a mailbox self test: ' + $jobId)
    return $true
}

function Repair-MailboxLayout {
    # First run created a file called "README.md`r" (see New-MailboxBranch), and
    # an empty queue needs an inbox/ and outbox/ directory to exist.  Both are
    # repaired here instead of asking a human to clean up.
    $changed = $false
    $bad = @(Get-ChildItem -LiteralPath $script:Worktree -Recurse -File -ErrorAction SilentlyContinue |
             Where-Object { $_.Name -match "`r" })
    foreach ($item in $bad) {
        try {
            Remove-Item -LiteralPath $item.FullName -Force
            Write-Log ('repaired mailbox: removed a file with an embedded CR in its name') 'WARN'
            $changed = $true
        } catch { }
    }
    $readme = Join-Path $script:Worktree 'README.md'
    if (-not (Test-Path -LiteralPath $readme)) {
        $text = @(
            '# CGMD mailbox',
            '',
            'Queue work for the workstation from any session, branch or machine:',
            '',
            '    python3 -m core.hub_mailbox run --kind smoke --timeout 1800',
            '',
            '* inbox/<id>.json   request  (cgmd.mailbox.request.v1)',
            '* outbox/<id>.json  result   (cgmd.mailbox.result.v1)',
            ''
        ) -join [Environment]::NewLine
        [System.IO.File]::WriteAllText($readme, $text, (New-Object System.Text.UTF8Encoding($false)))
        $changed = $true
    }
    return $changed
}

function Publish-MailboxChanges {
    param([string]$Message)
    $add = Invoke-Git -Directory $script:Worktree -GitArgs @('add', '-A')
    if ($add.Code -ne 0) { Write-Log ('mailbox add failed: ' + $add.Output) 'WARN' }
    $commit = Invoke-Git -Directory $script:Worktree -GitArgs @('-c', 'user.name=CGMD-Desk',
        '-c', 'user.email=hukeying85-ux@users.noreply.github.com',
        'commit', '--quiet', '-m', $Message)
    if ($commit.Code -ne 0) {
        if ($commit.Output -match 'nothing to commit') { return $true }
        Write-Log ('mailbox commit failed: ' + $commit.Output) 'WARN'
        return $false
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $push = Invoke-Git -Directory $script:Worktree -GitArgs @('push', '--quiet', 'origin', ('HEAD:refs/heads/' + $Ref))
        if ($push.Code -eq 0) { return $true }
        Write-Log ('mailbox push rejected (attempt {0}): {1}' -f $attempt, $push.Output) 'WARN'
        $null = Invoke-Git -Directory $script:Worktree -GitArgs @('fetch', '--quiet', 'origin')
        $rebase = Invoke-Git -Directory $script:Worktree -GitArgs @('pull', '--rebase', '--autostash', '--quiet',
            'origin', $Ref)
        if ($rebase.Code -ne 0) {
            Write-Log ('mailbox rebase failed: ' + $rebase.Output) 'WARN'
            $null = Invoke-Git -Directory $script:Worktree -GitArgs @('rebase', '--abort')
            $null = Invoke-Git -Directory $script:Worktree -GitArgs @('reset', '--hard', '--quiet', ('origin/' + $Ref))
            return $false
        }
    }
    return $false
}

# ---------------------------------------------------------------------------
# job kinds
# ---------------------------------------------------------------------------
function Get-GmxBinary {
    foreach ($name in @('gmx.exe', 'gmx')) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $found) { return $found.Source }
    }
    return $null
}

function Get-QuickInventory {
    $gmx = Get-GmxBinary
    $version = $null
    if ($gmx) {
        $out = Join-Path $script:StateDir 'mailbox-gmx-version.txt'
        $null = Invoke-Captured -CommandLine ('"' + $gmx + '" --version') -OutFile $out -TimeoutSeconds 60
        $text = ''
        try { $text = [System.IO.File]::ReadAllText($out, [System.Text.Encoding]::UTF8) } catch { }
        $match = [regex]::Match($text, 'GROMACS version:\s*(\S+)')
        if ($match.Success) { $version = $match.Groups[1].Value }
    }
    $gpus = @()
    $smi = Get-Command 'nvidia-smi' -ErrorAction SilentlyContinue
    if ($smi) {
        try {
            $lines = & $smi.Source '--query-gpu=name,driver_version,memory.total' '--format=csv,noheader'
            foreach ($line in @($lines)) {
                if ($line -and $line.Trim()) { $gpus += $line.Trim() }
            }
        } catch { }
    }
    $lan = @()
    try {
        foreach ($nic in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
            if ($nic.OperationalStatus -ne 'Up') { continue }
            foreach ($info in $nic.GetIPProperties().UnicastAddresses) {
                if ($info.Address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { continue }
                if ([System.Net.IPAddress]::IsLoopback($info.Address)) { continue }
                if ($info.Address.GetAddressBytes()[0] -in @(169)) { continue }
                $lan += $info.Address.ToString()
            }
        }
    } catch { }
    return [ordered]@{
        host        = $env:COMPUTERNAME
        user        = $env:USERNAME
        gmx         = $gmx
        version     = $version
        gpus        = $gpus
        cpus        = [Environment]::ProcessorCount
        lan         = $lan
        bridge_port = [int](Get-Property $script:Config 'bridge_port' 8765)
        bridge_hint = 'python3 -m core.desk_bridge ping --host <lan address above>'
    }
}

function Invoke-JobPing {
    $inventory = Get-QuickInventory
    $inventory['time'] = Get-BeijingStamp
    $inventory['ready'] = [bool]$inventory['gmx']
    return [ordered]@{
        status  = 'ok'
        summary = ('{0} alive, gmx {1}, {2} gpu(s)' -f $env:COMPUTERNAME, $inventory['version'], @($inventory['gpus']).Count)
        detail  = $inventory
    }
}

function Invoke-JobSelfcheck {
    $script = Join-Path $script:ScriptDir 'Test-CgmdHub.ps1'
    if (-not (Test-Path -LiteralPath $script)) {
        return [ordered]@{ status = 'unsupported'; summary = 'Test-CgmdHub.ps1 is missing' }
    }
    $out = Join-Path $script:StateDir 'mailbox-selfcheck.log'
    $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $script + '" -Quiet'
    if ($RepoPath) { $line += ' -RepoPath "' + $RepoPath + '"' }
    if ($Branch) { $line += ' -Branch "' + $Branch + '"' }
    $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds ([math]::Min($MaxJobSeconds, 900))
    $report = Read-JsonFile -Path (Join-Path $RepoPath 'results\status\desktop_selfcheck.json')
    $summary = 'selfcheck exit ' + $code
    if ($null -ne $report) {
        $summary = ('selfcheck: {0} pass / {1} warn / {2} fail' -f
            (Get-Property (Get-Property $report 'summary' $null) 'passed' 0),
            (Get-Property (Get-Property $report 'summary' $null) 'warnings' 0),
            (Get-Property (Get-Property $report 'summary' $null) 'failed' 0))
    }
    return [ordered]@{
        status  = $(if ($code -eq 0) { 'ok' } else { 'fail' })
        summary = $summary
        detail  = [ordered]@{ exit_code = $code; report = $report }
        logs_tail = @(Get-Tail -Path $out -Count 25)
    }
}

function Invoke-JobSync {
    param($JobArgs)
    $script = Join-Path $script:ScriptDir 'Sync-Desktop.ps1'
    if (-not (Test-Path -LiteralPath $script)) {
        return [ordered]@{ status = 'unsupported'; summary = 'Sync-Desktop.ps1 is missing' }
    }
    $out = Join-Path $script:StateDir 'mailbox-sync.log'
    $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $script + '" -Quiet'
    if ($RepoPath) { $line += ' -RepoPath "' + $RepoPath + '"' }
    if ($Branch) { $line += ' -Branch "' + $Branch + '"' }
    # args.desk=true redeploys the Arena Desk panel itself (needed whenever the
    # panel's own html/js/css change, not just the hub scripts).
    if ([bool](Get-Property $JobArgs 'desk' $false)) { $line += ' -Desk -Force' }
    $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds ([math]::Min($MaxJobSeconds, 900))

    # A redeployed panel keeps running the *old* python if the process is not
    # restarted, which is how a fixed server.py kept answering 404 on /mobile.
    $restarted = $false
    if ([bool](Get-Property $JobArgs 'desk' $false)) {
        $restarted = Restart-Panel -DeskRoot ([string](Get-Property $script:Config 'desk_root' 'C:\0apps\ArenaDesk'))
    }
    $summary = 'sync exit ' + $code
    if ([bool](Get-Property $JobArgs 'desk' $false)) {
        $summary += $(if ($restarted) { ' | panel restarted' } else { ' | panel restart failed' })
    }
    return [ordered]@{
        status    = $(if ($code -eq 0 -or $code -eq 6) { 'ok' } else { 'fail' })
        summary   = $summary
        detail    = [ordered]@{ exit_code = $code; panel_restarted = $restarted }
        logs_tail = @(Get-Tail -Path $out -Count 25)
    }
}

function Restart-Panel {
    # Stop the panel process and let the scheduled task bring it back, so the
    # newly deployed server.py / app.js are actually loaded.
    param([string]$DeskRoot)
    try {
        $null = Invoke-Captured -CommandLine 'taskkill /F /IM ArenaDesk.exe /T' -TimeoutSeconds 60
        $pythons = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
                     Where-Object { $_.CommandLine -match 'server\.py' -and $_.CommandLine -match 'ArenaDesk' })
        foreach ($proc in $pythons) {
            try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
        }
        Start-Sleep -Seconds 2
        $task = Get-ScheduledTask -TaskName 'arena-desk-panel' -TaskPath '\' -ErrorAction SilentlyContinue
        if ($task) { Start-ScheduledTask -TaskName 'arena-desk-panel' -TaskPath '\' -ErrorAction SilentlyContinue }
        else {
            $launcher = Join-Path $script:ScriptDir '..\..\..\code\panel\launch_panel.ps1'
            if (Test-Path -LiteralPath $launcher) {
                $null = Invoke-Captured -CommandLine ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $launcher + '"') -TimeoutSeconds 60
            }
        }
        # give the panel time to bind 18765 again
        for ($attempt = 1; $attempt -le 15; $attempt++) {
            Start-Sleep -Seconds 2
            try {
                $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:18765/api/state' -TimeoutSec 4 -UseBasicParsing -ErrorAction Stop
                if ($probe.StatusCode -eq 200) { return $true }
            } catch { }
        }
        Write-Log 'panel did not come back on 18765 within 30 s' 'WARN'
        return $false
    } catch {
        Write-Log ('panel restart failed: ' + $_.Exception.Message) 'WARN'
        return $false
    }
}

function Invoke-JobSmoke {
    param($JobArgs)
    $script = Join-Path $script:ScriptDir 'Run-Gmx-Native.ps1'
    $wantedPs = [double](Get-Property $JobArgs 'ps' 100)
    $gpuId = [int](Get-Property $JobArgs 'gpu_id' 0)
    if (-not (Test-Path -LiteralPath $script)) {
        return [ordered]@{ status = 'unsupported'; summary = 'Run-Gmx-Native.ps1 is missing' }
    }
    $out = Join-Path $script:StateDir 'mailbox-smoke.log'
    $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $script + '"'
    $line += ' -Ps ' + $wantedPs + ' -GpuId ' + $gpuId + ' -Quiet'
    if ($RepoPath) { $line += ' -RepoPath "' + $RepoPath + '"' }
    if ($Branch) { $line += ' -Branch "' + $Branch + '"' }
    $limit = [math]::Min($MaxJobSeconds, 2400)
    $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds $limit
    $report = Read-JsonFile -Path (Join-Path $RepoPath 'results\status\gmx_smoke.json')
    $status = $(if ($code -eq 0) { 'ok' } else { 'fail' })
    $summary = 'smoke exit ' + $code
    $detail = [ordered]@{ exit_code = $code }
    if ($null -ne $report) {
        $version = ''
        $software = Get-Property $report 'software' $null
        if ($null -ne $software) {
            $block = Get-Property $software 'gromacs' $null
            if ($null -ne $block) { $version = [string](Get-Property $block 'version' '') }
        }
        $psDone = Get-Property $report 'ps_completed' 0
        $status = [string](Get-Property $report 'status' $status)
        $summary = ('gmx {0}: {1} ps integrated on {2}' -f $version, $psDone, (Get-Property $report 'accelerator' '?'))
        $detail['report'] = $report
        $detail['artifact'] = 'results/status/gmx_smoke.json'
    }
    return [ordered]@{
        status    = $status
        summary   = $summary
        detail    = $detail
        logs_tail = @(Get-Tail -Path $out -Count 30)
    }
}

$script:GmxAllowList = @(
    '--version', '-version', 'solvate', 'grompp', 'mdrun', 'editconf', 'genion', 'insert-molecules',
    'energy', 'traj', 'check', 'dump', 'select', 'rms', 'distance', 'gyrate', 'make_ndx', 'pdb2gmx',
    'trjconv', 'trjcat', 'convert-tpr', 'genrestr', 'wham', 'do_dssp', 'sasa', 'hbond', 'density',
    'potential', 'bar', 'enemat', 'covar', 'anaeig', 'filter', 'helix', 'sorient', 'order', 'polystat',
    'ram', 'sans', 'sham', 'spatial', 'wheel', 'xpm2ps', 'view', 'nmens', 'cluster'
)

function Invoke-JobGmx {
    param($JobArgs)
    $argv = @(Get-Property $JobArgs 'argv' @())
    if ($argv.Count -eq 0) {
        return [ordered]@{ status = 'unsupported'; summary = 'gmx needs args.argv, e.g. ["--version"]' }
    }
    $first = [string]$argv[0]
    if ($script:GmxAllowList -notcontains $first) {
        return [ordered]@{ status = 'unsupported'; summary = ('gmx subcommand not allowed: ' + $first) }
    }
    foreach ($word in $argv) {
        if ($word -match '[;&|<>`]' -or $word -match '\$\(') {
            return [ordered]@{ status = 'unsupported'; summary = 'shell metacharacters are not allowed in gmx args' }
        }
    }
    $gmx = Get-GmxBinary
    if (-not $gmx) { return [ordered]@{ status = 'fail'; summary = 'gmx.exe not found on this workstation' } }
    $scratch = Join-Path $script:StateDir ('gmx-job-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    if (-not (Test-Path -LiteralPath $scratch)) { New-Item -ItemType Directory -Path $scratch -Force | Out-Null }
    $out = Join-Path $scratch 'output.log'
    $quoted = @()
    foreach ($word in $argv) {
        if ($word -match '\s') { $quoted += ('"' + $word + '"') } else { $quoted += $word }
    }
    $line = '"' + $gmx + '" ' + ($quoted -join ' ')
    $limit = [math]::Min($MaxJobSeconds, [int](Get-Property $JobArgs 'timeout_s' 900))
    $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds $limit -WorkingDirectory $scratch
    $tail = @(Get-Tail -Path $out -Count 40)
    $status = $(if ($code -eq 0) { 'ok' } elseif ($code -eq 124) { 'timeout' } else { 'fail' })
    $headline = ''
    foreach ($candidate in $tail) {
        if ($candidate -match 'Fatal error') { $headline = $candidate.Trim(); break }
    }
    if (-not $headline -and $tail.Count -gt 0) { $headline = [string]$tail[$tail.Count - 1] }
    return [ordered]@{
        status    = $status
        summary   = ('gmx {0} exit {1}: {2}' -f ($argv -join ' '), $code, $headline)
        detail    = [ordered]@{ exit_code = $code; argv = $argv; workdir = $scratch; gmx = $gmx }
        logs_tail = $tail
    }
}

function Get-FileHashShort {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return '' }
    try {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.Substring(0, 12).ToLower()
    } catch { return '' }
}

function Find-DeskRoot {
    # Where Arena Desk is actually deployed (any drive - this box has no E:).
    $candidates = @()
    if ($script:Config) {
        $configured = [string](Get-Property $script:Config 'desk_root' '')
        if ($configured) { $candidates += $configured }
    }
    foreach ($drv in @('C:\', 'D:\', 'E:\', 'F:\', 'G:\')) {
        if (-not (Test-Path -LiteralPath $drv)) { continue }
        $candidates += (Join-Path $drv '0apps\ArenaDesk')
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'server.py')) { return $candidate }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return ''
}

function Invoke-JobDeskdiag {
    # Ground truth, not inference: what is on disk, what is served, and whether
    # the boot animation task exists.  Every "the desk is still broken" report so
    # far came from comparing the repo against something nobody measured.
    $repoPanel = Join-Path $RepoPath 'code\panel'
    $deskRoot = Find-DeskRoot
    $files = @('index.html', 'app.js', 'style.css', 'server.py', 'desktop_ops.py')
    $drift = @()
    $rows = [ordered]@{}
    foreach ($name in $files) {
        $repoPath = Join-Path $repoPanel $name
        $deskPath = ''
        if ($deskRoot) { $deskPath = Join-Path $deskRoot $name }
        $repoHash = Get-FileHashShort -Path $repoPath
        $deskHash = Get-FileHashShort -Path $deskPath
        $rows[$name] = [ordered]@{
            repo = $repoHash
            desk = $deskHash
            same = ($repoHash -ne '' -and $repoHash -eq $deskHash)
            desk_path = $deskPath
        }
        if ($repoHash -and $deskHash -and $repoHash -ne $deskHash) { $drift += $name }
        if ($repoHash -and -not $deskHash) { $drift += ($name + ' (missing)') }
    }

    # what the browser is actually being served right now
    $served = [ordered]@{ ok = $false; has_boot_fallback = $false; has_boot_fallback_css = $false;
                          has_app_js_fallback = $false; bytes = 0; status = 0 }
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:18765/' -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
        $body = [string]$response.Content
        $served['ok'] = $true
        $served['status'] = [int]$response.StatusCode
        $served['bytes'] = $body.Length
        $served['has_boot_fallback'] = ($body -match 'id="boot-fallback"')
        $js = ''
        try {
            $js = [string](Invoke-WebRequest -Uri 'http://127.0.0.1:18765/app.js' -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop).Content
        } catch { }
        $served['has_app_js_fallback'] = ($js -match 'showBootFallback')
        $css = ''
        try {
            $css = [string](Invoke-WebRequest -Uri 'http://127.0.0.1:18765/style.css' -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop).Content
        } catch { }
        $served['has_boot_fallback_css'] = ($css -match 'dsvs-boot-fallback')
    } catch {
        $served['error'] = $_.Exception.Message
    }

    # the clips the overlay wants, on disk
    $clips = [ordered]@{}
    foreach ($clip in @('dsh-boot.mp4', 'dsh-bg.mp4', 'boot-mascot.jpg', 'wallpaper-anime.jpg')) {
        $here = Join-Path $repoPanel ('assets\' + $clip)
        $there = ''
        if ($deskRoot) { $there = Join-Path $deskRoot ('assets\' + $clip) }
        $clips[$clip] = [ordered]@{
            repo = (Test-Path -LiteralPath $here)
            desk = $(if ($there) { Test-Path -LiteralPath $there } else { $false })
        }
    }

    # boot animation plumbing: the scheduled tasks and the preference file
    $tasks = @(Get-DesktopTasks)

    # A locked or disconnected console explains a hidden browser window, and a
    # hidden window is why an animation can look like "nothing happened".
    $session = [ordered]@{ user = $env:USERNAME; session_id = 0; locked = $false; logonui = $false }
    try { $session['session_id'] = (Get-Process -Id $PID).SessionId } catch { }
    try {
        $logon = @(Get-Process -Name 'LogonUI' -ErrorAction SilentlyContinue)
        $session['logonui'] = ($logon.Count -gt 0)
        $session['locked'] = ($logon.Count -gt 0)
    } catch { }

    $appearance = $null
    $bootAck = $null
    if ($deskRoot) {
        $appearance = Read-JsonFile -Path (Join-Path $deskRoot 'data\appearance.json')
        # the page posts here when the overlay closes; "mode" is the reason tag,
        # which tells us whether the video, the fallback or nothing played.
        $bootAck = Read-JsonFile -Path (Join-Path $deskRoot 'data\boot-ack.json')
    }

    $status = 'ok'
    if ($drift.Count -gt 0) { $status = 'drift' }
    elseif (-not $served['ok']) { $status = 'offline' }
    elseif (-not $served['has_boot_fallback']) { $status = 'stale-panel' }

    $summary = ('desk {0} | drift {1} | served boot-fallback {2} | tasks {3}' -f
        $deskRoot, $drift.Count, $served['has_boot_fallback'],
        (@($tasks | Where-Object { $_['exists'] }).Count))
    return [ordered]@{
        status  = $status
        summary = $summary
        detail  = [ordered]@{
            repo_panel   = $repoPanel
            desk_root    = $deskRoot
            files        = $rows
            drift        = $drift
            served       = $served
            clips        = $clips
            tasks        = $tasks
            appearance   = $appearance
            boot_ack     = $bootAck
            session      = $session
            peer_repos   = @(Get-Property $script:Config 'peer_repos' @())
            peers        = @(Get-Property (Read-JsonFile -Path $script:LastPath) 'peers' @())
        }
    }
}

function Get-DesktopTasks {
    param([string[]]$Names = @('arena-desk-boot-demo', 'arena-desk-open', 'arena-desk-open-manual', 'arena-desk-panel'))
    $rows = @()
    foreach ($name in $Names) {
        $row = [ordered]@{
            name = $name; exists = $false; state = ''; last_result = ''; last_run = ''
            triggers = @(); actions = @()
        }
        $task = $null
        try { $task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction Stop } catch { $task = $null }
        if ($null -ne $task) {
            $row['exists'] = $true
            $row['state'] = [string]$task.State
            foreach ($t in @($task.Triggers)) {
                $row['triggers'] += $(if ($t.CimClass.CimClassName) { $t.CimClass.CimClassName } else { '?' })
            }
            foreach ($a in @($task.Actions)) {
                $row['actions'] += ([string]$a.Execute + ' ' + [string]$a.Arguments).Trim()
            }
            try {
                $info = Get-ScheduledTaskInfo -TaskName $name -TaskPath '\' -ErrorAction Stop
                $row['last_result'] = [string]$info.LastTaskResult
                $row['last_run'] = $(if ($info.LastRunTime -and $info.LastRunTime.Year -gt 2000) {
                                        ([datetime]$info.LastRunTime).ToString('yyyy-MM-dd HH:mm:ss') } else { '' })
            } catch { }
        }
        $rows += $row
    }
    return $rows
}

function Invoke-JobDeskfix {
    # Repair the desktop-side plumbing end to end, from here, with no human.
    # 0) optionally record which other repositories this desk should serve;
    # 1) the boot animation task needs an AtLogOn trigger (it had none);
    # 2) only one task may open a window at logon, or two windows appear;
    # 3) the panel has to be running before any window opens;
    # 4) finally launch the animation so the result is visible immediately.
    param($JobArgs)
    $deskRoot = Find-DeskRoot
    $notes = @()
    $peerValue = Get-Property $JobArgs 'peer_repos' $null
    if ($null -ne $peerValue) {
        try {
            $list = @()
            foreach ($item in @($peerValue)) {
                $text = ([string]$item).Trim()
                if ($text) { $list += $text }
            }
            $cfgPath = Set-HubConfigValue -Name 'peer_repos' -Value $list
            $script:Config = Read-JsonFile -Path $cfgPath
            $notes += ('peer_repos -> ' + ($list -join ', ') + ' in ' + $cfgPath)
        } catch {
            $notes += ('peer_repos write failed: ' + $_.Exception.Message)
        }
    }
    if (-not $deskRoot) {
        return [ordered]@{ status = 'fail'; summary = 'Arena Desk is not deployed on any drive'; detail = @{} }
    }
    $exePath = Join-Path $deskRoot 'ArenaDesk.exe'
    if (-not (Test-Path -LiteralPath $exePath)) {
        $notes += 'ArenaDesk.exe missing, falling back to launch_panel.ps1'
    }
    $user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0) -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

    # --- the boot animation owns the logon trigger -------------------------
    $bootRegistered = $false
    if (Test-Path -LiteralPath $exePath) {
        try {
            $bootAction = New-ScheduledTaskAction -Execute $exePath -Argument '--boot' -WorkingDirectory $deskRoot
            Register-ScheduledTask -TaskName 'arena-desk-boot-demo' -TaskPath '\' -Action $bootAction `
                -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
            $bootRegistered = $true
            $notes += 'arena-desk-boot-demo re-registered WITH an AtLogOn trigger'
        } catch {
            $notes += ('boot-demo registration failed: ' + $_.Exception.Message)
        }
        # a second window at logon would be noise
        try {
            $openTask = Get-ScheduledTask -TaskName 'arena-desk-open' -TaskPath '\' -ErrorAction SilentlyContinue
            if ($openTask) {
                Disable-ScheduledTask -TaskName 'arena-desk-open' -TaskPath '\' -ErrorAction SilentlyContinue | Out-Null
                $notes += 'arena-desk-open disabled at logon (the animation task opens the window instead)'
            }
            $openAction = New-ScheduledTaskAction -Execute $exePath -WorkingDirectory $deskRoot
            Register-ScheduledTask -TaskName 'arena-desk-open-manual' -TaskPath '\' -Action $openAction `
                -Principal $principal -Settings $settings -Force | Out-Null
            $notes += 'arena-desk-open-manual registered (no trigger, for "skip the animation")'
        } catch {
            $notes += ('open-manual registration failed: ' + $_.Exception.Message)
        }
    } else {
        $launcher = Join-Path $deskRoot 'launch_panel.ps1'
        if (Test-Path -LiteralPath $launcher) {
            $args = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $launcher + '"'
            try {
                $openAction = New-ScheduledTaskAction -Execute $ps -Argument $args -WorkingDirectory $deskRoot
                Register-ScheduledTask -TaskName 'arena-desk-open' -TaskPath '\' -Action $openAction `
                    -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
                $bootRegistered = $true
                $notes += 'no exe: arena-desk-open re-registered with the AtLogOn trigger'
            } catch {
                $notes += ('open registration failed: ' + $_.Exception.Message)
            }
        }
    }

    # --- the panel must be alive before the window opens -------------------
    $panelUp = $false
    try {
        $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:18765/api/state' -TimeoutSec 6 -UseBasicParsing -ErrorAction Stop
        $panelUp = ($probe.StatusCode -eq 200)
    } catch { $panelUp = $false }
    if (-not $panelUp) {
        $notes += 'panel was down, starting it'
        $null = Restart-Panel -DeskRoot $deskRoot
        try {
            $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:18765/api/state' -TimeoutSec 6 -UseBasicParsing -ErrorAction Stop
            $panelUp = ($probe.StatusCode -eq 200)
        } catch { $panelUp = $false }
    }

    # --- show the animation now, so "did it work" is answerable ------------
    $launched = $false
    if ($bootRegistered -and $panelUp) {
        try {
            Start-ScheduledTask -TaskName 'arena-desk-boot-demo' -TaskPath '\' -ErrorAction Stop
            $launched = $true
            $notes += 'arena-desk-boot-demo started now'
        } catch {
            try {
                & schtasks.exe /Run /TN 'arena-desk-boot-demo' | Out-Null
                $launched = ($LASTEXITCODE -eq 0)
                if ($launched) { $notes += 'arena-desk-boot-demo started now (schtasks)' }
            } catch { }
        }
    }
    Start-Sleep -Seconds 3
    $tasks = Get-DesktopTasks
    $boot = @($tasks | Where-Object { $_['name'] -eq 'arena-desk-boot-demo' })[0]
    $summary = ('panel {0} | boot task trigger {1} | launched {2}' -f
        $(if ($panelUp) { 'up' } else { 'DOWN' }), @($boot['triggers']).Count, $launched)
    $status = 'ok'
    if (-not $panelUp) { $status = 'fail' }
    elseif (-not $bootRegistered -or @($boot['triggers']).Count -eq 0) { $status = 'fail' }
    elseif (-not $launched) { $status = 'warn' }
    return [ordered]@{
        status  = $status
        summary = $summary
        detail  = [ordered]@{
            desk_root = $deskRoot
            panel_up  = $panelUp
            launched  = $launched
            peer_repos = @(Get-Property $script:Config 'peer_repos' @())
            tasks     = $tasks
            notes     = $notes
        }
    }
}

function Invoke-JobShell {
    param($JobArgs)
    if (-not $AllowShell) {
        return [ordered]@{ status = 'unsupported'
                           summary = 'shell jobs are disabled; start Invoke-CgmdMailbox.ps1 with -AllowShell' }
    }
    $command = [string](Get-Property $JobArgs 'command' '')
    if (-not $command) { return [ordered]@{ status = 'unsupported'; summary = 'shell needs args.command' } }
    $out = Join-Path $script:StateDir ('shell-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    $limit = [math]::Min($MaxJobSeconds, [int](Get-Property $JobArgs 'timeout_s' 300))
    $code = Invoke-Captured -CommandLine $command -OutFile $out -TimeoutSeconds $limit
    return [ordered]@{
        status    = $(if ($code -eq 0) { 'ok' } else { 'fail' })
        summary   = 'shell exit ' + $code
        detail    = [ordered]@{ exit_code = $code; command = $command }
        logs_tail = @(Get-Tail -Path $out -Count 40)
    }
}

function Get-DeskPython {
    # Every interpreter this box has, best first.  The panel runs on a Windows
    # python that is often NOT on PATH, so globbing the usual install roots is
    # what actually finds it.
    param($JobArgs)
    $list = @()
    $explicit = [string](Get-Property $JobArgs 'python' '')
    if ($explicit) { $list += $explicit }
    foreach ($name in @('python.exe', 'python3.exe', 'python')) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $found -and $found.Source) { $list += $found.Source }
    }
    $patterns = @()
    if ($env:LOCALAPPDATA) { $patterns += (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python*\python.exe') }
    if ($env:ProgramFiles) { $patterns += (Join-Path $env:ProgramFiles 'Python*\python.exe') }
    $patterns += 'C:\Python3*\python.exe'
    $patterns += 'C:\ProgramData\Anaconda3\python.exe'
    foreach ($pattern in $patterns) {
        foreach ($hit in @(Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue)) {
            $list += $hit.FullName
        }
    }
    # First-existing is not good enough: this box has a Python 3.2 on PATH, and
    # handing the dispatcher to it fails before the inventory can even start.
    # Ask every candidate for its version and keep the newest usable one.
    $first = ''
    $best = ''
    $bestCode = -1
    foreach ($candidate in @($list | Select-Object -Unique)) {
        if (-not $candidate) { continue }
        if (-not (Test-Path -LiteralPath $candidate)) { continue }
        if (-not $first) { $first = $candidate }
        $code = Get-PythonCode -Exe $candidate
        if ($code -ge 306 -and $code -gt $bestCode) {
            $best = $candidate
            $bestCode = $code
        }
    }
    if ($best) { return $best }
    return $first
}

function Get-PythonCode {
    # 3.11 -> 311, 3.2 -> 302.  0 means 'could not run it'.
    param([string]$Exe)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe -c "import sys;sys.stdout.write('%d%02d' % (sys.version_info[0], sys.version_info[1]))" 2>$null
        if ($null -eq $out) { return 0 }
        $text = ([string]$out).Trim()
        if ($text -match '^[0-9]{2,3}$') { return [int]$text }
        return 0
    } catch {
        return 0
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Invoke-JobCgmd {
    # Coarse-grained work without a shell: one fixed dispatcher script, six
    # fixed modes.  The caller passes a JSON document, never a command line.
    param($JobArgs)
    $script = Join-Path $RepoPath 'code\cgmd\desk_ops.py'
    if (-not (Test-Path -LiteralPath $script)) {
        return [ordered]@{ status = 'unsupported'; summary = 'code/cgmd/desk_ops.py is missing on this checkout' }
    }
    $python = Get-DeskPython -JobArgs $JobArgs
    if (-not $python) {
        return [ordered]@{ status = 'unsupported'; summary = 'no python interpreter found on this workstation' }
    }
    $mode = [string](Get-Property $JobArgs 'mode' 'probe')
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $argFile = Join-Path $script:StateDir ('cgmd-args-' + $stamp + '.json')
    $resultFile = Join-Path $script:StateDir ('cgmd-result-' + $stamp + '.json')
    $log = Join-Path $script:StateDir ('mailbox-cgmd-' + $stamp + '.log')
    Write-JsonFile -Path $argFile -Data $JobArgs
    $line = '"' + $python + '" "' + $script + '" --mode ' + $mode + ' --args "' + $argFile + '" --out "' + $resultFile + '"'
    $limit = [math]::Min($MaxJobSeconds, [int](Get-Property $JobArgs 'timeout_s' 1800))
    $code = Invoke-Captured -CommandLine $line -OutFile $log -TimeoutSeconds $limit -WorkingDirectory $RepoPath
    $result = Read-JsonFile -Path $resultFile
    $tail = @(Get-Tail -Path $log -Count 30)
    if ($null -eq $result) {
        return [ordered]@{
            status    = $(if ($code -eq 124) { 'timeout' } else { 'fail' })
            summary   = ('cgmd ' + $mode + ' exit ' + $code + ': no result file')
            detail    = [ordered]@{ exit_code = $code; python = $python; mode = $mode }
            logs_tail = $tail
        }
    }
    $status = [string](Get-Property $result 'status' 'fail')
    if ($code -eq 124) { $status = 'timeout' }
    $summary = [string](Get-Property $result 'summary' '')
    return [ordered]@{
        status    = $status
        summary   = ('cgmd ' + $mode + ': ' + $summary)
        detail    = [ordered]@{ exit_code = $code; python = $python; mode = $mode; ops = $result }
        logs_tail = $tail
    }
}

function Invoke-Job {
    param($Request)
    $kind = [string](Get-Property $Request 'kind' 'ping')
    $jobArgs = Get-Property $Request 'args' $null
    $requested = [int](Get-Property $Request 'timeout_s' 900)
    if ($requested -gt 0) { $script:MaxJobSeconds = [math]::Min($MaxJobSeconds, $requested) }
    Write-Log ('job kind=' + $kind)
    switch ($kind) {
        'ping'      { return Invoke-JobPing }
        'selfcheck' { return Invoke-JobSelfcheck }
        'sync'      { return Invoke-JobSync -JobArgs $jobArgs }
        'smoke'     { return Invoke-JobSmoke -JobArgs $jobArgs }
        'gmx'       { return Invoke-JobGmx -JobArgs $jobArgs }
        'deskdiag'  { return Invoke-JobDeskdiag }
        'deskfix'   { return Invoke-JobDeskfix -JobArgs $jobArgs }
        'shell'     { return Invoke-JobShell -JobArgs $jobArgs }
        'cgmd'      { return Invoke-JobCgmd -JobArgs $jobArgs }
        'pipeline'  { return [ordered]@{ status = 'unsupported'
                                         summary = 'the Martini pipeline job kind is not wired yet; use smoke or gmx' } }
        default     { return [ordered]@{ status = 'unsupported'; summary = ('unknown kind: ' + $kind) } }
    }
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
$jobs = @()
$mailboxState = 'ran'
$queuedCount = 0
$script:InitNote = ''
$branchCreated = $false
try {
    $cfg = Get-HubConfig
    $script:Config = $cfg
    if (-not $RepoPath) { $RepoPath = [string](Get-Property $cfg 'repo_path' $script:HubRoot) }
    if (-not $Branch) { $Branch = [string](Get-Property $cfg 'branch' '') }
    if (-not $Ref) { $Ref = [string](Get-Property $cfg 'mailbox_ref' 'hub/mailbox') }
    if (-not $Branch) {
        $head = Invoke-Git -Directory $RepoPath -GitArgs @('rev-parse', '--abbrev-ref', 'HEAD')
        if ($head.Code -eq 0) { $Branch = $head.Output.Trim() }
    }
    $repoMailbox = [string](Get-Property $cfg 'mailbox_enabled' $true)
    if (-not $AllowShell) { $AllowShell = [bool](Get-Property $cfg 'allow_shell' $false) }

    if (-not $repoMailbox) {
        $mailboxState = 'disabled'
        Write-Log 'mailbox disabled in the config'
    } elseif (-not (Initialize-Mailbox)) {
        if (-not (Get-MailboxBranchExists)) {
            Write-Log 'mailbox branch does not exist on origin yet, creating it'
            $created = New-MailboxBranch
            $branchCreated = [bool]$created
            if ($created -and (Initialize-Mailbox)) { $mailboxState = 'created' } else { $mailboxState = 'no-branch' }
        } else {
            # The branch exists but cannot be checked out here: the first
            # attempt wrote a file called "README.md" plus a CR, which Windows
            # cannot create ("invalid path 'README.md?'").  When nothing has
            # been queued yet, rebuild the branch cleanly; a queue with real
            # work in it is never force-pushed.
            $tree = Invoke-Git -Directory $RepoPath -GitArgs @('ls-tree', '-r', '--name-only', ('origin/' + $Ref))
            $work = @(($tree.Output -split "`r?`n") | Where-Object { $_ -match '^(inbox|outbox)/' })
            if ($work.Count -eq 0) {
                Write-Log 'mailbox branch exists but cannot be checked out and is empty, rebuilding it'
                if (New-MailboxBranch -Force) {
                    $branchCreated = $true
                    # Initialize-Mailbox re-fetches, so the tracking ref follows
                    # the rebuilt branch on its own.
                    if (Initialize-Mailbox) { $mailboxState = 'repaired' }
                }
            }
            if ($mailboxState -ne 'repaired') {
                $script:InitNote = $script:InitNote + ' | existing branch unusable (' + $work.Count + ' queued items)'
                $mailboxState = 'no-branch'
            }
        }
        if ($mailboxState -eq 'no-branch') { Write-Log 'mailbox unavailable this cycle' }
    }
    if ($mailboxState -eq 'created' -or $mailboxState -eq 'repaired') {
        $createdInbox = Join-Path $script:Worktree 'inbox'
        if (-not (Test-Path -LiteralPath $createdInbox)) {
            New-Item -ItemType Directory -Path $createdInbox -Force | Out-Null
        }
        $null = Add-SelfTestRequest
        $null = Publish-MailboxChanges -Message 'mailbox: open the queue [desktop hub]'
        $mailboxState = 'ran'
    }
    if ($mailboxState -eq 'ran') {
        $inboxDir = Join-Path $script:Worktree 'inbox'
        $outboxDir = Join-Path $script:Worktree 'outbox'
        if (-not (Test-Path -LiteralPath $outboxDir)) {
            New-Item -ItemType Directory -Path $outboxDir -Force | Out-Null
        }
        if (Repair-MailboxLayout) {
            $null = Publish-MailboxChanges -Message 'mailbox: repair layout [desktop hub]'
        }
        # weekly proof that the bus works, queued by the desk itself
        $null = Add-SelfTestRequest
        $requests = @()
        if (Test-Path -LiteralPath $inboxDir) {
            $requests = @(Get-ChildItem -LiteralPath $inboxDir -Filter '*.json' -File -ErrorAction SilentlyContinue |
                          Sort-Object Name)
        }
        $queuedCount = $requests.Count
        Write-Log ('mailbox: {0} queued, running at most {1}' -f $requests.Count, $MaxJobs)
        # Read-JsonFile returns PSObjects, and PowerShell 5.1 refuses to index
        # those ("Cannot index into an object of type PSObject").  Anything read
        # back from disk is copied into a real dictionary first.
        $ledgerRaw = Read-JsonFile -Path $script:LedgerPath
        $ledger = [ordered]@{}
        if ($null -ne $ledgerRaw) {
            foreach ($prop in $ledgerRaw.PSObject.Properties) { $ledger[$prop.Name] = $prop.Value }
        }
        # Attempts per job: a job that cannot be completed must still produce
        # an answer, otherwise the caller waits forever and the desk re-runs it
        # on every single poll.
        $attemptsPath = Join-Path $script:StateDir 'mailbox-attempts.json'
        $attempts = [ordered]@{}
        $storedAttempts = Read-JsonFile -Path $attemptsPath
        if ($null -ne $storedAttempts) {
            foreach ($prop in $storedAttempts.PSObject.Properties) {
                $attempts[$prop.Name] = [int]$prop.Value
            }
        }
        $script:MaxAttempts = [int](Get-Property $script:Config 'mailbox_max_attempts' 3)

        foreach ($requestFile in ($requests | Select-Object -First $MaxJobs)) {
            $jobId = [System.IO.Path]::GetFileNameWithoutExtension($requestFile.Name)
            $answerPath = Join-Path $outboxDir ($jobId + '.json')
            if (Test-Path -LiteralPath $answerPath) {
                # The answer was written but a later step failed before it was
                # published.  Publish it now instead of dropping the request:
                # silently discarding a finished job left the caller waiting for
                # 15 minutes on 2026-10-29.
                Write-Log ('job {0} already has an answer on disk, publishing it instead of re-running' -f $jobId) 'WARN'
                Remove-Item -LiteralPath $requestFile.FullName -Force -ErrorAction SilentlyContinue
                $existing = Read-JsonFile -Path $answerPath
                if ($null -ne $existing) {
                    $normalised = [ordered]@{
                        id          = [string](Get-Property $existing 'id' $jobId)
                        kind        = [string](Get-Property $existing 'kind' 'unknown')
                        status      = [string](Get-Property $existing 'status' 'error')
                        summary     = [string](Get-Property $existing 'summary' '')
                        finished_at = [string](Get-Property $existing 'finished_at' '')
                    }
                    $jobs += $normalised
                    $ledger[$jobId] = $normalised
                }
                continue
            }
            $request = $null
            try {
                $request = Read-JsonFile -Path $requestFile.FullName
            } catch {
                Write-Log ('job {0} has broken JSON: {1}' -f $jobId, $_.Exception.Message) 'WARN'
            }
            if (-not $attempts.Contains($jobId)) { $attempts[$jobId] = 0 }
            $attempts[$jobId] = [int]$attempts[$jobId] + 1
            if ($attempts[$jobId] -gt $script:MaxAttempts) {
                # Give up loudly instead of looping forever.
                Write-Log ('job {0} exceeded {1} attempts, answering with an error' -f $jobId, $script:MaxAttempts) 'WARN'
                $failed = [ordered]@{
                    schema      = 'cgmd.mailbox.result.v1'
                    id          = $jobId
                    kind        = [string](Get-Property $request 'kind' 'unknown')
                    status      = 'error'
                    summary     = ('the desk tried {0} times and could not finish this job' -f $script:MaxAttempts)
                    detail      = [ordered]@{ attempts = $attempts[$jobId]; hint = 'see results/status/hub_mailbox.json log_tail' }
                    logs_tail   = @(Get-Tail -Path (Join-Path $script:LogDir ('mailbox-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))) -Count 30)
                    note        = [string](Get-Property $request 'note' '')
                    worker      = $env:COMPUTERNAME
                    finished_at = Get-BeijingStamp
                }
                Write-JsonFile -Path $answerPath -Data $failed
                Remove-Item -LiteralPath $requestFile.FullName -Force -ErrorAction SilentlyContinue
                $jobs += $failed
                continue
            }
            $started = Get-Date
            $outcome = $null
            try {
                if ($null -eq $request) {
                    $outcome = [ordered]@{ status = 'error'; summary = 'request JSON could not be parsed' }
                } else {
                    $outcome = Invoke-Job -Request $request
                }
            } catch {
                $outcome = [ordered]@{ status = 'error'; summary = ('job crashed: ' + $_.Exception.Message) }
            }
            $finished = Get-Date
            $result = [ordered]@{
                schema      = 'cgmd.mailbox.result.v1'
                id          = $jobId
                kind        = [string](Get-Property $request 'kind' 'unknown')
                status      = [string](Get-Property $outcome 'status' 'error')
                summary     = [string](Get-Property $outcome 'summary' '')
                detail      = Get-Property $outcome 'detail' $null
                logs_tail   = @(Get-Property $outcome 'logs_tail' @())
                note        = [string](Get-Property $request 'note' '')
                requested_by = [string](Get-Property $request 'from' 'unknown')
                started_at  = $started.ToUniversalTime().AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
                finished_at = $finished.ToUniversalTime().AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
                seconds     = [math]::Round(($finished - $started).TotalSeconds, 2)
                worker      = $env:COMPUTERNAME
            }
            Write-JsonFile -Path $answerPath -Data $result
            Remove-Item -LiteralPath $requestFile.FullName -Force -ErrorAction SilentlyContinue
            $ledger[$jobId] = [ordered]@{ kind = $result['kind']; status = $result['status'];
                                          finished_at = $result['finished_at']; summary = $result['summary'] }
            Write-Log ('job {0} ({1}) -> {2}: {3}' -f $jobId, $result['kind'], $result['status'], $result['summary'])
            $jobs += $result
        }

        # Peers: other projects cannot push into this repo (their session token
        # only covers their own repository), so the desk pulls their mailbox and
        # answers here.  Anonymous read is enough - every peer repo is public.
        try {
            $peerBudget = [int](Get-Property $script:Config 'peer_jobs_per_poll' 1)
            if ($peerBudget -gt 0) {
                $peerAnswers = @(Invoke-PeerCycle -Budget $peerBudget -Ledger $ledger)
                if ($peerAnswers.Count -gt 0) { $jobs += $peerAnswers }
            }
        } catch {
            Write-Log ('peer cycle failed: ' + $_.Exception.Message) 'WARN'
        }

        if ($jobs.Count -gt 0) {
            $null = Publish-MailboxChanges -Message ('mailbox: {0} answer(s) from {1}' -f $jobs.Count, $env:COMPUTERNAME)
        }
        try { Write-JsonFile -Path $script:AttemptsPath -Data $attempts } catch {
            Write-Log ('attempt ledger write failed: ' + $_.Exception.Message) 'WARN'
        }
        try { Write-JsonFile -Path $script:LedgerPath -Data $ledger } catch {
            Write-Log ('ledger write failed: ' + $_.Exception.Message) 'WARN'
        }
        # Remember the last few answers: an idle cycle must not make the
        # published report look like nothing ever ran.
        if ($jobs.Count -gt 0) {
            $recentPath = Join-Path $script:StateDir 'mailbox-recent.json'
            $recent = @(Get-Property (Read-JsonFile -Path $recentPath) 'items' @())
            $fresh = @($jobs | ForEach-Object {
                [ordered]@{ id = $_['id']; kind = $_['kind']; status = $_['status'];
                            summary = $_['summary']; finished_at = $_['finished_at'] }
            })
            $merged = @($fresh) + @($recent)
            $newest = @($merged | Select-Object -First 20)
            Write-JsonFile -Path $recentPath -Data ([ordered]@{ items = $newest })
        }
    }
} catch {
    $mailboxState = 'error'
    Write-Log ('mailbox cycle failed: ' + $_.Exception.Message) 'ERROR'
    Write-Log ($_.ScriptStackTrace) 'ERROR'
    # A crash after the work is done must not strand the answer on this disk.
    try {
        if (Test-Path -LiteralPath (Join-Path $script:Worktree '.git')) {
            $dirty = Invoke-Git -Directory $script:Worktree -GitArgs @('status', '--porcelain')
            if ($dirty.Output) {
                Write-Log 'publishing the mailbox state reached before the failure'
                $null = Publish-MailboxChanges -Message ('mailbox: partial publish after an error on {0}' -f $env:COMPUTERNAME)
            }
        }
    } catch { }
}

# Always leave a ledger behind, even when there was nothing to do: a remote
# reader has to be able to tell "worker ran, queue empty" from "worker never
# ran", and "the mailbox branch does not exist yet" from "machine is broken".
try {
    Write-JsonFile -Path $script:LastPath -Data ([ordered]@{
        schema       = 'cgmd.mailbox.worker.v1'
        generated_at = Get-BeijingStamp
        host         = $env:COMPUTERNAME
        ref          = $Ref
        state        = $mailboxState
        branch_created = $branchCreated
        init_note    = $script:InitNote
        worktree     = $script:Worktree
        queued       = $queuedCount
        max_jobs     = $MaxJobs
        allow_shell  = [bool]$AllowShell
        inbox        = @($requests | ForEach-Object { $_.Name })
        attempts     = $attempts
        log_tail     = @(Get-Tail -Path (Join-Path $script:LogDir ('mailbox-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))) -Count 60)
        call_tail    = @(Get-Tail -Path (Join-Path $script:StateDir 'mailbox-call.log') -Count 40)
        peer_repos   = @(Get-Property $script:Config 'peer_repos' @())
        peers        = @($script:PeerInfo)
        processed    = @($jobs | ForEach-Object { [ordered]@{ id = $_['id']; kind = $_['kind']; status = $_['status']; summary = $_['summary'] } })
        recent       = @(Get-Property (Read-JsonFile -Path (Join-Path $script:StateDir 'mailbox-recent.json')) 'items' @())
    })
} catch { }

if (-not $Quiet) {
    Write-Output (([ordered]@{
        schema    = 'cgmd.mailbox.worker.v1'
        ref       = $Ref
        processed = @($jobs | ForEach-Object { [ordered]@{ id = $_['id']; kind = $_['kind']; status = $_['status']; summary = $_['summary'] } })
    } | ConvertTo-Json -Depth 6))
}
exit 0
