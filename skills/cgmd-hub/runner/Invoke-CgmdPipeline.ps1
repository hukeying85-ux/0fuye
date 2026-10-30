#Requires -Version 5.1
<#
.SYNOPSIS
    Run the Martini 3 coarse-grained pipeline on the NATIVE Windows side.

.DESCRIPTION
    This is the engine behind the mailbox / LAN-bridge job kind ``pipeline``.
    It never touches WSL: it finds a native CPython (3.12 preferred), the
    native gmx.exe of the workstation and runs

        python -m cgmd.cli run --sequence ... --workdir ... --output ...

    which performs the whole chain: sequence -> structure -> martinize2 ->
    insane -> flat Martini 3 topology -> index -> EM -> NPT equilibration ->
    production -> analysis -> summary_metrics.json + SVG figures.

    Everything heavy (top/gro/tpr/xtc/edr/cpt) stays under
    ``skills/cgmd-hub/state/cgmd-runs/<task>`` which .gitignore excludes; only
    the < 1 MB metrics + SVG figures land in ``results/cgmd/<task>`` inside the
    clone, where the poller publishes them.

.PARAMETER Sequence
    One-letter peptide sequence, e.g. GIGKFLHSAKKFGKAFVGEIMNS.

.PARAMETER ProductionNs
    Production length in ns (default 100).

.PARAMETER Maxh
    Wall-clock ceiling per mdrun call in hours.  A positive value makes mdrun
    stop by itself at a step boundary and write a checkpoint, so a job that is
    cut short by a timeout loses nothing: the next call continues with -cpi.

.PARAMETER TimeoutSeconds
    Hard ceiling for the python process (default 5400).

.PARAMETER ResultFile
    Where to write the machine readable result (the mailbox reads this back).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Invoke-CgmdPipeline.ps1 `
        -Sequence GIGKFLHSAKKFGKAFVGEIMNS -ProductionNs 100 -EquilibrationNs 10
#>
[CmdletBinding()]
param(
    [string]$Sequence = '',
    [string]$Name = 'peptide',
    [double]$ProductionNs = 100,
    [double]$EquilibrationNs = 10,
    [double]$BoxXyNm = 0,
    [double]$BoxZNm = 0,
    [double]$SaltM = -1,
    [double]$TemperatureK = 0,
    [string]$Lipids = '',
    [int]$GpuId = 0,
    [double]$Maxh = 0,
    [double]$SegmentNs = 0,
    [int]$TimeoutSeconds = 5400,
    [string]$TaskId = '',
    [string]$WorkDir = '',
    [string]$OutDir = '',
    [string]$Gmx = '',
    [string]$Python = '',
    [string]$Martini3Dir = '',
    [string]$RepoPath = '',
    [string]$ConfigPath = '',
    [string]$ResultFile = '',
    [switch]$Install,
    [switch]$NoFetchForcefield,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StateDir = Join-Path $script:HubRoot 'state'
$script:LogDir = Join-Path $script:HubRoot 'logs'
$script:StartedAt = Get-Date

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

function Write-Say {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    try {
        $file = Join-Path $script:LogDir ('pipeline-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))
        [System.IO.File]::AppendAllText($file, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
    if (-not $Quiet) { Write-Host $line }
}

function Read-JsonFile {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return ($raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Write-JsonFile {
    param([string]$Path, $Data)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, ($Data | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
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
    $candidates = @()
    if ($ConfigPath) { $candidates += $ConfigPath }
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.local.json')
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.json')
    foreach ($candidate in $candidates) {
        $cfg = Read-JsonFile -Path $candidate
        if ($null -ne $cfg) { return $cfg }
    }
    return $null
}

function Invoke-Captured {
    # cmd.exe wrapper: the environment is set inside the .cmd so the parent
    # process is untouched, and %ERRORLEVEL% is echoed into the log because
    # Start-Process -PassThru does not expose ExitCode reliably on PS 5.1.
    param([string]$CommandLine, [string]$OutFile, [int]$TimeoutSeconds = 5400,
          [string]$WorkingDirectory = '', [hashtable]$Environment = @{})
    if (-not $OutFile) {
        $OutFile = Join-Path $script:StateDir ('pipeline-{0}.log' -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
    }
    $cmdFile = [System.IO.Path]::ChangeExtension($OutFile, '.cmd')
    $lines = @('@echo off')
    foreach ($key in $Environment.Keys) {
        $lines += ('set "' + $key + '=' + $Environment[$key] + '"')
    }
    $lines += ($CommandLine + ' > "' + $OutFile + '" 2>&1')
    $lines += ('echo CGMD_EXIT_CODE=%ERRORLEVEL% >> "' + $OutFile + '"')
    [System.IO.File]::WriteAllText($cmdFile, ($lines -join [Environment]::NewLine), [System.Text.Encoding]::ASCII)
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
    if ($match.Success) { return [int]$match.Groups[1].Value }
    if ($text -match 'Fatal error|Traceback') { return 1 }
    return 0
}

function Get-Tail {
    param([string]$Path, [int]$Count = 40)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return @() }
    try {
        return @([System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8) |
                 Where-Object { $_ -ne '' } | Select-Object -Last $Count)
    } catch { return @() }
}

function Get-PythonVersion {
    param([string]$Exe)
    if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) { return $null }
    $out = Join-Path $script:StateDir 'python-version.txt'
    $code = Invoke-Captured -CommandLine ('"' + $Exe + '" -c "import sys;print(sys.version.split()[0])"') `
        -OutFile $out -TimeoutSeconds 60
    if ($code -ne 0) { return $null }
    $match = [regex]::Match((Get-Tail -Path $out -Count 5) -join ' ', '(\d+)\.(\d+)\.(\d+)')
    if (-not $match.Success) { return $null }
    return [pscustomobject]@{ Text = $match.Value; Major = [int]$match.Groups[1].Value; Minor = [int]$match.Groups[2].Value }
}

