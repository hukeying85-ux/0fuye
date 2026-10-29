#Requires -Version 5.1
<#
.SYNOPSIS
    One-shot self-check of the CGMD desktop hub, with a machine-readable report
    that is pushed back into the repository.

.DESCRIPTION
    Run this on the workstation whenever you want to know whether the desktop is
    really able to take a simulation task.  It prints a compact table and writes

        results/status/desktop_selfcheck.json      (schema cgmd.selfcheck.v1)

    so that the phone, the Arena agent and any other client can read the result
    straight out of git.  With -Push the report is committed and pushed to the
    configured branch; with -Notify a phone beacon summarises the outcome.

    Checks performed:

        repo      clone exists and is a git work tree
        origin    origin is the locked repository (hukeying85-ux/0fuye)
        branch    branch exists locally and tracks origin without divergence
        creds     repository-local git identity / credential helper present
        wsl       the configured WSL2 distribution starts and answers
        gpu       nvidia-smi sees a CUDA device inside WSL2
        gromacs   gmx runs and was built with GPU support CUDA
        martini3  martini_v3.0.0.itp is discoverable
        python    vermouth / insane / MDAnalysis / matplotlib import
        tools     martinize2 and insane are on PATH inside the distro
        disk      free space for trajectories in the WSL home
        launcher  CGMDHub.exe (/target:winexe) has been compiled
        task      the silent poll task is registered and reported its last run
        beacon    the ntfy topic accepts a POST

    Exit codes:  0 all pass | 6 warnings only | 7 at least one failure |
                 5 origin lock violation | 4 configuration missing.

    Every .ps1 file in this hub is pure ASCII on purpose so that Windows
    PowerShell 5.1 in a non-UTF8 code page can never mis-parse it.

.PARAMETER ConfigPath
    Explicit hub config; defaults to config/cgmd_hub.local.json then
    config/cgmd_hub.json.

.PARAMETER RepoPath
    Override the clone location recorded in the config.

.PARAMETER Branch
    Override the branch recorded in the config.

.PARAMETER WslDistro
    Override the WSL2 distribution recorded in the config.

.PARAMETER GpuId
    CUDA device the pipeline will use (only reported, must be 0 or higher).

.PARAMETER NtfyTopic
    Override the phone topic.

.PARAMETER MinFreeGB
    Minimum free gigabytes inside WSL home to accept a microsecond campaign.

.PARAMETER Json
    Print the JSON report instead of the table.

.PARAMETER Push
    Commit and push results/status/desktop_selfcheck.json.

.PARAMETER Notify
    Send a phone beacon with the verdict.

.PARAMETER NoRemote
    Skip the network probes (git fetch, ntfy POST).

.PARAMETER Quiet
    Do not print the table (used when the poller calls this script).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Test-CgmdHub.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Test-CgmdHub.ps1 -Push -Notify
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = '',
    [string]$RepoPath = '',
    [string]$Branch = '',
    [string]$WslDistro = '',
    [int]$GpuId = -1,
    [string]$NtfyTopic = '',
    [double]$MinFreeGB = 20,
    [int]$TimeoutSeconds = 180,
    [switch]$Json,
    [switch]$Push,
    [switch]$Notify,
    [switch]$NoRemote,
    [switch]$Quiet
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StateDir = Join-Path $script:HubRoot 'state'
$script:Checks = New-Object System.Collections.ArrayList
$script:StartedAt = Get-Date
if ($Json) { $Quiet = $true }

if (-not (Test-Path -LiteralPath $script:StateDir)) {
    New-Item -ItemType Directory -Path $script:StateDir -Force | Out-Null
}

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
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
        return ($raw | ConvertFrom-Json)
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

