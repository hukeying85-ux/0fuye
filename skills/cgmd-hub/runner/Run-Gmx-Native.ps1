#Requires -Version 5.1
<#
.SYNOPSIS
    Native Windows GROMACS smoke test: minimise then integrate 100 ps, print the
    full version inventory and publish results/status/gmx_smoke.json.

.DESCRIPTION
    This is the path for a workstation that uses the *Windows* build of GROMACS
    instead of the WSL2 one.  It needs nothing but gmx.exe:

      * the force field is the one shipped inside GROMACS itself
        (oplsaa.ff + spce.itp), so no Martini files, no Python and no WSL are
        involved;
      * the box is filled by `gmx solvate -cs spc216.gro` (2.5 nm cube, ~500
        SPC waters);
      * steepest-descent minimisation, then 50000 x 0.002 ps = 100 ps of NPT
        at 300 K with PME, LINCS (h-bonds), v-rescale and C-rescale;
      * GPU is tried first (-nb gpu -pme gpu -bonded gpu); if mdrun complains
        the same run is retried on the CPU so the test can never be blocked by
        a driver problem;
      * the report has the same schema as the Python flavour
        (cgmd.gmxsmoke.v1), so either machine can publish it.

.PARAMETER Gmx
    Path to gmx.exe.  When omitted the script searches PATH, the usual
    C:\Program Files\GROMACS* / C:\GROMACS* directories and the conda family.

.PARAMETER Ps
    Picoseconds to integrate (default 100).

.PARAMETER BoxNm
    Cubic box edge in nm (default 2.5).

.PARAMETER WorkDir
    Scratch directory; defaults to %USERPROFILE%\cgmd-runs\smoke-native-<stamp>.

.PARAMETER Out
    Report path; defaults to results/status/gmx_smoke.json inside the clone.

.PARAMETER RepoPath
    Clone used for the report; defaults to the hub config, then C:\cgmd\0fuye.

.PARAMETER NoPush
    Keep the report local.

.PARAMETER Quiet
    No console output (scheduled-task friendly).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Run-Gmx-Native.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Run-Gmx-Native.ps1 -Gmx "C:\Program Files\GROMACS 2024.3\bin\gmx.exe" -Ps 100
#>
[CmdletBinding()]
param(
    [string]$Gmx = '',
    [double]$Ps = 100,
    [double]$BoxNm = 2.5,
    [double]$Temperature = 300,
    [string]$WorkDir = '',
    [string]$Out = '',
    [string]$ConfigPath = '',
    [string]$RepoPath = '',
    [string]$Branch = '',
    [int]$GpuId = 0,
    [int]$TimeoutSeconds = 1800,
    [switch]$NoPush,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StartedAt = Get-Date
$script:StartedAtUtc = [DateTime]::UtcNow
$script:ProbeDir = [System.IO.Path]::GetTempPath()

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
        return ($raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Get-Property {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    # both the JSON objects (PSCustomObject) and the [ordered] hashtables built
    # in this script must be readable with the same helper.
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
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
    } catch {
        return ''
    }
    if ($bytes.Length -eq 0) { return '' }
    $nul = 0
    $probe = [math]::Min($bytes.Length, 400)
    for ($i = 0; $i -lt $probe; $i++) { if ($bytes[$i] -eq 0) { $nul++ } }
    if ($nul -gt ($probe / 4)) { return ([System.Text.Encoding]::Unicode.GetString($bytes)).Trim() }
    return ([System.Text.Encoding]::UTF8.GetString($bytes)).Trim()
}

function Invoke-Program {
    param([string]$Exe, [string[]]$Arguments, [string]$WorkDirectory = '', [int]$Timeout = 900)
    # Start-Process -PassThru does not reliably expose ExitCode for console
    # programs on PowerShell 5.1 (it came back $null on the workstation).  The
    # proven pattern here is the same one the poller uses: a tiny .cmd wrapper
    # that echoes %ERRORLEVEL% into the output file.
    $stamp = [guid]::NewGuid().ToString('N').Substring(0, 8)
    $outFile = Join-Path ([System.IO.Path]::GetTempPath()) ('cgmd-' + $stamp + '.out')
    $errFile = Join-Path ([System.IO.Path]::GetTempPath()) ('cgmd-' + $stamp + '.err')
    $cmdFile = Join-Path ([System.IO.Path]::GetTempPath()) ('cgmd-' + $stamp + '.cmd')
    $quoted = @()
    foreach ($argument in $Arguments) {
        if ($argument -match '\s' -and $argument -notmatch '^"') {
            $quoted += ('"' + $argument + '"')
        } else {
            $quoted += $argument
        }
    }
    $line = '@echo off' + [Environment]::NewLine +
            ('"' + $Exe + '" ' + ($quoted -join ' ') + ' > "' + $outFile + '" 2> "' + $errFile + '"') + [Environment]::NewLine +
            ('echo CGMD_EXIT_CODE=%ERRORLEVEL% >> "' + $outFile + '"') + [Environment]::NewLine
    [System.IO.File]::WriteAllText($cmdFile, $line, [System.Text.Encoding]::ASCII)
    $started = Get-Date
    # Start-Process rejects an empty -WorkingDirectory ("parameter is null or
    # empty"), which silently broke gmx --version and nvidia-smi.  Only pass the
    # switch when there is a directory to pass, otherwise inherit the cwd.
    if (-not $WorkDirectory) { $WorkDirectory = (Get-Location).Path }
    try {
        $proc = Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /c "{0}"' -f $cmdFile) `
            -NoNewWindow -PassThru -WorkingDirectory $WorkDirectory
        if (-not $proc.WaitForExit($Timeout * 1000)) {
            & taskkill.exe /F /T /PID $proc.Id 2>&1 | Out-Null
            return [pscustomobject]@{
                Code    = 124
                Out     = (Read-TextSafely -Path $outFile)
                Err     = 'timed out after ' + $Timeout + ' s'
                Seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
            }
        }
        $text = Read-TextSafely -Path $outFile
        $code = $null
        $match = [regex]::Match($text, 'CGMD_EXIT_CODE=(-?\d+)')
        if ($match.Success) { $code = [int]$match.Groups[1].Value }
        $text = [regex]::Replace($text, 'CGMD_EXIT_CODE=-?\d+', '').Trim()
        if ($null -eq $code -and $text -notmatch 'Fatal error') { $code = 0 }
        return [pscustomobject]@{
            Code    = $code
            Out     = $text
            Err     = (Read-TextSafely -Path $errFile)
            Seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 2)
        }
    } catch {
        return [pscustomobject]@{ Code = 127; Out = ''; Err = $_.Exception.Message; Seconds = 0.0 }
    } finally {
        foreach ($path in @($outFile, $errFile, $cmdFile)) {
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
        }
    }
}

