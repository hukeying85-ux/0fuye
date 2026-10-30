#Requires -Version 5.1
<#
.SYNOPSIS
    Tiny LAN endpoint so the laptop can talk to this workstation directly.

.DESCRIPTION
    The git mailbox is the reliable path (it works from anywhere) but it costs
    up to one poll interval.  On the same LAN the laptop should get an answer in
    milliseconds, so this script serves a very small HTTP API over a raw
    TcpListener (no admin rights, no URL ACL, no IIS):

        GET  /health                 liveness + gmx version + gpus
        GET  /status                 last smoke report, heartbeat, disk
        POST /job                    {"kind":"ping|smoke|selfcheck|gmx|pipeline","args":{...}}

    Every answer is the same JSON shape the mailbox uses
    (cgmd.mailbox.result.v1), so one client reads both transports.

    Security: loopback and RFC1918 clients (10/8, 172.16/12, 192.168/16) are
    accepted; anything else needs the token from -Token (or bridge_token in the
    config).  shell jobs stay disabled unless -AllowShell is passed.  A one-time
    firewall rule is needed for other machines to reach the port:

        # once, in an ADMIN PowerShell
        netsh advfirewall firewall add rule name="CGMD bridge" dir=in action=allow protocol=TCP localport=8765

    or run this script once with -OpenFirewall from an elevated prompt.

.PARAMETER Port
    TCP port, default from the config (8765).

.PARAMETER Once
    Serve exactly one request then exit (used by tests).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Invoke-CgmdBridge.ps1
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = '',
    [string]$RepoPath = '',
    [string]$Branch = '',
    [int]$Port = 0,
    [string]$Token = '',
    [int]$MaxJobSeconds = 5400,
    [switch]$AllowShell,
    [switch]$OpenFirewall,
    [switch]$Once,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:StateDir = Join-Path $script:HubRoot 'state'
$script:LogDir = Join-Path $script:HubRoot 'logs'
$script:ScriptDir = $PSScriptRoot
$script:StartedAt = Get-Date
$script:JobsDone = 0