function Resolve-Python {
    # Native interpreter only.  The workstation has an old 3.6 first on PATH, so
    # every candidate is version checked and 3.12 wins.
    param([string]$Explicit)
    $candidates = @()
    if ($Explicit) { $candidates += $Explicit }
    if ($Python) { $candidates += $Python }
    foreach ($name in @('python3.12.exe', 'python.exe', 'python3.exe')) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found -and $found.Source) { $candidates += $found.Source }
    }
    $bases = @()
    if ($env:LOCALAPPDATA) { $bases += (Join-Path $env:LOCALAPPDATA 'Programs\Python') }
    foreach ($drive in @('C:\', 'D:\', 'F:\')) {
        if (Test-Path -LiteralPath $drive) { $bases += $drive }
    }
    foreach ($base in $bases) {
        foreach ($pattern in @('Python312\python.exe', 'Python31*\python.exe', 'Python3*\python.exe', 'Python\python.exe')) {
            try {
                foreach ($hit in @(Get-ChildItem -Path (Join-Path $base $pattern) -ErrorAction SilentlyContinue)) {
                    $candidates += $hit.FullName
                }
            } catch { }
        }
    }
    $seen = @{}
    $best = $null
    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        $path = [string]$candidate
        if ($seen.ContainsKey($path)) { continue }
        $seen[$path] = $true
        $version = Get-PythonVersion -Exe $path
        if ($null -eq $version) { continue }
        if ($version.Major -lt 3 -or $version.Minor -lt 8) { continue }
        $score = $version.Minor
        if ($version.Major -eq 3 -and $version.Minor -eq 12) { $score = 100 }
        if ($null -eq $best -or $score -gt $best.Score) {
            $best = [pscustomobject]@{ Path = $path; Version = $version.Text; Score = $score }
        }
    }
    return $best
}

function Resolve-Gmx {
    param([string]$Explicit)
    $candidates = @()
    if ($Explicit) { $candidates += $Explicit }
    foreach ($name in @('gmx.exe', 'gmx')) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found -and $found.Source) { $candidates += $found.Source }
    }
    foreach ($pattern in @('F:\gromacs*\gromacs*\bin\gmx.exe', 'F:\gromacs*\bin\gmx.exe',
                           'C:\gromacs*\bin\gmx.exe', 'C:\Program Files\GROMACS*\bin\gmx.exe')) {
        try {
            foreach ($hit in @(Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue)) {
                $candidates += $hit.FullName
            }
        } catch { }
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return [string]$candidate }
    }
    return ''
}