function Find-Gmx {
    param([string]$Explicit)
    if ($Explicit) {
        if (Test-Path -LiteralPath $Explicit) { return (Resolve-Path -LiteralPath $Explicit).Path }
        return ''
    }
    foreach ($name in @('gmx.exe', 'gmx', 'gmx_mpi.exe', 'gmx_mpi')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $cmd -and $cmd.Source) { return $cmd.Source }
    }
    $roots = @(
        (Join-Path $env:ProgramFiles 'GROMACS*'),
        (Join-Path $env:ProgramFiles 'gromacs*'),
        'C:\GROMACS*',
        'C:\gromacs*',
        (Join-Path $env:USERPROFILE 'gromacs*'),
        (Join-Path $env:USERPROFILE 'miniconda3\envs\*\Library\bin'),
        (Join-Path $env:USERPROFILE 'anaconda3\envs\*\Library\bin'),
        (Join-Path $env:USERPROFILE 'mambaforge\envs\*\Library\bin'),
        'C:\ProgramData\miniconda3\envs\*\Library\bin',
        'C:\ProgramData\anaconda3\envs\*\Library\bin'
    )
    foreach ($root in $roots) {
        try {
            $hits = @(Get-ChildItem -Path (Join-Path $root 'bin\gmx.exe') -ErrorAction SilentlyContinue)
            foreach ($hit in $hits) { return $hit.FullName }
        } catch { }
        try {
            $hits = @(Get-ChildItem -Path (Join-Path $root 'gmx.exe') -ErrorAction SilentlyContinue)
            foreach ($hit in $hits) { return $hit.FullName }
        } catch { }
    }
    return ''
}

function Get-Tail {
    param([string]$Path, [int]$Count = 20)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    try {
        return @([System.IO.File]::ReadAllLines($Path) | Select-Object -Last $Count)
    } catch {
        return @()
    }
}

# ---------------------------------------------------------------------------
# configuration / paths
# ---------------------------------------------------------------------------
$cfg = $null
foreach ($candidate in @($ConfigPath, (Join-Path $script:HubRoot 'config\cgmd_hub.local.json'), (Join-Path $script:HubRoot 'config\cgmd_hub.json'))) {
    if (-not $candidate) { continue }
    if (Test-Path -LiteralPath $candidate) {
        $loaded = Read-JsonFile -Path $candidate
        if ($null -ne $loaded) { $cfg = $loaded; break }
    }
}

$repo = $RepoPath
if (-not $repo) { $repo = Get-Property $cfg 'repo_path' 'C:\cgmd\0fuye' }
$branch = $Branch
if (-not $branch) { $branch = Get-Property $cfg 'branch' 'main' }
if ($GpuId -le 0) { $GpuId = [int](Get-Property $cfg 'gpu_id' 0) }

