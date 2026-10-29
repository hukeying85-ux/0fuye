#Requires -Version 5.1
<#
One-time, read-only-on-the-PC handshake for the arena/7ed6241a-0fuye branch.
Run this manually ON the intended Windows desktop from a fresh clone of this
branch. It reads a challenge and pushes ONLY a small, non-identifying receipt.
It does not install services, open ports, or execute commands from the challenge.
#>
[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
$expectedRemote = 'https://github.com/hukeying85-ux/0fuye.git'
$expectedBranch = 'arena/7ed6241a-0fuye'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git for Windows is required. Install it yourself, then retry.'
}

function Read-Git([string[]]$GitArguments) {
    $output = @(& git -C $repoRoot @GitArguments)
    if ($LASTEXITCODE -ne 0) { throw ('git ' + $GitArguments[0] + ' failed') }
    return ($output -join "`n").Trim()
}
function Run-Git([string[]]$GitArguments) {
    & git -C $repoRoot @GitArguments
    if ($LASTEXITCODE -ne 0) { throw ('git ' + $GitArguments[0] + ' failed; see git output above') }
}

$gitRoot = [IO.Path]::GetFullPath((Read-Git -GitArguments @('rev-parse', '--show-toplevel')))
if ($gitRoot -ne $repoRoot) { throw 'Run the script from its own repository clone.' }
$remote = Read-Git -GitArguments @('remote', 'get-url', 'origin')
if ($remote -ne $expectedRemote -and $remote -ne 'https://github.com/hukeying85-ux/0fuye') {
    throw 'Unexpected origin URL. Clone the documented repository instead.'
}
$branch = Read-Git -GitArguments @('symbolic-ref', '--short', 'HEAD')
if ($branch -ne $expectedBranch) { throw 'Wrong branch. Refusing to push.' }
$dirty = Read-Git -GitArguments @('status', '--porcelain', '--untracked-files=normal')
if ($dirty) { throw 'Working tree is not clean. Use a fresh, separate clone.' }

# Never pull changed scripts or rebase automatically. If origin moved, the user
# must review it and fast-forward the clone before running this script again.
$trackingRef = 'refs/remotes/origin/' + $expectedBranch
Run-Git -GitArguments @('fetch', '--quiet', 'origin', ('+refs/heads/' + $expectedBranch + ':' + $trackingRef))
$localCommit = Read-Git -GitArguments @('rev-parse', 'HEAD')
$remoteCommit = Read-Git -GitArguments @('rev-parse', $trackingRef)
if ($localCommit -ne $remoteCommit) {
    throw 'Remote branch moved. Review changes, git pull --ff-only, then retry.'
}

$challengePath = Join-Path $repoRoot 'bridge\challenge.json'
$challenge = Get-Content -LiteralPath $challengePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($challenge.version -ne 1 -or $challenge.kind -ne 'desktop-handshake' -or
    $challenge.repo -ne 'hukeying85-ux/0fuye' -or $challenge.branch -ne $expectedBranch) {
    throw 'Unexpected challenge protocol, repository, or branch.'
}
$nonce = [string]$challenge.nonce
if ($nonce -cnotmatch '^[0-9a-f]{32}$') { throw 'Invalid challenge nonce.' }
try {
    $issued = [DateTimeOffset]::Parse([string]$challenge.issued_at_utc)
    $expires = [DateTimeOffset]::Parse([string]$challenge.expires_at_utc)
} catch { throw 'Invalid challenge timestamp.' }
$now = [DateTimeOffset]::UtcNow
if ($expires -le $issued -or $expires -gt $issued.AddDays(7) -or
    $now -lt $issued.AddMinutes(-5) -or $now -gt $expires) {
    throw 'Challenge is expired or has an invalid clock. Ask for a new challenge.'
}
$challengeCommit = Read-Git -GitArguments @('log', '-1', '--format=%H', '--', 'bridge/challenge.json')
if ($challengeCommit -cnotmatch '^[0-9a-f]{40}$') { throw 'Challenge commit was not found.' }
$relativePath = 'bridge/receipts/' + $nonce + '.json'
$receiptPath = Join-Path (Join-Path $repoRoot 'bridge\receipts') ($nonce + '.json')

if (Test-Path -LiteralPath $receiptPath) {
    $previous = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($previous.nonce -ne $nonce -or $previous.challenge_commit -ne $challengeCommit -or
        $previous.status -ne 'received') { throw 'Existing receipt does not match this challenge.' }
    Write-Host 'Existing matching receipt found. Will retry push without a new commit.'
} else {
    Write-Host ('Challenge read: ' + $nonce.Substring(0, 8) + '...')
    Write-Host 'Receipt contains only a nonce, commit, status, and UTC time (no hostname/IP/user).'
}
if ($DryRun) {
    Write-Host 'DRY RUN: no file created, no commit, no push.'
    return
}

if (-not (Test-Path -LiteralPath $receiptPath)) {
    $receipt = [ordered]@{
        version = 1
        nonce = $nonce
        challenge_commit = $challengeCommit
        status = 'received'
        observed_at_utc = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $receiptPath) | Out-Null
    $json = ConvertTo-Json -InputObject $receipt -Depth 3
    [IO.File]::WriteAllText($receiptPath, ($json + "`n"), [Text.UTF8Encoding]::new($false))
    Run-Git -GitArguments @('add', '--', $relativePath)
    # Set a pseudonymous author ONLY for this commit. No global git config changes.
    Run-Git -GitArguments @('-c', 'user.name=Desktop Bridge', '-c', 'user.email=desktop-bridge@users.noreply.github.com',
              'commit', '-m', ('bridge: desktop handshake ' + $nonce.Substring(0, 8)), '--', $relativePath)
}
Run-Git -GitArguments @('push', 'origin', ('HEAD:refs/heads/' + $expectedBranch))
Write-Host 'OK: receipt pushed to this branch. Tell the agent to fetch and verify it.'
