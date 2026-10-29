# Read the locally generated launch URL. Never print or sync its bootstrap token.
$ErrorActionPreference='Stop'
$log='E:\0apps\ArenaDesk\data\dsh-runtime.log'
for ($i=0; $i -lt 20; $i++) {
    $t=Get-ScheduledTask -TaskName 'arena-dsh-web' -TaskPath '\' -ErrorAction SilentlyContinue
    if (-not $t -or [string]$t.State -eq 'Disabled') { exit 0 }
    if (Test-Path $log) {
        $text=[string](Get-Content $log -Raw)
        $m=[regex]::Match($text,'http://127\.0\.0\.1:3080/\?token=[A-Za-z0-9_-]+')
        if ($m.Success) {
            # A launch token is for the browser bootstrap. Do not consume it in a probe.
            Start-Process $m.Value
            exit 0
        }
    }
    Start-Sleep -Seconds 1
}
throw 'DSH is not ready; enable its optional task first.'
