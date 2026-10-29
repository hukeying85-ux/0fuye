#Requires -Version 5.1
# deploy.ps1 - Deploy Arena Desk v2.1 Native Desktop Edition to E:\0apps\ArenaDesk.
# Protects git-sync-hub strictly; compiles ArenaDesk.exe with custom ArenaDesk.ico;
# deploys Lark-Formatter headless bridge, multi-session coord, personal hub, and 3-account gh auth;
# supports -LaunchBootDemo to showcase the boot animation (#boot) live on desktop.

param(
    [switch]$NoOpenWindow,
    [switch]$LaunchBootDemo,
    [switch]$OpenMainWindow,
    [switch]$SkipAutoHeal
)

$ErrorActionPreference = 'Stop'
$driveRoots = @('C:\', 'D:\', 'E:\', 'F:\', 'G:\') | Where-Object { Test-Path -LiteralPath $_ }
$root = $null
foreach ($drv in $driveRoots) {
    if (Test-Path -LiteralPath (Join-Path $drv '0apps\ArenaDesk')) { $root = (Join-Path $drv '0apps\ArenaDesk'); break }
}
if (-not $root) { $root = 'C:\0apps\ArenaDesk' }
$appDrive = ($root.Substring(0, 2))

# Resolve a legacy "E:\..." path onto a drive this machine actually has.  The
# reference laptop had an E: drive; the GPU workstation only has C:/F:, so
# hardcoded E: paths silently found nothing there.
function Resolve-AnyDrive {
    param([string]$Path)
    if (-not $Path) { return $null }
    if (Test-Path -LiteralPath $Path) { return $Path }
    if ($Path -match '^[A-Za-z]:\\(.*)$') {
        $tail = $Matches[1]
        foreach ($drv in $driveRoots) {
            $candidate = Join-Path $drv $tail
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return $null
}
New-Item -ItemType Directory -Force "$root\data", "$root\assets", "$root\media", "$root\samples", "$root\auth" | Out-Null
$verMarker = Join-Path "$root\data" 'deployed-version.txt'
$prevDeployedVersion = ''
if (Test-Path -LiteralPath $verMarker) {
    $prevDeployedVersion = (Get-Content -LiteralPath $verMarker -Raw -ErrorAction SilentlyContinue).Trim()
}

# Stop only Arena Desk's own panel service while updating files (NEVER touch git-sync-hub)
$old = Get-ScheduledTask -TaskName 'arena-desk-panel' -TaskPath '\' -ErrorAction SilentlyContinue
if ($old) { Stop-ScheduledTask -TaskName 'arena-desk-panel' -TaskPath '\' -ErrorAction SilentlyContinue }
try {
    $oldPy = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'ArenaDesk[\\/]+server\.py' })
    foreach ($op in $oldPy) {
        Stop-Process -Id $op.ProcessId -Force -ErrorAction SilentlyContinue
    }
} catch {}

# Stop existing tray instance; keep active cloudflared tunnel alive so mobile HTTPS URL does not rotate on background sync
Get-Process -Name 'ArenaDesk' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$hadOpenWindow = $false
$isVersionUpgrade = ($prevDeployedVersion -ne '2.8.0')
if ($isVersionUpgrade -or $LaunchBootDemo -or $OpenMainWindow) {
    try {
        $appWins = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe' OR Name='chrome.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'ArenaDesk[\\/]+data[\\/]+desktop-window-profile' })
        if ($appWins.Count -gt 0) {
            $hadOpenWindow = $true
            foreach ($aw in $appWins) {
                Stop-Process -Id $aw.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {}
    # Migrate appearance.json to v2.5.0 dsh-video-skin ultra-transparent video skin + boot audio
    $appJsonPath = Join-Path "$root\data" 'appearance.json'
    if (Test-Path -LiteralPath $appJsonPath) {
        try {
            $ap = Get-Content -LiteralPath $appJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($ap -and $isVersionUpgrade) {
                $ap | Add-Member -NotePropertyName 'appearance_schema_v' -NotePropertyValue 25 -Force
                $ap | Add-Member -NotePropertyName 'theme' -NotePropertyValue 'sakura-mist' -Force
                $ap | Add-Member -NotePropertyName 'builtin_wallpaper' -NotePropertyValue 'dsh-bg.mp4' -Force
                $ap | Add-Member -NotePropertyName 'boot_video' -NotePropertyValue 'dsh-boot.mp4' -Force
                $ap | Add-Member -NotePropertyName 'custom_media_id' -NotePropertyValue '' -Force
                $ap | Add-Member -NotePropertyName 'surface_opacity' -NotePropertyValue 0.14 -Force
                $ap | Add-Member -NotePropertyName 'veil_opacity' -NotePropertyValue 0.10 -Force
                $ap | Add-Member -NotePropertyName 'glass_blur' -NotePropertyValue 4 -Force
                $ap | Add-Member -NotePropertyName 'boot_enabled' -NotePropertyValue $true -Force
                $ap | Add-Member -NotePropertyName 'boot_sound' -NotePropertyValue $true -Force
                ($ap | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $appJsonPath -Encoding UTF8
            }
        } catch {}
    }
    # Scrub legacy pre-v2.5 school-name strings in persisted data/*.json files on host
    $uLDUniv = [string][char]0x9C81 + [string][char]0x4E1C + [string][char]0x5927 + [string][char]0x5B66
    $uLD     = [string][char]0x9C81 + [string][char]0x4E1C
    $uUni    = [string][char]0x9AD8 + [string][char]0x6821
    Get-ChildItem -LiteralPath "$root\data" -Filter '*.json' -File -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $jt = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
            if ($jt) {
                $nj = $jt.Replace($uLDUniv, $uUni).Replace($uLD, '').Replace('ludong_master_2026', 'academic_master_2026').Replace('ludong_sample_thesis', 'master_sample_thesis').Replace('ldu-beacon-', 'arena-beacon-').Replace('Ludong', 'Academic').Replace('ludong', 'academic')
                if ($nj -ne $jt) {
                    Set-Content -LiteralPath $_.FullName -Value $nj -Encoding UTF8
                }
            }
        } catch {}
    }
}
Start-Sleep -Milliseconds 800

$panelFiles = @(
    'server.py', 'desktop_ops.py', 'thesis_ops.py', 'session_coord.py', 'qr_svg.py',
    'war_room.py', 'ai_quota_hub.py', 'federation_hub.py', 'media_cua_hub.py', 'tri_account_console.py',
    'catalog.json', 'personal_hub.json', 'build_icon.py',
    'ArenaDesk.cs', 'GitCredSilent.cs', 'ArenaSilentRun.cs',
    'index.html', 'style.css', 'app.js',
    'control.ps1', 'launch_panel.ps1', 'launch_dsh.ps1', 'launch_pet.ps1',
    'pet_toggle.ps1', 'open_dsh.ps1', 'enable_private_hub.ps1',
    'notion-links.json', 'software-registry.json', 'README.md'
)
foreach ($name in $panelFiles) {
    $src = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $root $name) -Force
    }
}

