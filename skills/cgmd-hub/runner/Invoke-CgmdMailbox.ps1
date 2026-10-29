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
$script:LastPath = Join-Path $script:StateDir 'mailbox-last.json'
$script:Stopped = $false

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
    return ($raw | ConvertFrom-Json)
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
    $push = Invoke-Git -Directory $RepoPath -GitArgs @('push', '--quiet', 'origin', ($commit + ':refs/heads/' + $Ref))
    if ($push.Code -ne 0) {
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
            (Get-Property $report 'pass' 0), (Get-Property $report 'warn' 0), (Get-Property $report 'fail' 0))
    }
    return [ordered]@{
        status  = $(if ($code -eq 0) { 'ok' } else { 'fail' })
        summary = $summary
        detail  = [ordered]@{ exit_code = $code; report = $report }
        logs_tail = @(Get-Tail -Path $out -Count 25)
    }
}

function Invoke-JobSync {
    $script = Join-Path $script:ScriptDir 'Sync-Desktop.ps1'
    if (-not (Test-Path -LiteralPath $script)) {
        return [ordered]@{ status = 'unsupported'; summary = 'Sync-Desktop.ps1 is missing' }
    }
    $out = Join-Path $script:StateDir 'mailbox-sync.log'
    $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $script + '" -Quiet'
    if ($RepoPath) { $line += ' -RepoPath "' + $RepoPath + '"' }
    if ($Branch) { $line += ' -Branch "' + $Branch + '"' }
    $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds ([math]::Min($MaxJobSeconds, 900))
    return [ordered]@{
        status    = $(if ($code -eq 0) { 'ok' } else { 'fail' })
        summary   = 'sync exit ' + $code
        detail    = [ordered]@{ exit_code = $code }
        logs_tail = @(Get-Tail -Path $out -Count 25)
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
        'sync'      { return Invoke-JobSync }
        'smoke'     { return Invoke-JobSmoke -JobArgs $jobArgs }
        'gmx'       { return Invoke-JobGmx -JobArgs $jobArgs }
        'shell'     { return Invoke-JobShell -JobArgs $jobArgs }
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
            if ($created -and (Initialize-Mailbox)) {
                $mailboxState = 'created'
            } else {
                $mailboxState = 'no-branch'
            }
        } else {
            $mailboxState = 'no-branch'
        }
        if ($mailboxState -ne 'created' -and $mailboxState -ne 'ran') {
            Write-Log 'mailbox unavailable this cycle'
        }
    }
    if ($mailboxState -eq 'created') {
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
        $ledger = Read-JsonFile -Path $script:LedgerPath
        if ($null -eq $ledger) { $ledger = [ordered]@{} }

        foreach ($requestFile in ($requests | Select-Object -First $MaxJobs)) {
            $jobId = [System.IO.Path]::GetFileNameWithoutExtension($requestFile.Name)
            $answerPath = Join-Path $outboxDir ($jobId + '.json')
            if (Test-Path -LiteralPath $answerPath) {
                Write-Log ('job {0} already answered, dropping the duplicate request' -f $jobId) 'WARN'
                Remove-Item -LiteralPath $requestFile.FullName -Force -ErrorAction SilentlyContinue
                continue
            }
            $request = $null
            try {
                $request = Read-JsonFile -Path $requestFile.FullName
            } catch {
                Write-Log ('job {0} has broken JSON: {1}' -f $jobId, $_.Exception.Message) 'WARN'
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

        if ($jobs.Count -gt 0) {
            $null = Publish-MailboxChanges -Message ('mailbox: {0} answer(s) from {1}' -f $jobs.Count, $env:COMPUTERNAME)
        }
        Write-JsonFile -Path $script:LedgerPath -Data $ledger
    }
} catch {
    $mailboxState = 'error'
    Write-Log ('mailbox cycle failed: ' + $_.Exception.Message) 'ERROR'
    Write-Log ($_.ScriptStackTrace) 'ERROR'
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
        processed    = @($jobs | ForEach-Object { [ordered]@{ id = $_['id']; kind = $_['kind']; status = $_['status']; summary = $_['summary'] } })
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
