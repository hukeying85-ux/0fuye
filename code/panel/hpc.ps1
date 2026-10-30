#Requires -Version 5.1
<#
.SYNOPSIS
    Bridge the laptop to the campus HPC (mu01) through WSL, where the working SSH
    key/alias already lives. One entry point for run / put / get / submit / jobs.

.DESCRIPTION
    The Windows OpenSSH client has no key for mu01; the WSL distro Ubuntu-26.04
    does (Host mu01 -> 25wenshaohua@10.10.5.210, ~/.ssh/id_ed25519). So every
    remote call is executed as: wsl.exe -d Ubuntu-26.04 -e bash <generated script>.

    Actions
      info    - inventory: host, slurm partitions, quota, tree of $HOME
      run     - run an arbitrary shell command on mu01, print stdout
      put     - rsync local file/dir -> mu01
      get     - rsync mu01 path -> local
      submit  - copy a local script to mu01 and sbatch it, print the job id
      jobs    - squeue for the user, plus tail of the newest .out
      log     - tail a remote file

    Every action prints to stdout and, unless -NoOut, also appends to
    results\jev-monitor\hpc-last.txt. ASCII only.
#>
[CmdletBinding()]
param(
    [ValidateSet('info', 'run', 'put', 'get', 'submit', 'jobs', 'log')]
    [string]$Action = 'info',
    [string]$Cmd = '',
    [string]$CmdFile = '',
    [string]$Local = '',
    [string]$Remote = '',
    [string]$Script = '',
    [string]$Distro = 'Ubuntu-26.04',
    [string]$Out = 'results\jev-monitor\hpc-last.txt',
    [switch]$NoOut
)

$ErrorActionPreference = 'Continue'
$repo = (Get-Location).Path
$outPath = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path $repo $Out }
New-Item -ItemType Directory -Force -Path (Split-Path $outPath) | Out-Null

# ---- build the payload that runs inside WSL --------------------------------
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('set -u')
$lines.Add('SSH="ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new mu01"')
$lines.Add('S() { $SSH "$@"; }')

switch ($Action) {
    'info' {
        $rc = 'hostname; whoami; uname -srm; echo "--- partitions"; sinfo -s 2>&1 | head -12; ' +
              'echo "--- my jobs"; squeue -u $USER 2>&1 | head -12; ' +
              'echo "--- limits"; scontrol show partition 2>/dev/null | grep -E "PartitionName|MaxTime|MaxNodes|MaxMemPerNode" | head -20; ' +
              'echo "--- storage"; df -h $HOME | tail -1; echo HOME=$HOME; ' +
              'echo "--- stack"; for c in python3 conda mamba apptainer singularity gcc nvcc; do printf "%-12s %s\n" $c "$(command -v $c || echo -)"; done; ' +
              'echo "--- home"; ls -d $HOME/* 2>/dev/null | head -15'
        $lines.Add("S '" + $rc.Replace("'", "'\''") + "'")
    }
    'run' {
        # -CmdFile avoids every quoting layer between the hub, powershell and WSL
        if ($CmdFile) {
            $cf = if ([IO.Path]::IsPathRooted($CmdFile)) { $CmdFile } else { Join-Path (Get-Location).Path $CmdFile }
            if (-not (Test-Path -LiteralPath $cf)) { Write-Output 'NO_CMDFILE'; exit 2 }
            $Cmd = [IO.File]::ReadAllText($cf)
        }
        if (-not $Cmd) { Write-Output 'NO_CMD'; exit 2 }
        $esc = $Cmd.Replace("'", "'\''")
        $lines.Add("S '$esc'")
    }
    'put' {
        if (-not $Local -or -not $Remote) { Write-Output 'NEED -Local and -Remote'; exit 2 }
        $lw = $Local -replace '\\', '/'
        $lines.Add("rsync -az --info=progress2 -e 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' " +
                   "'$lw' mu01:'$Remote' && echo PUT_OK")
    }
    'get' {
        if (-not $Remote -or -not $Local) { Write-Output 'NEED -Remote and -Local'; exit 2 }
        $lw = $Local -replace '\\', '/'
        $lines.Add("rsync -az --info=progress2 -e 'ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' " +
                   "mu01:'$Remote' '$lw' && echo GET_OK")
    }
    'submit' {
        if (-not $Script) { Write-Output 'NEED -Script <local sbatch file>'; exit 2 }
        $sw = $Script -replace '\\', '/'
        $lines.Add('echo "== uploading =="')
        $lines.Add("rsync -az -e 'ssh -o BatchMode=yes' '$sw' mu01:~/jobs/ 2>/dev/null || ($SSH 'mkdir -p ~/jobs' && rsync -az -e 'ssh -o BatchMode=yes' '$sw' mu01:~/jobs/)")
        $lines.Add('$SSH "cd ~/jobs && sbatch $(basename ' + "'$sw'" + ')"')
    }
    'jobs' {
        $lines.Add('S ''squeue -u $USER -o "%.10i %.22j %.8T %.10M %.6D %R" 2>&1 | head -20''')
        $lines.Add('echo; echo "== newest output =="')
        $lines.Add('S ''f=$(ls -t ~/jobs/*.out 2>/dev/null | head -1); echo "$f"; tail -25 "$f" 2>/dev/null''')
    }
    'log' {
        if (-not $Remote) { Write-Output 'NEED -Remote <path>'; exit 2 }
        $lines.Add("S 'tail -40 $Remote'")
    }
}

$payload = ($lines -join "`n") + "`n"
$tmpWin = Join-Path $env:TEMP ('hpc_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.sh')
[IO.File]::WriteAllText($tmpWin, $payload)
# WSL cannot exec a CRLF script from /mnt with a Windows path; feed it to bash on stdin
$tmpMnt = '/mnt/' + $tmpWin.Substring(0, 1).ToLower() + (($tmpWin.Substring(2)) -replace '\\', '/')

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'wsl.exe'
$psi.Arguments = '-d ' + $Distro + ' -e bash ' + $tmpMnt
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.StandardOutputEncoding = [Text.Encoding]::UTF8
$psi.StandardErrorEncoding = [Text.Encoding]::UTF8

$sw = [Diagnostics.Stopwatch]::StartNew()
$p = [Diagnostics.Process]::Start($psi)
$o = $p.StandardOutput.ReadToEnd()
$e = $p.StandardError.ReadToEnd()
$p.WaitForExit(180000) | Out-Null
$sw.Stop()
Remove-Item -LiteralPath $tmpWin -Force -ErrorAction SilentlyContinue

# wsl.exe prints harmless config warnings on stderr; keep only interesting lines
$errKeep = @($e -split "`n" | Where-Object { $_ -and $_ -notmatch 'wsl2\.|Unknown key|localhost|WSL2' -and $_ -match '^[\x20-\x7E]*$' })
$text = $o
if ($errKeep.Count -gt 0) { $text += "`n[stderr] " + (($errKeep -join ' ') -replace '\s+', ' ') }

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$block = "===== $Action @ $stamp (exit=$($p.ExitCode), $([int]$sw.Elapsed.TotalSeconds)s) =====`n$text"
Write-Output $block
if (-not $NoOut) { Add-Content -LiteralPath $outPath -Value $block -Encoding UTF8 }
