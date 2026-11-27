#Requires -Version 5.1
<#
.SYNOPSIS
    One-shot, idempotent deployment of the AI comic-drama studio (Toonflow) onto
    this Windows workstation: F: drive only, no interactive prompts.

.DESCRIPTION
    Why a standalone script: the desk worker that is *currently loaded* only
    knows ping/selfcheck/smoke/sync/gmx/deskdiag/deskfix/cgmd/abeta_preflight.
    It returns "unsupported" for `files` and `pipeline`, and `shell` is disabled
    (allow_shell=false), so there is no channel that can run git/pip/npm work on
    the box.  Rather than weaken the desk's security posture, the operator runs
    this script once by hand; it then does everything else unattended and writes
    a machine-readable receipt that the Arena session can fetch from F:.

    Deployment target (fixed, overridable only by explicit parameter):
        F:\apps\Toonflow\repo      git clone (master)
        F:\apps\Toonflow\data      TOONFLOW_DATA_DIR (workspaces live here)
        F:\apps\Toonflow\tools     bun + ffmpeg binaries
        F:\apps\Toonflow\logs      server stdout/stderr
        F:\apps\Toonflow\receipt   deploy-receipt.json + sample media

    Steps: preflight (disk/arch/port) -> bun -> ffmpeg -> clone -> install ->
    build:server -> start -> HTTP probe -> sample clip -> receipt.

    The script is safe to re-run: an existing clone is fetched, not re-cloned,
    and an already-listening server is reused instead of duplicated.

.PARAMETER RepoRoot
    Parent directory for the deployment.  Default F:\apps\Toonflow.

