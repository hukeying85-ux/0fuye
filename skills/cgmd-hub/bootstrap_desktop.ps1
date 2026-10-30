#Requires -Version 5.1
<#
.SYNOPSIS
    One-shot first-run setup of the CGMD desktop hub on a Windows 11 GPU box.

.DESCRIPTION
    Run this ONCE on the workstation.  It is idempotent: running it again
    simply repairs whatever is missing.  It performs, in order:

      1. preflight  - PowerShell, git, WSL2, NVIDIA driver;
      2. repository - clone (or verify) https://github.com/hukeying85-ux/0fuye
                      and REFUSE to continue if origin points anywhere else;
      3. credentials- repository-local git identity + credential helper.
                      Nothing outside this clone is modified: the global
                      git config and other GitHub accounts stay untouched;
      4. WSL2/GPU   - GROMACS + CUDA + Martini 3 self-check inside the distro;
      5. hub config - writes config/cgmd_hub.local.json (git-ignored);
      6. silence    - compiles CGMDHub.exe (/target:winexe);
      7. scheduling - registers the 60 s silent poll task (wscript, no window);
      8. validation - runs one silent poll, one phone beacon and the full
                      Test-CgmdHub.ps1 self-check (exit code 0/6/7), which
                      pushes results/status/desktop_selfcheck.json.

    Every .ps1 file here is pure ASCII on purpose so that Windows PowerShell
    5.1 in a non-UTF8 code page can never mis-parse it.

.PARAMETER RepoUrl
    Locked repository URL.  Any other repository is rejected.

.PARAMETER RepoPath
    Local clone location, default F:\cgmd\0fuye.

.PARAMETER Branch
    Branch to poll.  Default: the branch currently checked out in the clone.

.PARAMETER WslDistro
    WSL2 distribution that provides GROMACS/CUDA, default Ubuntu.

.PARAMETER GpuId
    CUDA device id handed to gmx mdrun, default 0.

.PARAMETER IntervalSeconds
    Polling period, default 60.

.PARAMETER GitHubUser
    Locked GitHub account, default hukeying85-ux.

.PARAMETER LockedRepo
    owner/name the clone is locked to.  Default: derived from RepoUrl, so the
    hub only ever pushes to the repository it was bootstrapped from.

.PARAMETER GitHubToken
    Personal access token.  When omitted you are prompted once (hidden input)
    and the token is stored in a repository-local credential file that is
    git-ignored and ACL-restricted.

.PARAMETER InstallWslDeps
    Let code/cgmd/setup_env.sh install python packages / check for GROMACS
    (GROMACS itself is never installed silently; the script prints the exact
    apt/conda command instead).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap_desktop.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap_desktop.ps1 -RepoPath D:\cgmd\0fuye -GpuId 1
#>
[CmdletBinding()]
param(
    [string]$RepoUrl = 'https://github.com/hukeying85-ux/0fuye.git',
    [string]$RepoPath = 'F:\cgmd\0fuye',
    [string]$Branch = '',
    [string]$WslDistro = 'Ubuntu',
    [int]$GpuId = 0,
    [int]$IntervalSeconds = 60,
    [string]$TaskName = 'CGMD-Hub-Poll',
    [string]$GitHubUser = 'hukeying85-ux',
    [string]$GitHubEmail = '',
    [string]$GitHubToken = '',
    [string]$NtfyTopic = 'arena-beacon-95bc796a66',
    [string]$WslWorkDir = '',
    [switch]$SkipCredentials,
    [switch]$SkipWslSetup,
    [switch]$SkipTask,
    [switch]$SkipFirstPoll,
    [string]$LockedRepo = '',
    [switch]$InstallWslDeps,
    [switch]$NoBeaconTest,
    [switch]$SkipSelfCheck
)

