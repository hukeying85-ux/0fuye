#Requires -Version 5.1
# setup_media_and_cua.ps1 - One-click setup for:
#   1) Universal Video Downloading (yt-dlp + FFmpeg + Edge cookie reuse)
#   2) Douyin / Xiaohongshu / WeChat MP local connectors & MCP config
#   3) Computer Use stack (OpenCLI + Windows-MCP + isolated Edge CDP port 9222)

param(
    [switch]$InstallBinaries,
    [switch]$LaunchLoginBrowser
)

$ErrorActionPreference = 'Stop'
$mediaRoot = 'E:\0downloads\ArenaMedia'
if (-not (Test-Path -LiteralPath 'E:\')) {
    $mediaRoot = Join-Path $env:USERPROFILE 'Downloads\ArenaMedia'
}
foreach ($sub in @('douyin', 'xiaohongshu', 'wechat_mp', 'bilibili', 'youtube', 'generic')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $mediaRoot $sub) | Out-Null
}

if ($InstallBinaries) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        foreach ($pkg in @('yt-dlp.yt-dlp', 'Gyan.FFmpeg')) {
            & $winget.Source install --id $pkg -e --accept-package-agreements --accept-source-agreements --silent 2>$null | Out-Null
        }
    }
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npm) {
        & $npm.Source install -g '@jackwener/opencli' 2>$null | Out-Null
    }
}

# Generate unified MCP config template for Claude Desktop / Cursor / Antigravity / OmniRoute
$dataDir = if (Test-Path -LiteralPath 'E:\') { 'E:\0apps\ArenaDesk\data' } else { Join-Path $env:LOCALAPPDATA 'ArenaDesk\data' }
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$mcpConfig = [ordered]@{
    mcpServers = [ordered]@{
        'windows-cua' = [ordered]@{
            command = 'uvx'
            args    = @('windows-mcp')
        }
        'xiaohongshu-mcp' = [ordered]@{
            command = 'npx'
            args    = @('-y', 'xiaohongshu-mcp@latest')
        }
        'wechat-wenyan-mcp' = [ordered]@{
            command = 'npx'
            args    = @('-y', '@wenyan-md/mcp')
            env     = [ordered]@{
                WECHAT_APP_ID     = 'YOUR_WECHAT_MP_APPID_LOCAL_ONLY'
                WECHAT_APP_SECRET = 'YOUR_WECHAT_MP_SECRET_LOCAL_ONLY'
            }
        }
    }
}
$mcpPath = Join-Path $dataDir 'mcp-media-cua-config.json'
($mcpConfig | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $mcpPath -Encoding UTF8

if ($LaunchLoginBrowser) {
    $pyExe = if (Test-Path -LiteralPath 'E:\spider\python.exe') { 'E:\spider\python.exe' } else { 'python.exe' }
    $guardPy = Join-Path (Split-Path $PSScriptRoot -Parent) 'cua\local_cua_guard.py'
    if (Test-Path -LiteralPath $guardPy) {
        & $pyExe $guardPy --launch-cdp
    }
}

[ordered]@{
    ok          = $true
    media_root  = $mediaRoot
    mcp_config  = $mcpPath
    yt_dlp      = [bool](Get-Command yt-dlp.exe -ErrorAction SilentlyContinue)
    ffmpeg      = [bool](Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)
    opencli     = [bool](Get-Command opencli.cmd -ErrorAction SilentlyContinue)
} | ConvertTo-Json -Depth 4