# Copy assets (icon.svg, whale.svg, ArenaDesk.ico, icon-256.png, icon-64.png)
$srcAssets = Join-Path $PSScriptRoot 'assets'
if (Test-Path -LiteralPath $srcAssets) {
    Get-ChildItem -LiteralPath $srcAssets -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path "$root\assets" $_.Name) -Force
    }
}

# Copy bundled sample thesis for instant 1-click formatting test (and purge legacy school-named sample)
$legacySample = Join-Path "$root\samples" '*ludong*'
Remove-Item -Path $legacySample -Force -ErrorAction SilentlyContinue
$srcSamples = Join-Path $PSScriptRoot 'samples'
if (Test-Path -LiteralPath $srcSamples) {
    Get-ChildItem -LiteralPath $srcSamples -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path "$root\samples" $_.Name) -Force
    }
}

# Copy helper and multi-account auth scripts so standalone E:\0apps\ArenaDesk is self-contained
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
foreach ($pair in @(
    @{ s = (Join-Path $repoRoot 'code\bootstrap\pc-diag-install.ps1'); d = (Join-Path $root 'pc-diag-install.ps1') },
    @{ s = (Join-Path $repoRoot 'code\connect\hpc.ps1');               d = (Join-Path $root 'hpc.ps1') },
    @{ s = (Join-Path $repoRoot 'code\connect\free_mobile_tunnel.ps1');d = (Join-Path $root 'free_mobile_tunnel.ps1') },
    @{ s = (Join-Path $repoRoot 'code\connect\setup_ad_dual_mesh.ps1');d = (Join-Path $root 'setup_ad_dual_mesh.ps1') },
    @{ s = (Join-Path $repoRoot 'code\connect\setup_media_and_cua.ps1');d = (Join-Path $root 'setup_media_and_cua.ps1') },
    @{ s = (Join-Path $repoRoot 'code\verify_when_back.ps1');          d = (Join-Path $root 'verify_when_back.ps1') },
    @{ s = (Join-Path $repoRoot 'code\federation\node_agent.py');      d = (Join-Path $root 'node_agent.py') },
    @{ s = (Join-Path $repoRoot 'code\cua\local_cua_guard.py');        d = (Join-Path $root 'local_cua_guard.py') },
    @{ s = (Join-Path $repoRoot 'auth.ps1');                           d = (Join-Path $root 'auth.ps1') },
    @{ s = (Join-Path $repoRoot 'code\auth\setup_multi_gh.py');        d = (Join-Path "$root\auth" 'setup_multi_gh.py') },
    @{ s = (Join-Path $repoRoot 'code\auth\connect_hukeying_gh.ps1');  d = (Join-Path "$root\auth" 'connect_hukeying_gh.ps1') }
)) {
    if (Test-Path -LiteralPath $pair.s) {
        Copy-Item -LiteralPath $pair.s -Destination $pair.d -Force
    }
}