foreach ($dir in @($script:StateDir, $script:LogDir)) {
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

function Write-BridgeLog {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    try {
        $file = Join-Path $script:LogDir ('bridge-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))
        [System.IO.File]::AppendAllText($file, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
    if (-not $Quiet) { Write-Host $line }
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

function Invoke-Captured {
    param([string]$CommandLine, [string]$OutFile = '', [int]$TimeoutSeconds = 600, [string]$WorkingDirectory = '')
    if (-not $OutFile) {
        $OutFile = Join-Path $script:StateDir ('bridge-{0}.log' -f ([guid]::NewGuid().ToString('N').Substring(0, 8)))
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
    if ($match.Success) { return [int]$match.Groups[1].Value }
    if ($text -match 'Fatal error') { return 1 }
    return 0
}

function Get-Tail {
    param([string]$Path, [int]$Count = 30)
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    try {
        return @([System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8) |
                 Where-Object { $_ -ne '' } | Select-Object -Last $Count)
    } catch { return @() }
}

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
        $out = Join-Path $script:StateDir 'bridge-gmx-version.txt'
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
            foreach ($line in @(& $smi.Source '--query-gpu=name,driver_version,memory.total' '--format=csv,noheader')) {
                if ($line -and $line.Trim()) { $gpus += $line.Trim() }
            }
        } catch { }
    }
    return [ordered]@{
        host    = $env:COMPUTERNAME
        gmx     = $gmx
        version = $version
        gpus    = $gpus
        cpus    = [Environment]::ProcessorCount
        uptime_s = [math]::Round(((Get-Date) - $script:StartedAt).TotalSeconds, 1)
        jobs    = $script:JobsDone
    }
}

# ---------------------------------------------------------------------------
# jobs (same result shape as the mailbox: cgmd.mailbox.result.v1)
# ---------------------------------------------------------------------------
$script:GmxAllowList = @(
    '--version', '-version', 'solvate', 'grompp', 'mdrun', 'editconf', 'genion', 'insert-molecules',
    'energy', 'traj', 'check', 'dump', 'select', 'rms', 'distance', 'gyrate', 'make_ndx', 'pdb2gmx',
    'trjconv', 'trjcat', 'convert-tpr', 'genrestr', 'wham', 'sasa', 'hbond', 'density', 'bar', 'view'
)

function New-Result {
    param([string]$Kind, [string]$Status, [string]$Summary, $Detail = $null, [string[]]$Tail = @())
    return [ordered]@{
        schema      = 'cgmd.mailbox.result.v1'
        id          = 'bridge-' + (Get-Date -Format 'yyyyMMddTHHmmss')
        kind        = $Kind
        status      = $Status
        summary     = $Summary
        detail      = $Detail
        logs_tail   = @($Tail)
        worker      = $env:COMPUTERNAME
        transport   = 'lan-bridge'
        finished_at = Get-BeijingStamp
    }
}

function Invoke-BridgeJob {
    param($Request)
    $kind = [string](Get-Property $Request 'kind' 'ping')
    $jobArgs = Get-Property $Request 'args' $null
    $script:JobsDone++
    switch ($kind) {
        'ping' {
            $inventory = Get-QuickInventory
            $inventory['time'] = Get-BeijingStamp
            return New-Result -Kind 'ping' -Status 'ok' `
                -Summary ('{0} alive, gmx {1}' -f $env:COMPUTERNAME, $inventory['version']) -Detail $inventory
        }
        'status' {
            $reportPath = Join-Path $RepoPath 'results\status\gmx_smoke.json'
            $report = Read-JsonFile -Path $reportPath
            $detail = [ordered]@{
                inventory = Get-QuickInventory
                smoke     = $report
                heartbeat = Read-JsonFile -Path (Join-Path $RepoPath 'results\status\hub_heartbeat.json')
            }
            $status = 'ok'
            $summary = 'no smoke report yet'
            if ($null -ne $report) {
                $status = [string](Get-Property $report 'status' 'unknown')
                $summary = ('smoke {0}: {1} ps, {2}' -f $status,
                    (Get-Property $report 'ps_completed' 0),
                    (Get-Property $report 'accelerator' '?'))
            }
            return New-Result -Kind 'status' -Status $status -Summary $summary -Detail $detail
        }
        'smoke' {
            $runner = Join-Path $script:ScriptDir 'Run-Gmx-Native.ps1'
            if (-not (Test-Path -LiteralPath $runner)) {
                return New-Result -Kind 'smoke' -Status 'unsupported' -Summary 'Run-Gmx-Native.ps1 is missing'
            }
            $ps = [double](Get-Property $jobArgs 'ps' 100)
            $gpuId = [int](Get-Property $jobArgs 'gpu_id' 0)
            $out = Join-Path $script:StateDir 'bridge-smoke.log'
            $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $runner + '" -Ps ' + $ps + ' -GpuId ' + $gpuId + ' -Quiet'
            if ($RepoPath) { $line += ' -RepoPath "' + $RepoPath + '"' }
            if ($Branch) { $line += ' -Branch "' + $Branch + '"' }
            $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds ([math]::Min($MaxJobSeconds, 2400))
            $report = Read-JsonFile -Path (Join-Path $RepoPath 'results\status\gmx_smoke.json')
            $status = $(if ($code -eq 0) { 'ok' } else { 'fail' })
            $summary = 'smoke exit ' + $code
            $detail = [ordered]@{ exit_code = $code; report = $report }
            if ($null -ne $report) {
                $status = [string](Get-Property $report 'status' $status)
                $version = ''
                $software = Get-Property $report 'software' $null
                if ($null -ne $software) {
                    $block = Get-Property $software 'gromacs' $null
                    if ($null -ne $block) { $version = [string](Get-Property $block 'version' '') }
                }
                $summary = ('gmx {0}: {1} ps on {2}' -f $version, (Get-Property $report 'ps_completed' 0),
                    (Get-Property $report 'accelerator' '?'))
            }
            return New-Result -Kind 'smoke' -Status $status -Summary $summary -Detail $detail -Tail (Get-Tail -Path $out -Count 20)
        }
        'selfcheck' {
            $script_path = Join-Path $script:ScriptDir 'Test-CgmdHub.ps1'
            if (-not (Test-Path -LiteralPath $script_path)) {
                return New-Result -Kind 'selfcheck' -Status 'unsupported' -Summary 'Test-CgmdHub.ps1 is missing'
            }
            $out = Join-Path $script:StateDir 'bridge-selfcheck.log'
            $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $script_path + '" -Quiet'
            if ($RepoPath) { $line += ' -RepoPath "' + $RepoPath + '"' }
            if ($Branch) { $line += ' -Branch "' + $Branch + '"' }
            $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds ([math]::Min($MaxJobSeconds, 900))
            return New-Result -Kind 'selfcheck' -Status $(if ($code -eq 0) { 'ok' } else { 'fail' }) `
                -Summary ('selfcheck exit ' + $code) -Detail ([ordered]@{ exit_code = $code }) -Tail (Get-Tail -Path $out -Count 25)
        }
        'gmx' {
            $argv = @(Get-Property $jobArgs 'argv' @())
            if ($argv.Count -eq 0) {
                return New-Result -Kind 'gmx' -Status 'unsupported' -Summary 'args.argv is required'
            }
            if ($script:GmxAllowList -notcontains [string]$argv[0]) {
                return New-Result -Kind 'gmx' -Status 'unsupported' -Summary ('gmx subcommand not allowed: ' + $argv[0])
            }
            foreach ($word in $argv) {
                if ($word -match '[;&|<>`]' -or $word -match '\$\(') {
                    return New-Result -Kind 'gmx' -Status 'unsupported' -Summary 'shell metacharacters are not allowed'
                }
            }
            $gmx = Get-GmxBinary
            if (-not $gmx) { return New-Result -Kind 'gmx' -Status 'fail' -Summary 'gmx.exe not found' }
            $scratch = Join-Path $script:StateDir ('bridge-gmx-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
            if (-not (Test-Path -LiteralPath $scratch)) { New-Item -ItemType Directory -Path $scratch -Force | Out-Null }
            $out = Join-Path $scratch 'output.log'
            $quoted = @()
            foreach ($word in $argv) {
                if ($word -match '\s') { $quoted += ('"' + $word + '"') } else { $quoted += $word }
            }
            $code = Invoke-Captured -CommandLine ('"' + $gmx + '" ' + ($quoted -join ' ')) -OutFile $out `
                -TimeoutSeconds ([math]::Min($MaxJobSeconds, 600)) -WorkingDirectory $scratch
            $tail = @(Get-Tail -Path $out -Count 40)
            return New-Result -Kind 'gmx' -Status $(if ($code -eq 0) { 'ok' } else { 'fail' }) `
                -Summary ('gmx {0} exit {1}' -f ($argv -join ' '), $code) `
                -Detail ([ordered]@{ exit_code = $code; argv = $argv; workdir = $scratch }) -Tail $tail
        }
        'pipeline' {
            # Same native runner the mailbox uses: native python (3.12 first) and
            # the native gmx.exe, never WSL.
            $runner = Join-Path $script:ScriptDir 'Invoke-CgmdPipeline.ps1'
            if (-not (Test-Path -LiteralPath $runner)) {
                return New-Result -Kind 'pipeline' -Status 'unsupported' -Summary 'Invoke-CgmdPipeline.ps1 is missing'
            }
            $sequence = [string](Get-Property $jobArgs 'sequence' '')
            if (-not $sequence) {
                return New-Result -Kind 'pipeline' -Status 'unsupported' -Summary 'args.sequence is required'
            }
            $taskId = [string](Get-Property $jobArgs 'task_id' '')
            if (-not $taskId) { $taskId = 'cgmd-' + (Get-Date -Format 'yyyyMMdd-HHmmss') }
            $resultFile = Join-Path $script:StateDir ('pipeline-' + $taskId + '.json')
            $out = Join-Path $script:StateDir ('bridge-pipeline-' + $taskId + '.log')
            $line = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $runner + '"'
            $line += ' -Sequence "' + $sequence + '"'
            $line += ' -Name "' + [string](Get-Property $jobArgs 'name' 'peptide') + '"'
            $line += ' -ProductionNs ' + [double](Get-Property $jobArgs 'production_ns' 100)
            $line += ' -EquilibrationNs ' + [double](Get-Property $jobArgs 'equilibration_ns' 10)
            $line += ' -GpuId ' + [int](Get-Property $jobArgs 'gpu_id' 0)
            $line += ' -TaskId "' + $taskId + '"'
            $line += ' -ResultFile "' + $resultFile + '"'
            if ($RepoPath) { $line += ' -RepoPath "' + $RepoPath + '"' }
            $salt = Get-Property $jobArgs 'salt_M' $null
            if ($null -ne $salt) { $line += (' -SaltM ' + [double]$salt) }
            $temperature = Get-Property $jobArgs 'temperature_K' $null
            if ($null -ne $temperature) { $line += (' -TemperatureK ' + [double]$temperature) }
            if ([bool](Get-Property $jobArgs 'install' $false)) { $line += ' -Install' }
            $requested = [int](Get-Property $jobArgs 'timeout_s' $MaxJobSeconds)
            $limit = [math]::Max(120, [math]::Min($MaxJobSeconds, $requested) - 60)
            $code = Invoke-Captured -CommandLine $line -OutFile $out -TimeoutSeconds $limit -WorkingDirectory $script:StateDir
            $answer = Read-JsonFile -Path $resultFile
            if ($null -eq $answer) {
                return New-Result -Kind 'pipeline' -Status $(if ($code -eq 124) { 'timeout' } else { 'fail' }) `
                    -Summary ('pipeline runner exit {0} without a result file' -f $code) `
                    -Detail ([ordered]@{ exit_code = $code; task_id = $taskId }) -Tail (Get-Tail -Path $out -Count 30)
            }
            return New-Result -Kind 'pipeline' -Status ([string](Get-Property $answer 'status' 'fail')) `
                -Summary ([string](Get-Property $answer 'summary' '')) `
                -Detail (Get-Property $answer 'detail' $null) `
                -Tail (Get-Property $answer 'logs_tail' @(Get-Tail -Path $out -Count 30))
        }
        'shell' {
            if (-not $AllowShell) {
                return New-Result -Kind 'shell' -Status 'unsupported' -Summary 'shell is disabled; restart the bridge with -AllowShell'
            }
            $command = [string](Get-Property $jobArgs 'command' '')
            if (-not $command) { return New-Result -Kind 'shell' -Status 'unsupported' -Summary 'args.command is required' }
            $out = Join-Path $script:StateDir ('bridge-shell-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
            $code = Invoke-Captured -CommandLine $command -OutFile $out -TimeoutSeconds ([math]::Min($MaxJobSeconds, 600))
            return New-Result -Kind 'shell' -Status $(if ($code -eq 0) { 'ok' } else { 'fail' }) `
                -Summary ('shell exit ' + $code) -Detail ([ordered]@{ exit_code = $code }) -Tail (Get-Tail -Path $out -Count 40)
        }
        default {
            return New-Result -Kind $kind -Status 'unsupported' -Summary ('unknown kind: ' + $kind)
        }
    }
}

# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
function Test-ClientAllowed {
    param($Address, [string]$SuppliedToken)
    if ($null -eq $Address) { return $true }
    if ([System.Net.IPAddress]::IsLoopback($Address)) { return $true }
    $bytes = $Address.GetAddressBytes()
    if ($bytes.Length -eq 4) {
        $private = ($bytes[0] -eq 10) -or
                   ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or
                   ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
        if ($private) { return $true }
    }
    if ($Token) { return ($SuppliedToken -eq $Token) }
    return $false
}

function Send-HttpResponse {
    param($Stream, [int]$StatusCode = 200, [string]$Body = '{}')
    $reason = @{ 200 = 'OK'; 400 = 'Bad Request'; 403 = 'Forbidden'; 404 = 'Not Found'; 405 = 'Method Not Allowed' }
    $payload = [System.Text.Encoding]::UTF8.GetBytes($Body)
    $head = 'HTTP/1.1 ' + $StatusCode + ' ' + $reason[$StatusCode] + "\r\n" +
            "Content-Type: application/json; charset=utf-8\r\n" +
            'Content-Length: ' + $payload.Length + "\r\n" +
            "Connection: close\r\n" +
            'X-CGMD-Bridge: ' + $env:COMPUTERNAME + "\r\n\r\n"
    $headBytes = [System.Text.Encoding]::ASCII.GetBytes($head)
    $Stream.Write($headBytes, 0, $headBytes.Length)
    $Stream.Write($payload, 0, $payload.Length)
    $Stream.Flush()
}

function Read-HttpRequest {
    param($Stream)
    $buffer = New-Object System.IO.MemoryStream
    $one = New-Object byte[] 1
    $text = ''
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $read = $Stream.Read($one, 0, 1)
        if ($read -le 0) { break }
        $null = $buffer.Write($one, 0, 1)
        if ($buffer.Length -ge 4) {
            $text = [System.Text.Encoding]::ASCII.GetString($buffer.ToArray())
            if ($text.EndsWith("`r`n`r`n")) { break }
        }
    }
    $text = [System.Text.Encoding]::ASCII.GetString($buffer.ToArray())
    if (-not $text) { return $null }
    $lines = $text -split "`r`n"
    $requestLine = $lines[0]
    $headers = @{}
    foreach ($line in ($lines | Select-Object -Skip 1)) {
        if (-not $line.Trim()) { continue }
        $idx = $line.IndexOf(':')
        if ($idx -gt 0) {
            $headers[$line.Substring(0, $idx).Trim().ToLower()] = $line.Substring($idx + 1).Trim()
        }
    }
    $body = ''
    $length = 0
    if ($headers.ContainsKey('content-length')) { [void][int]::TryParse($headers['content-length'], [ref]$length) }
    if ($length -gt 0) {
        $payload = New-Object byte[] $length
        $offset = 0
        while ($offset -lt $length) {
            $read = $Stream.Read($payload, $offset, $length - $offset)
            if ($read -le 0) { break }
            $offset += $read
        }
        $body = [System.Text.Encoding]::UTF8.GetString($payload, 0, $offset)
    }
    $parts = $requestLine -split ' '
    return [pscustomobject]@{
        Method  = $(if ($parts.Count -ge 1) { $parts[0] } else { 'GET' })
        Path    = $(if ($parts.Count -ge 2) { ($parts[1] -split '\?')[0] } else { '/' })
        Headers = $headers
        Body    = $body
    }
}

function Get-LanAddresses {
    $addresses = @()
    try {
        foreach ($nic in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
            if ($nic.OperationalStatus -ne 'Up') { continue }
            foreach ($info in $nic.GetIPProperties().UnicastAddresses) {
                if ($info.Address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { continue }
                if ([System.Net.IPAddress]::IsLoopback($info.Address)) { continue }
                $addresses += $info.Address.ToString()
            }
        }
    } catch { }
    return $addresses
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
$cfg = $null
foreach ($candidate in @($ConfigPath,
                          (Join-Path $script:HubRoot 'config\cgmd_hub.local.json'),
                          (Join-Path $script:HubRoot 'config\cgmd_hub.json'))) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $cfg = Read-JsonFile -Path $candidate; break }
}
if (-not $RepoPath) { $RepoPath = [string](Get-Property $cfg 'repo_path' $script:HubRoot) }
if (-not $Branch) { $Branch = [string](Get-Property $cfg 'branch' '') }
if ($Port -le 0) { $Port = [int](Get-Property $cfg 'bridge_port' 8765) }
if (-not $Token) { $Token = [string](Get-Property $cfg 'bridge_token' '') }
$allowShellCfg = [bool](Get-Property $cfg 'allow_shell' $false)
if ($allowShellCfg) { $AllowShell = $true }

if ($OpenFirewall) {
    $rule = 'netsh advfirewall firewall add rule name="CGMD bridge" dir=in action=allow protocol=TCP localport=' + $Port
    $code = Invoke-Captured -CommandLine $rule -TimeoutSeconds 60
    Write-BridgeLog ('firewall rule exit ' + $code + ' (needs an elevated prompt)') $(if ($code -eq 0) { 'INFO' } else { 'WARN' })
}

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Port)
try {
    $listener.Start()
} catch {
    Write-BridgeLog ('cannot listen on port ' + $Port + ': ' + $_.Exception.Message) 'ERROR'
    exit 7
}

$statePath = Join-Path $script:StateDir 'bridge.json'
$state = [ordered]@{
    schema     = 'cgmd.bridge.v1'
    host       = $env:COMPUTERNAME
    port       = $Port
    lan        = @(Get-LanAddresses)
    token_required_for_public = [bool]$Token
    allow_shell = [bool]$AllowShell
    pid        = $PID
    started_at = Get-BeijingStamp
}
[System.IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
Write-BridgeLog ('bridge listening on 0.0.0.0:{0} (lan: {1})' -f $Port, (@(Get-LanAddresses) -join ', '))

try {
    while ($true) {
        $client = $listener.AcceptTcpClient()
        try {
            $client.ReceiveTimeout = 60000
            $stream = $client.GetStream()
            $remote = $client.Client.RemoteEndPoint.Address
            $request = Read-HttpRequest -Stream $stream
            if ($null -eq $request) { continue }
            $supplied = ''
            if ($request.Headers.ContainsKey('x-cgmd-token')) { $supplied = $request.Headers['x-cgmd-token'] }
            if (-not (Test-ClientAllowed -Address $remote -SuppliedToken $supplied)) {
                Send-HttpResponse -Stream $stream -StatusCode 403 -Body '{"status":"forbidden","summary":"client not on the LAN and no valid token"}'
                Write-BridgeLog ('denied ' + $remote.ToString()) 'WARN'
                continue
            }
            $response = $null
            switch ($request.Path) {
                '/health' {
                    $inventory = Get-QuickInventory
                    $response = New-Result -Kind 'health' -Status 'ok' `
                        -Summary ('{0} bridge up, gmx {1}' -f $env:COMPUTERNAME, $inventory['version']) -Detail $inventory
                }
                '/status' {
                    $response = Invoke-BridgeJob -Request ([pscustomobject]@{ kind = 'status'; args = $null })
                }
                '/job' {
                    if ($request.Method -ne 'POST') {
                        Send-HttpResponse -Stream $stream -StatusCode 405 -Body '{"status":"error","summary":"POST /job"}'
                        continue
                    }
                    $payload = $null
                    try { $payload = $request.Body | ConvertFrom-Json } catch { $payload = $null }
                    if ($null -eq $payload) {
                        Send-HttpResponse -Stream $stream -StatusCode 400 -Body '{"status":"error","summary":"body must be JSON"}'
                        continue
                    }
                    $response = Invoke-BridgeJob -Request $payload
                }
                default {
                    Send-HttpResponse -Stream $stream -StatusCode 404 -Body '{"status":"error","summary":"GET /health, /status or POST /job"}'
                    continue
                }
            }
            Send-HttpResponse -Stream $stream -StatusCode 200 -Body ($response | ConvertTo-Json -Depth 8)
            Write-BridgeLog ('served ' + $request.Path + ' for ' + $remote.ToString())
        } catch {
            Write-BridgeLog ('request failed: ' + $_.Exception.Message) 'WARN'
        } finally {
            try { $client.Close() } catch { }
        }
        if ($Once) { break }
    }
} finally {
    try { $listener.Stop() } catch { }
    try { Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue } catch { }
    Write-BridgeLog 'bridge stopped'
}
exit 0
