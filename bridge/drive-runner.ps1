#Requires -Version 5.1
<#
Desktop-side, allowlisted Google Drive task reader for this session.
Only the inventory_peptides action is supported. No scripts/commands/paths
are accepted from the inbox JSON. It never updates itself or uses Git auth.
Run -Mode Once initially; -Mode Watch only after reviewing the code.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$DriveRoot,
    [ValidateSet('Once', 'Watch')][string]$Mode = 'Once',
    [string]$SearchRoot = 'F:\0wsh\asd',
    [ValidateRange(15, 3600)][int]$IntervalSeconds = 60
)

$ErrorActionPreference = 'Stop'
# Check the root *before* Join-Path: on Windows an absent drive letter (e.g. G:)
# makes Join-Path throw a provider error instead of a useful diagnostic.
if (-not (Test-Path -LiteralPath $DriveRoot -PathType Container -ErrorAction SilentlyContinue)) {
    throw ('DriveRoot is not available: ' + $DriveRoot + '. This local-mirror runner needs an existing synced Drive folder. Do not create an empty drive/folder; use the Arena Google Drive connector to search cloud files instead. It cannot read the local F: disk.')
}
$inbox = Join-Path $DriveRoot 'inbox'
$outbox = Join-Path $DriveRoot 'outbox'
if (-not (Test-Path -LiteralPath $inbox -PathType Container) -or
    -not (Test-Path -LiteralPath $outbox -PathType Container)) {
    throw 'Drive inbox/outbox are not visible. Check the mounted account and sync status; do not create them locally.'
}
$inventoryScript = Join-Path $PSScriptRoot 'peptide-inventory.ps1'
if (-not (Test-Path -LiteralPath $inventoryScript -PathType Leaf)) {
    throw 'Local inventory script is missing from the reviewed clone.'
}

function Save-Receipt([string]$JobId, [object]$Payload) {
    $target = Join-Path $outbox ($JobId + '.json')
    $partial = Join-Path $outbox ($JobId + '.' + [Guid]::NewGuid().ToString('N') + '.partial')
    $json = ConvertTo-Json -InputObject $Payload -Depth 10
    [IO.File]::WriteAllText($partial, ($json + "`n"), [Text.UTF8Encoding]::new($false))
    try {
        if (-not (Test-Path -LiteralPath $target)) {
            Move-Item -LiteralPath $partial -Destination $target -ErrorAction Stop
        }
    } finally {
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
    Write-Host ('Receipt saved: ' + $target)
}

function Invoke-Pending {
    $jobs = @(Get-ChildItem -LiteralPath $inbox -File -Filter 'inv-*.json' -ErrorAction Stop |
        Sort-Object Name | Select-Object -First 20)
    if ($jobs.Count -eq 0) { Write-Host 'No inventory jobs in inbox.'; return }
    foreach ($job in $jobs) {
        if ($job.Name -cnotmatch '^inv-[0-9a-f]{16}\.json$') { continue }
        $id = $job.BaseName
        if (Test-Path -LiteralPath (Join-Path $outbox ($id + '.json'))) { continue }
        try {
            $task = Get-Content -LiteralPath $job.FullName -Encoding UTF8 -Raw | ConvertFrom-Json
            $expectedFields = @('schema', 'job_id', 'action', 'issued_at_utc')
            $actualFields = @($task.PSObject.Properties.Name)
            if (@(Compare-Object $expectedFields $actualFields).Count -gt 0 -or
                $task.schema -ne 'desktop-bridge.v1' -or $task.job_id -cne $id -or
                $task.action -ne 'inventory_peptides') {
                throw 'Invalid schema, job ID, or action; only inventory_peptides is allowed.'
            }
            $issued = [DateTimeOffset]::Parse([string]$task.issued_at_utc)
            $now = [DateTimeOffset]::UtcNow
            if ($issued -lt $now.AddDays(-7) -or $issued -gt $now.AddMinutes(5)) {
                throw 'Job is too old or its timestamp is in the future.'
            }
            Write-Host ('Processing read-only inventory: ' + $id)
            $result = & $inventoryScript -SearchRoot $SearchRoot -DaysBack 90 -MaxCandidates 12
            $receipt = [ordered]@{
                schema = 'desktop-bridge-receipt.v1'
                job_id = $id
                action = 'inventory_peptides'
                status = 'completed'
                completed_at_utc = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
                result = $result
            }
            Save-Receipt $id $receipt
        } catch {
            # Only well-formed filenames are answered. Never execute task content.
            $receipt = [ordered]@{
                schema = 'desktop-bridge-receipt.v1'
                job_id = $id
                action = 'inventory_peptides'
                status = 'failed'
                completed_at_utc = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
                error = $_.Exception.Message
            }
            Save-Receipt $id $receipt
        }
    }
}

if ($Mode -eq 'Once') {
    Invoke-Pending
} else {
    Write-Host 'Watching the Drive inbox; Ctrl+C stops. This is not a Windows service.'
    while ($true) {
        try { Invoke-Pending } catch { Write-Warning $_.Exception.Message }
        Start-Sleep -Seconds $IntervalSeconds
    }
}