$jbSrc = @(
    (Join-Path $PSScriptRoot 'jobbeacon_src\jobbeacon'),
    (Join-Path $repoRoot 'projects\jobbeacon\src\jobbeacon')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($jbSrc) {
    $jbDst = Join-Path $root 'jobbeacon_src\jobbeacon'
    New-Item -ItemType Directory -Force -Path $jbDst | Out-Null
    Copy-Item -Path (Join-Path $jbSrc '*') -Destination $jbDst -Recurse -Force
}

# Ensure standalone cloudflared.exe is available in E:\0apps\ArenaDesk\bin for 1-click Android HTTPS WebAPK installation
$cfBinDir = Join-Path $root 'bin'
New-Item -ItemType Directory -Force -Path $cfBinDir | Out-Null
$cfLocal = Join-Path $cfBinDir 'cloudflared.exe'
if ((-not (Test-Path -LiteralPath $cfLocal)) -and (-not (Get-Command 'cloudflared.exe' -ErrorAction SilentlyContinue))) {
    $cfUrl = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
    $cfTmp = Join-Path $cfBinDir 'cloudflared.exe.tmp'
    try {
        & curl.exe -sSL --connect-timeout 8 --max-time 32 -x 'socks5h://127.0.0.1:10808' -o $cfTmp $cfUrl 2>$null
        if ((-not (Test-Path -LiteralPath $cfTmp)) -or ((Get-Item -LiteralPath $cfTmp).Length -lt 10000000)) {
            & curl.exe -sSL --connect-timeout 8 --max-time 32 -o $cfTmp $cfUrl 2>$null
        }
        if ((Test-Path -LiteralPath $cfTmp) -and ((Get-Item -LiteralPath $cfTmp).Length -gt 10000000)) {
            Move-Item -LiteralPath $cfTmp -Destination $cfLocal -Force
        } else {
            Remove-Item -LiteralPath $cfTmp -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Remove-Item -LiteralPath $cfTmp -Force -ErrorAction SilentlyContinue
    }
}

# Ensure real working Python exe (skip WindowsApps Store stub; auto-provision portable Python 3.11 if missing!)
function Test-WorkingPython([string]$cand) {
    if ([string]::IsNullOrWhiteSpace($cand) -or ($cand -match 'WindowsApps')) { return $false }
    if (-not (Test-Path -LiteralPath $cand)) { return $false }
    try {
        $probe = (& $cand -c "import http.server; print('ARENA_PY_OK')" 2>$null) -join ''
        return ($LASTEXITCODE -eq 0 -and ($probe -match 'ARENA_PY_OK'))
    } catch {
        return $false
    }
}

$pyCands = @(
    (Join-Path $root 'python\python.exe'),
    'E:\spider\python.exe',
    'C:\ProgramData\Miniforge3\python.exe',
    'C:\ProgramData\anaconda3\python.exe',
    'C:\ProgramData\miniconda3\python.exe',
    "$env:USERPROFILE\Miniforge3\python.exe",
    "$env:USERPROFILE\miniconda3\python.exe",
    "$env:USERPROFILE\anaconda3\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    'D:\Miniforge3\python.exe',
    'D:\miniconda3\python.exe',
    'D:\anaconda3\python.exe',
    'C:\Python312\python.exe',
    'C:\Python311\python.exe'
)
foreach ($cmdItem in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
    if ($cmdItem.Source -and ($cmdItem.Source -notmatch 'WindowsApps') -and ($pyCands -notcontains $cmdItem.Source)) {
        $pyCands += $cmdItem.Source
    }
}

$pyExe = ''
foreach ($c in $pyCands) {
    if (Test-WorkingPython $c) { $pyExe = $c; break }
}

if (-not $pyExe) {
    $embedDir = Join-Path $root 'python'
    New-Item -ItemType Directory -Force -Path $embedDir | Out-Null
    $zipTmp = Join-Path $embedDir 'py311-embed.zip'
    $mirrors = @(
        'https://repo.huaweicloud.com/python/3.11.9/python-3.11.9-embed-amd64.zip',
        'https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-embed-amd64.zip',
        'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'
    )
    foreach ($u in $mirrors) {
        try {
            & curl.exe -sSL --connect-timeout 8 --max-time 35 -o $zipTmp $u 2>$null
            if ((Test-Path -LiteralPath $zipTmp) -and ((Get-Item -LiteralPath $zipTmp).Length -gt 5000000)) {
                Expand-Archive -LiteralPath $zipTmp -DestinationPath $embedDir -Force
                Remove-Item -LiteralPath $zipTmp -Force -ErrorAction SilentlyContinue
                $pthFile = Join-Path $embedDir 'python311._pth'
                $pthLines = @('python311.zip', '.', '..', '..\jobbeacon_src', 'import site')
                [System.IO.File]::WriteAllLines($pthFile, $pthLines, [System.Text.Encoding]::ASCII)
                $candEmbed = Join-Path $embedDir 'python.exe'
                if (Test-WorkingPython $candEmbed) { $pyExe = $candEmbed; break }
            }
        } catch {}
    }
    Remove-Item -LiteralPath $zipTmp -Force -ErrorAction SilentlyContinue
}

if (-not $pyExe) { $pyExe = 'python.exe' }
$pywExe = $pyExe -replace 'python\.exe$', 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pywExe)) { $pywExe = $pyExe }
[System.IO.File]::WriteAllText((Join-Path "$root\data" 'pythonw-path.txt'), $pywExe, [System.Text.Encoding]::ASCII)