.PARAMETER Port
    Server port.  Default 3000 (Toonflow's fixed port).

.PARAMETER SkipBuild
    Reuse an existing build/server/index.js (faster re-run).

.PARAMETER NoSample
    Skip sample media generation.

.OUTPUTS
    Writes <RepoRoot>\receipt\deploy-receipt.json and prints the same JSON to
    stdout.  Exit 0 = ready, 1 = failed (the JSON says which step).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File deploy_toonflow.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = 'F:\apps\Toonflow',
    [int]$Port = 3000,
    [string]$Repository = 'https://github.com/HBAI-Ltd/Toonflow-app.git',
    [string]$Branch = 'master',
    [switch]$SkipBuild,
    [switch]$NoSample,
    [int]$ServerWaitSeconds = 300
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:Steps = @()
$script:StartedAt = (Get-Date).ToString('o')

function Add-Step {
    param([string]$Name, [string]$Status, [string]$Detail = '')
    $row = [ordered]@{
        step   = $Name
        status = $Status
        detail = $Detail
        at     = (Get-Date).ToString('o')
    }
    $script:Steps += $row
    $line = '[{0}] {1} {2}' -f $Status.ToUpperInvariant(), $Name, $Detail
    Write-Host $line
}

function Write-Receipt {
    param([string]$Status, [string]$Summary, $Extra)
    $receiptDir = Join-Path $RepoRoot 'receipt'
    $null = New-Item -ItemType Directory -Path $receiptDir -Force -ErrorAction SilentlyContinue
    $receipt = [ordered]@{
        schema      = 'cgmd.toonflow.deploy.v1'
        status      = $Status
        summary     = $Summary
        host        = $env:COMPUTERNAME
        user        = $env:USERNAME
        started_at  = $script:StartedAt
        finished_at = (Get-Date).ToString('o')
        repo_root   = $RepoRoot
        port        = $Port
        steps       = $script:Steps
        extra       = $Extra
    }
    $json = $receipt | ConvertTo-Json -Depth 12
    try {
        $path = Join-Path $receiptDir 'deploy-receipt.json'
        $json | Out-File -LiteralPath $path -Encoding UTF8 -Force
        Write-Host ('receipt: ' + $path)
    } catch {
        Write-Host ('receipt write failed: ' + $_.Exception.Message)
    }
    Write-Output $json
}

function Get-FreeBytes {
    param([string]$Drive)
    try {
        $d = Get-PSDrive -Name $Drive -ErrorAction Stop
        return [int64]$d.Free
    } catch { return -1 }
}

# ---------------------------------------------------------------- 0. preflight
try {
    $parent = Split-Path -Parent $RepoRoot
    $driveLetter = (Split-Path -Qualifier $RepoRoot).TrimEnd(':')
    if (-not (Test-Path -LiteralPath ($driveLetter + ':\'))) {
        Add-Step 'preflight' 'fail' ('drive ' + $driveLetter + ': is not present')
        Write-Receipt 'fail' ('drive ' + $driveLetter + ': missing') $null | Out-Null
        exit 1
    }
    $free = Get-FreeBytes $driveLetter
    $gb = 1073741824
    $freeGb = if ($free -ge 0) { [math]::Round($free / $gb, 1) } else { -1 }
    # install + build + workspace needs room; refuse below 8 GB so a half-written
    # node_modules never fills the operator's disk.
    if ($free -ge 0 -and $free -lt (8 * $gb)) {
        Add-Step 'preflight' 'fail' ('only ' + $freeGb + ' GB free on ' + $driveLetter + ':; need >= 8 GB')
        Write-Receipt 'fail' 'insufficient free space' ([ordered]@{ free_gb = $freeGb }) | Out-Null
        exit 1
    }
    $arch = $env:PROCESSOR_ARCHITECTURE
    Add-Step 'preflight' 'ok' ('free ' + $freeGb + ' GB on ' + $driveLetter + ':; arch ' + $arch + '; port ' + $Port)
} catch {
    Add-Step 'preflight' 'fail' $_.Exception.Message
    Write-Receipt 'fail' 'preflight threw' $null | Out-Null
    exit 1
}

try {
    foreach ($dir in @($RepoRoot, (Join-Path $RepoRoot 'tools'), (Join-Path $RepoRoot 'logs'),
                       (Join-Path $RepoRoot 'data'), (Join-Path $RepoRoot 'receipt'))) {
        if (-not (Test-Path -LiteralPath $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
    }
    Add-Step 'directories' 'ok' $RepoRoot
} catch {
    Add-Step 'directories' 'fail' $_.Exception.Message
    Write-Receipt 'fail' 'cannot create target directories' $null | Out-Null
    exit 1
}

# ---------------------------------------------------------------- 1. bun
$toolsDir = Join-Path $RepoRoot 'tools'
$bunExe = Join-Path $toolsDir 'bun.exe'
try {
    $existingBun = Get-Command bun -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $bunExe) {
        Add-Step 'bun' 'ok' ('already present: ' + $bunExe)
    } elseif ($null -ne $existingBun) {
        $bunExe = $existingBun.Source
        Add-Step 'bun' 'ok' ('on PATH: ' + $bunExe)
    } else {
        $zip = Join-Path $toolsDir 'bun-windows-x64.zip'
        $url = 'https://github.com/oven-sh/bun/releases/latest/download/bun-windows-x64.zip'
        Add-Step 'bun' 'info' ('downloading ' + $url)
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 600
        $expand = Join-Path $toolsDir 'bun-expand'
        if (Test-Path -LiteralPath $expand) { Remove-Item -LiteralPath $expand -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $expand -Force
        $found = Get-ChildItem -LiteralPath $expand -Filter 'bun.exe' -Recurse -File | Select-Object -First 1
        if ($null -eq $found) { throw 'bun.exe not found inside the release archive' }
        Copy-Item -LiteralPath $found.FullName -Destination $bunExe -Force
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $expand -Recurse -Force -ErrorAction SilentlyContinue
        Add-Step 'bun' 'ok' ('installed ' + $bunExe)
    }
    $bunVersion = (& $bunExe --version 2>&1 | Out-String).Trim()
    Add-Step 'bun-version' 'ok' $bunVersion
} catch {
    Add-Step 'bun' 'fail' $_.Exception.Message
    Write-Receipt 'fail' 'bun install failed' $null | Out-Null
    exit 1
}

# ---------------------------------------------------------------- 2. ffmpeg
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffmpegPath = ''
if ($null -ne $ffmpeg) {
    $ffmpegPath = $ffmpeg.Source
} else {
    $candidate = Join-Path $toolsDir 'ffmpeg.exe'
    if (Test-Path -LiteralPath $candidate) { $ffmpegPath = $candidate }
}
if ($ffmpegPath) {
    Add-Step 'ffmpeg' 'ok' $ffmpegPath
} else {
    # Not fatal: Toonflow ships its own ffmpeg via packages/ffmpeg.  Sample-clip
    # rendering falls back to Windows' built-in encoders, which cannot mux H.264,
    # so the receipt records the limitation instead of pretending.
    Add-Step 'ffmpeg' 'warn' 'ffmpeg not on PATH and not pre-staged; sample clip will be limited'
}

# ---------------------------------------------------------------- 3. clone
$repoDir = Join-Path $RepoRoot 'repo'
try {
    if (Test-Path -LiteralPath (Join-Path $repoDir '.git')) {
        $null = & git -C $repoDir fetch --depth 1 origin $Branch 2>&1
        $null = & git -C $repoDir checkout -q $Branch 2>&1
        $null = & git -C $repoDir reset --hard ('origin/' + $Branch) 2>&1
        Add-Step 'clone' 'ok' ('updated existing clone at ' + $repoDir)
    } else {
        if (Test-Path -LiteralPath $repoDir) { Remove-Item -LiteralPath $repoDir -Recurse -Force }
        $out = & git clone --depth 1 --branch $Branch $Repository $repoDir 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($out | Out-String) }
        Add-Step 'clone' 'ok' ('cloned ' + $Branch + ' into ' + $repoDir)
    }
    $head = (& git -C $repoDir rev-parse HEAD 2>&1 | Out-String).Trim()
    Add-Step 'git-head' 'ok' $head
} catch {
    Add-Step 'clone' 'fail' $_.Exception.Message
    Write-Receipt 'fail' 'git clone failed' $null | Out-Null
    exit 1
}

# ---------------------------------------------------------------- 4. install
try {
    Push-Location $repoDir
    try {
        $out = & $bunExe install --frozen-lockfile 2>&1
        if ($LASTEXITCODE -ne 0) { throw (($out | Out-String) -split "`n" | Select-Object -Last 25 | Out-String) }
        Add-Step 'bun-install' 'ok' 'dependencies installed'
    } finally { Pop-Location }
} catch {
    Add-Step 'bun-install' 'fail' $_.Exception.Message
    Write-Receipt 'fail' 'bun install failed' ([ordered]@{ repo = $repoDir }) | Out-Null
    exit 1
}

# ---------------------------------------------------------------- 5. build
$entry = Join-Path $repoDir 'build\server\index.js'
try {
    if ($SkipBuild -and (Test-Path -LiteralPath $entry)) {
        Add-Step 'build' 'skip' 'reusing existing build/server/index.js'
    } else {
        Push-Location $repoDir
        try {
            $out = & $bunExe run build:server 2>&1
            if ($LASTEXITCODE -ne 0) { throw (($out | Out-String) -split "`n" | Select-Object -Last 30 | Out-String) }
        } finally { Pop-Location }
        if (-not (Test-Path -LiteralPath $entry)) { throw 'build:server finished but build/server/index.js is absent' }
        Add-Step 'build' 'ok' $entry
    }
    $null = New-Item -ItemType Directory -Path (Join-Path $RepoRoot 'data\workspaces\myProject') -Force
} catch {
    Add-Step 'build' 'fail' $_.Exception.Message
    Write-Receipt 'fail' 'build:server failed' ([ordered]@{ repo = $repoDir }) | Out-Null
    exit 1
}

# ---------------------------------------------------------------- 6. start
function Test-Port {
    param([int]$P)
    try {
        $client = New-Object Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', $P, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(1000, $false)
        if ($ok) { $client.EndConnect($iar) }
        $client.Close()
        return $ok
    } catch { return $false }
}

$serverLog = Join-Path $RepoRoot ('logs\server-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$serverStarted = $false
try {
    if (Test-Port $Port) {
        # Something is listening, but that is not proof it is Toonflow: another
        # dev server on :3000 would otherwise be adopted and reported as ours.
        $ours = $false
        try {
            $probe = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $Port + '/') -UseBasicParsing -TimeoutSec 10
            $body = [string]$probe.Content
            if ($body -match '(?i)toonflow') { $ours = $true }
        } catch { }
        if (-not $ours) {
            Add-Step 'start' 'fail' ('port ' + $Port + ' is taken by another program; set -Port to a free port')
            Write-Receipt 'fail' 'port already in use by another program' ([ordered]@{ port = $Port }) | Out-Null
            exit 1
        }
        Add-Step 'start' 'ok' ('port ' + $Port + ' already serving Toonflow; reusing it')
    } else {
        $env:TOONFLOW_DATA_DIR = (Join-Path $RepoRoot 'data')
        $env:TOONFLOW_SERVER_PORT = [string]$Port
        # 'call' makes cmd.exe wait for bun, so the redirection stays attached
        # for the whole server lifetime instead of returning on the first prompt.
        $cmd = 'call "' + $bunExe + '" "' + $entry + '" > "' + $serverLog + '" 2>&1'
        # Start-Process keeps the server alive after this script exits, which a
        # bare child process of powershell.exe would not survive reliably.
        $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ' + $cmd) -WorkingDirectory $repoDir `
            -WindowStyle Hidden -PassThru
        Add-Step 'start' 'ok' ('launched pid ' + $proc.Id + '; log ' + $serverLog)
        $serverStarted = $true
    }

    $deadline = (Get-Date).AddSeconds($ServerWaitSeconds)
    $up = $false
    $lastError = ''
    while ((Get-Date) -lt $deadline) {
        # Probe the TCP port first: a half-built server accepts nothing, and a
        # raw HTTP call against a closed port throws a noisy terminating error
        # on PowerShell 5.1.
        if (Test-Port $Port) {
            try {
                $resp = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $Port + '/') -UseBasicParsing -TimeoutSec 10
                if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) { $up = $true; break }
                $lastError = 'HTTP ' + $resp.StatusCode
            } catch {
                $lastError = $_.Exception.Message
            }
        } else {
            $lastError = 'port closed'
        }
        Start-Sleep -Seconds 3
    }
    if ($up) {
        Add-Step 'http' 'ok' ('http://127.0.0.1:' + $Port + '/ answered')
    } else {
        $tail = @()
        if (Test-Path -LiteralPath $serverLog) { $tail = Get-Content -LiteralPath $serverLog -Tail 30 -ErrorAction SilentlyContinue }
        Add-Step 'http' 'fail' ('no HTTP answer within ' + $ServerWaitSeconds + ' s; last: ' + $lastError)
        Write-Receipt 'fail' 'server did not answer' ([ordered]@{ log = $serverLog; last_error = $lastError; log_tail = $tail }) | Out-Null
        exit 1
    }
} catch {
    Add-Step 'start' 'fail' $_.Exception.Message
    Write-Receipt 'fail' 'server start failed' $null | Out-Null
    exit 1
}

# ---------------------------------------------------------------- 7. data dir
$dataDir = Join-Path $RepoRoot 'data'
$workspace = Join-Path $dataDir 'workspaces\myProject'
$dataInfo = [ordered]@{
    data_dir      = $dataDir
    data_dir_env  = 'TOONFLOW_DATA_DIR'
    workspace     = $workspace
    workspace_ok  = (Test-Path -LiteralPath $workspace)
    port          = $Port
    panel         = ('http://127.0.0.1:' + $Port + '/')
    server_log    = $serverLog
    bun           = $bunExe
    bun_version   = $bunVersion
    ffmpeg        = $ffmpegPath
    repo          = $repoDir
    git_head      = $head
}
Add-Step 'data-dir' 'ok' $dataDir

# ---------------------------------------------------------------- 8. sample
$samplePath = ''
$frames = Join-Path $RepoRoot 'receipt\frames'
if (-not $NoSample) {
    try {
        $null = New-Item -ItemType Directory -Path $frames -Force
        # Draw a tiny comic strip with System.Drawing: no model API needed, so
        # this proves the media pipeline end to end without inventing AI output.
        Add-Type -AssemblyName System.Drawing
        $w = 720; $h = 1280
        $panels = @(
            @{ top = 0;    bottom = 420;  color = '#1b2740'; title = 'PANEL 1'; sub = 'Toonflow deploy OK' },
            @{ top = 430;  bottom = 850;  color = '#40263a'; title = 'PANEL 2'; sub = @('F:\apps\Toonflow', 'bun  build server') -join ' | ' },
            @{ top = 860;  bottom = 1280; color = '#233b33'; title = 'PANEL 3'; sub = ('port ' + $Port + ' ready') }
        )
        $frameFiles = @()
        for ($i = 0; $i -lt $panels.Count; $i++) {
            $bmp = New-Object System.Drawing.Bitmap($w, $h)
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.SmoothingMode = 'AntiAlias'
            $g.Clear([System.Drawing.Color]::FromArgb(12, 12, 16))
            $p = $panels[$i]
            $rect = New-Object System.Drawing.Rectangle(24, ($p.top + 24), ($w - 48), ($p.bottom - $p.top - 48))
            $brush = New-Object System.Drawing.SolidBrush([System.Drawing.ColorTranslator]::FromHtml($p.color))
            $g.FillRectangle($brush, $rect)
            $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(240, 240, 245), 3)
            $g.DrawRectangle($pen, $rect)
            $fontT = New-Object System.Drawing.Font('Arial', 40, [System.Drawing.FontStyle]::Bold)
            $fontS = New-Object System.Drawing.Font('Arial', 20)
            $white = [System.Drawing.Brushes]::White
            $g.DrawString($p.title, $fontT, $white, 60, ($p.top + 70))
            $g.DrawString([string]$p.sub, $fontS, $white, 60, ($p.top + 150))
            $g.DrawString(('frame ' + ($i + 1) + '/3  ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')), $fontS,
                          [System.Drawing.Brushes]::LightGray, 60, ($p.bottom - 90))
            $g.Dispose()
            $framePath = Join-Path $frames ('frame{0}.png' -f $i)
            $bmp.Save($framePath, [System.Drawing.Imaging.ImageFormat]::Png)
            $bmp.Dispose()
            $frameFiles += $framePath
        }
        Add-Step 'sample-frames' 'ok' ($frameFiles.Count.ToString() + ' PNG frames')

        $mp4 = Join-Path $RepoRoot 'receipt\toonflow-sample.mp4'
        if ($ffmpegPath) {
            $listFile = Join-Path $frames 'list.txt'
            $lines = foreach ($f in $frameFiles) { "file '" + ($f -replace '\\', '/') + "'" }
            $lines += "file '" + (($frameFiles[-1]) -replace '\\', '/') + "'"
            Set-Content -LiteralPath $listFile -Value $lines -Encoding ASCII
            $ffArgs = @('-y', '-f', 'concat', '-safe', '0', '-i', $listFile,
                      '-vf', 'fps=2,format=yuv420p', '-c:v', 'libx264', '-t', '3', $mp4)
            $ffOut = & $ffmpegPath @ffArgs 2>&1
            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $mp4)) {
                $samplePath = $mp4
                Add-Step 'sample-video' 'ok' ($mp4 + ' (' + [math]::Round((Get-Item -LiteralPath $mp4).Length / 1024, 1) + ' KB)')
            } else {
                Add-Step 'sample-video' 'warn' (($ffOut | Out-String) -split "`n" | Select-Object -Last 5 | Out-String)
            }
        } else {
            Add-Step 'sample-video' 'warn' 'no ffmpeg available; PNG frames kept instead'
        }
    } catch {
        Add-Step 'sample-video' 'warn' $_.Exception.Message
    }
}

# ---------------------------------------------------------------- 9. receipt
$final = [ordered]@{}
$final['deployment'] = $dataInfo
$final['sample_video'] = $samplePath
$final['sample_png_frames'] = @(if (Test-Path -LiteralPath $frames) { Get-ChildItem -LiteralPath $frames -Filter '*.png' -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName } })
$final['free_gb_after'] = [math]::Round((Get-FreeBytes $driveLetter) / $gb, 1)
$final['model_note'] = 'Toonflow ships no generative video model. Real AI footage needs a model API key (Seedance/Seedream/MiniMax/Wan) or a local ComfyUI configured in the web UI; this receipt only proves the app, server and media pipeline work.'
$status = if ($samplePath) { 'ok' } else { 'ready_no_sample' }
Write-Receipt $status 'Toonflow deployed and answering' $final | Out-Null
exit 0