$reportPath = $Out
if (-not $reportPath) { $reportPath = Join-Path (Join-Path (Join-Path $repo 'results') 'status') 'gmx_smoke.json' }
$workdir = $WorkDir
if (-not $workdir) {
    $workdir = Join-Path (Join-Path $env:USERPROFILE 'cgmd-runs') ('smoke-native-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
New-Item -ItemType Directory -Path $workdir -Force | Out-Null

Say ''
Say '  CGMD-Engine - native Windows GROMACS smoke test' 'White'
Say ('  workdir : ' + $workdir)
Say ('  repo    : ' + $repo)
Say ''

$notes = New-Object System.Collections.ArrayList
$stages = New-Object System.Collections.ArrayList

$report = [ordered]@{
    schema        = 'cgmd.gmxsmoke.v1'
    generated_at  = Get-BeijingStamp
    status        = 'fail'
    ok            = $false
    ps_requested  = [double]$Ps
    ps_completed  = 0.0
    workdir       = $workdir
    gpu_id        = [int]$GpuId
    temperature_K = [double]$Temperature
    dt_ps         = 0.002
    system_kind   = 'spc'
    steps         = @{}
    stages        = @()
    stage_error   = $null
    notes         = @()
    software      = @{}
    system        = @{}
    mdrun         = @{}
    accelerator   = ''
    seconds_total = 0.0
}

# ---------------------------------------------------------------------------
# 1. find GROMACS and read its inventory
# ---------------------------------------------------------------------------
$gmx = Find-Gmx -Explicit $Gmx
$packages = [ordered]@{}
foreach ($module in @('numpy', 'MDAnalysis', 'vermouth', 'matplotlib')) {
    $packages[$module] = 'not checked (native run)'
}

$software = [ordered]@{
    generated_at = Get-BeijingStamp
    hostname     = $env:COMPUTERNAME
    platform     = [string](Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
    machine      = $env:PROCESSOR_ARCHITECTURE
    python       = ''
    packages     = $packages
    tools        = [ordered]@{ gmx = $gmx }
    gpus         = @()
    martini3_dir = ''
    gromacs      = [ordered]@{ version = $null; executable = $gmx; available = $false; gpu_support = $null; cuda = $false }
}

foreach ($tool in @('nvidia-smi', 'git')) {
    $found = Get-Command $tool -ErrorAction SilentlyContinue
    $software['tools'][$tool] = $(if ($found) { $found.Source } else { $null })
}
$smi = $software['tools']['nvidia-smi']
if ($smi) {
    $gpuInfo = Invoke-Program -Exe $smi -Arguments @('--query-gpu=name,driver_version,memory.total', '--format=csv,noheader') -WorkDirectory $script:ProbeDir -Timeout 60
    $devices = @()
    foreach ($line in ($gpuInfo.Out -split "`r?`n")) {
        if (-not $line.Trim()) { continue }
        $parts = @($line -split ',' | ForEach-Object { $_.Trim() })
        if ($parts.Count -ge 3) {
            $devices += [ordered]@{ name = $parts[0]; driver = $parts[1]; memory = $parts[2] }
        }
    }
    $software['gpus'] = $devices
}

if (-not $gmx) {
    $report['stage_error'] = 'gmx.exe not found: pass -Gmx "C:\Program Files\GROMACS xxxx\bin\gmx.exe" or add the GROMACS bin folder to PATH'
    [void]$notes.Add('typical install: conda install -c conda-forge gromacs, or the official Windows installer')
} else {
    $versionRun = Invoke-Program -Exe $gmx -Arguments @('--version') -WorkDirectory $script:ProbeDir -Timeout 60
    $versionText = ($versionRun.Out + "`n" + $versionRun.Err)
    $gromacs = [ordered]@{
        version      = $null
        executable   = $gmx
        available    = $false
        precision    = $null
        memory_model = $null
        simd         = $null
        gpu_support  = $null
        cuda_runtime = $null
        cuda_driver  = $null
        fft          = $null
        openmp       = $null
        compiler     = $null
        cuda         = $false
        raw          = @(($versionText -split "`r?`n") | Select-Object -First 30)
    }
    $patterns = @{
        version      = 'GROMACS version:\s*(\S+)'
        precision    = 'Precision:\s*(\S+)'
        memory_model = 'Memory model:\s*(.+)'
        simd         = 'SIMD instructions:\s*(.+)'
        gpu_support  = 'GPU support:\s*(.+)'
        cuda_runtime = 'CUDA runtime:\s*(.+)'
        cuda_driver  = 'CUDA driver:\s*(.+)'
        fft          = 'FFT library:\s*(.+)'
        openmp       = 'OpenMP:\s*(.+)'
        compiler     = '(?:GCC|Clang|CC)\s+[^:]*:\s*(.+)'
        data_prefix  = 'Data prefix:\s*(.+)'
    }
    foreach ($key in $patterns.Keys) {
        $match = [regex]::Match($versionText, $patterns[$key])
        if ($match.Success) { $gromacs[$key] = $match.Groups[1].Value.Trim() }
    }
    if ($gromacs['gpu_support']) {
        $gromacs['cuda'] = ($gromacs['gpu_support'] -match 'CUDA|SYCL|OpenCL')
    }
    $gromacs['available'] = [bool]$gromacs['version']
    $gromacs['version_returncode'] = $versionRun.Code
    $banner = @(($versionRun.Out -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1)
    $gromacs['banner'] = $banner -join ' '
    if (-not $gromacs['version']) {
        [void]$notes.Add('gmx --version printed nothing usable; see software.gromacs.banner and .raw')
    }
    $software['gromacs'] = $gromacs
}

$report['software'] = $software
$report['host'] = [ordered]@{
    hostname = $env:COMPUTERNAME
    platform = $software['platform']
    python   = ''
    gpus     = $software['gpus']
    gromacs  = (Get-Property $software['gromacs'] 'version' $null)
}
$v = Get-Property $software['gromacs'] 'version' 'not found'
Say ('  [ok] gmx ' + $v + ' -> ' + $gmx) 'Green'

# Where the bundled force fields and solvent boxes live.  A Windows build that
# ships only gmx.exe (no share/top) cannot run grompp at all, so the answer has
# to travel back in the report instead of being guessed at from here.
$dataPrefix = [string](Get-Property $software['gromacs'] 'data_prefix' '')
if (-not $dataPrefix) {
    $parent = Split-Path -Parent (Split-Path -Parent $gmx)
    if ($parent) { $dataPrefix = $parent }
}
$shareTop = ''
$candidates = @()
if ($dataPrefix) {
    $candidates += (Join-Path $dataPrefix 'share\top')
    $candidates += (Join-Path $dataPrefix 'share\gromacs\top')
    $candidates += (Join-Path $dataPrefix 'top')
    $parentOfPrefix = Split-Path -Parent $dataPrefix
    if ($parentOfPrefix -and $parentOfPrefix -ne $dataPrefix) {
        $candidates += (Join-Path $parentOfPrefix 'share\top')
        $candidates += (Join-Path $parentOfPrefix 'share\gromacs\top')
    }
}
foreach ($candidate in $candidates) {
    if ($shareTop) { continue }
    if (Test-Path -LiteralPath $candidate) { $shareTop = $candidate }
}
$ffProbe = [ordered]@{
    data_prefix   = $dataPrefix
    share_top     = $shareTop
    oplsaa_dir    = ''
    files         = [ordered]@{}
}
if ($shareTop) {
    $oplsaa = Join-Path $shareTop 'oplsaa.ff'
    if (Test-Path -LiteralPath $oplsaa) { $ffProbe['oplsaa_dir'] = $oplsaa }
    foreach ($item in @('oplsaa.ff\forcefield.itp', 'oplsaa.ff\ffbonded.itp', 'oplsaa.ff\ffnonbonded.itp',
                        'oplsaa.ff\spce.itp', 'oplsaa.ff\spc.itp', 'oplsaa.ff\tip3p.itp', 'oplsaa.ff\ions.itp',
                        'spc216.gro', 'charmm36.ff\forcefield.itp', 'amber99sb-ildn.ff\forcefield.itp')) {
        $ffProbe['files'][$item] = (Test-Path -LiteralPath (Join-Path $shareTop $item))
    }
}
$report['environment'] = $ffProbe

if (-not $gmx) {
    if (-not $Quiet) { Write-Output ($report | ConvertTo-Json -Depth 8) }
    exit 3
}

# ---------------------------------------------------------------------------
# 2. build the SPC water box with the force field bundled in GROMACS
# ---------------------------------------------------------------------------
function Write-SpcTopology {
    param([string]$Path, [string]$Kind = 'oplsaa', [int]$Molecules = 0)
    if ($Kind -eq 'inline') {
        # Every parameter inline: no #include, no force-field directory, no
        # liquid-file lookup.  SPC/E charges, OW-HW 0.1 nm, HWH 109.47 deg,
        # SETTLE on the oxygen.  Used when grompp refuses the bundled
        # oplsaa.ff (a Windows build crashed with 0xC0000005 there).
        $lines = @(
            '; CGMD smoke test -- self-contained SPC water (no force-field include)',
            '[ defaults ]',
            '1               3               no              1.0     1.0',
            '',
            '[ atomtypes ]',
            '; name  at.num  mass      charge  ptype  sigma(nm)  epsilon(kJ/mol)',
            '  OW    8       15.99940   0.000   A      0.315061   0.636386',
            '  HW    1        1.00800   0.000   A      0.000000   0.000000',
            '',
            '[ moleculetype ]',
            '; name  nrexcl',
            'SOL     2',
            '',
            '[ atoms ]',
            '; nr  type  resnr  residue  atom  cgnr  charge    mass',
            '1     OW    1      SOL      OW    1     -0.8476   15.99940',
            '2     HW    1      SOL      HW1   1      0.4238    1.00800',
            '3     HW    1      SOL      HW2   1      0.4238    1.00800',
            '',
            '[ settles ]',
            '; OW  funct  doh(nm)  dhh(nm)',
            '1     1      0.1      0.16330',
            '',
            '[ exclusions ]',
            '1  2  3',
            '2  1  3',
            '3  1  2',
            '',
            '[ system ]',
            'CGMD smoke test -- SPC water',
            '',
            '[ molecules ]',
            ('SOL ' + $Molecules)
        )
    } else {
        $lines = @(
            '; CGMD smoke test -- SPC water, stock GROMACS force field',
            '#include "oplsaa.ff/forcefield.itp"',
            '#include "oplsaa.ff/spce.itp"',
            '#include "oplsaa.ff/ions.itp"',
            '',
            '[ system ]',
            'CGMD smoke test -- SPC water',
            '',
            '[ molecules ]',
            'SOL 0'
        )
    }
    $text = ($lines -join [Environment]::NewLine) + [Environment]::NewLine
    [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding($false)))
    return $Path
}

$topFile = Write-SpcTopology -Path (Join-Path $workdir 'smoke_box.top') -Kind 'oplsaa'

$edge = ('{0:F3}' -f [double]$BoxNm)
$solvate = Invoke-Program -Exe $gmx -WorkDirectory $workdir -Timeout 300 -Arguments @(
    'solvate', '-cs', 'spc216.gro', '-box', $edge, $edge, $edge,
    '-o', 'smoke_box.gro', '-p', 'smoke_box.top'
)
[void]$stages.Add([ordered]@{
    stage           = 'solvate'
    command         = 'gmx solvate -cs spc216.gro -box ' + $edge + ' -o smoke_box.gro -p smoke_box.top'
    returncode      = $solvate.Code
    seconds         = $solvate.Seconds
    stderr_tail     = @(($solvate.Err -split "`r?`n") | Where-Object { $_ } | Select-Object -Last 6)
    missing_markers = @()
})
if ($solvate.Code -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $workdir 'smoke_box.gro'))) {
    $fatal = @(($solvate.Out + "`n" + $solvate.Err) -split "`r?`n" | Where-Object { $_ -match 'Fatal error|Error|error:' } | Select-Object -Last 1)
    if (-not $fatal) { $fatal = @(($solvate.Err -split "`r?`n") | Where-Object { $_ } | Select-Object -Last 1) }
    $report['stage_error'] = 'gmx solvate failed: ' + ($fatal -join ' ')
    $report['stages'] = $stages
    $report['notes'] = $notes
    [System.IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 8), (New-Object System.Text.UTF8Encoding($false)))
    Say ('  [fail] ' + $report['stage_error']) 'Red'
    exit 3
}