# The clone is locked to exactly one repository: whatever RepoUrl points at,
# unless LockedRepo says otherwise.  Anything else is refused, so a stray
# remote can never receive commits from this workstation.
if (-not $LockedRepo) {
    if ($RepoUrl -match 'github[.]com[/:]([^/]+)/([^/]+?)(?:[.]git)?$') {
        $LockedRepo = $Matches[1] + '/' + $Matches[2]
    } else {
        $LockedRepo = 'hukeying85-ux/0fuye'
    }
}

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = $PSScriptRoot
$script:RunnerDir = Join-Path $HubRoot 'runner'
$script:ConfigDir = Join-Path $HubRoot 'config'
$script:StateDir = Join-Path $HubRoot 'state'
$script:LogDir = Join-Path $HubRoot 'logs'
$script:StepCount = 0
$script:Failures = @()

foreach ($dir in @($script:ConfigDir, $script:StateDir, $script:LogDir)) {
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
}
$script:BootstrapLog = Join-Path $script:LogDir ('bootstrap-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
function Write-Step {
    param([string]$Title)
    $script:StepCount++
    $line = ''
    $line = ('[{0}] {1}' -f $script:StepCount, $Title)
    Write-Host ''
    Write-Host ('=' * 74) -ForegroundColor DarkGray
    Write-Host $line -ForegroundColor Cyan
    Write-Host ('=' * 74) -ForegroundColor DarkGray
    try { [System.IO.File]::AppendAllText($script:BootstrapLog, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false))) } catch { }
}

function Write-Ok {
    param([string]$Message)
    Write-Host ('  [ok]   ' + $Message) -ForegroundColor Green
    try { [System.IO.File]::AppendAllText($script:BootstrapLog, ('OK   ' + $Message) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false))) } catch { }
}

function Write-Warn {
    param([string]$Message)
    Write-Host ('  [warn] ' + $Message) -ForegroundColor Yellow
    try { [System.IO.File]::AppendAllText($script:BootstrapLog, ('WARN ' + $Message) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false))) } catch { }
}

function Write-Err {
    param([string]$Message)
    Write-Host ('  [fail] ' + $Message) -ForegroundColor Red
    $script:Failures += $Message
    try { [System.IO.File]::AppendAllText($script:BootstrapLog, ('FAIL ' + $Message) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false))) } catch { }
}

function Test-Command {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    return ($null -ne $cmd)
}

function Invoke-Git {
    param([string]$Repo, [string[]]$GitArgs, [switch]$AllowFail)
    $all = @()
    if ($Repo) { $all += @('-C', $Repo) }
    $all += $GitArgs
    $output = & git @all 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFail) {
        throw ("git {0} failed ({1}): {2}" -f ($GitArgs -join ' '), $code, (($output | ForEach-Object { "$_" }) -join ' '))
    }
    return [pscustomobject]@{ Code = $code; Output = (($output | ForEach-Object { "$_" }) -join [Environment]::NewLine).Trim() }
}

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $result = & wsl.exe -d $WslDistro -- wslpath -a $WindowsPath 2>&1
    if ($LASTEXITCODE -ne 0) { throw ("wslpath failed: " + ($result -join ' ')) }
    return ("$result").Trim()
}

function Set-RestrictedAcl {
    param([string]$Path)
    try {
        $acl = New-Object System.Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME),
            'FullControl', 'Allow')
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl
        return $true
    } catch {
        return $false
    }
}

# ---------------------------------------------------------------------------
Write-Host ''
Write-Host '  CGMD-Engine - desktop hub bootstrap (Windows 11 + WSL2 + CUDA)' -ForegroundColor White
Write-Host ('  run log: ' + $script:BootstrapLog) -ForegroundColor DarkGray

# --- 0. preflight -----------------------------------------------------------
Write-Step 'Preflight: PowerShell / git / WSL2 / NVIDIA'

if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Err ('PowerShell 5.1 or newer required, found ' + $PSVersionTable.PSVersion)
} else {
    Write-Ok ('PowerShell ' + $PSVersionTable.PSVersion)
}