$icoFile = Join-Path $root 'assets\ArenaDesk.ico'
if (-not (Test-Path -LiteralPath $icoFile)) {
    & $pyExe (Join-Path $root 'build_icon.py') | Out-Null
}

# Compile native Win32 GUI executables (/target:winexe -> ZERO console window allocation ever) BEFORE credential provisioning
$csc = Get-ChildItem "$env:SystemRoot\Microsoft.NET\Framework64" -Filter 'csc.exe' -Recurse -ErrorAction SilentlyContinue |
    Sort-Object FullName | Select-Object -Last 1
$exePath       = Join-Path $root 'ArenaDesk.exe'
$credExePath   = Join-Path $root 'git-credential-arenasilent.exe'
$silentRunPath = Join-Path $root 'ArenaSilentRun.exe'
$compiledExe = $false
$compiledCredExe = $false
$compiledSilentRun = $false

if ($csc) {
    $csPath = Join-Path $root 'ArenaDesk.cs'
    $cscArgs = @(
        '/nologo', '/target:winexe', '/optimize+',
        ('/out:' + $exePath), ('/win32icon:' + $icoFile),
        '/r:System.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll',
        $csPath
    )
    & $csc.FullName @cscArgs | Out-Null
    if (($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $exePath)) {
        $compiledExe = $true
    }

    $credCsPath = Join-Path $root 'GitCredSilent.cs'
    if (Test-Path -LiteralPath $credCsPath) {
        $credArgs = @(
            '/nologo', '/target:winexe', '/optimize+',
            ('/out:' + $credExePath),
            '/r:System.dll', '/r:System.Security.dll',
            $credCsPath
        )
        & $csc.FullName @credArgs | Out-Null
        if (($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $credExePath)) {
            $compiledCredExe = $true
        }
    }

    $runCsPath = Join-Path $root 'ArenaSilentRun.cs'
    if (Test-Path -LiteralPath $runCsPath) {
        $runArgs = @(
            '/nologo', '/target:winexe', '/optimize+',
            ('/out:' + $silentRunPath),
            '/r:System.dll',
            $runCsPath
        )
        & $csc.FullName @runArgs | Out-Null
        if (($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $silentRunPath)) {
            $compiledSilentRun = $true
        }
    }
}