$solventMatch = [regex]::Match($solvate.Out, 'Number of solvent molecules:\s*(\d+)')
if ($solventMatch.Success) { Say ('  [ok] gmx solvate added ' + $solventMatch.Groups[1].Value + ' SPC waters') 'Green' }

$groPath = Join-Path $workdir 'smoke_box.gro'
$groLines = @([System.IO.File]::ReadAllLines($groPath))
$atoms = 0
if ($groLines.Count -gt 1) { [void][int]::TryParse($groLines[1].Trim(), [ref]$atoms) }
$boxLine = $groLines[$groLines.Count - 1].Trim()
Say ('  [ok] solvate: ' + $atoms + ' atoms, box ' + $boxLine) 'Green'

$report['system'] = [ordered]@{
    kind       = 'spc-water-box'
    atoms      = $atoms
    molecules  = [int]($atoms / 3)
    box_nm     = @($BoxNm, $BoxNm, $BoxNm)
    gro        = $groPath
    top        = $topFile
    topology   = [ordered]@{ force_field = 'oplsaa.ff (bundled with GROMACS)'; water = 'SPC/E (spc216.gro)' }
}

# ---------------------------------------------------------------------------
# 3. mdp files
# ---------------------------------------------------------------------------
$steps = [int][math]::Round([double]$Ps / 0.002)
$report['steps'] = @{ md = $steps }
$compressed = [int][math]::Max(1, [math]::Floor($steps / 20))

