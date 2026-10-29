#Requires -Version 5.1
# enable_private_hub.ps1 - Hot-load private repository polling + zero-window silent credential helper
# + automatic gh account self-healing + auto-private lock into git-sync-hub without touching git-sync-hub task.
# ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = 'Stop'
$syncRoot = 'E:\0github\.git-sync'
$written = @()

$workerCode = @'
# hub-worker.ps1 - Hot-reloaded every 15s cycle by git-sync-hub v4.0 (v4.3 Zero-Window Silent Edition)
# 1. Auto-switches gh active account back to mqgg5630-cyber if hosts.yml drifted (CRLF-safe regex)
# 2. Pins GUI-subsystem git-credential-arenasilent.exe so git ls-remote NEVER spawns sh.exe / conhost
# 3. Auto-locks 0fuye back to private:true if ever temporarily opened

function Ensure-PrimaryGhAccount {
    $ghPath = 'C:\Program Files\GitHub CLI\gh.exe'
    if (-not (Test-Path -LiteralPath $ghPath)) {
        $cmd = Get-Command gh.exe -ErrorAction SilentlyContinue
        if ($cmd) { $ghPath = $cmd.Source } else { return }
    }

    # CRLF-safe <1ms check of hosts.yml so normal 15s cycles spawn ZERO extra processes
    $hostsYml = Join-Path $env:APPDATA 'GitHub CLI\hosts.yml'
    $needsSwitch = $false
    if (Test-Path -LiteralPath $hostsYml) {
        try {
            $raw = [System.IO.File]::ReadAllText($hostsYml)
            if (($raw -match 'mqgg5630-cyber') -and ($raw -notmatch '(?m)^\s*user:\s*mqgg5630-cyber\b')) {
                $needsSwitch = $true
            }
        } catch {}
    }

    $silentHelper = 'E:/0apps/ArenaDesk/git-credential-arenasilent.exe'
    $hasSilentHelper = Test-Path -LiteralPath 'E:\0apps\ArenaDesk\git-credential-arenasilent.exe'

    if ($needsSwitch) {
        $env:GH_PROMPT_DISABLED = '1'
        [void](Invoke-ProcessSilent -FileName $ghPath -Arguments 'auth switch -h github.com -u mqgg5630-cyber' -TimeoutSeconds 8)
        if (-not $hasSilentHelper) {
            [void](Invoke-ProcessSilent -FileName $ghPath -Arguments 'auth setup-git' -TimeoutSeconds 8)
        }
        $script:CachedGhToken = ''
        Write-HubLog 'AUTO-HEAL: switched gh active account back to mqgg5630-cyber'
    }

    if (-not $script:UrlCredsPinnedV43) {
        $script:UrlCredsPinnedV43 = $true
        $helperVal = if ($hasSilentHelper) { $silentHelper } else { "!`"$ghPath`" auth git-credential" }
        [void](Invoke-GitSilent -Arguments 'config --global --unset-all credential.https://github.com.helper' -TimeoutSeconds 5)
        [void](Invoke-GitSilent -Arguments 'config --global --add credential.https://github.com.helper ""' -TimeoutSeconds 5)
        [void](Invoke-GitSilent -Arguments "config --global --add credential.https://github.com.helper `"$helperVal`"" -TimeoutSeconds 5)
        foreach ($acct in @('mqgg5630-cyber', 'shaohuawen03-cyber', 'hukeying85-ux')) {
            $pfx = "credential.https://github.com/$acct"
            [void](Invoke-GitSilent -Arguments "config --global --unset-all ${pfx}.helper" -TimeoutSeconds 5)
            [void](Invoke-GitSilent -Arguments "config --global --add ${pfx}.helper `"`"" -TimeoutSeconds 5)
            [void](Invoke-GitSilent -Arguments "config --global --add ${pfx}.helper `"$helperVal`"" -TimeoutSeconds 5)
            [void](Invoke-GitSilent -Arguments "config --global ${pfx}.useHttpPath true" -TimeoutSeconds 5)
            [void](Invoke-GitSilent -Arguments "config --global ${pfx}.username $acct" -TimeoutSeconds 5)
        }
    }
}

function Get-TargetReposToCheck {
    if (Test-Path -LiteralPath 'E:\0github\.git-sync\PAUSE_WATCHER.flag') {
        return @()
    }
    Ensure-PrimaryGhAccount

    $skipRepos = @('git-pull-arena', 'rea', 'Light-skills', 'subs-check-pro', 'AgentArena', 'BrowserSkill', 'zhongqi')
    if ((-not $script:ActiveRepoNames) -or ($script:ActiveRepoNames.Count -gt 16)) {
        $script:ActiveRepoNames = @('0fuye', 'goutoujunshi', 'leanrea', 'skills', '-skills')
    } else {
        if ($script:ActiveRepoNames -notcontains '0fuye') {
            $script:ActiveRepoNames = @('0fuye') + $script:ActiveRepoNames
        }
        $script:ActiveRepoNames = @($script:ActiveRepoNames | Where-Object { $_ -notin $skipRepos })
    }
    $now = Get-Date
    if ((-not $script:LastApiRefresh) -or (($now - $script:LastApiRefresh).TotalSeconds -ge 45)) {
        $script:LastApiRefresh = $now
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $headers = @{
            'User-Agent' = 'arena-desk-git-sync-hub/4.3'
            'Accept'     = 'application/vnd.github.v3+json'
        }
        $tok = Get-GitHubToken
        if ($tok) {
            $headers['Authorization'] = "Bearer $tok"
        }
        $url = if ($tok) {
            'https://api.github.com/user/repos?affiliation=owner&per_page=25&sort=pushed&direction=desc'
        } else {
            "https://api.github.com/users/$Owner/repos?per_page=15&sort=pushed&direction=desc"
        }
        try {
            $repos = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 15 -ErrorAction Stop
            $fresh = @('0fuye', 'goutoujunshi', 'leanrea', 'skills', '-skills')
            foreach ($r in $repos) {
                if (($r.name -eq '0fuye') -and ($r.private -eq $false) -and $tok) {
                    try {
                        $lockBody = '{"private":true}'
                        [void](Invoke-RestMethod -Method Patch -Uri 'https://api.github.com/repos/mqgg5630-cyber/0fuye' -Headers $headers -Body $lockBody -ContentType 'application/json' -TimeoutSec 12 -ErrorAction Stop)
                        Write-HubLog 'AUTO-LOCK: restored mqgg5630-cyber/0fuye to private:true'
                    } catch {}
                }
                if (-not $r.pushed_at) { continue }
                $rn = [string]$r.name
                if ($rn -in $skipRepos) { continue }
                $pushedIso = ([DateTime]$r.pushed_at).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                if ($pushedIso -ge '2026-10-20T00:00:00Z') {
                    if ($fresh -notcontains $rn) { $fresh += $rn }
                }
            }
            $script:ActiveRepoNames = @($fresh | Select-Object -First 16)
        } catch {
            Write-HubLog "WARN: private+public API refresh skipped: $($_.Exception.Message)"
        }
    }
    return $script:ActiveRepoNames
}
'@

if (Test-Path -LiteralPath $syncRoot) {
    $dirs = @(Get-ChildItem -LiteralPath $syncRoot -Directory -ErrorAction SilentlyContinue)
    foreach ($d in $dirs) {
        if (Test-Path -LiteralPath (Join-Path $d.FullName 'hub-watch.ps1')) {
            $target = Join-Path $d.FullName 'hub-worker.ps1'
            Set-Content -LiteralPath $target -Value $workerCode -Encoding ASCII
            $written += $target
        }
    }
}

$gh = Get-Command gh.exe -ErrorAction SilentlyContinue
if (-not $gh -and (Test-Path 'C:\Program Files\GitHub CLI\gh.exe')) {
    $gh = Get-Item 'C:\Program Files\GitHub CLI\gh.exe'
}
$hasSilentExe = Test-Path -LiteralPath 'E:\0apps\ArenaDesk\git-credential-arenasilent.exe'
$switchedPrimary = $false
if ($gh) {
    $ghPath = if ($gh.Source) { $gh.Source } else { $gh.FullName }
    $env:GH_PROMPT_DISABLED = '1'
    & $ghPath auth switch -h github.com -u mqgg5630-cyber >$null 2>&1
    if ($LASTEXITCODE -eq 0) { $switchedPrimary = $true }
    if (-not $hasSilentExe) {
        & $ghPath auth setup-git >$null 2>&1
    }
}

@{
    ok               = ($written.Count -gt 0)
    worker_files     = $written
    switched_primary = $switchedPrimary
    silent_cred_exe  = $hasSilentExe
    note             = 'git-sync-hub v4.3 zero-window silent worker deployed without task restart'
} | ConvertTo-Json -Compress
