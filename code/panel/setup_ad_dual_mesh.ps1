#Requires -Version 5.1
# setup_ad_dual_mesh.ps1 - Free Plan A (Cloudflare Quick Tunnel) + Plan D (ZeroTier Free 25-node LAN)
# Supports 3-account / 3-machine split:
#   -NodeRole laptop   -> locks default gh to mqgg5630-cyber
#   -NodeRole desktop  -> locks default gh to hukeying85-ux (Coarse-Grained MD workstation)

param(
    [ValidateSet('laptop', 'desktop')]
    [string]$NodeRole = 'laptop',
    [ValidateSet('status', 'both', 'planA', 'planD')]
    [string]$Action = 'both',
    [string]$ZeroTierNetworkId = '',
    [int]$LocalPort = 18765
)

$ErrorActionPreference = 'Stop'
$dataDir = 'E:\0apps\ArenaDesk\data'
if (-not (Test-Path -LiteralPath 'E:\')) {
    $dataDir = Join-Path $env:LOCALAPPDATA 'ArenaDesk\data'
}
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

# 1. Enforce role-specific GitHub account binding
$expectedGh = if ($NodeRole -eq 'desktop') { 'hukeying85-ux' } else { 'mqgg5630-cyber' }
$ghCmd = Get-Command gh.exe -ErrorAction SilentlyContinue
if ($ghCmd) {
    try {
        & $ghCmd.Source auth switch -h github.com -u $expectedGh 2>$null | Out-Null
    } catch {}
}

$report = [ordered]@{
    timestamp        = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    node_role        = $NodeRole
    expected_gh_user = $expectedGh
    plan_a_cloudflare = [ordered]@{
        installed  = $false
        public_url = ''
        mobile_url = ''
        note       = ''
    }
    plan_d_zerotier = [ordered]@{
        installed   = $false
        node_id     = ''
        network_id  = $ZeroTierNetworkId
        assigned_ip = ''
        mobile_url  = ''
        note        = ''
    }
}

# 2. Plan D: ZeroTier Free (up to 25 devices free: Laptop + Desktop + Phone SSH/App)
if ($Action -in @('status', 'both', 'planD')) {
    $ztCandidates = @(
        'C:\Program Files (x86)\ZeroTier\One\zerotier-cli.bat',
        'C:\ProgramData\ZeroTier\One\zerotier-one_x64.exe'
    )
    $ztCli = $null
    $ztCmd = Get-Command zerotier-cli.bat -ErrorAction SilentlyContinue
    if ($ztCmd) { $ztCli = $ztCmd.Source }
    if (-not $ztCli) {
        foreach ($cand in $ztCandidates) {
            if (Test-Path -LiteralPath $cand) { $ztCli = $cand; break }
        }
    }

    if ($ztCli) {
        $report.plan_d_zerotier.installed = $true
        try {
            $infoLine = (& $ztCli info 2>$null | Out-String).Trim()
            if ($infoLine -match '200 info ([0-9a-f]{10})') {
                $report.plan_d_zerotier.node_id = $Matches[1]
            }
            if ($ZeroTierNetworkId -and ($ZeroTierNetworkId -match '^[0-9a-fA-F]{16}$')) {
                & $ztCli join $ZeroTierNetworkId 2>$null | Out-Null
                Start-Sleep -Seconds 2
            }
            $nets = (& $ztCli listnetworks 2>$null | Out-String)
            if ($nets -match '([0-9a-f]{16})\s+\S+\s+[0-9a-f:]+\s+OK\s+\S+\s+\S+\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)') {
                $report.plan_d_zerotier.network_id = $Matches[1]
                $report.plan_d_zerotier.assigned_ip = $Matches[2]
                $report.plan_d_zerotier.mobile_url = ('http://' + $Matches[2] + ':' + $LocalPort + '/mobile')
                $report.plan_d_zerotier.note = 'ZeroTier virtual LAN online (0 RMB, direct Desktop<->Laptop<->Mobile)'
            } else {
                $report.plan_d_zerotier.note = 'ZeroTier installed; create a free 16-hex Network ID at my.zerotier.com and pass -ZeroTierNetworkId <id>'
            }
        } catch {
            $report.plan_d_zerotier.note = 'Run PowerShell as Administrator once if zerotier-cli needs token access'
        }
    } else {
        $report.plan_d_zerotier.note = 'Install once via: winget install --id ZeroTier.ZeroTierOne -e'
    }
}

# 3. Plan A: Cloudflare Quick Tunnel (0 RMB, instant HTTPS for Mobile PWA without phone VPN app)
if ($Action -in @('status', 'both', 'planA')) {
    $cfCmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($cfCmd) {
        $report.plan_a_cloudflare.installed = $true
        $logPath = Join-Path $dataDir ('cloudflared-' + $NodeRole + '.log')
        if ($Action -in @('both', 'planA')) {
            $existing = Get-Process -Name 'cloudflared' -ErrorAction SilentlyContinue
            if (-not $existing) {
                Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue
                Start-Process -FilePath $cfCmd.Source -ArgumentList @(
                    'tunnel', '--url', ('http://127.0.0.1:' + $LocalPort), '--no-autoupdate', '--logfile', $logPath
                ) -WindowStyle Hidden | Out-Null
                for ($i = 0; $i -lt 16; $i++) {
                    Start-Sleep -Milliseconds 600
                    if (Test-Path -LiteralPath $logPath) {
                        $raw = Get-Content -LiteralPath $logPath -Raw -ErrorAction SilentlyContinue
                        if ($raw -match '(https://[a-z0-9-]+\.trycloudflare\.com)') { break }
                    }
                }
            }
        }
        if (Test-Path -LiteralPath $logPath) {
            $raw = Get-Content -LiteralPath $logPath -Raw -ErrorAction SilentlyContinue
            if ($raw -match '(https://[a-z0-9-]+\.trycloudflare\.com)') {
                $report.plan_a_cloudflare.public_url = $Matches[1]
                $report.plan_a_cloudflare.mobile_url = ($Matches[1] + '/mobile')
                $report.plan_a_cloudflare.note = 'Cloudflare Quick Tunnel active (0 RMB HTTPS)'
            }
        }
        if (-not $report.plan_a_cloudflare.public_url) {
            $report.plan_a_cloudflare.note = 'cloudflared ready; pass -Action planA to open HTTPS tunnel'
        }
    } else {
        $report.plan_a_cloudflare.note = 'Install once via: winget install --id Cloudflare.cloudflared -e'
    }
}

$outJson = Join-Path $dataDir ('ad-dual-mesh-' + $NodeRole + '.json')
($report | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $outJson -Encoding UTF8
$report | ConvertTo-Json -Depth 6