$emMdp = @(
    'integrator              = steep',
    'emtol                   = 100.0',
    'emstep                  = 0.01',
    'nsteps                  = 500',
    'cutoff-scheme           = Verlet',
    'nstlist                 = 10',
    'pbc                     = xyz',
    'coulombtype             = PME',
    'rcoulomb                = 1.0',
    'rvdw                    = 1.0',
    'vdwtype                 = cutoff',
    'constraints             = none'
) -join [Environment]::NewLine

$mdMdp = @(
    'integrator              = md',
    'dt                      = 0.002',
    ('nsteps                  = ' + $steps),
    'constraints             = h-bonds',
    'constraint-algorithm    = lincs',
    'continuation            = no',
    'gen-vel                 = yes',
    ('gen-temp                = ' + [int]$Temperature),
    'gen-seed                = -1',
    'cutoff-scheme           = Verlet',
    'nstlist                 = 10',
    'pbc                     = xyz',
    'coulombtype             = PME',
    'rcoulomb                = 1.0',
    'rvdw                    = 1.0',
    'vdwtype                 = cutoff',
    'dispcorr                = EnerPres',
    'tcoupl                  = v-rescale',
    'tc-grps                 = System',
    'tau-t                   = 0.1',
    ('ref-t                   = ' + [int]$Temperature),
    'pcoupl                  = c-rescale',
    'pcoupltype              = isotropic',
    'tau-p                   = 1.0',
    'compressibility         = 4.5e-5',
    'ref-p                   = 1.0',
    'nstxout                 = 0',
    'nstvout                 = 0',
    'nstfout                 = 0',
    'nstenergy               = 50',
    'nstlog                  = 50',
    'nstcalcenergy           = 10',
    ('nstxout-compressed      = ' + $compressed),
    'compressed-x-grps       = System'
) -join [Environment]::NewLine

