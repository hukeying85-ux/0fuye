#Requires -Version 5.1
<#
.SYNOPSIS
    Run the 100 ps GROMACS smoke test right now, print the version inventory and
    push the report to the branch.

.DESCRIPTION
    This is the manual escape hatch for the scheduled poller.  It

      1. optionally clears a stale poll lock and stale poll processes;
      2. resolves the WSL2 distribution (config first, then whatever wsl -l -q
         reports, so a wrong wsl_distro in the config cannot block the test);
      3. runs `python3 -m cgmd.smoke --ps 100` inside WSL2, streaming stdout so
         the operator sees GROMACS complain in real time;
      4. prints the reduced report (gmx version, precision, SIMD, GPU, python
         packages, ns/day) from results/status/gmx_smoke.json;
      5. commits and pushes that report unless -NoPush is given.

    The simulation itself is a 3 nm Martini 3 water box (216 W beads):
    steepest-descent minimisation then 5000 steps x 0.02 ps = 100 ps.

.PARAMETER ConfigPath
    Explicit hub config; defaults to config/cgmd_hub.local.json then the
    template config/cgmd_hub.json.

.PARAMETER RepoPath
    Override the clone location recorded in the config.

.PARAMETER Branch
    Override the branch recorded in the config.

.PARAMETER WslDistro
    Force a distribution name instead of resolving one.

.PARAMETER GpuId
    CUDA device handed to mdrun (default from the config).

.PARAMETER Ps
    Picoseconds to integrate, default 100.

.PARAMETER ClearLock
    Delete state/poll.lock and stop stale poller processes before running.

.PARAMETER Native
    Use the Windows build of GROMACS instead of WSL2: delegates to
    Run-Gmx-Native.ps1 (stock oplsaa.ff + SPC water, no Python, no Martini
    files).  Use this when `gmx.exe --version` works in PowerShell.

.PARAMETER NoPush
    Keep the report local.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Run-Smoke.ps1 -ClearLock

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Run-Smoke.ps1 -Ps 100 -WslDistro Ubuntu
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = '',
    [string]$RepoPath = '',
    [string]$Branch = '',
    [string]$WslDistro = '',
    [int]$GpuId = -1,
    [double]$Ps = 100,
    [switch]$ClearLock,
    [switch]$Native,
    [switch]$NoPush
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StateDir = Join-Path $script:HubRoot 'state'
$script:LogDir = Join-Path $script:HubRoot 'logs'

function Say {
    param([string]$Message, [string]$Colour = 'Gray')
    Write-Host $Message -ForegroundColor $Colour
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

function Read-TextSafely {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -eq 0) { return '' }
    $nul = 0
    $probe = [math]::Min($bytes.Length, 400)
    for ($i = 0; $i -lt $probe; $i++) { if ($bytes[$i] -eq 0) { $nul++ } }
    if ($nul -gt ($probe / 4)) { return ([System.Text.Encoding]::Unicode.GetString($bytes)).Trim() }
    return ([System.Text.Encoding]::UTF8.GetString($bytes)).Trim()
}

function Get-WslExe {
    $candidate = Join-Path $env:SystemRoot 'System32\wsl.exe'
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    $cmd = Get-Command 'wsl.exe' -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    return ''
}