# Provision non-destructive multi-account SSH 443 + zero-window git credential helper on primary laptop only
$multiGhPy = Join-Path "$root\auth" 'setup_multi_gh.py'
$multiGhStatus = $null
if (($env:COMPUTERNAME -eq 'LAPTOP-R77M5D6M') -and (Test-Path -LiteralPath $multiGhPy)) {
    try {
        $rawGh = & $pyExe $multiGhPy --provision 2>$null
        if ($rawGh) { $multiGhStatus = ($rawGh | Out-String | ConvertFrom-Json) }
    } catch {}
}

# Parse-check all deployed PowerShell scripts on real Windows
Get-ChildItem $root -Filter '*.ps1' -Recurse | ForEach-Object {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) { throw ($errors | Out-String) }
}

# Disable unused DeepSeek Harness (@deepseek-ai/dsh) tasks cleanly per user design
foreach ($dshTask in @('arena-dsh-web', 'arena-dsh-open')) {
    $dt = Get-ScheduledTask -TaskName $dshTask -TaskPath '\' -ErrorAction SilentlyContinue
    if ($dt) {
        Disable-ScheduledTask -TaskName $dshTask -TaskPath '\' -ErrorAction SilentlyContinue | Out-Null
        Stop-ScheduledTask -TaskName $dshTask -TaskPath '\' -ErrorAction SilentlyContinue
    }
}

# Register Arena Desk background service & login tasks (git-sync-hub is NEVER touched)
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

