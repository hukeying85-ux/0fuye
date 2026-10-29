#Requires -Version 5.1
<#
.SYNOPSIS
    Arena Desk Cross-PC One-Click Diagnostic & Software Installer (Windows 10/11).
    ASCII-only for Windows PowerShell 5.1 compatibility.

.DESCRIPTION
    1. Hardware, disk, GPU, network, proxy, Tailscale, OpenSSH, Git, gh, Python,
       Conda/Mamba, uv, Node.js, and PyMOL health diagnostics.
    2. Optional one-click installation of Open-Source PyMOL (conda-forge::pymol-open-source),
       base developer tools (Git, GitHub CLI gh, uv), Tailscale, OpenSSH Server,
       and custom Winget packages.
    3. Writes both .txt and .json diagnostic reports to Desktop (or -OutDir).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\pc-diag-install.ps1 -Mode diag
    powershell -ExecutionPolicy Bypass -File .\pc-diag-install.ps1 -Mode install -InstallPyMOL -InstallBase
    powershell -ExecutionPolicy Bypass -File .\pc-diag-install.ps1 -Mode node -InstallPyMOL -InstallBase -InstallTailscale
#>
[CmdletBinding()]
param(
    [ValidateSet('diag', 'install', 'node')]
    [string]$Mode = 'diag',
    [switch]$InstallPyMOL,
    [switch]$InstallBase,
    [switch]$InstallTailscale,
    [string]$ExtraWinget = '',
    [string]$PreferredDrive = 'Auto',
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$reportLines = New-Object System.Collections.Generic.List[string]
function Log-Line([string]$msg) {
    $ts = Get-Date -Format 'HH:mm:ss'
    $row = "[${ts}] ${msg}"
    Write-Host $row
    $script:reportLines.Add($row)
}

function Select-BestDrive([string]$pref) {
    if ($pref -and $pref -ne 'Auto') {
        $d = ($pref.TrimEnd(':').Substring(0, 1).ToUpper()) + ':'
        if (Test-Path -LiteralPath "${d}\") { return $d }
    }
    $drives = @(Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue |
        Where-Object { $_.Free -gt 5GB -and $_.Root -match '^[C-Z]:\\$' } |
        Sort-Object -Property @{Expression = { if ($_.Name -eq 'C') { 0 } else { 1 } }; Descending = $true}, @{Expression = 'Free'; Descending = $true})
    if ($drives.Count -gt 0) { return ($drives[0].Name + ':') }
    return 'C:'
}

function Find-Tool([string]$cmdName, [string[]]$extraPaths) {
    foreach ($p in $extraPaths) {
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    $c = Get-Command $cmdName -ErrorAction SilentlyContinue
    if ($c -and $c.Source -and ($c.Source -notmatch 'WindowsApps\\python')) {
        return $c.Source
    }
    return ''
}

function Get-ToolVersion([string]$exe, [string]$arg = '--version') {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return '' }
    try {
        $out = (& $exe $arg 2>&1 | Select-Object -First 2) -join ' '
        return (($out -replace '\s+', ' ').Trim())
    } catch {
        return 'present'
    }
}

function Test-TcpQuick([string]$targetHost, [int]$port, [int]$ms = 2500) {
    try {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $tcp = New-Object System.Net.Sockets.TcpClient
        $ok = $tcp.BeginConnect($targetHost, $port, $null, $null).AsyncWaitHandle.WaitOne($ms, $false)
        $sw.Stop()
        if (-not $ok) { $tcp.Close(); return @{ ok = $false; ms = -1 } }
        $tcp.EndConnect($null) | Out-Null
        $tcp.Close()
        return @{ ok = $true; ms = [int]$sw.ElapsedMilliseconds }
    } catch {
        return @{ ok = $false; ms = -1 }
    }
}

Log-Line '============================================================'
Log-Line '  Arena Desk - Cross-PC Diagnostic & Software Bootstrap v2.0'
Log-Line '============================================================'

$bestDrive = Select-BestDrive $PreferredDrive
$osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$cpuInfo = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
$gpus = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
$ramGb = if ($osInfo) { [math]::Round($osInfo.TotalVisibleMemorySize / 1MB, 1) } else { 0 }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

Log-Line ("Host       : " + $env:COMPUTERNAME + " (User: " + $env:USERNAME + ", Admin: " + $isAdmin + ")")
Log-Line ("OS         : " + $(if ($osInfo) { $osInfo.Caption + " Build " + $osInfo.BuildNumber } else { [Environment]::OSVersion.VersionString }))
Log-Line ("CPU / RAM  : " + $(if ($cpuInfo) { $cpuInfo.Name.Trim() } else { 'unknown' }) + " | " + $ramGb + " GB RAM")
Log-Line ("GPU        : " + $(if ($gpus.Count -gt 0) { $gpus -join ' ; ' } else { 'none detected' }))
Log-Line ("TargetDrive: " + $bestDrive + " (Mode: " + $Mode + ")")

$diskSummary = @()
foreach ($d in @(Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue | Where-Object { $_.Root -match '^[A-Z]:\\$' })) {
    $freeGb = [math]::Round($d.Free / 1GB, 1)
    $usedGb = [math]::Round($d.Used / 1GB, 1)
    $diskSummary += [ordered]@{ drive = ($d.Name + ':'); free_gb = $freeGb; used_gb = $usedGb }
    Log-Line ("Disk " + $d.Name + ":    : " + $freeGb + " GB free / " + ($freeGb + $usedGb) + " GB total")
}

# ---- Network & Proxy check ----
$netGithub = Test-TcpQuick 'github.com' 443
$netConda  = Test-TcpQuick 'conda.anaconda.org' 443
$netPypi   = Test-TcpQuick 'pypi.org' 443
Log-Line ("Network    : github.com=" + $netGithub.ok + "(" + $netGithub.ms + "ms) conda-forge=" + $netConda.ok + "(" + $netConda.ms + "ms) pypi=" + $netPypi.ok + "(" + $netPypi.ms + "ms)")

# ---- Probe existing tools ----
$gitExe   = Find-Tool 'git.exe' @('E:\hermes\git\cmd\git.exe', 'C:\Program Files\Git\cmd\git.exe')
$ghExe    = Find-Tool 'gh.exe' @('C:\Program Files\GitHub CLI\gh.exe', "${bestDrive}\0apps\GitHubCLI\bin\gh.exe")
$pyExe    = Find-Tool 'python.exe' @('E:\spider\python.exe', "${bestDrive}\Miniforge3\python.exe", 'E:\miniconda3\python.exe', 'C:\Python312\python.exe', 'C:\Python311\python.exe')
$condaExe = Find-Tool 'mamba.exe' @("${bestDrive}\Miniforge3\Scripts\mamba.exe", 'E:\Miniforge3\Scripts\mamba.exe', 'C:\ProgramData\miniforge3\Scripts\mamba.exe', "$env:USERPROFILE\miniforge3\Scripts\mamba.exe")
if (-not $condaExe) {
    $condaExe = Find-Tool 'conda.exe' @("${bestDrive}\Miniforge3\Scripts\conda.exe", 'E:\Miniforge3\Scripts\conda.exe', 'E:\miniconda3\Scripts\conda.exe', 'E:\spider\Scripts\conda.exe', "$env:USERPROFILE\miniconda3\Scripts\conda.exe")
}
$uvExe    = Find-Tool 'uv.exe' @('E:\0apps\jev-chat-windows\uv\uv.exe', "$env:USERPROFILE\.local\bin\uv.exe")
$nodeExe  = Find-Tool 'node.exe' @('E:\hermes\node\node.exe', 'C:\Program Files\nodejs\node.exe')
$tsExe    = Find-Tool 'tailscale.exe' @('E:\Tailscale\tailscale.exe', 'C:\Program Files\Tailscale\tailscale.exe')
$pymolExe = Find-Tool 'pymol.exe' @(
    "${bestDrive}\0apps\PyMOL\Library\bin\pymol.exe",
    "${bestDrive}\0apps\PyMOL\Scripts\pymol.exe",
    'E:\0apps\PyMOL\Library\bin\pymol.exe',
    'D:\Pymol\PyMOLWin.exe',
    'D:\Pymol\pymol.exe',
    'E:\Pymol\PyMOLWin.exe',
    "${bestDrive}\Miniforge3\envs\pymol\Library\bin\pymol.exe"
)
$wingetExe = Find-Tool 'winget.exe' @("$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe")

Log-Line ("Tool git   : " + $(if ($gitExe) { $gitExe + " (" + (Get-ToolVersion $gitExe) + ")" } else { 'MISSING' }))
Log-Line ("Tool gh    : " + $(if ($ghExe) { $ghExe + " (" + (Get-ToolVersion $ghExe) + ")" } else { 'MISSING' }))
Log-Line ("Tool python: " + $(if ($pyExe) { $pyExe + " (" + (Get-ToolVersion $pyExe) + ")" } else { 'MISSING' }))
Log-Line ("Tool conda : " + $(if ($condaExe) { $condaExe + " (" + (Get-ToolVersion $condaExe) + ")" } else { 'MISSING' }))
Log-Line ("Tool uv    : " + $(if ($uvExe) { $uvExe + " (" + (Get-ToolVersion $uvExe) + ")" } else { 'MISSING' }))
Log-Line ("Tool node  : " + $(if ($nodeExe) { $nodeExe + " (" + (Get-ToolVersion $nodeExe) + ")" } else { 'MISSING' }))
Log-Line ("Tool pymol : " + $(if ($pymolExe) { $pymolExe } else { 'NOT INSTALLED' }))

# ---- Check gh auth status (redacted) ----
$ghAuthOk = $false
if ($ghExe) {
    $env:GH_PROMPT_DISABLED = '1'
    $ghOut = (& $ghExe auth status 2>&1) -join ' | '
    if ($LASTEXITCODE -eq 0) { $ghAuthOk = $true }
    $ghSafe = ($ghOut -replace '(gho_|ghp_|github_pat_)[A-Za-z0-9_]+', '[REDACTED]')
    Log-Line ("GH Auth    : ok=" + $ghAuthOk + " :: " + $ghSafe)
}

function Invoke-WingetInstall([string]$pkgId) {
    if (-not $wingetExe) {
        Log-Line ("WARN: winget.exe not available, skipping " + $pkgId)
        return $false
    }
    Log-Line ("Installing via winget: " + $pkgId + " ...")
    & $wingetExe install --id $pkgId -e --silent --accept-package-agreements --accept-source-agreements 2>&1 |
        Select-Object -Last 6 | ForEach-Object { Log-Line ("  " + $_) }
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    return ($LASTEXITCODE -eq 0)
}

# ---- Installations when requested ----
$actionsTaken = @()

if (($Mode -in @('install', 'node')) -and $InstallBase) {
    if (-not $gitExe)  { if (Invoke-WingetInstall 'Git.Git')        { $actionsTaken += 'installed:Git.Git' } }
    if (-not $ghExe)   { if (Invoke-WingetInstall 'GitHub.cli')     { $actionsTaken += 'installed:GitHub.cli' } }
    if (-not $uvExe)   { if (Invoke-WingetInstall 'astral-sh.uv')   { $actionsTaken += 'installed:astral-sh.uv' } }
}

if (($Mode -in @('install', 'node')) -and $InstallTailscale) {
    if (-not $tsExe) {
        if (Invoke-WingetInstall 'Tailscale.Tailscale') { $actionsTaken += 'installed:Tailscale.Tailscale' }
    }
}

if (($Mode -in @('install', 'node')) -and $ExtraWinget) {
    foreach ($rawId in ($ExtraWinget -split ',')) {
        $cleanId = $rawId.Trim()
        if ($cleanId -and ($cleanId -match '^[A-Za-z0-9._-]+$')) {
            if (Invoke-WingetInstall $cleanId) { $actionsTaken += ("installed:" + $cleanId) }
        }
    }
}

# ---- Open-Source PyMOL One-Click Installer ----
if (($Mode -in @('install', 'node')) -and $InstallPyMOL) {
    Log-Line '--- PyMOL Open-Source Setup ---'
    if ($pymolExe -and (Test-Path -LiteralPath $pymolExe)) {
        Log-Line ("PyMOL already present at: " + $pymolExe)
    } else {
        # Ensure Conda/Mamba exists; install Miniforge3 to <bestDrive>:\Miniforge3 if absent
        if (-not $condaExe) {
            $mfRoot = "${bestDrive}\Miniforge3"
            $mfInstaller = Join-Path $env:TEMP 'Miniforge3-Windows-x86_64.exe'
            $mfUrl = 'https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe'
            Log-Line ("Conda/Mamba not found; bootstrapping Miniforge3 into " + $mfRoot + " ...")
            try {
                Invoke-WebRequest -Uri $mfUrl -OutFile $mfInstaller -UseBasicParsing -TimeoutSec 300
                if (Test-Path -LiteralPath $mfInstaller) {
                    $p = Start-Process -FilePath $mfInstaller -ArgumentList @('/InstallationType=JustMe', '/RegisterPython=0', '/S', ("/D=" + $mfRoot)) -Wait -PassThru -WindowStyle Hidden
                    Log-Line ("Miniforge3 installer exited with code " + $p.ExitCode)
                }
            } catch {
                Log-Line ("Miniforge3 direct download failed (" + $_.Exception.Message + "), trying winget...")
                [void](Invoke-WingetInstall 'CondaForge.Miniforge3')
            }
            $condaExe = Find-Tool 'mamba.exe' @("${mfRoot}\Scripts\mamba.exe", "$env:USERPROFILE\miniforge3\Scripts\mamba.exe")
            if (-not $condaExe) {
                $condaExe = Find-Tool 'conda.exe' @("${mfRoot}\Scripts\conda.exe", "$env:USERPROFILE\miniforge3\Scripts\conda.exe")
            }
        }

        if ($condaExe) {
            $pymolPrefix = "${bestDrive}\0apps\PyMOL"
            New-Item -ItemType Directory -Force -Path (Split-Path $pymolPrefix -Parent) | Out-Null
            Log-Line ("Creating isolated PyMOL environment at " + $pymolPrefix + " using " + $condaExe + " ...")
            & $condaExe create -y -p $pymolPrefix -c conda-forge pymol-open-source numpy biopython matplotlib 2>&1 |
                Select-Object -Last 15 | ForEach-Object { Log-Line ("  " + $_) }

            $pymolExe = Find-Tool 'pymol.exe' @("${pymolPrefix}\Library\bin\pymol.exe", "${pymolPrefix}\Scripts\pymol.exe")
            if ($pymolExe) {
                $actionsTaken += 'installed:pymol-open-source'
                Log-Line ("PyMOL installed successfully: " + $pymolExe)
                # Headless verification
                $verOut = (& $pymolExe -cq -d "print('PYMOL_VERIFIED', cmd.get_version()[0]); quit" 2>&1) -join ' '
                Log-Line ("PyMOL verify: " + $verOut)
                # Desktop shortcut
                try {
                    $desk = [Environment]::GetFolderPath('Desktop')
                    if ($desk) {
                        $ws = New-Object -ComObject WScript.Shell
                        $sc = $ws.CreateShortcut((Join-Path $desk 'PyMOL Molecular Viewer.lnk'))
                        $sc.TargetPath = $pymolExe
                        $sc.WorkingDirectory = (Split-Path $pymolExe -Parent)
                        $sc.Description = 'Open-Source PyMOL 3D Molecular Visualization (Arena Desk)'
                        $sc.Save()
                        Log-Line 'Created Desktop shortcut: PyMOL Molecular Viewer.lnk'
                    }
                } catch {}
            } else {
                Log-Line 'WARN: Conda finished but pymol.exe was not located; check network or run winget install Schrodinger.PyMOL'
            }
        } else {
            Log-Line 'WARN: Conda unavailable; falling back to winget Schrodinger.PyMOL...'
            if (Invoke-WingetInstall 'Schrodinger.PyMOL') { $actionsTaken += 'installed:Schrodinger.PyMOL' }
        }
    }
}

# ---- Optional Node Bridge Mode (OpenSSH Server + Awake on AC) ----
if ($Mode -eq 'node' -and $isAdmin) {
    Log-Line '--- Configuring Remote Control Node (OpenSSH + AC Awake) ---'
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction SilentlyContinue
    if ($cap -and $cap.State -ne 'Installed') {
        Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction SilentlyContinue | Out-Null
    }
    Set-Service -Name sshd -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service -Name sshd -ErrorAction SilentlyContinue
    if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue | Out-Null
    }
    & powercfg.exe /change standby-timeout-ac 0 2>&1 | Out-Null
    & powercfg.exe /change hibernate-timeout-ac 0 2>&1 | Out-Null
    $actionsTaken += 'configured:sshd+power'
}

# ---- Save Diagnostic Reports ----
$destDir = if ($OutDir) { $OutDir } else { [Environment]::GetFolderPath('Desktop') }
if (-not $destDir -or -not (Test-Path -LiteralPath $destDir)) { $destDir = $env:TEMP }
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

$txtFile  = Join-Path $destDir ("pc-diag-report-" + $env:COMPUTERNAME + ".txt")
$jsonFile = Join-Path $destDir ("pc-diag-report-" + $env:COMPUTERNAME + ".json")

$summaryObj = [ordered]@{
    generated_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    host         = $env:COMPUTERNAME
    user         = $env:USERNAME
    is_admin     = $isAdmin
    mode         = $Mode
    target_drive = $bestDrive
    os           = $(if ($osInfo) { $osInfo.Caption + ' (' + $osInfo.BuildNumber + ')' } else { '' })
    cpu          = $(if ($cpuInfo) { $cpuInfo.Name.Trim() } else { '' })
    ram_gb       = $ramGb
    gpus         = $gpus
    disks        = $diskSummary
    network      = [ordered]@{ github = $netGithub; conda_forge = $netConda; pypi = $netPypi }
    tools        = [ordered]@{
        git       = $gitExe
        gh        = $ghExe
        gh_authed = $ghAuthOk
        python    = $pyExe
        conda     = $condaExe
        uv        = $uvExe
        node      = $nodeExe
        tailscale = $tsExe
        pymol     = $pymolExe
    }
    actions      = $actionsTaken
}

$reportLines | Set-Content -LiteralPath $txtFile -Encoding UTF8
($summaryObj | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $jsonFile -Encoding UTF8
Log-Line ("Saved report : " + $txtFile)
Log-Line ("Saved JSON   : " + $jsonFile)
exit 0
