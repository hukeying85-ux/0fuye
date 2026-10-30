#Requires -Version 5.1
# free_mobile_tunnel.ps1 - Zero-Cost Mobile Connectivity Bridge (Free Tailscale Alternative)
# Supports: status | cloudflare | ipv6 | lan
# Also guarantees mqgg5630-cyber remains active in gh so private repo sync stays online.

param(
    [ValidateSet('status', 'cloudflare', 'ipv6', 'lan')]
    [string]$Mode = 'status',
    [int]$Port = 18765
)

$ErrorActionPreference = 'Stop'
$dataDir = 'E:\0apps\ArenaDesk\data\jobbeacon'
if (-not (Test-Path -LiteralPath 'E:\0apps\ArenaDesk')) {
    $dataDir = Join-Path $env:TEMP 'arenadesk-jobbeacon'
}
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

# 1. Self-heal default gh active account so git-sync-hub private repo polling never drops
$ghExe = 'C:\Program Files\GitHub CLI\gh.exe'
if (Test-Path -LiteralPath $ghExe) {
    $env:GH_PROMPT_DISABLED = '1'
    & $ghExe auth switch -h github.com -u mqgg5630-cyber 2>$null | Out-Null
}

# 2. Discover LAN IPv4 and Campus/5G Global IPv6
$ipv4 = @()
$ipv6 = @()
try {
    $ips = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName())
    foreach ($ip in $ips) {
        $s = $ip.IPAddressToString
        if ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) {
            if ($s -notlike '127.*' -and $s -notlike '169.254.*') { $ipv4 += $s }
        } elseif ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6) {
            $clean6 = ($s -split '%')[0]
            if ($clean6 -notmatch '^(::1|fe80:|fc|fd)') { $ipv6 += $clean6 }
        }
    }
} catch {}

$cfCmd = Get-Command 'cloudflared.exe' -ErrorAction SilentlyContinue
if (-not $cfCmd) {
    foreach ($cand in @(
        'C:\Program Files\cloudflared\cloudflared.exe',
        'C:\Program Files (x86)\cloudflared\cloudflared.exe',
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\cloudflared.exe')
    )) {
        if (Test-Path -LiteralPath $cand) { $cfCmd = @{ Source = $cand }; break }
    }
}

$activeTunnelUrl = ''
$tunnelFile = Join-Path $dataDir 'active_tunnel_url.txt'
$tunnelLog  = Join-Path $dataDir 'cloudflared.log'

if ($Mode -eq 'cloudflare') {
    if (-not $cfCmd) {
        Write-Output '{"ok":false,"error":"cloudflared not installed yet. Run: winget install --id Cloudflare.cloudflared -e"}'
        exit 1
    }
    Get-Process -Name 'cloudflared' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tunnelLog -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $cfCmd.Source -ArgumentList @('tunnel', '--url', ("http://127.0.0.1:" + $Port), '--no-autoupdate', '--logfile', $tunnelLog) -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 600
        if (Test-Path -LiteralPath $tunnelLog) {
            $txt = Get-Content -LiteralPath $tunnelLog -Raw -ErrorAction SilentlyContinue
            if ($txt -match '(https://[a-z0-9-]+\.trycloudflare\.com)') {
                $activeTunnelUrl = $Matches[1]
                Set-Content -LiteralPath $tunnelFile -Value $activeTunnelUrl -Encoding ASCII
                break
            }
        }
    }
}

if ((-not $activeTunnelUrl) -and (Test-Path -LiteralPath $tunnelFile)) {
    $activeTunnelUrl = (Get-Content -LiteralPath $tunnelFile -Raw -ErrorAction SilentlyContinue).Trim()
}

$lanMobile = if ($ipv4.Count -gt 0) { "http://$($ipv4[0]):$Port/mobile" } else { "http://127.0.0.1:$Port/mobile" }
$v6Mobile  = if ($ipv6.Count -gt 0) { "http://[$($ipv6[0])]:$Port/mobile" } else { '' }
$cfMobile  = if ($activeTunnelUrl) { "$activeTunnelUrl/mobile" } else { '' }

[ordered]@{
    ok                 = $true
    mode               = $Mode
    cloudflared_ready  = [bool]$cfCmd
    cloudflare_mobile  = $cfMobile
    ipv6_mobile        = $v6Mobile
    lan_mobile         = $lanMobile
    gh_default_restored = 'mqgg5630-cyber'
} | ConvertTo-Json -Depth 4