function Install-Task([string]$n, [string]$exe, [string]$arguments = '', [bool]$start = $false) {
    if ([string]::IsNullOrWhiteSpace($arguments)) {
        $a = New-ScheduledTaskAction -Execute $exe -WorkingDirectory $root
    } else {
        $a = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $root
    }
    Register-ScheduledTask -TaskName $n -TaskPath '\' -Action $a -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    if ($start) { Start-ScheduledTask -TaskName $n -TaskPath '\' }
}

Install-Task 'arena-desk-panel' $pywExe ('"' + $root + '\server.py"') $true
$launchArgs = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $root + '\launch_panel.ps1"'
if ($compiledExe) {
    Install-Task 'arena-desk-open' $exePath ''
    $bootAction = New-ScheduledTaskAction -Execute $exePath -Argument '--boot' -WorkingDirectory $root
    Register-ScheduledTask -TaskName 'arena-desk-boot-demo' -TaskPath '\' -Action $bootAction -Principal $principal -Settings $settings -Force | Out-Null
} else {
    Install-Task 'arena-desk-open' $ps $launchArgs
}

# Mirror universal launcher stub to C:\0apps\ArenaDesk so OneDrive-synced Desktop shortcuts work across all PCs
$universalExe = $exePath
if ($compiledExe -and ($root -ne 'C:\0apps\ArenaDesk')) {
    try {
        New-Item -ItemType Directory -Force -Path 'C:\0apps\ArenaDesk\assets' | Out-Null
        Copy-Item -LiteralPath $exePath -Destination 'C:\0apps\ArenaDesk\ArenaDesk.exe' -Force
        if (Test-Path -LiteralPath $icoFile) {
            Copy-Item -LiteralPath $icoFile -Destination 'C:\0apps\ArenaDesk\assets\ArenaDesk.ico' -Force
        }
        $universalExe = 'C:\0apps\ArenaDesk\ArenaDesk.exe'
    } catch {
        $universalExe = $exePath
    }
}

# Create Desktop & Start Menu shortcuts with custom ArenaDesk.ico across local + OneDrive Desktop folders
$w = New-Object -ComObject WScript.Shell
$shortcutFolders = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path $HOME 'Desktop'),
    (Join-Path $HOME 'OneDrive\Desktop'),
    [Environment]::GetFolderPath('Programs')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
foreach ($folder in $shortcutFolders) {
    $link = $w.CreateShortcut((Join-Path $folder 'Arena Desk.lnk'))
    if ($compiledExe) {
        $link.TargetPath = $universalExe
        $link.Arguments = ''
    } else {
        $link.TargetPath = $ps
        $link.Arguments = $launchArgs
        $link.WindowStyle = 7
    }
    $link.WorkingDirectory = (Split-Path -Parent $universalExe)
    $link.IconLocation = ($icoFile + ',0')
    $link.Description = 'Arena Desk v2.8 Desktop Control Plane'
    $link.Save()
}

# Best-effort LAN firewall rule (Private + Public Wi-Fi profiles) for read-only Mobile PWA companion port 18766
try {
    $fwRule = Get-NetFirewallRule -DisplayName 'ArenaDesk Mobile LAN 18766' -ErrorAction SilentlyContinue
    if (-not $fwRule) {
        New-NetFirewallRule -DisplayName 'ArenaDesk Mobile LAN 18766' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18766 -Profile Any -ErrorAction Stop | Out-Null
    }
} catch {}

$desktop = [Environment]::GetFolderPath('Desktop')
$petLink = $w.CreateShortcut((Join-Path $desktop 'Toggle Desktop Pet.lnk'))
if ($compiledSilentRun) {
    $petLink.TargetPath = $silentRunPath
    $petLink.Arguments = '"' + $root + '\pet_toggle.ps1"'
} else {
    $petLink.TargetPath = $ps
    $petLink.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $root + '\pet_toggle.ps1"'
    $petLink.WindowStyle = 7
}
$petLink.IconLocation = ($icoFile + ',0')
$petLink.Hotkey = 'CTRL+ALT+H'
$petLink.Save()

