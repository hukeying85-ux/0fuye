#Requires -Version 5.1
<#
.SYNOPSIS
    Send a zero-token push notification to the configured ntfy topic.

.DESCRIPTION
    Companion of code/federation/node_agent.py.  Both speak the same protocol:
    a UTF-8 JSON body POSTed to https://ntfy.sh with priority 5, so the Xiaomi
    phone pops up and vibrates.

    The message always carries a Beijing (UTC+8) timestamp.

.PARAMETER Topic
    ntfy topic, default arena-beacon-95bc796a66.

.PARAMETER Title
    Notification title (ASCII or UTF-8, the JSON body is sent as UTF-8 bytes).

.PARAMETER Message
    Body text.  Newlines are allowed.

.PARAMETER Tags
    ntfy tags, e.g. 'rocket', 'white_check_mark', 'rotating_light'.

.PARAMETER Priority
    1..5, default 5 (max: heads-up popup + vibration).

.EXAMPLE
    .\Send-CgmdBeacon.ps1 -Title '[CGMD] hub' -Message 'desktop poller started'
#>
[CmdletBinding()]
param(
    [string]$Topic = 'arena-beacon-95bc796a66',
    [string]$Title = '[CGMD] desktop hub',
    [string]$Message = 'beacon test',
    [string[]]$Tags = @('desktop_computer'),
    [int]$Priority = 5,
    [string]$Server = 'https://ntfy.sh',
    [int]$TimeoutSec = 10,
    [switch]$Quiet
)

function Get-BeijingStamp {
    $utc = [DateTime]::UtcNow
    foreach ($id in @('China Standard Time', 'Asia/Shanghai')) {
        try {
            $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById($id)
            return [System.TimeZoneInfo]::ConvertTimeFromUtc($utc, $tz).ToString('yyyy-MM-ddTHH:mm:sszzz')
        } catch {
            continue
        }
    }
    return $utc.AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
}

$stamp = Get-BeijingStamp
$body = "{0}`nBeijing time {1} (UTC+8)" -f $Message, $stamp

$payload = @{
    topic    = $Topic
    title    = $Title
    message  = $body
    priority = $Priority
    tags     = $Tags
}

$json = $payload | ConvertTo-Json -Depth 4 -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)

try {
    $null = Invoke-RestMethod -Uri $Server -Method Post -Body $bytes `
        -ContentType 'application/json; charset=utf-8' -TimeoutSec $TimeoutSec
    if (-not $Quiet) { Write-Host ("beacon sent: {0}" -f $Title) }
    return $true
} catch {
    if (-not $Quiet) { Write-Warning ("beacon failed: {0}" -f $_.Exception.Message) }
    return $false
}