function Add-Check {
    param(
        [string]$Id,
        [string]$Title,
        [string]$Status,
        [string]$Detail,
        [double]$Seconds = 0
    )
    $entry = [pscustomobject]@{
        id      = $Id
        title   = $Title
        status  = $Status
        detail  = $Detail
        seconds = [math]::Round($Seconds, 2)
    }
    [void]$script:Checks.Add($entry)
    if (-not $Quiet) {
        $colour = 'Gray'
        if ($Status -eq 'pass') { $colour = 'Green' }
        if ($Status -eq 'warn') { $colour = 'Yellow' }
        if ($Status -eq 'fail') { $colour = 'Red' }
        Write-Host ('  [{0}] {1,-9} {2,-14} {3}' -f $Status, $Id, $Title, $Detail) -ForegroundColor $colour
    }
}

function Invoke-Git {
    param([string]$Repo, [string[]]$GitArgs)
    $all = @()
    if ($Repo) { $all += @('-C', $Repo) }
    $all += $GitArgs
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

function Get-WslExe {
    $candidate = Join-Path $env:SystemRoot 'System32\wsl.exe'
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    $cmd = Get-Command 'wsl.exe' -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    return ''
}

function Invoke-WslProbe {
    param([string]$Distro, [string]$ScriptText, [int]$TimeoutSeconds = 120)
    $exe = Get-WslExe
    if (-not $exe) { return $null }
    $bytes = [System.Text.Encoding]::ASCII.GetBytes($ScriptText)
    $payload = [Convert]::ToBase64String($bytes)
    $inner = 'echo ' + $payload + ' | base64 -d | bash'
    # cmd.exe/wsl.exe re-parse the command line, so the bash payload is wrapped
    # in double quotes; the payload itself is base64 and holds no quote at all.
    $argumentLine = '-d ' + $Distro + ' -- bash -lc "' + $inner + '"'
    $outFile = Join-Path $script:StateDir 'wsl-probe.out'
    $errFile = Join-Path $script:StateDir 'wsl-probe.err'
    try {
        $proc = Start-Process -FilePath $exe -ArgumentList $argumentLine -NoNewWindow -PassThru `
            -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            & taskkill.exe /F /T /PID $proc.Id 2>&1 | Out-Null
            return [pscustomobject]@{ Code = -1; Lines = @(); Error = 'probe timed out' }
        }
        $lines = @()
        if (Test-Path -LiteralPath $outFile) {
            $lines = [System.IO.File]::ReadAllLines($outFile, [System.Text.Encoding]::UTF8)
        }
        $errorText = ''
        if (Test-Path -LiteralPath $errFile) {
            $errorText = ([System.IO.File]::ReadAllText($errFile, [System.Text.Encoding]::UTF8)).Trim()
        }
        return [pscustomobject]@{ Code = $proc.ExitCode; Lines = $lines; Error = $errorText }
    } catch {
        return [pscustomobject]@{ Code = -1; Lines = @(); Error = $_.Exception.Message }
    } finally {
        foreach ($path in @($outFile, $errFile)) {
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
        }
    }
}

function ConvertFrom-ProbeLines {
    param($Lines)
    $map = @{}
    foreach ($line in $Lines) {
        if ($null -eq $line) { continue }
        $text = [string]$line
        $index = $text.IndexOf('=')
        if ($index -le 0) { continue }
        $key = $text.Substring(0, $index).Trim()
        $value = $text.Substring($index + 1).Trim()
        if ($key) { $map[$key] = $value }
    }
    return $map
}

function Send-SelfCheckBeacon {
    param([string]$Title, [string]$Message, [string]$Topic, [string[]]$Tags = @('desktop_computer'))
    if (-not $Topic) { return $false }
    $beacon = Join-Path $PSScriptRoot 'Send-CgmdBeacon.ps1'
    if (Test-Path -LiteralPath $beacon) {
        try {
            return [bool](& $beacon -Topic $Topic -Title $Title -Message $Message -Tags $Tags -Quiet)
        } catch {
            return $false
        }
    }
    try {
        $body = @{ topic = $Topic; title = $Title; message = $Message; priority = 4; tags = $Tags } | ConvertTo-Json -Depth 4
        $null = Invoke-RestMethod -Uri 'https://ntfy.sh' -Method Post -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
            -ContentType 'application/json' -TimeoutSec 15
        return $true
    } catch {
        return $false
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

if (-not $Quiet) {
    Write-Host ''
    Write-Host '  CGMD-Engine - desktop self-check' -ForegroundColor White
    Write-Host ('  config: ' + $(if ($cfgPath) { $cfgPath } else { '(none)' })) -ForegroundColor DarkGray
    Write-Host ('  time  : ' + (Get-BeijingStamp)) -ForegroundColor DarkGray
    Write-Host ''
}

if ($null -eq $cfg) {
    Add-Check 'repo' 'repository clone' 'fail' 'no config/cgmd_hub.local.json; run bootstrap_desktop.ps1 first'
    $report = [pscustomobject]@{
        schema     = 'cgmd.selfcheck.v1'
        checked_at = Get-BeijingStamp
        overall    = 'fail'
        config     = ''
        checks     = @($script:Checks)
        exit_code  = 4
    }
    if ($Json) { $report | ConvertTo-Json -Depth 8 }
    exit 4
}

$repo = $RepoPath
if (-not $repo) { $repo = Get-Property $cfg 'repo_path' 'C:\cgmd\0fuye' }
$branch = $Branch
if (-not $branch) { $branch = Get-Property $cfg 'branch' 'main' }
$distro = $WslDistro
if (-not $distro) { $distro = Get-Property $cfg 'wsl_distro' 'Ubuntu' }
if (-not $NtfyTopic) { $NtfyTopic = Get-Property $cfg 'ntfy_topic' 'arena-beacon-95bc796a66' }
$lockedRepo = Get-Property $cfg 'locked_repo' 'hukeying85-ux/0fuye'
$gpuId = Get-Property $cfg 'gpu_id' 0
if ($GpuId -ge 0) { $gpuId = $GpuId }
$wslWork = Get-Property $cfg 'wsl_workdir_root' '~/cgmd-runs'
$taskName = Get-Property $cfg 'task_name' 'CGMD-Hub-Poll'

# ---------------------------------------------------------------------------
# 1. repository
# ---------------------------------------------------------------------------
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$repoOk = $false
$gitPresent = $null -ne (Get-Command 'git' -ErrorAction SilentlyContinue)
if (-not $gitPresent) {
    Add-Check 'repo' 'repository clone' 'fail' 'git is not on PATH; install Git for Windows'
} elseif ($repo -and (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    $repoOk = $true
    Add-Check 'repo' 'repository clone' 'pass' $repo
} elseif ($repo -and (Test-Path -LiteralPath $repo)) {
    Add-Check 'repo' 'repository clone' 'fail' ('directory exists but is not a git clone: ' + $repo)
} else {
    Add-Check 'repo' 'repository clone' 'fail' ('missing: ' + $repo)
}
$sw.Stop()
$script:Checks[$script:Checks.Count - 1].seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)

# ---------------------------------------------------------------------------
# 2. origin lock
# ---------------------------------------------------------------------------
$originOk = $false
if ($repoOk) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $remote = Invoke-Git -Repo $repo -GitArgs @('remote', 'get-url', 'origin')
    if ($remote.Code -ne 0) {
        Add-Check 'origin' 'origin lock' 'fail' 'origin remote is not configured'
    } elseif ($remote.Output -notmatch [regex]::Escape($lockedRepo)) {
        Add-Check 'origin' 'origin lock' 'fail' ('origin is ' + $remote.Output + ', expected ' + $lockedRepo)
    } else {
        $originOk = $true
        Add-Check 'origin' 'origin lock' 'pass' $remote.Output
    }
    $sw.Stop()
    $script:Checks[$script:Checks.Count - 1].seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
}

# ---------------------------------------------------------------------------
# 3. branch synchronisation
# ---------------------------------------------------------------------------
if ($repoOk -and $originOk) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $head = Invoke-Git -Repo $repo -GitArgs @('rev-parse', '--abbrev-ref', 'HEAD')
    $current = $head.Output
    $sha = (Invoke-Git -Repo $repo -GitArgs @('rev-parse', '--short', 'HEAD')).Output
    if (-not $NoRemote) {
        $null = Invoke-Git -Repo $repo -GitArgs @('fetch', '--quiet', 'origin', $branch)
    }
    $ahead = '0'
    $behind = '0'
    $counts = Invoke-Git -Repo $repo -GitArgs @('rev-list', '--left-right', '--count', ('HEAD...origin/' + $branch))
    if ($counts.Code -eq 0 -and $counts.Output) {
        $parts = $counts.Output -split '\s+'
        if ($parts.Count -ge 2) { $ahead = $parts[0]; $behind = $parts[1] }
    }
    $detail = ('{0} @ {1} (ahead {2}, behind {3})' -f $current, $sha, $ahead, $behind)
    if ($current -ne $branch) {
        Add-Check 'branch' 'branch synchronisation' 'warn' ($detail + ' | configured branch is ' + $branch)
    } elseif ($behind -ne '0') {
        Add-Check 'branch' 'branch synchronisation' 'warn' ($detail + ' | run a poll to fast-forward')
    } else {
        Add-Check 'branch' 'branch synchronisation' 'pass' $detail
    }
    $sw.Stop()
    $script:Checks[$script:Checks.Count - 1].seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
}

# ---------------------------------------------------------------------------
# 4. repository-local credentials
# ---------------------------------------------------------------------------
if ($repoOk) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $name = (Invoke-Git -Repo $repo -GitArgs @('config', '--local', 'user.name')).Output
    $helper = (Invoke-Git -Repo $repo -GitArgs @('config', '--local', 'credential.helper')).Output
    if ($name -and $helper) {
        Add-Check 'creds' 'git credentials' 'pass' ($name + ' / ' + $helper)
    } elseif ($name -or $helper) {
        Add-Check 'creds' 'git credentials' 'warn' ('partial: user.name=' + $name + ' credential.helper=' + $helper)
    } else {
        Add-Check 'creds' 'git credentials' 'warn' 'no repository-local identity; a push will prompt for credentials'
    }
    $sw.Stop()
    $script:Checks[$script:Checks.Count - 1].seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
}

# ---------------------------------------------------------------------------
# 5. WSL2 probe (single round trip, base64 transferred)
# ---------------------------------------------------------------------------
$probeScript = @'
set +e
echo "WSL_OK=1"
echo "OS=$(. /etc/os-release 2>/dev/null; echo $PRETTY_NAME)"
echo "NPROC=$(nproc 2>/dev/null)"
echo "MEM_GB=$(awk '/MemTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo 2>/dev/null)"
echo "HOME=$HOME"
NVIDIA=""
if command -v nvidia-smi >/dev/null 2>&1; then
    NVIDIA=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)
fi
echo "NVIDIA=$NVIDIA"
GMX_BIN=$(command -v gmx 2>/dev/null)
echo "GMX_BIN=$GMX_BIN"
GMX_VERSION=""
GMX_CUDA=0
if [ -n "$GMX_BIN" ]; then
    GMX_OUT=$(gmx --version 2>&1)
    GMX_VERSION=$(echo "$GMX_OUT" | sed -n 's/^GROMACS version:[[:space:]]*//p' | head -1)
    GMX_CUDA=$(echo "$GMX_OUT" | grep -c "GPU support: CUDA")
fi
echo "GMX_VERSION=$GMX_VERSION"
echo "GMX_CUDA=$GMX_CUDA"
echo "PY_BIN=$(command -v python3 2>/dev/null)"
echo "PY_VER=$(python3 -c 'import platform; print(platform.python_version())' 2>/dev/null)"
echo "MOD_VERMOUTH=$(python3 -c 'import vermouth; print(getattr(vermouth, "__version__", "0"))' 2>/dev/null)"
echo "MOD_INSANE=$(python3 -c 'import insane; print("ok")' 2>/dev/null)"
echo "MOD_MDANALYSIS=$(python3 -c 'import MDAnalysis; print(MDAnalysis.__version__)' 2>/dev/null)"
echo "MOD_MATPLOTLIB=$(python3 -c 'import matplotlib; print(matplotlib.__version__)' 2>/dev/null)"
echo "BIN_MARTINIZE2=$(command -v martinize2 2>/dev/null)"
echo "BIN_INSANE=$(command -v insane 2>/dev/null)"
M3=""
for cand in "$CGMD_MARTINI3_DIR" "$HOME/martini3" "$HOME/martini3/martini_v3.0.0" "$HOME/gmx_files/martini3" /usr/share/gromacs/top/martini3 /usr/local/share/gromacs/top/martini3; do
    if [ -n "$cand" ] && [ -f "$cand/martini_v3.0.0.itp" ]; then M3="$cand"; break; fi
done
echo "M3_DIR=$M3"
echo "DISK_GB=$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2 {printf "%.1f", $4/1048576}')"
echo "PROBE_DONE=1"
'@

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$probeResult = Invoke-WslProbe -Distro $distro -ScriptText $probeScript -TimeoutSeconds $TimeoutSeconds
$sw.Stop()
$probeSeconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
$probe = @{}
if ($null -eq $probeResult) {
    Add-Check 'wsl' 'WSL2 distro' 'fail' 'wsl.exe not found; install WSL2 (wsl --install -d Ubuntu)'
} elseif ($probeResult.Code -ne 0 -or $probeResult.Lines.Count -eq 0) {
    $why = $probeResult.Error
    if (-not $why) { $why = 'no output' }
    Add-Check 'wsl' 'WSL2 distro' 'fail' ('distro ' + $distro + ' did not answer: ' + $why)
} else {
    $probe = ConvertFrom-ProbeLines -Lines $probeResult.Lines
    if ($probe.ContainsKey('WSL_OK') -and $probe.ContainsKey('PROBE_DONE')) {
        Add-Check 'wsl' 'WSL2 distro' 'pass' ($distro + ' | ' + $probe['OS'] + ' | ' + $probe['NPROC'] + ' cores | ' + $probe['MEM_GB'] + ' GB RAM') $probeSeconds
    } else {
        Add-Check 'wsl' 'WSL2 distro' 'fail' ('probe exited early: ' + $probeResult.Error) $probeSeconds
    }
}

# ---------------------------------------------------------------------------
# 6. GPU / GROMACS / Martini 3 / python / tools / disk  (all from the probe)
# ---------------------------------------------------------------------------
if ($probe.Count -gt 0 -and $probe.ContainsKey('PROBE_DONE')) {
    $nvidia = [string]$probe['NVIDIA']
    if ($nvidia) {
        Add-Check 'gpu' 'CUDA device' 'pass' $nvidia
    } else {
        Add-Check 'gpu' 'CUDA device' 'fail' 'nvidia-smi sees no GPU inside WSL2; install the Windows driver 535+ and reboot'
    }

    $gmxVersion = [string]$probe['GMX_VERSION']
    $gmxCuda = [string]$probe['GMX_CUDA']
    if (-not $gmxVersion) {
        Add-Check 'gromacs' 'GROMACS + CUDA' 'fail' 'gmx not on PATH inside WSL2'
    } elseif ($gmxCuda -ne '1') {
        Add-Check 'gromacs' 'GROMACS + CUDA' 'warn' ('GROMACS ' + $gmxVersion + ' without GPU support; production will run on CPU')
    } else {
        Add-Check 'gromacs' 'GROMACS + CUDA' 'pass' ('GROMACS ' + $gmxVersion + ' (GPU support: CUDA)')
    }

    $m3 = [string]$probe['M3_DIR']
    if ($m3) {
        Add-Check 'martini3' 'Martini 3 force field' 'pass' $m3
    } else {
        Add-Check 'martini3' 'Martini 3 force field' 'warn' 'martini_v3.0.0.itp not found; pip install martini-forcefields or set CGMD_MARTINI3_DIR'
    }

    $missing = @()
    foreach ($pair in @(@('vermouth', 'MOD_VERMOUTH'), @('insane', 'MOD_INSANE'), @('MDAnalysis', 'MOD_MDANALYSIS'), @('matplotlib', 'MOD_MATPLOTLIB'))) {
        $value = [string]$probe[$pair[1]]
        if (-not $value) { $missing += $pair[0] }
    }
    $pyVersion = [string]$probe['PY_VER']
    if (-not $pyVersion) {
        Add-Check 'python' 'python packages' 'fail' 'python3 not found inside WSL2'
    } elseif ($missing.Count -gt 0) {
        Add-Check 'python' 'python packages' 'fail' ('missing: ' + ($missing -join ', ') + ' | bash code/cgmd/setup_env.sh --install --yes')
    } else {
        Add-Check 'python' 'python packages' 'pass' ('python ' + $pyVersion + ' | vermouth ' + $probe['MOD_VERMOUTH'] + ' | MDAnalysis ' + $probe['MOD_MDANALYSIS'] + ' | matplotlib ' + $probe['MOD_MATPLOTLIB'])
    }

    $martinize = [string]$probe['BIN_MARTINIZE2']
    $insaneBin = [string]$probe['BIN_INSANE']
    if ($martinize -and $insaneBin) {
        Add-Check 'tools' 'martinize2 + insane' 'pass' ($martinize + ' | ' + $insaneBin)
    } elseif ($martinize -or $insaneBin) {
        Add-Check 'tools' 'martinize2 + insane' 'warn' ('martinize2=' + $martinize + ' insane=' + $insaneBin)
    } else {
        Add-Check 'tools' 'martinize2 + insane' 'fail' 'neither martinize2 nor insane on PATH'
    }

    $disk = 0.0
    [void][double]::TryParse([string]$probe['DISK_GB'], [ref]$disk)
    if ($disk -le 0) {
        Add-Check 'disk' 'free space' 'warn' 'could not read free space in WSL home'
    } elseif ($disk -lt $MinFreeGB) {
        Add-Check 'disk' 'free space' 'warn' ('{0:N1} GB free in WSL home, a 1 us campaign wants {1:N0} GB+' -f $disk, $MinFreeGB)
    } else {
        Add-Check 'disk' 'free space' 'pass' ('{0:N1} GB free in WSL home (workdir ' + $wslWork + ')' -f $disk)
    }
} else {
    foreach ($id in @(@('gpu', 'CUDA device'), @('gromacs', 'GROMACS + CUDA'), @('martini3', 'Martini 3 force field'), @('python', 'python packages'), @('tools', 'martinize2 + insane'), @('disk', 'free space'))) {
        Add-Check $id[0] $id[1] 'fail' 'skipped: WSL2 probe failed'
    }
}

# ---------------------------------------------------------------------------
# 7. silent launcher
# ---------------------------------------------------------------------------
$launcher = Join-Path (Join-Path $script:HubRoot 'runner') 'CGMDHub.exe'
$launcherSrc = Join-Path (Join-Path $script:HubRoot 'runner') 'SilentLauncher.cs'
if (Test-Path -LiteralPath $launcher) {
    $size = (Get-Item -LiteralPath $launcher).Length
    Add-Check 'launcher' 'silent launcher' 'pass' ('CGMDHub.exe ' + $size + ' bytes')
} elseif (Test-Path -LiteralPath $launcherSrc) {
    Add-Check 'launcher' 'silent launcher' 'fail' 'CGMDHub.exe missing; run runner/Build-SilentLauncher.ps1'
} else {
    Add-Check 'launcher' 'silent launcher' 'fail' 'SilentLauncher.cs missing'
}

# ---------------------------------------------------------------------------
# 8. scheduled task
# ---------------------------------------------------------------------------
$taskCheck = $null
try {
    $taskCheck = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
} catch {
    $taskCheck = $null
}
if ($null -eq $taskCheck) {
    Add-Check 'task' 'poll task' 'fail' ('scheduled task ' + $taskName + ' is not registered')
} else {
    $info = $null
    try { $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction Stop } catch { $info = $null }
    $state = [string]$taskCheck.State
    if ($null -eq $info) {
        Add-Check 'task' 'poll task' 'warn' ('registered, state ' + $state)
    } else {
        $lastRun = [string]$info.LastRunTime
        $lastResult = [string]$info.LastTaskResult
        $detail = ('{0} | state {1} | last run {2} | result {3}' -f $taskName, $state, $lastRun, $lastResult)
        if ($lastResult -eq '0' -or $lastResult -eq '267009' -or $lastResult -eq '267011') {
            Add-Check 'task' 'poll task' 'pass' $detail
        } else {
            Add-Check 'task' 'poll task' 'warn' ($detail + ' | see logs\hub-*.log')
        }
    }
}

# ---------------------------------------------------------------------------
# 9. beacon
# ---------------------------------------------------------------------------
if ($NoRemote) {
    Add-Check 'beacon' 'phone beacon' 'warn' 'skipped (NoRemote)'
} else {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $sent = Send-SelfCheckBeacon -Title '[CGMD] self-check' -Message ('desktop self-check running on ' + $env:COMPUTERNAME) -Topic $NtfyTopic -Tags @('mag')
    $sw.Stop()
    if ($sent) {
        Add-Check 'beacon' 'phone beacon' 'pass' ('POST https://ntfy.sh/' + $NtfyTopic) $sw.Elapsed.TotalSeconds
    } else {
        Add-Check 'beacon' 'phone beacon' 'fail' 'could not POST to ntfy.sh'
    }
}

# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------
$failCount = @($script:Checks | Where-Object { $_.status -eq 'fail' }).Count
$warnCount = @($script:Checks | Where-Object { $_.status -eq 'warn' }).Count
$overall = 'pass'
$exitCode = 0
if ($failCount -gt 0) {
    $overall = 'fail'
    $exitCode = 7
} elseif ($warnCount -gt 0) {
    $overall = 'warn'
    $exitCode = 6
}
if ($repoOk -and -not $originOk) { $exitCode = 5 }

$report = [pscustomobject]@{
    schema     = 'cgmd.selfcheck.v1'
    checked_at = Get-BeijingStamp
    overall    = $overall
    exit_code  = $exitCode
    config     = $cfgPath
    host       = [pscustomobject]@{
        computer   = $env:COMPUTERNAME
        user       = $env:USERNAME
        powershell = [string]$PSVersionTable.PSVersion
        os         = [string](Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
        repo       = $repo
        branch     = $branch
        wsl_distro = $distro
        gpu_id     = $gpuId
    }
    versions   = [pscustomobject]@{
        gromacs    = [string]$probe['GMX_VERSION']
        nvidia     = [string]$probe['NVIDIA']
        python     = [string]$probe['PY_VER']
        vermouth   = [string]$probe['MOD_VERMOUTH']
        mdanalysis = [string]$probe['MOD_MDANALYSIS']
        matplotlib = [string]$probe['MOD_MATPLOTLIB']
        martini3   = [string]$probe['M3_DIR']
    }
    summary    = [pscustomobject]@{
        checks   = $script:Checks.Count
        passed   = @($script:Checks | Where-Object { $_.status -eq 'pass' }).Count
        warnings = $warnCount
        failed   = $failCount
        seconds  = [math]::Round(((Get-Date) - $script:StartedAt).TotalSeconds, 1)
    }
    checks     = @($script:Checks)
}

$repoRoot = $repo
if (-not $repoRoot -or -not (Test-Path -LiteralPath $repoRoot)) { $repoRoot = $script:HubRoot }
$reportPath = Join-Path (Join-Path (Join-Path $repoRoot 'results') 'status') 'desktop_selfcheck.json'
$reportDir = Split-Path -Parent $reportPath
if (-not (Test-Path -LiteralPath $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}
$json = $report | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($reportPath, $json, (New-Object System.Text.UTF8Encoding($false)))
$stateCopy = Join-Path $script:StateDir 'last-selfcheck.json'
[System.IO.File]::WriteAllText($stateCopy, $json, (New-Object System.Text.UTF8Encoding($false)))

if ($Json) {
    Write-Output $json
} elseif (-not $Quiet) {
    Write-Host ''
    Write-Host ('=' * 74) -ForegroundColor DarkGray
    if ($overall -eq 'pass') {
        Write-Host '  SELF-CHECK PASS - this desktop can take a simulation task' -ForegroundColor Green
    } elseif ($overall -eq 'warn') {
        Write-Host ('  SELF-CHECK PASSED WITH ' + $warnCount + ' WARNING(S)') -ForegroundColor Yellow
    } else {
        Write-Host ('  SELF-CHECK FAILED - ' + $failCount + ' check(s) must be fixed') -ForegroundColor Red
    }
    Write-Host ('=' * 74) -ForegroundColor DarkGray
    Write-Host ('  report: ' + $reportPath)
    Write-Host ('  copied: ' + $stateCopy)
    Write-Host ''
}

# ---------------------------------------------------------------------------
# optional publish
# ---------------------------------------------------------------------------
if ($Push -and $repoOk -and $originOk) {
    $rel = 'results/status/desktop_selfcheck.json'
    $null = Invoke-Git -Repo $repo -GitArgs @('add', '-A', '--', $rel)
    $status = Invoke-Git -Repo $repo -GitArgs @('status', '--porcelain')
    if ($status.Output) {
        $message = ('selfcheck: {0} ({1} pass / {2} warn / {3} fail) [{4}]' -f $overall, $report.summary.passed, $report.summary.warnings, $report.summary.failed, $env:COMPUTERNAME)
        $commit = Invoke-Git -Repo $repo -GitArgs @('commit', '-m', $message)
        if ($commit.Code -eq 0) {
            for ($attempt = 1; $attempt -le 3; $attempt++) {
                $pushResult = Invoke-Git -Repo $repo -GitArgs @('push', 'origin', ('HEAD:' + $branch))
                if ($pushResult.Code -eq 0) {
                    if (-not $Quiet) { Write-Host ('  pushed to origin/' + $branch) -ForegroundColor Green }
                    break
                }
                $pull = Invoke-Git -Repo $repo -GitArgs @('pull', '--rebase', '--autostash', 'origin', $branch)
                if ($pull.Code -ne 0) { break }
            }
        } elseif (-not $Quiet) {
            Write-Host ('  commit failed: ' + $commit.Output) -ForegroundColor Yellow
        }
    } elseif (-not $Quiet) {
        Write-Host '  report unchanged, nothing to push' -ForegroundColor DarkGray
    }
}

if ($Notify) {
    $verdict = 'PASS'
    if ($overall -eq 'warn') { $verdict = 'WARN' }
    if ($overall -eq 'fail') { $verdict = 'FAIL' }
    $lines = @()
    $lines += ('{0} on {1}' -f $verdict, $env:COMPUTERNAME)
    $lines += ('pass {0} / warn {1} / fail {2}' -f $report.summary.passed, $report.summary.warnings, $report.summary.failed)
    foreach ($entry in $script:Checks) {
        if ($entry.status -ne 'pass') {
            $lines += ('- ' + $entry.id + ': ' + $entry.detail)
        }
    }
    $tags = @('white_check_mark')
    if ($overall -eq 'warn') { $tags = @('warning') }
    if ($overall -eq 'fail') { $tags = @('rotating_light') }
    $null = Send-SelfCheckBeacon -Title ('[CGMD] self-check ' + $verdict) -Message ($lines -join [Environment]::NewLine) -Topic $NtfyTopic -Tags $tags
}

exit $exitCode