function Invoke-WslRaw {
    param([string]$Arguments, [int]$TimeoutSeconds = 60)
    $exe = Get-WslExe
    if (-not $exe) { return [pscustomobject]@{ Code = -1; Out = ''; Err = 'wsl.exe not found' } }
    $stamp = [guid]::NewGuid().ToString('N').Substring(0, 8)
    $outFile = Join-Path $script:StateDir ('smoke-' + $stamp + '.out')
    $errFile = Join-Path $script:StateDir ('smoke-' + $stamp + '.err')
    try {
        $proc = Start-Process -FilePath $exe -ArgumentList $Arguments -NoNewWindow -PassThru `
            -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            & taskkill.exe /F /T /PID $proc.Id 2>&1 | Out-Null
            return [pscustomobject]@{ Code = -1; Out = (Read-TextSafely -Path $outFile); Err = 'timed out' }
        }
        return [pscustomobject]@{ Code = $proc.ExitCode; Out = (Read-TextSafely -Path $outFile); Err = (Read-TextSafely -Path $errFile) }
    } finally {
        foreach ($path in @($outFile, $errFile)) {
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
        }
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
$configuredDistro = $WslDistro
if (-not $configuredDistro) { $configuredDistro = Get-Property $cfg 'wsl_distro' 'Ubuntu' }
$gpuId = Get-Property $cfg 'gpu_id' 0
if ($GpuId -ge 0) { $gpuId = $GpuId }
$lockedRepo = Get-Property $cfg 'locked_repo' 'hukeying85-ux/0fuye'

if ($Native) {
    $nativeScript = Join-Path $PSScriptRoot 'Run-Gmx-Native.ps1'
    if (-not (Test-Path -LiteralPath $nativeScript)) {
        Write-Host '  [fail] Run-Gmx-Native.ps1 is missing from this clone' -ForegroundColor Red
        exit 7
    }
    $nativeArgs = @('-Ps', $Ps)
    if ($NoPush) { $nativeArgs += '-NoPush' }
    if ($GpuId -ge 0) { $nativeArgs += @('-GpuId', $GpuId) }
    & $nativeScript @nativeArgs
    exit $LASTEXITCODE
}

Say ''
Say '  CGMD-Engine - manual 100 ps GROMACS smoke test' 'White'
Say ('  repo  : ' + $repo)
Say ('  branch: ' + $branch)
Say ('  distro: ' + $configuredDistro + ' (will fall back to whatever wsl reports)')
Say ''

if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    Say ('  [fail] no git clone at ' + $repo) 'Red'
    exit 4
}
$remote = Invoke-Git -Repo $repo -GitArgs @('remote', 'get-url', 'origin')
if ($remote.Output -notmatch [regex]::Escape($lockedRepo)) {
    Say ('  [fail] origin is ' + $remote.Output + ', expected ' + $lockedRepo) 'Red'
    exit 5
}

# ---------------------------------------------------------------------------
# optional: clear a wedged poller
# ---------------------------------------------------------------------------
if ($ClearLock) {
    $lock = Join-Path $script:StateDir 'poll.lock'
    if (Test-Path -LiteralPath $lock) {
        try { Remove-Item -LiteralPath $lock -Force; Say '  [ok] stale poll.lock removed' 'Green' }
        catch { Say ('  [warn] could not remove poll.lock: ' + $_.Exception.Message) 'Yellow' }
    }
    $victims = @(Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'Invoke-CgmdPoll|Sync-Desktop' })
    foreach ($victim in $victims) {
        try {
            Stop-Process -Id $victim.ProcessId -Force -ErrorAction Stop
            Say ('  [ok] stopped stale poll pid ' + $victim.ProcessId) 'Green'
        } catch { }
    }
    if ($victims.Count -eq 0) { Say '  [ok] no stale poll process found' 'DarkGray' }
}

# ---------------------------------------------------------------------------
# resolve a working distro
# ---------------------------------------------------------------------------
$candidates = @($configuredDistro)
$listing = Invoke-WslRaw -Arguments '-l -q' -TimeoutSeconds 30
foreach ($line in ($listing.Out -split "`r?`n")) {
    $name = ($line -replace "`0", '').Trim()
    if ($name -and ($candidates -notcontains $name)) { $candidates += $name }
}

$wslRepo = $null
$distro = $null
foreach ($candidate in $candidates) {
    # wslpath needs the Windows path verbatim; it travels inside double quotes
    # so the spaces in "C:\cgmd\0fuye" survive the command line re-parse.
    $probe = Invoke-WslRaw -Arguments ('-d ' + $candidate + ' -- wslpath -a "' + $repo + '"') -TimeoutSeconds 45
    $value = ($probe.Out -split "`r?`n" | Where-Object { $_ -and $_ -match '/' } | Select-Object -First 1)
    if ($value) {
        $wslRepo = $value.Trim()
        $distro = $candidate
        break
    }
}
if (-not $wslRepo) {
    Say ('  [fail] no WSL distro could resolve the repository path (tried: ' + ($candidates -join ', ') + ')') 'Red'
    Say '         check with: wsl -l -v' 'DarkGray'
    exit 7
}
Say ('  [ok] using distro ' + $distro + ' -> ' + $wslRepo) 'Green'

# ---------------------------------------------------------------------------
# run the smoke test in WSL2 (streaming to the console)
# ---------------------------------------------------------------------------
$work = '~/cgmd-runs/smoke-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$inner = 'cd "' + $wslRepo + '" && export PYTHONPATH="' + $wslRepo + ':' + $wslRepo + '/code/cgmd" PYTHONIOENCODING=utf-8 && ' +
         'python3 -m cgmd.smoke --ps ' + $Ps + ' --gpu-id ' + $gpuId + ' --workdir "' + $work + '" ' +
         '--out results/status/gmx_smoke.json --timeout 900 < /dev/null'
$argumentLine = '-d ' + $distro + ' -- bash -lc "' + $inner.Replace('"', '\"') + '"'

Say ''
Say '  running (this is the real GROMACS run, ~10-60 s)' 'Cyan'
Say ''
$exe = Get-WslExe
$started = Get-Date
$proc = Start-Process -FilePath $exe -ArgumentList $argumentLine -NoNewWindow -PassThru
[void]$proc.WaitForExit(1500000)
$code = $proc.ExitCode
Say ''
Say ('  exit code ' + $code + ' after ' + [math]::Round(((Get-Date) - $started).TotalSeconds, 1) + ' s')

# ---------------------------------------------------------------------------
# show the report
# ---------------------------------------------------------------------------
$reportPath = Join-Path (Join-Path (Join-Path $repo 'results') 'status') 'gmx_smoke.json'
$report = Read-JsonFile -Path $reportPath
if ($null -eq $report) {
    Say ''
    Say '  [fail] no report produced - the failure is above' 'Red'
    Say '         common causes: gmx not on PATH (sudo apt install gromacs), or python3 < 3.6' 'DarkGray'
    exit 7
}

$software = Get-Property $report 'software' $null
$gromacs = Get-Property $software 'gromacs' $null
Say ''
Say ('=' * 74) -ForegroundColor DarkGray
Say ('  {0} - {1} ps integrated' -f (Get-Property $report 'status' '?').ToUpper(), (Get-Property $report 'ps_completed' 0)) `
    -ForegroundColor $(if ((Get-Property $report 'ok' $false)) { 'Green' } else { 'Red' })
Say ('=' * 74) -ForegroundColor DarkGray
Say ('  gromacs        : ' + (Get-Property $gromacs 'version' 'not found'))
Say ('  executable     : ' + (Get-Property $gromacs 'executable' 'n/a'))
Say ('  precision      : ' + (Get-Property $gromacs 'precision' 'n/a'))
Say ('  simd           : ' + (Get-Property $gromacs 'simd' 'n/a'))
Say ('  gpu support    : ' + (Get-Property $gromacs 'gpu_support' 'n/a'))
Say ('  cuda runtime   : ' + (Get-Property $gromacs 'cuda_runtime' 'n/a'))
Say ('  fft            : ' + (Get-Property $gromacs 'fft' 'n/a'))
$packages = Get-Property $software 'packages' $null
if ($null -ne $packages) {
    foreach ($property in $packages.PSObject.Properties) {
        Say ('  {0,-14} : {1}' -f $property.Name, $property.Value)
    }
}
Say ('  martini3       : ' + (Get-Property $software 'martini3_dir' 'not found'))
$mdrun = Get-Property $report 'mdrun' $null
Say ('  ns/day         : ' + (Get-Property $mdrun 'performance_ns_per_day' 'n/a'))
Say ('  accelerator    : ' + (Get-Property $report 'accelerator' 'n/a'))
$errorText = Get-Property $report 'stage_error' ''
if ($errorText) { Say ('  stage error    : ' + $errorText) 'Red' }
Say ''

# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------
if (-not $NoPush) {
    $null = Invoke-Git -Repo $repo -GitArgs @('add', '-A', '--', 'results/status/gmx_smoke.json')
    $status = Invoke-Git -Repo $repo -GitArgs @('status', '--porcelain')
    if ($status.Output) {
        $commit = Invoke-Git -Repo $repo -GitArgs @('commit', '-m', ('smoke: gmx {0} - {1} ps [{2}]' -f (Get-Property $gromacs 'version' '?'), (Get-Property $report 'ps_completed' 0), $env:COMPUTERNAME))
        if ($commit.Code -eq 0) {
            for ($attempt = 1; $attempt -le 3; $attempt++) {
                $push = Invoke-Git -Repo $repo -GitArgs @('push', 'origin', ('HEAD:' + $branch))
                if ($push.Code -eq 0) { Say ('  [ok] report pushed to origin/' + $branch) 'Green'; break }
                $pull = Invoke-Git -Repo $repo -GitArgs @('pull', '--rebase', '--autostash', 'origin', $branch)
                if ($pull.Code -ne 0) { Say ('  [warn] push failed: ' + $push.Output) 'Yellow'; break }
            }
        } else {
            Say ('  [warn] commit failed: ' + $commit.Output) 'Yellow'
        }
    } else {
        Say '  [ok] report unchanged, nothing to push' 'DarkGray'
    }
}

Say ('  report: ' + $reportPath)
Say ''
if ((Get-Property $report 'ok' $false)) { exit 0 }
exit 3
