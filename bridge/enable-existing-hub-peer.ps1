#Requires -Version 5.1
<#
One-time, opt-in link from the ALREADY RUNNING desktop CGMD hub to this
session's fixed branch. No Google Drive mount, credentials, token, admin,
repository switch, scheduled-task changes, or arbitrary shell jobs.

The existing hub's Invoke-CgmdMailbox.ps1 reads peer_repos from its private
cgmd_hub.local.json every poll and fetches inbox/*.json from peer branches.
This adds ONE allowed peer while preserving every other local setting. It
changes only the ignored local config and an ignored backup under state/.
The caller must run it ON THE DESKTOP once; Drive cloud/API access cannot edit
this Windows-local file. Review before running.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$HubRepoPath = 'C:\cgmd\0fuye'
)

$ErrorActionPreference = 'Stop'
$peer = 'hukeying85-ux/0fuye#arena/7ed6241a-0fuye'
$expectedRepo = 'hukeying85-ux/0fuye'
$cfgPath = Join-Path $HubRepoPath 'skills\cgmd-hub\config\cgmd_hub.local.json'
$workerPath = Join-Path $HubRepoPath 'skills\cgmd-hub\runner\Invoke-CgmdMailbox.ps1'
if (-not (Test-Path -LiteralPath $cfgPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $workerPath -PathType Leaf)) {
    throw ('Existing desktop hub/config not found at ' + $HubRepoPath + '; nothing was changed.')
}
$raw = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8
$cfg = $raw | ConvertFrom-Json
if ([string]$cfg.locked_repo -cne $expectedRepo) {
    throw 'Local hub belongs to a different repository; refusing to edit its config.'
}
# Match Invoke-CgmdMailbox.ps1: Get-Property 'mailbox_enabled' defaults to
# $true when the key is absent (older local configs omit this newer option).
# An explicit JSON false is different: respect it and never turn it on here.
$mailboxField = $cfg.PSObject.Properties['mailbox_enabled']
if ($null -eq $mailboxField -or $null -eq $mailboxField.Value) {
    Write-Host 'INFO: mailbox_enabled is absent/null in this older local config; hub defaults it to true.'
} else {
    if ($mailboxField.Value -isnot [bool]) {
        throw 'mailbox_enabled must be a JSON boolean; refusing to edit an ambiguous hub config.'
    }
    if (-not $mailboxField.Value) {
        throw 'Existing hub mailbox is explicitly disabled (mailbox_enabled: false); nothing was changed.'
    }
}
$ref = [string]$cfg.mailbox_ref
if ($ref -and $ref -cne 'hub/mailbox') {
    throw 'Existing hub uses an unexpected mailbox ref; refusing to edit its config.'
}
if ([bool]$cfg.allow_shell) {
    throw 'Existing hub has unrestricted shell jobs enabled. Disable them before linking this public branch.'
}
$existing = @($cfg.peer_repos | Where-Object { $null -ne $_ -and ([string]$_).Trim() })
if ($existing -ccontains $peer) {
    Write-Host ('ALREADY_LINKED: ' + $peer + '; no changes made.')
    return
}
$peers = @($existing + @($peer) | Select-Object -Unique)
$action = ('Add peer ' + $peer + ' to local CGMD hub config, keeping ' + $existing.Count + ' existing peer(s)')
if (-not $PSCmdlet.ShouldProcess($cfgPath, $action)) { return }

$backupDir = Join-Path $HubRepoPath 'skills\cgmd-hub\state\peer-config-backups'
if (-not (Test-Path -LiteralPath $backupDir -PathType Container)) {
    $null = New-Item -ItemType Directory -Path $backupDir -Force -ErrorAction Stop
}
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmss')
$backup = Join-Path $backupDir ('cgmd_hub.' + $stamp + '.' + [Guid]::NewGuid().ToString('N') + '.json')
Copy-Item -LiteralPath $cfgPath -Destination $backup -ErrorAction Stop

# Rebuild the object to preserve unknown fields. Never add a credential or
# overwrite the caller's already-configured peers. A temporary .local.json
# file remains gitignored even if an unexpected error interrupts the write.
$data = [ordered]@{}
foreach ($prop in $cfg.PSObject.Properties) { $data[$prop.Name] = $prop.Value }
$data['peer_repos'] = $peers
$json = ConvertTo-Json -InputObject $data -Depth 40
$tmp = Join-Path (Split-Path -Parent $cfgPath) ('peer-' + [Guid]::NewGuid().ToString('N') + '.local.json')
try {
    [IO.File]::WriteAllText($tmp, ($json + "`n"), [Text.UTF8Encoding]::new($false))
    $check = Get-Content -LiteralPath $tmp -Raw -Encoding UTF8 | ConvertFrom-Json
    if (@($check.peer_repos | Where-Object { $_ -ceq $peer }).Count -ne 1) {
        throw 'Temporary config did not contain exactly one copy of the requested peer.'
    }
    # Both paths are in the same directory: atomic replacement keeps readers
    # from ever seeing a partially written JSON file. The backup above stays.
    [IO.File]::Replace($tmp, $cfgPath, $null)
} finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
}
Write-Host ('LINKED: ' + $peer)
Write-Host ('Backup (private, ignored by Git): ' + $backup)
Write-Host 'Do not enable arbitrary shell jobs. The existing hub should read peer_repos on its next poll.'