function Resolve-PipScript {
    # <python>\Scripts\<name>.exe for a normal install, <python_dir>\Scripts for
    # a --user install one level up.  Both are checked so a pip --user vermouth
    # is found without touching PATH.
    param([string]$PythonExe, [string]$Name)
    if (-not $PythonExe) { return '' }
    $pythonDir = Split-Path -Parent $PythonExe
    $roots = @($pythonDir, (Split-Path -Parent $pythonDir), (Join-Path $env:APPDATA 'Python'))
    foreach ($root in $roots) {
        if (-not $root) { continue }
        foreach ($pattern in @('Scripts\' + $Name + '.exe', 'Python3*\Scripts\' + $Name + '.exe')) {
            try {
                foreach ($hit in @(Get-ChildItem -Path (Join-Path $root $pattern) -ErrorAction SilentlyContinue)) {
                    return $hit.FullName
                }
            } catch { }
        }
    }
    $found = Get-Command ($Name + '.exe') -ErrorAction SilentlyContinue
    if ($found -and $found.Source) { return $found.Source }
    $found = Get-Command $Name -ErrorAction SilentlyContinue
    if ($found -and $found.Source) { return $found.Source }
    return ''
}

function Test-PythonModule {
    param([string]$PythonExe, [string]$Module)
    $out = Join-Path $script:StateDir ('module-' + $Module + '.txt')
    $code = Invoke-Captured -CommandLine ('"' + $PythonExe + '" -c "import ' + $Module + '"') `
        -OutFile $out -TimeoutSeconds 120
    return ($code -eq 0)
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
$result = [ordered]@{
    schema    = 'cgmd.pipeline.result.v1'
    status    = 'fail'
    summary   = ''
    detail    = [ordered]@{}
    logs_tail = @()
}
$logFile = Join-Path $script:StateDir ('pipeline-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.out')

try {
    $cfg = Get-HubConfig
    if (-not $RepoPath) {
        $RepoPath = [string](Get-Property $cfg 'repo_path' $script:HubRoot)
    }
    if (-not $RepoPath -or -not (Test-Path -LiteralPath $RepoPath)) {
        $RepoPath = Split-Path -Parent (Split-Path -Parent $script:HubRoot)
    }
    if (-not $Sequence) {
        $result['status'] = 'unsupported'
        $result['summary'] = 'pipeline needs a peptide sequence (args.sequence)'
        throw 'no sequence'
    }
    if (-not $TaskId) {
        $TaskId = 'cgmd-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 4))
    }
    if (-not $WorkDir) {
        $WorkDir = Join-Path $script:StateDir ('cgmd-runs\' + $TaskId)
    }
    if (-not $OutDir) {
        $OutDir = Join-Path $RepoPath ('results\cgmd\' + $TaskId)
    }
    foreach ($dir in @($WorkDir, $OutDir)) {
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    }

    $pythonInfo = Resolve-Python -Explicit $Python
    if ($null -eq $pythonInfo) {
        $result['status'] = 'unsupported'
        $result['summary'] = 'no native Python >= 3.8 found (3.12 preferred); install it or pass -Python'
        $result['detail'] = [ordered]@{ repo = $RepoPath; searched = 'PATH, %LOCALAPPDATA%\Programs\Python, C:\Python*' }
        throw 'no python'
    }
    $pythonExe = $pythonInfo.Path
    $gmxExe = Resolve-Gmx -Explicit $Gmx
    if (-not $gmxExe) {
        $result['status'] = 'unsupported'
        $result['summary'] = 'native gmx.exe not found; pass -Gmx or set gmx_binary in the config'
        $result['detail'] = [ordered]@{ python = $pythonExe }
        throw 'no gmx'
    }
    Write-Say ('python {0} ({1}) | gmx {2}' -f $pythonExe, $pythonInfo.Version, $gmxExe)

    $missing = @()
    foreach ($module in @('vermouth', 'insane')) {
        if (-not (Test-PythonModule -PythonExe $pythonExe -Module $module)) { $missing += $module }
    }
    if ($missing.Count -gt 0) {
        if ($Install) {
            Write-Say ('installing python packages: ' + ($missing -join ', '))
            $pipOut = Join-Path $script:StateDir 'pipeline-pip.log'
            $packages = @()
            foreach ($module in $missing) {
                switch ($module) {
                    'vermouth' { $packages += 'vermouth' }
                    'insane'   { $packages += 'insane' }
                }
            }
            $packages += @('MDAnalysis', 'numpy', 'matplotlib')
            $pipLine = '"' + $pythonExe + '" -m pip install --disable-pip-version-check --no-input ' + ($packages -join ' ')
            $pipCode = Invoke-Captured -CommandLine $pipLine -OutFile $pipOut -TimeoutSeconds 1800
            Write-Say ('pip exit ' + $pipCode)
            $missing = @()
            foreach ($module in @('vermouth', 'insane')) {
                if (-not (Test-PythonModule -PythonExe $pythonExe -Module $module)) { $missing += $module }
            }
        }
    }
    if ($missing.Count -gt 0) {
        $result['status'] = 'unsupported'
        $result['summary'] = ('python {0} is missing: {1} (rerun with install=true)' -f $pythonInfo.Version, ($missing -join ', '))
        $result['detail'] = [ordered]@{ python = $pythonExe; version = $pythonInfo.Version; missing = $missing }
        throw 'missing modules'
    }

    $martinizeExe = Resolve-PipScript -PythonExe $pythonExe -Name 'martinize2'
    $insaneExe = Resolve-PipScript -PythonExe $pythonExe -Name 'insane'
    if (-not $martinizeExe) {
        $result['status'] = 'unsupported'
        $result['summary'] = 'martinize2 is not installed for ' + $pythonExe
        throw 'no martinize2'
    }

    $arguments = @(
        '-m', 'cgmd.cli', 'run',
        '--sequence', $Sequence,
        '--name', $Name,
        '--production-ns', ([string]$ProductionNs),
        '--equilibration-ns', ([string]$EquilibrationNs),
        '--gpu-id', ([string]$GpuId),
        '--gmx', ('"' + $gmxExe + '"'),
        '--martinize', ('"' + $martinizeExe + '"'),
        '--workdir', ('"' + $WorkDir + '"'),
        '--output', ('"' + $OutDir + '"'),
        '--no-notify'
    )
    if ($insaneExe) { $arguments += @('--insane', ('"' + $insaneExe + '"')) }
    if ($Lipids) { $arguments += @('--lipids', ('"' + $Lipids + '"')) }
    if ($BoxXyNm -gt 0) { $arguments += @('--box-xy-nm', ([string]$BoxXyNm)) }
    if ($BoxZNm -gt 0) { $arguments += @('--box-z-nm', ([string]$BoxZNm)) }
    if ($SaltM -ge 0) { $arguments += @('--salt-m', ([string]$SaltM)) }
    if ($TemperatureK -gt 0) { $arguments += @('--temperature-k', ([string]$TemperatureK)) }
    if ($Maxh -gt 0) { $arguments += @('--maxh', ([string]$Maxh)) }
    if ($SegmentNs -gt 0) { $arguments += @('--segment-ns', ([string]$SegmentNs)) }
    if ($NoFetchForcefield) { $arguments += @('--no-fetch-ff') }

    $envMap = @{
        PYTHONPATH        = ($RepoPath + ';' + (Join-Path $RepoPath 'code\cgmd'))
        PYTHONIOENCODING  = 'utf-8'
        PYTHONUNBUFFERED  = '1'
    }
    if ($Martini3Dir) { $envMap['CGMD_MARTINI3_DIR'] = $Martini3Dir }

    $commandLine = '"' + $pythonExe + '" ' + ($arguments -join ' ')
    Write-Say ('running: ' + $commandLine)
    $code = Invoke-Captured -CommandLine $commandLine -OutFile $logFile -TimeoutSeconds $TimeoutSeconds `
        -WorkingDirectory $WorkDir -Environment $envMap
    Write-Say ('pipeline exit ' + $code)

    $metricsPath = Join-Path $OutDir 'summary_metrics.json'
    $metrics = Read-JsonFile -Path $metricsPath
    $tail = @(Get-Tail -Path $logFile -Count 40)
    if ($null -eq $metrics) {
        $result['status'] = $(if ($code -eq 124) { 'timeout' } else { 'fail' })
        $result['summary'] = ('pipeline exit {0}; no summary_metrics.json in {1}' -f $code, $OutDir)
        $result['detail'] = [ordered]@{
            exit_code   = $code
            python      = $pythonExe
            python_version = $pythonInfo.Version
            gmx         = $gmxExe
            workdir     = $WorkDir
            output      = $OutDir
            command     = $commandLine
        }
        $result['logs_tail'] = $tail
    } else {
        $simulation = Get-Property $metrics 'simulation' $null
        $production = Get-Property $simulation 'production' $null
        $insertion = Get-Property $metrics 'membrane_insertion' $null
        $pore = Get-Property $metrics 'pore' $null
        $system = Get-Property $metrics 'system' $null
        $figures = @(Get-Property $metrics 'figures' @())
        $completed = [bool](Get-Property $production 'completed' $false)
        $diverged = [bool](Get-Property $simulation 'diverged' $false)
        $status = 'ok'
        if ($diverged) { $status = 'fail' }
        elseif ($code -ne 0) { $status = 'fail' }
        elseif (-not $completed) { $status = 'partial' }
        $result['status'] = $status
        $result['summary'] = ('Martini 3 {0}: {1}/{2} ns, {3} ns/day, {4} steps, z={5} nm, code {6}' -f
            $Name,
            (Get-Property $production 'completed_ns' 0),
            (Get-Property $production 'target_ns' $ProductionNs),
            (Get-Property $simulation 'ns_per_day' '?'),
            (Get-Property $production 'steps_completed' 0),
            (Get-Property $insertion 'z_distance_mean_nm' 'n/a'),
            $code)
        $result['detail'] = [ordered]@{
            exit_code      = $code
            task_id        = $TaskId
            python         = $pythonExe
            python_version = $pythonInfo.Version
            gmx            = $gmxExe
            martinize2     = $martinizeExe
            insane         = $insaneExe
            workdir        = $WorkDir
            output         = $OutDir
            metrics        = $metricsPath
            figures        = $figures
            completed_ns   = (Get-Property $production 'completed_ns' $null)
            target_ns      = (Get-Property $production 'target_ns' $null)
            completed      = $completed
            steps_completed = (Get-Property $production 'steps_completed' $null)
            steps_target   = (Get-Property $production 'steps_target' $null)
            mdrun_calls    = (Get-Property $production 'mdrun_calls' $null)
            gpu_flags      = (Get-Property $production 'gpu_flags' $null)
            ns_per_day     = (Get-Property $simulation 'ns_per_day' $null)
            diverged       = $diverged
            z_distance_nm  = (Get-Property $insertion 'z_distance_mean_nm' $null)
            inserted_fraction = (Get-Property $insertion 'inserted_fraction' $null)
            pore_score     = (Get-Property $pore 'pore_score_mean' $null)
            pore_formed    = (Get-Property $pore 'pore_formed' $null)
            atoms          = (Get-Property $system 'atoms' $null)
            includes       = @(Get-Property $system 'topology_includes' @())
        }
        $result['logs_tail'] = $tail
    }
} catch {
    if (-not $result['summary']) {
        $result['status'] = 'error'
        $result['summary'] = ('pipeline failed: ' + $_.Exception.Message)
    }
    if (-not $result['logs_tail'] -or @($result['logs_tail']).Count -eq 0) {
        $result['logs_tail'] = @(Get-Tail -Path $logFile -Count 40)
    }
}

$result['finished_at'] = Get-BeijingStamp
$result['seconds'] = [math]::Round(((Get-Date) - $script:StartedAt).TotalSeconds, 2)
$result['worker'] = $env:COMPUTERNAME

if (-not $ResultFile) {
    $ResultFile = Join-Path $script:StateDir ('pipeline-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
}
try { Write-JsonFile -Path $ResultFile -Data $result } catch { }
if (-not $Quiet) { Write-Output ($result | ConvertTo-Json -Depth 12) }

if ($result['status'] -eq 'ok' -or $result['status'] -eq 'partial') { exit 0 }
exit 1
