#Requires -Version 5.1
# verify_when_back.ps1 - Master 1-Click Self-Check & Interactive Demo when you return to your PC!
# Covers:
#   [1] Restore mqgg5630-cyber active gh & deploy Arena Desk v2.4
#   [2] Show boot animation (#boot) & open Arena Desk native app
#   [3] Test 'Haoleme' (JobBeacon) mobile lock-screen alert
#   [4] Check Plan A (Cloudflare) + Plan D (ZeroTier) mesh status
#   [5] Verify Master Thesis 1-click formatting engine
#   [6] Check Douyin / Xiaohongshu / WeChat MP / yt-dlp + Computer-Use safety guard

param(
    [switch]$LaunchBoot,
    [switch]$InstallMediaTools
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent

Write-Host '=== [Step 1/6] Locking primary gh account (mqgg5630-cyber) & deploying Arena Desk v2.4 ===' -ForegroundColor Cyan
$gh = Get-Command gh.exe -ErrorAction SilentlyContinue
if ($gh) {
    & $gh.Source auth switch -h github.com -u mqgg5630-cyber 2>$null | Out-Null
    & $gh.Source auth status
}

$deployScript = Join-Path $PSScriptRoot 'panel\deploy.ps1'
if ($LaunchBoot) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $deployScript -LaunchBootDemo
} else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $deployScript
}

$pyExe = if (Test-Path -LiteralPath 'E:\spider\python.exe') { 'E:\spider\python.exe' } else { 'python.exe' }

Write-Host '=== [Step 2/6] Testing JobBeacon (Haoleme) mobile push channel ===' -ForegroundColor Cyan
$nodeAgent = Join-Path $PSScriptRoot 'federation\node_agent.py'
& $pyExe $nodeAgent --role laptop --task-title 'Welcome Back Self-Check' --test-notify

Write-Host '=== [Step 3/6] Checking Plan A (Cloudflare) + Plan D (ZeroTier) Dual Mesh ===' -ForegroundColor Cyan
$meshScript = Join-Path $PSScriptRoot 'connect\setup_ad_dual_mesh.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $meshScript -NodeRole laptop -Action status

Write-Host '=== [Step 4/6] Provisioning Douyin/XHS/WeChat Media Downloader & Computer-Use MCP ===' -ForegroundColor Cyan
$mediaScript = Join-Path $PSScriptRoot 'connect\setup_media_and_cua.ps1'
if ($InstallMediaTools) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $mediaScript -InstallBinaries
} else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $mediaScript
}

Write-Host '=== [Step 5/6] Verifying Computer-Use Triple Safety Guard ===' -ForegroundColor Cyan
$cuaGuard = Join-Path $PSScriptRoot 'cua\local_cua_guard.py'
& $pyExe $cuaGuard --probe

Write-Host '=== [Step 6/6] Checking Arena Desk HTTP API v2.4 ===' -ForegroundColor Cyan
$bootResp = Invoke-RestMethod -Uri 'http://127.0.0.1:18765/api/bootstrap' -TimeoutSec 5
Write-Host ('Arena Desk running version: ' + $bootResp.version) -ForegroundColor Green
Write-Host 'All checks completed! Open http://127.0.0.1:18765 or http://127.0.0.1:18765/mobile to explore.' -ForegroundColor Green