if (-not (Test-Command 'git')) {
    Write-Err 'git is not on PATH - install Git for Windows https://git-scm.com/download/win'
    throw 'git missing'
}
Write-Ok ('git ' + ((& git --version) -replace 'git version ', ''))

$wslExe = Join-Path $env:SystemRoot 'System32\wsl.exe'
if (Test-Path -LiteralPath $wslExe) {
    Write-Ok 'wsl.exe found'
} elseif (Test-Command 'wsl') {
    $wslExe = 'wsl.exe'
    Write-Ok 'wsl.exe found on PATH'
} else {
    Write-Err 'WSL2 is not installed - run "wsl --install" in an admin PowerShell, reboot, then rerun this script'
    throw 'wsl missing'
}

$distros = @()
try {
    $distros = (& wsl.exe -l -q 2>&1) | ForEach-Object { ("$_").Trim() } | Where-Object { $_ }
} catch { }
if ($distros -contains $WslDistro) {
    Write-Ok ('WSL distro available: ' + $WslDistro)
} else {
    Write-Warn ('distro "{0}" not listed; found: {1}' -f $WslDistro, (($distros -join ', ')))
}

if (Test-Command 'nvidia-smi') {
    try {
        $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>&1) | Select-Object -First 1
        Write-Ok ('GPU: ' + $gpu)
    } catch {
        Write-Warn 'nvidia-smi exists but returned no data'
    }
} else {
    Write-Warn 'nvidia-smi not found on the Windows side (fine if the GPU is only exposed inside WSL2)'
}

# --- 1. repository ----------------------------------------------------------
Write-Step ('Repository: ' + $RepoPath)

if (-not (Test-Path -LiteralPath (Join-Path $RepoPath '.git'))) {
    if (Test-Path -LiteralPath $RepoPath) {
        $existing = @(Get-ChildItem -LiteralPath $RepoPath -Force | Where-Object { $_.Name -ne '.' })
        if ($existing.Count -gt 0) {
            throw ("{0} exists and is not a git clone; move it away or pass -RepoPath" -f $RepoPath)
        }
    }
    $parent = Split-Path -Parent $RepoPath
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Write-Host ('  cloning ' + $RepoUrl)
    $clone = & git clone --quiet $RepoUrl $RepoPath 2>&1
    if ($LASTEXITCODE -ne 0) { throw ("git clone failed: " + (($clone | ForEach-Object { "$_" }) -join ' ')) }
    Write-Ok 'repository cloned'
} else {
    Write-Ok 'existing clone reused'
}

$RepoPath = (Resolve-Path -LiteralPath $RepoPath).Path
$origin = Invoke-Git -Repo $RepoPath -GitArgs @('remote', 'get-url', 'origin')
if ($origin.Output -notmatch [regex]::Escape($LockedRepo)) {
    Write-Err ('origin is "' + $origin.Output + '" but this hub is locked to ' + $LockedRepo)
    throw 'origin mismatch: refusing to touch a foreign repository'
}
Write-Ok ('origin locked to ' + $origin.Output)

