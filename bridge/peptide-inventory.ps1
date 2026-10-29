#Requires -Version 5.1
<#
Read-only inventory of short peptides in a local simulation folder.
Outputs a small JSON object to the pipeline; never reads trajectory contents.
No network calls, installation, or changes to the scanned folder.
#>
[CmdletBinding()]
param(
    [string]$SearchRoot = 'F:\0wsh\asd',
    [ValidateRange(1, 365)][int]$DaysBack = 90,
    [ValidateRange(1, 50)][int]$MaxCandidates = 12
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $SearchRoot -PathType Container)) {
    throw ('Search root not found or inaccessible: ' + $SearchRoot)
}

$amino = @{
    ALA='A'; ARG='R'; ASN='N'; ASP='D'; CYS='C'; GLN='Q'; GLU='E'; GLY='G';
    HIS='H'; ILE='I'; LEU='L'; LYS='K'; MET='M'; PHE='F'; PRO='P'; SER='S';
    THR='T'; TRP='W'; TYR='Y'; VAL='V'
}
$structureExtensions = @('.pdb', '.gro', '.fa', '.fasta')
$runExtensions = @('.xtc', '.trr', '.cpt', '.log', '.edr', '.dcd')
$maxStructureBytes = 20 * 1024 * 1024
$cutoff = [DateTime]::UtcNow.AddDays(-$DaysBack)

function Parse-Pdb([string]$Path) {
    $chains = @{}
    $n = 0
    foreach ($line in [IO.File]::ReadLines($Path)) {
        $n++
        if ($n -gt 250000 -or $line.StartsWith('ENDMDL')) { break }
        if ($line.Length -lt 27 -or
            (-not $line.StartsWith('ATOM  ') -and -not $line.StartsWith('HETATM'))) { continue }
        $alt = $line.Substring(16, 1)
        if ($alt -ne ' ' -and $alt -ne 'A') { continue }
        $res = $line.Substring(17, 3).Trim().ToUpperInvariant()
        if (-not $amino.ContainsKey($res)) { continue }
        $chain = $line.Substring(21, 1).Trim()
        if (-not $chain) { $chain = '_' }
        if (-not $chains.ContainsKey($chain)) {
            $chains[$chain] = New-Object System.Collections.Specialized.OrderedDictionary
        }
        $position = $line.Substring(22, 5).Trim()
        if (-not $chains[$chain].Contains($position)) {
            $chains[$chain].Add($position, $amino[$res])
        }
    }
    foreach ($chain in @($chains.Keys | Sort-Object)) {
        $sequence = -join @($chains[$chain].Values)
        if ($sequence.Length -ge 2 -and $sequence.Length -le 30) {
            [pscustomobject]@{ chain = $chain; sequence = $sequence; residues = $sequence.Length }
        }
    }
}

function Parse-Gro([string]$Path) {
    $reader = [IO.File]::OpenText($Path)
    try {
        $null = $reader.ReadLine()
        $atomLine = $reader.ReadLine()
        [int]$atomCount = 0
        if (-not [int]::TryParse($atomLine, [ref]$atomCount) -or $atomCount -gt 200000) { return }
        $residues = New-Object System.Collections.Specialized.OrderedDictionary
        for ($i = 0; $i -lt $atomCount; $i++) {
            $line = $reader.ReadLine()
            if (-not $line -or $line.Length -lt 10) { break }
            $res = $line.Substring(5, 5).Trim().ToUpperInvariant()
            if (-not $amino.ContainsKey($res)) { continue }
            $key = $line.Substring(0, 5).Trim() + ':' + $res
            if (-not $residues.Contains($key)) { $residues.Add($key, $amino[$res]) }
        }
        $sequence = -join @($residues.Values)
        if ($sequence.Length -ge 2 -and $sequence.Length -le 30) {
            [pscustomobject]@{ chain = '_'; sequence = $sequence; residues = $sequence.Length }
        }
    } finally { $reader.Dispose() }
}

function Parse-Fasta([string]$Path) {
    $sequence = ''
    $started = $false
    foreach ($line in [IO.File]::ReadLines($Path)) {
        if ($line.StartsWith('>')) {
            if ($started) { break }
            $started = $true
            continue
        }
        if ($started) { $sequence += $line.Trim().ToUpperInvariant() }
        if ($sequence.Length -gt 30) { break }
    }
    if ($sequence -cmatch '^[ACDEFGHIKLMNPQRSTVWY]{2,30}$') {
        [pscustomobject]@{ chain = '_'; sequence = $sequence; residues = $sequence.Length }
    }
}

$files = @(Get-ChildItem -LiteralPath $SearchRoot -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $structureExtensions -contains $_.Extension.ToLowerInvariant() -and $_.Length -le $maxStructureBytes } |
    Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 250)
$results = New-Object System.Collections.Generic.List[object]
$warnings = New-Object System.Collections.Generic.List[string]
foreach ($file in $files) {
    try {
        $parsed = @()
        switch ($file.Extension.ToLowerInvariant()) {
            '.pdb' { $parsed = @(Parse-Pdb $file.FullName); break }
            '.gro' { $parsed = @(Parse-Gro $file.FullName); break }
            default { $parsed = @(Parse-Fasta $file.FullName) }
        }
        if ($parsed.Count -eq 0) { continue }
        # Files are only inspected for their name and modification time. Their
        # trajectories, checkpoints, and log contents stay on the PC.
        $nearby = @(Get-ChildItem -LiteralPath $file.DirectoryName -File -ErrorAction SilentlyContinue |
            Where-Object { $runExtensions -contains $_.Extension.ToLowerInvariant() } |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 3)
        $last = $file.LastWriteTimeUtc
        foreach ($evidence in $nearby) {
            if ($evidence.LastWriteTimeUtc -gt $last) { $last = $evidence.LastWriteTimeUtc }
        }
        if ($last -lt $cutoff) { continue }
        foreach ($p in $parsed) {
            $results.Add([pscustomobject]@{
                file = $file.FullName
                format = $file.Extension.ToLowerInvariant().TrimStart('.')
                chain = $p.chain
                sequence = $p.sequence
                residues = $p.residues
                last_activity_utc = $last.ToString('o')
                run_evidence = @($nearby | Select-Object -ExpandProperty Name)
            })
        }
    } catch {
        if ($warnings.Count -lt 8) { $warnings.Add(('Could not inspect ' + $file.Name + ': ' + $_.Exception.Message)) }
    }
}
$ranked = @($results | Sort-Object `
    @{Expression = { $_.run_evidence.Count -gt 0 }; Descending = $true},
    @{Expression = { $_.last_activity_utc }; Descending = $true} |
    Select-Object -First $MaxCandidates)
$tools = [ordered]@{}
foreach ($tool in @('gmx', 'wsl', 'nvidia-smi', 'python', 'py')) {
    $tools[$tool] = [bool](Get-Command $tool -ErrorAction SilentlyContinue)
}
[pscustomobject]@{
    schema = 'peptide-inventory.v1'
    scanned_at_utc = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    root = $SearchRoot
    days_back = $DaysBack
    scanned_structure_files = $files.Count
    candidates = $ranked
    tools_on_windows_path = $tools
    warnings = @($warnings.ToArray())
}