# Also place quick-connect shortcut for hukeying85-ux GitHub CLI OAuth in ArenaDesk root
$ghLink = $w.CreateShortcut((Join-Path $root 'Connect Hukeying GitHub.lnk'))
$ghLink.TargetPath = $ps
$ghLink.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $root + '\auth\connect_hukeying_gh.ps1"'
$ghLink.WorkingDirectory = $root
$ghLink.IconLocation = ($icoFile + ',0')
$ghLink.Description = 'One-Click GitHub CLI OAuth for hukeying85@gmail.com (Chrome Profile 1)'
$ghLink.Save()

# Hot-enable private repository polling + zero-window silent credential helper on primary laptop only
if ($env:COMPUTERNAME -eq 'LAPTOP-R77M5D6M') {
    try {
        & (Join-Path $root 'enable_private_hub.ps1') | Out-Null
    } catch {}
}

# Keep verified standalone desktop pet task active via GUI-subsystem ArenaSilentRun.exe (ZERO powershell console flash)
$petRoot = Resolve-AnyDrive 'E:\0apps\DSHPet'
$petExe = $null
if ($petRoot) {
    $petExe = Get-ChildItem $petRoot -Filter 'dsh-pet-standalone-webm.exe' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
}
if ($petExe) {
    if ($compiledSilentRun) {
        Install-Task 'arena-desktop-pet' $silentRunPath ('"' + $root + '\launch_pet.ps1"') $true
    } else {
        Install-Task 'arena-desktop-pet' $petExe.FullName '' $true
    }
}

# Migrate jev-chat-analyze & jev-chat-monitor off powershell.exe onto GUI-subsystem pythonw.exe / ArenaSilentRun.exe
try {
    $jevRoot = Resolve-AnyDrive 'E:\0apps\jev-chat-windows'
    $jevPyw  = Join-Path $jevRoot 'venv\Scripts\pythonw.exe'
    $jevAna  = Join-Path $jevRoot 'monitor\auto_analyze.py'
    $jevMon  = Join-Path $jevRoot 'monitor\start_monitor.ps1'
    if ((Test-Path -LiteralPath $jevPyw) -and (Test-Path -LiteralPath $jevAna)) {
        $anaProcs = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match 'auto_analyze\.py' } | Sort-Object CreationDate)
        if ($anaProcs.Count -gt 1) {
            foreach ($dup in ($anaProcs | Select-Object -Skip 1)) {
                Stop-Process -Id $dup.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
        $actAna = New-ScheduledTaskAction -Execute $jevPyw -Argument ('"' + $jevAna + '"') -WorkingDirectory $jevRoot
        Register-ScheduledTask -TaskName 'jev-chat-analyze' -TaskPath '\' -Action $actAna -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        if ($anaProcs.Count -eq 0) {
            Start-ScheduledTask -TaskName 'jev-chat-analyze' -TaskPath '\' -ErrorAction SilentlyContinue
        }
    }
    if ($compiledSilentRun -and (Test-Path -LiteralPath $jevMon)) {
        $actMon = New-ScheduledTaskAction -Execute $silentRunPath -Argument ('"' + $jevMon + '"') -WorkingDirectory $jevRoot
        Register-ScheduledTask -TaskName 'jev-chat-monitor' -TaskPath '\' -Action $actMon -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    }
} catch {}

Start-Sleep -Seconds 3
try {
    $hubTask = Get-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\' -ErrorAction SilentlyContinue
    if ($hubTask) {
        $infSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
        Set-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\' -Settings $infSettings -ErrorAction SilentlyContinue | Out-Null
        if ($hubTask.State -ne 'Running') {
            Start-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\' -ErrorAction SilentlyContinue
        }
    }
} catch {}
if ($env:COMPUTERNAME -eq 'LAPTOP-R77M5D6M') {
    try {
        $epHub = Join-Path $root 'enable_private_hub.ps1'
        if (Test-Path -LiteralPath $epHub) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $epHub | Out-Null
        }
    } catch {}
}