# hub scripts must live inside the clone; when bootstrapping from a temp copy
# the freshly cloned copy is authoritative.
$cloneHub = Join-Path $RepoPath 'skills\cgmd-hub'
if (Test-Path -LiteralPath $cloneHub) {
    if ([System.IO.Path]::GetFullPath($cloneHub).TrimEnd('\') -ne [System.IO.Path]::GetFullPath($script:HubRoot).TrimEnd('\')) {
        Write-Warn ('using hub scripts from the clone: ' + $cloneHub)
        $script:HubRoot = $cloneHub
        $script:RunnerDir = Join-Path $cloneHub 'runner'
        $script:ConfigDir = Join-Path $cloneHub 'config'
        $script:StateDir = Join-Path $cloneHub 'state'
        $script:LogDir = Join-Path $cloneHub 'logs'
        foreach ($dir in @($script:ConfigDir, $script:StateDir, $script:LogDir)) {
            if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        }
    }
} else {
    throw ('hub scripts missing in the clone: ' + $cloneHub)
}

if (-not $Branch) {
    $current = Invoke-Git -Repo $RepoPath -GitArgs @('rev-parse', '--abbrev-ref', 'HEAD')
    $Branch = $current.Output
    if (-not $Branch -or $Branch -eq 'HEAD') { $Branch = 'main' }
}
Write-Ok ('branch: ' + $Branch)

if (-not $WslWorkDir) {
    $WslWorkDir = '/mnt/f/cgmd/runs'
}

# --- 2. credentials (repository local only) --------------------------------
Write-Step 'Git credentials (repository-local, no global config is touched)'

if ($SkipCredentials) {
    Write-Warn 'skipped (-SkipCredentials)'
} else {
    $credFile = Join-Path $script:StateDir 'git-credentials'
    $userEmail = $GitHubEmail
    if (-not $userEmail) { $userEmail = ($GitHubUser + '@users.noreply.github.com') }

    Invoke-Git -Repo $RepoPath -GitArgs @('config', 'user.name', $GitHubUser) | Out-Null
    Invoke-Git -Repo $RepoPath -GitArgs @('config', 'user.email', $userEmail) | Out-Null
    Write-Ok ('identity: {0} <{1}> (local to this clone)' -f $GitHubUser, $userEmail)

    $remoteCheck = Invoke-Git -Repo $RepoPath -GitArgs @('ls-remote', '--heads', 'origin', $Branch) -AllowFail
    $needToken = ($remoteCheck.Code -ne 0)

    if ($needToken -and -not $GitHubToken) {
        Write-Host '  A GitHub personal access token is needed once to push results back.' -ForegroundColor Yellow
        Write-Host '  Create one (scope: repo) at https://github.com/settings/tokens' -ForegroundColor Yellow
        $secure = Read-Host -AsSecureString ('  Paste token for ' + $GitHubUser)
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $GitHubToken = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        } finally {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }

    if ($GitHubToken) {
        $line = ('https://{0}:{1}@github.com' -f $GitHubUser, $GitHubToken)
        [System.IO.File]::WriteAllText($credFile, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        $aclOk = Set-RestrictedAcl -Path $credFile
        if ($aclOk) { Write-Ok 'credential file written with a restricted ACL' } else { Write-Warn 'credential file written (ACL hardening unavailable)' }
        Invoke-Git -Repo $RepoPath -GitArgs @('config', 'credential.helper', ('store --file=' + $credFile)) | Out-Null
        Write-Ok 'credential.helper set in the repository config only'
    } elseif (-not $needToken) {
        Write-Ok 'existing credentials already work for this remote'
    } else {
        Write-Warn 'no token supplied; pushes will fail until credentials are configured'
    }

    $after = Invoke-Git -Repo $RepoPath -GitArgs @('ls-remote', '--heads', 'origin', $Branch) -AllowFail
    if ($after.Code -eq 0) {
        Write-Ok 'remote reachable (ls-remote ok)'
    } else {
        Write-Warn ('remote still not reachable: ' + $after.Output)
    }
}

# --- 3. WSL2 environment ---------------------------------------------------
Write-Step 'WSL2 environment: GROMACS / CUDA / Martini 3'

if ($SkipWslSetup) {
    Write-Warn 'skipped (-SkipWslSetup)'
} else {
    try {
        $wslRepo = Convert-ToWslPath -WindowsPath $RepoPath
        Write-Ok ('repository visible in WSL at ' + $wslRepo)

        $setupScript = $wslRepo + '/code/cgmd/setup_env.sh'
        $mode = '--check'
        if ($InstallWslDeps) { $mode = '--install --yes' }
        $bash = 'cd ' + $wslRepo + ' && bash code/cgmd/setup_env.sh ' + $mode
        $envOut = & wsl.exe -d $WslDistro -- bash -lc $bash 2>&1
        $envCode = $LASTEXITCODE
        foreach ($line in $envOut) { Write-Host ('    ' + $line) }
        if ($envCode -eq 0) {
            Write-Ok 'WSL environment check passed'
        } else {
            Write-Warn 'WSL environment incomplete (see messages above; rerun with -InstallWslDeps)'
        }
    } catch {
        Write-Warn ('WSL check failed: ' + $_.Exception.Message)
    }
}

# --- 4. hub config ---------------------------------------------------------
Write-Step 'Hub configuration'

$cfgPath = Join-Path $script:ConfigDir 'cgmd_hub.local.json'
$cfg = [ordered]@{
    repo_path         = $RepoPath
    branch            = $Branch
    locked_repo       = $LockedRepo
    github_user       = $GitHubUser
    wsl_distro        = $WslDistro
    wsl_workdir_root  = $WslWorkDir
    run_root          = 'F:\cgmd\runs'
    result_root       = 'F:\cgmd\results'
    f_repo_path       = 'F:\cgmd\0fuye'
    migration_source_dir = 'C:\cgmd\0fuye\skills\cgmd-hub\state'
    legacy_task_name  = 'CGMD-Hub-Poll'
    f_task_name       = 'CGMD-Hub-Poll-F'
    gpu_id            = $GpuId
    ntfy_topic        = $NtfyTopic
    poll_seconds      = $IntervalSeconds
    task_name         = $TaskName
    prune_raw         = $true
    max_frames        = 400
    martini3_dir      = ''
    gmx_binary        = ''
    created_at        = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
}
$json = $cfg | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($cfgPath, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok ('config written: ' + $cfgPath)

$taskFile = Join-Path $RepoPath 'results\status\cgmd_task.json'
if (-not (Test-Path -LiteralPath $taskFile)) {
    $idle = [ordered]@{
        schema     = 'cgmd.task.v1'
        task_id    = 'idle'
        status     = 'idle'
        created_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
        created_by = 'bootstrap_desktop'
        notes      = 'Waiting for a pending task. Any client may write status=pending here.'
    }
    $json = $idle | ConvertTo-Json -Depth 4
    $dir = Split-Path -Parent $taskFile
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($taskFile, $json, (New-Object System.Text.UTF8Encoding($false)))
    Write-Ok 'created an idle results/status/cgmd_task.json'
} else {
    Write-Ok 'task document already present'
}

# --- 5. silent launcher ----------------------------------------------------
Write-Step 'Silent launcher (CGMDHub.exe, /target:winexe)'

$buildScript = Join-Path $script:RunnerDir 'Build-SilentLauncher.ps1'
if (Test-Path -LiteralPath $buildScript) {
    try {
        $exe = & $buildScript
        if ($exe) { Write-Ok ('built ' + $exe) } else { Write-Warn 'csc.exe unavailable; wscript.exe will be used (also windowless)' }
    } catch {
        Write-Warn ('launcher build failed: ' + $_.Exception.Message)
    }
} else {
    Write-Warn 'Build-SilentLauncher.ps1 missing'
}

# --- 6. scheduled task -----------------------------------------------------
Write-Step ('Scheduled task (silent, every ' + $IntervalSeconds + ' s)')

if ($SkipTask) {
    Write-Warn 'skipped (-SkipTask)'
} else {
    $registerScript = Join-Path $script:RunnerDir 'Register-CgmdHubTask.ps1'
    try {
        if ($SkipFirstPoll) {
            & $registerScript -TaskName $TaskName -IntervalSeconds $IntervalSeconds -SkipFirstRun
        } else {
            & $registerScript -TaskName $TaskName -IntervalSeconds $IntervalSeconds
        }
        Write-Ok ('task registered: ' + $TaskName)
    } catch {
        Write-Err ('task registration failed: ' + $_.Exception.Message)
    }
}

# --- 7. validation ---------------------------------------------------------
Write-Step 'Validation'

if (-not $NoBeaconTest) {
    $beaconScript = Join-Path $script:RunnerDir 'Send-CgmdBeacon.ps1'
    if (Test-Path -LiteralPath $beaconScript) {
        try {
            $ok = & $beaconScript -Topic $NtfyTopic -Title '[CGMD] desktop hub online' `
                -Message ("bootstrap complete on {0}`nbranch: {1}`ngpu: {2}`npoll: every {3}s" -f $env:COMPUTERNAME, $Branch, $GpuId, $IntervalSeconds) `
                -Tags @('desktop_computer', 'white_check_mark') -Quiet
            if ($ok) { Write-Ok 'phone beacon sent (check the Xiaomi notification)' } else { Write-Warn 'beacon could not be delivered' }
        } catch {
            Write-Warn ('beacon error: ' + $_.Exception.Message)
        }
    }
}

if (-not $SkipSelfCheck) {
    $selfCheckScript = Join-Path $script:RunnerDir 'Test-CgmdHub.ps1'
    if (Test-Path -LiteralPath $selfCheckScript) {
        & $selfCheckScript -Push
        $selfCheckCode = $LASTEXITCODE
        switch ($selfCheckCode) {
            0 { Write-Ok 'full self-check PASS (report pushed to the branch)' }
            6 { Write-Warn 'full self-check passed with warnings - see results/status/desktop_selfcheck.json' }
            5 { Write-Err 'self-check: origin is not the locked repository' }
            4 { Write-Err 'self-check: hub configuration missing' }
            default { Write-Err ('self-check failed with exit code ' + $selfCheckCode + ' - see results/status/desktop_selfcheck.json') }
        }
    } else {
        Write-Warn 'Test-CgmdHub.ps1 not found, skipping the full self-check'
    }
}

$statePath = Join-Path $script:StateDir 'hub-state.json'
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    Write-Ok ('last poll: ' + $state.last_poll_at + ' (task ' + $state.task_id + ')')
} else {
    Write-Warn ('no heartbeat yet - check ' + (Join-Path $script:LogDir 'hub-*.log') + ' in 30-60 s')
}

# --- summary ---------------------------------------------------------------
Write-Host ''
Write-Host ('=' * 74) -ForegroundColor DarkGray
if ($script:Failures.Count -eq 0) {
    Write-Host '  BOOTSTRAP COMPLETE' -ForegroundColor Green
} else {
    Write-Host ('  BOOTSTRAP FINISHED WITH ' + $script:Failures.Count + ' ISSUE(S)') -ForegroundColor Yellow
    foreach ($failure in $script:Failures) { Write-Host ('   - ' + $failure) -ForegroundColor Yellow }
}
Write-Host ('=' * 74) -ForegroundColor DarkGray
Write-Host ''
Write-Host '  Next steps'
Write-Host '  ----------'
Write-Host ('  1. Watch the hub:      Get-Content "' + (Join-Path $script:LogDir 'hub-*.log') + '" -Tail 20 -Wait')
Write-Host '  2. Queue a task:       edit results\status\cgmd_task.json (status = pending) and push'
Write-Host  '  3. Phone beacon test:  python3 code/federation/node_agent.py test'
Write-Host ('  4. Self-check again:   pwsh/powershell -File ' + (Join-Path $script:RunnerDir 'Test-CgmdHub.ps1') + ' -Push -Notify')
Write-Host ('  5. Remove the task:    ' + (Join-Path $script:RunnerDir 'Unregister-CgmdHubTask.ps1'))
Write-Host ''
Write-Host ('  Log file: ' + $script:BootstrapLog)
Write-Host ''