[System.IO.File]::WriteAllText((Join-Path $workdir 'smoke_em.mdp'), $emMdp + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
[System.IO.File]::WriteAllText((Join-Path $workdir 'smoke_md.mdp'), $mdMdp + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))

function Invoke-Stage {
    param([string]$Name, [string[]]$Arguments, [string[]]$Expect = @(), [int]$Timeout = 900)
    $result = Invoke-Program -Exe $gmx -Arguments $Arguments -WorkDirectory $workdir -Timeout $Timeout
    $text = $result.Out + "`n" + $result.Err
    $missing = @()
    foreach ($token in $Expect) {
        if ($text -notmatch [regex]::Escape($token)) { $missing += $token }
    }
    [void]$stages.Add([ordered]@{
        stage           = $Name
        command         = 'gmx ' + ($Arguments -join ' ')
        returncode      = $result.Code
        seconds         = $result.Seconds
        stderr_tail     = @(($result.Err -split "`r?`n") | Where-Object { $_ } | Select-Object -Last 6)
        output_tail     = @((($result.Out + "`n" + $result.Err) -split "`r?`n") | Where-Object { $_ } | Select-Object -Last 30)
        missing_markers = $missing
    })
    $okStage = (($result.Code -eq 0) -or ($null -eq $result.Code)) -and ($missing.Count -eq 0)
    if (-not $okStage) {
        Say ('  [warn] stage ' + $Name + ' exit ' + $result.Code + ' ' + (($result.Err -split "`r?`n") | Where-Object { $_ } | Select-Object -Last 1)) 'Yellow'
    }
    return $okStage
}