# Detached Win32_Process fallback when Start-ScheduledTask runs inside non-interactive OpenSSH sshd
$httpReady = $false
for ($w = 0; $w -lt 4; $w++) {
    try {
        $b = Invoke-RestMethod 'http://127.0.0.1:18765/api/bootstrap' -TimeoutSec 2
        if ($b.version) { $httpReady = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 600
}
if (-not $httpReady) {
    try {
        $cmdLine = '"' + $pywExe + '" "' + (Join-Path $root 'server.py') + '"'
        Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmdLine; CurrentDirectory = $root } -ErrorAction SilentlyContinue | Out-Null
        for ($w2 = 0; $w2 -lt 10; $w2++) {
            Start-Sleep -Milliseconds 700
            try {
                $b2 = Invoke-RestMethod 'http://127.0.0.1:18765/api/bootstrap' -TimeoutSec 2
                if ($b2.version) { $httpReady = $true; break }
            } catch {}
        }
    } catch {}
}

if ((-not $SkipAutoHeal) -and ($env:COMPUTERNAME -eq 'LAPTOP-R77M5D6M')) {
    try {
        $bootInfo = Invoke-RestMethod 'http://127.0.0.1:18765/api/bootstrap' -TimeoutSec 10
        if ($bootInfo.csrf) {
            Invoke-RestMethod -Uri 'http://127.0.0.1:18765/api/system/auto-heal-4step' -Method Post -Headers @{ 'X-CSRF-Token' = $bootInfo.csrf; 'Origin' = 'http://127.0.0.1:18765' } -Body '{}' -ContentType 'application/json' -TimeoutSec 45 | Out-Null
        }
    } catch {}
}
$r = Invoke-RestMethod 'http://127.0.0.1:18765/api/state' -TimeoutSec 25
$newVer = [string]$r.version
if ($newVer) {
    Set-Content -LiteralPath $verMarker -Value $newVer -Encoding ASCII
}

$bootLaunched = $false
$mainWindowOpened = $false
if (($LaunchBootDemo -or $isVersionUpgrade) -and $compiledExe -and (-not $NoOpenWindow)) {
    try {
        Start-ScheduledTask -TaskName 'arena-desk-boot-demo' -TaskPath '\' -ErrorAction Stop
        $bootLaunched = $true
    } catch {
        try {
            & schtasks.exe /Run /TN 'arena-desk-boot-demo' >$null 2>&1
            $bootLaunched = ($LASTEXITCODE -eq 0)
        } catch {}
    }
} elseif ($OpenMainWindow -or (-not $NoOpenWindow) -or $hadOpenWindow) {
    try {
        Start-ScheduledTask -TaskName 'arena-desk-open' -TaskPath '\' -ErrorAction Stop
        $mainWindowOpened = $true
    } catch {
        try {
            & schtasks.exe /Run /TN 'arena-desk-open' >$null 2>&1
            $mainWindowOpened = ($LASTEXITCODE -eq 0)
        } catch {}
    }
}

@{
    panel_http_ok      = $true
    version            = $r.version
    compiled_exe       = $compiledExe
    compiled_cred_exe  = $compiledCredExe
    compiled_silentrun = $compiledSilentRun
    exe_path           = $(if ($compiledExe) { $exePath } else { '' })
    icon_path          = $icoFile
    thesis_ready       = [bool]$r.thesis.engine_ready
    coord_sessions     = @($r.coord.sessions).Count
    gh_accounts        = @($r.gh_auth.multi_accounts).Count
    boot_launched      = $bootLaunched
    main_window_opened = $mainWindowOpened
    session_count      = @($r.sessions).Count
    tasks              = $r.tasks
    desktop            = $desktop
    hub                = (Get-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\' -ErrorAction SilentlyContinue | Select-Object TaskName, State)
} | ConvertTo-Json -Depth 6 -Compress