function Save-Report {
    param([string]$Verdict = 'fail')
    $report['status'] = $Verdict
    $report['ok'] = ($Verdict -eq 'ok')
    $report['stages'] = $stages
    $report['notes'] = $notes
    $report['seconds_total'] = [math]::Round(([DateTime]::UtcNow - $script:StartedAtUtc).TotalSeconds, 2)
    $report['stages_seconds'] = [math]::Round((@($stages) | ForEach-Object { if ($_.seconds) { [double]$_.seconds } else { 0 } } | Measure-Object -Sum).Sum, 2)
    $dir = Split-Path -Parent $reportPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 8), (New-Object System.Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------------------
# 4. minimise
# ---------------------------------------------------------------------------
Say '  running grompp + mdrun (energy minimisation)' 'Cyan'
$emOk = Invoke-Stage -Name 'grompp-em' -Arguments @('grompp', '-f', 'smoke_em.mdp', '-c', 'smoke_box.gro', '-p', $topFile, '-o', 'smoke_em.tpr', '-maxwarn', '2')
if (-not $emOk) {
    # A Windows build of GROMACS died with 0xC0000005 inside grompp while
    # reading the bundled oplsaa.ff includes.  Do not give up: redo the same
    # system with a topology that carries every parameter inline, then keep the
    # run going.  Which route worked is recorded in the report.
    Say '  [warn] grompp failed on the bundled force field, retrying with an inline SPC topology' 'Yellow'
    $topFile = Write-SpcTopology -Path (Join-Path $workdir 'smoke_box_inline.top') -Kind 'inline' -Molecules ([int]($atoms / 3))
    $report['system']['top'] = $topFile
    $report['system']['topology'] = [ordered]@{
        force_field = 'inline (self-contained SPC parameters)'
        water       = 'SPC/E, SETTLE on OW'
        reason      = 'grompp failed on oplsaa.ff; every parameter is now written to the topology'
    }
    if (-not $notes.Contains('grompp failed on the bundled oplsaa.ff, retried with an inline SPC topology')) {
        [void]$notes.Add('grompp failed on the bundled oplsaa.ff, retried with an inline SPC topology')
    }
    $emOk = Invoke-Stage -Name 'grompp-em-inline' -Arguments @('grompp', '-f', 'smoke_em.mdp', '-c', 'smoke_box.gro', '-p', $topFile, '-o', 'smoke_em.tpr', '-maxwarn', '2')
}
if (-not $emOk) {
    $report['stage_error'] = 'grompp (energy minimisation) failed, with the bundled force field and with the inline topology'
    Save-Report
    Say ('  [fail] ' + $report['stage_error']) 'Red'
    exit 3
}
if (-not (Invoke-Stage -Name 'mdrun-em' -Arguments @('mdrun', '-deffnm', 'smoke_em', '-nb', 'cpu') -Expect @('Steepest Descents'))) {
    $report['stage_error'] = 'mdrun (energy minimisation) failed'
    Save-Report
    Say ('  [fail] ' + $report['stage_error']) 'Red'
    exit 3
}

# ---------------------------------------------------------------------------
# 5. 100 ps of dynamics, GPU first then CPU
# ---------------------------------------------------------------------------
Say ('  running ' + $Ps + ' ps (' + $steps + ' steps x 0.002 ps)' ) 'Cyan'
if (-not (Invoke-Stage -Name 'grompp-md' -Arguments @('grompp', '-f', 'smoke_md.mdp', '-c', 'smoke_em.gro', '-p', $topFile, '-o', 'smoke_md.tpr', '-maxwarn', '2'))) {
    $report['stage_error'] = 'grompp (production) failed'
    Save-Report
    Say ('  [fail] ' + $report['stage_error']) 'Red'
    exit 3
}

$gpuFlags = @('mdrun', '-deffnm', 'smoke_md', '-nb', 'gpu', '-gpu_id', [string]$GpuId)
$accelerator = 'gpu'
if (-not (Invoke-Stage -Name 'mdrun-md-gpu' -Arguments $gpuFlags -Timeout $TimeoutSeconds)) {
    $accelerator = 'cpu'
    [void]$notes.Add('GPU mdrun failed, retried on the CPU (see stages for the GPU error)')
    foreach ($artifact in @('smoke_md.log', 'smoke_md.edr', 'smoke_md.xtc', 'smoke_md.gro', 'smoke_md.cpt')) {
        $path = Join-Path $workdir $artifact
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    }
    if (-not (Invoke-Stage -Name 'mdrun-md-cpu' -Arguments @('mdrun', '-deffnm', 'smoke_md', '-nb', 'cpu') -Timeout $TimeoutSeconds)) {
        $report['stage_error'] = 'mdrun (production) failed on GPU and on CPU'
        $report['accelerator'] = $accelerator
        Save-Report
        Say ('  [fail] ' + $report['stage_error']) 'Red'
        exit 3
    }
}
$report['accelerator'] = $accelerator

# ---------------------------------------------------------------------------
# 6. verdict
# ---------------------------------------------------------------------------
$logPath = Join-Path $workdir 'smoke_md.log'
$logText = Read-TextSafely -Path $logPath
$mdrunInfo = [ordered]@{
    performance_ns_per_day = $null
    steps_requested        = $steps
    dt_ps                  = 0.002
    simulated_ps           = [double]$Ps
    time_ps                = 0.0
    finished               = ($logText -match 'Finished mdrun')
    fatal                  = $null
}

$perf = [regex]::Match($logText, 'Performance:\s+([0-9.]+)')
if ($perf.Success) { $mdrunInfo['performance_ns_per_day'] = [double]$perf.Groups[1].Value }

$timeMatches = [regex]::Matches($logText, '(?m)^\s*(\d+)\s+([0-9.]+)\s*$')
if ($timeMatches.Count -gt 0) {
    $last = $timeMatches[$timeMatches.Count - 1]
    $mdrunInfo['time_ps'] = [double]$last.Groups[2].Value
}
foreach ($marker in @('Fatal error', 'There is no domain decomposition', 'GPU API call failed', 'CUDA error')) {
    if ($logText -match [regex]::Escape($marker)) {
        $idx = $logText.IndexOf($marker)
        $rest = $logText.Substring($idx + $marker.Length).Trim().TrimStart(':').Trim()
        if ($rest) { $mdrunInfo['fatal'] = ($rest -split "`r?`n")[0].Trim() } else { $mdrunInfo['fatal'] = $marker }
        break
    }
}

$report['mdrun'] = $mdrunInfo
$report['ps_completed'] = [double]$mdrunInfo['time_ps']
$report['log_tail'] = @(Get-Tail -Path $logPath -Count 20)
$report['files'] = @(Get-ChildItem -Path $workdir -File | ForEach-Object { $_.Name } | Sort-Object)

$integrated = ([double]$mdrunInfo['time_ps'] -ge ([double]$Ps * 0.999 - 1e-9))
if ($mdrunInfo['fatal']) {
    $report['stage_error'] = 'GROMACS reported: ' + $mdrunInfo['fatal']
} elseif (-not $integrated) {
    $report['stage_error'] = ('only {0:F3} of {1:F1} ps integrated' -f [double]$mdrunInfo['time_ps'], [double]$Ps)
} elseif (-not $mdrunInfo['finished']) {
    $report['stage_error'] = "mdrun produced no 'Finished mdrun' line"
}

$verdict = 'fail'
if ($integrated -and $mdrunInfo['finished'] -and (-not $mdrunInfo['fatal'])) { $verdict = 'ok' }
Save-Report -Verdict $verdict

# ---------------------------------------------------------------------------
# 7. print the inventory
# ---------------------------------------------------------------------------
$gromacsOut = $report['software']['gromacs']
Say ''
Say ('=' * 74) -ForegroundColor DarkGray
Say ('  ' + $verdict.ToUpper() + ' - ' + $report['ps_completed'] + ' / ' + $Ps + ' ps integrated (' + $accelerator + ')') `
    -ForegroundColor $(if ($verdict -eq 'ok') { 'Green' } else { 'Red' })
Say ('=' * 74) -ForegroundColor DarkGray
Say ('  gromacs        : ' + (Get-Property $gromacsOut 'version' 'not found'))
Say ('  executable     : ' + $gmx)
Say ('  precision      : ' + (Get-Property $gromacsOut 'precision' 'n/a'))
Say ('  memory model   : ' + (Get-Property $gromacsOut 'memory_model' 'n/a'))
Say ('  simd           : ' + (Get-Property $gromacsOut 'simd' 'n/a'))
Say ('  gpu support    : ' + (Get-Property $gromacsOut 'gpu_support' 'n/a'))
Say ('  cuda runtime   : ' + (Get-Property $gromacsOut 'cuda_runtime' 'n/a'))
Say ('  cuda driver    : ' + (Get-Property $gromacsOut 'cuda_driver' 'n/a'))
Say ('  fft            : ' + (Get-Property $gromacsOut 'fft' 'n/a'))
Say ('  openmp         : ' + (Get-Property $gromacsOut 'openmp' 'n/a'))
foreach ($gpu in @($report['software']['gpus'])) {
    if ($gpu) { Say ('  gpu            : ' + $gpu['name'] + ' | driver ' + $gpu['driver'] + ' | ' + $gpu['memory']) }
}
Say ('  system         : ' + $report['system']['atoms'] + ' atoms (' + $report['system']['molecules'] + ' SPC waters), box ' + $BoxNm + ' nm')
Say ('  ns/day         : ' + (Get-Property $mdrunInfo 'performance_ns_per_day' 'n/a'))
if ($report['stage_error']) { Say ('  stage error    : ' + $report['stage_error']) 'Red' }
Say ''

# ---------------------------------------------------------------------------
# 8. publish
# ---------------------------------------------------------------------------
if ((-not $NoPush) -and (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    $relative = 'results/status/gmx_smoke.json'
    $null = Invoke-Git -Repo $repo -GitArgs @('add', '-A', '--', $relative)
    $status = Invoke-Git -Repo $repo -GitArgs @('status', '--porcelain')
    if ($status.Output) {
        $message = 'smoke: gmx ' + (Get-Property $gromacsOut 'version' '?') + ' - ' + $report['ps_completed'] + ' ps [native windows]'
        $commit = Invoke-Git -Repo $repo -GitArgs @('commit', '-m', $message)
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
if ($verdict -eq 'ok') { exit 0 }
exit 3
