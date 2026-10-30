#Requires -Version 5.1
<#
Read-only, one-shot local evidence collection for an EXACT peptide sequence.
Reads F: (or -SearchRoot), never modifies it, does not run MD or access the network.
Writes a private ZIP under LOCALAPPDATA (not a synced Documents folder), NOT to this public repository.
It can include a full log (if <=5 MB); review it for private paths before upload.
A same-stem GRO + TPR + completed recent MD log is required to label a run
"verified_recent_md"; adjacent files alone are explicitly not proof.
Review the ZIP locally before uploading it to a private Drive folder.
#>
[CmdletBinding()]
param(
    [ValidatePattern('^[ACDEFGHIKLMNPQRSTVWY]{2,30}$')][string]$Sequence = 'YLSLLQR',
    [string]$SearchRoot = 'F:\0wsh\asd',
    [ValidateRange(1, 365)][int]$DaysBack = 90,
    [ValidateRange(1, 10000)][int]$MaxStructures = 3000,
    [ValidateRange(1, 100)][int]$MaxStructureMB = 30,
    [string]$OutputRoot = ''
)

$ErrorActionPreference = 'Stop'
$Sequence = $Sequence.ToUpperInvariant()
if (-not (Test-Path -LiteralPath $SearchRoot -PathType Container -ErrorAction SilentlyContinue)) {
    throw ('SearchRoot is not accessible: ' + $SearchRoot + '. Run this ON the Windows PC with the real F: project; no G: disk is needed.')
}
if (-not $OutputRoot) {
    $privateBase = $env:LOCALAPPDATA
    if (-not $privateBase) { $privateBase = $HOME }
    $OutputRoot = Join-Path $privateBase 'ArenaPrivatePeptideEvidence'
}
$trailingSeparators = [char[]]@('\', '/')
$sourceRoot = [IO.Path]::GetFullPath($SearchRoot).TrimEnd($trailingSeparators)
$output = [IO.Path]::GetFullPath($OutputRoot).TrimEnd($trailingSeparators)
$comparison = [StringComparison]::OrdinalIgnoreCase
if ($output.Equals($sourceRoot, $comparison) -or
    $output.StartsWith(($sourceRoot + [IO.Path]::DirectorySeparatorChar), $comparison)) {
    throw 'OutputRoot must be OUTSIDE the source simulation tree.'
}
# Prevent accidental placement of original structures or local paths in public Git.
$ancestor = $output
while ($ancestor) {
    if (Test-Path -LiteralPath (Join-Path $ancestor '.git') -PathType Container -ErrorAction SilentlyContinue) {
        throw 'OutputRoot is inside a Git repository; choose a private local folder instead.'
    }
    $parent = [IO.Directory]::GetParent($ancestor)
    if ($null -eq $parent) { break }
    $ancestor = $parent.FullName
}

$aa = @{
    ALA='A'; ARG='R'; ASN='N'; ASP='D'; CYS='C'; GLN='Q'; GLU='E'; GLY='G';
    HIS='H'; ILE='I'; LEU='L'; LYS='K'; MET='M'; PHE='F'; PRO='P'; SER='S';
    THR='T'; TRP='W'; TYR='Y'; VAL='V'
}
$extensions = @('.pdb', '.pdbqt', '.gro', '.fa', '.fasta')
$cutoffUtc = [DateTime]::UtcNow.AddDays(-$DaysBack)
$limitBytes = [int64]$MaxStructureMB * 1024 * 1024

function Get-PdbMatch([IO.FileInfo]$File, [string]$Wanted) {
    $chains = @{}
    foreach ($line in [IO.File]::ReadLines($File.FullName)) {
        if ($line.StartsWith('ENDMDL')) { break } # only the first model
        if ($line.Length -lt 27 -or
            (-not $line.StartsWith('ATOM  ') -and -not $line.StartsWith('HETATM'))) { continue }
        if ($line.Substring(16, 1) -notin @(' ', 'A')) { continue }
        $name = $line.Substring(17, 3).Trim().ToUpperInvariant()
        if (-not $aa.ContainsKey($name)) { continue }
        $chain = $line.Substring(21, 1).Trim()
        if (-not $chain) { $chain = '_' }
        $position = $line.Substring(22, 5).Trim() # includes insertion code
        if (-not $position) { continue }
        if (-not $chains.ContainsKey($chain)) {
            $chains[$chain] = New-Object System.Collections.Specialized.OrderedDictionary
        }
        if (-not $chains[$chain].Contains($position)) {
            $chains[$chain].Add($position, $aa[$name])
        }
    }
    $embeddedChain = $null
    foreach ($chain in @($chains.Keys | Sort-Object)) {
        $chainSequence = -join @($chains[$chain].Values)
        if ($chainSequence -ceq $Wanted) {
            return [pscustomobject]@{ kind = 'exact_pdb_chain'; chain = $chain }
        }
        if ($chainSequence.Contains($Wanted)) { $embeddedChain = $chain }
    }
    if ($null -ne $embeddedChain) {
        return [pscustomobject]@{ kind = 'embedded_in_pdb_chain'; chain = $embeddedChain }
    }
    return $null
}

function Get-GroMatch([IO.FileInfo]$File, [string]$Wanted) {
    $reader = [IO.File]::OpenText($File.FullName)
    try {
        $null = $reader.ReadLine() # title
        $atomLine = $reader.ReadLine()
        [int]$atomCount = 0
        if (-not [int]::TryParse($atomLine, [ref]$atomCount) -or
            $atomCount -lt 1 -or $atomCount -gt 1000000) {
            throw ('Malformed or unsupported GRO atom count: ' + $File.FullName)
        }
        $segments = New-Object System.Collections.Generic.List[string]
        $sequenceFound = ''
        $prevKey = ''
        $prevId = -1
        for ($i = 0; $i -lt $atomCount; $i++) {
            $line = $reader.ReadLine()
            if (-not $line -or $line.Length -lt 20) {
                throw ('Truncated GRO atom records: ' + $File.FullName)
            }
            $name = $line.Substring(5, 5).Trim().ToUpperInvariant()
            $idText = $line.Substring(0, 5).Trim()
            [int]$id = 0
            if (-not $aa.ContainsKey($name) -or -not [int]::TryParse($idText, [ref]$id)) {
                if ($sequenceFound) { $segments.Add($sequenceFound) }
                $sequenceFound = ''; $prevKey = ''; $prevId = -1
                continue
            }
            $key = $idText + ':' + $name
            if ($key -ceq $prevKey) { continue } # another atom of same residue
            if ($prevId -ge 0 -and $id -ne (($prevId + 1) % 100000)) {
                if ($sequenceFound) { $segments.Add($sequenceFound) }
                $sequenceFound = ''
            }
            $sequenceFound += $aa[$name]
            $prevKey = $key; $prevId = $id
            if ($sequenceFound.Length -gt 2000) {
                $segments.Add($sequenceFound)
                $sequenceFound = ''; $prevKey = ''; $prevId = -1
            }
        }
        if ($sequenceFound) { $segments.Add($sequenceFound) }
        $embedded = $false
        foreach ($segment in $segments) {
            if ($segment -ceq $Wanted) {
                return [pscustomobject]@{ kind = 'exact_gro_molecule'; chain = '_' }
            }
            if ($segment.Contains($Wanted)) { $embedded = $true }
        }
        if ($embedded) {
            return [pscustomobject]@{ kind = 'embedded_in_gro_segment'; chain = '?' }
        }
        return $null
    } finally { $reader.Dispose() }
}

function Get-FastaMatch([IO.FileInfo]$File, [string]$Wanted) {
    $sequenceFound = ''
    $label = ''
    $active = $false
    foreach ($line in [IO.File]::ReadLines($File.FullName)) {
        if ($line.StartsWith('>')) {
            if ($active -and $sequenceFound -ceq $Wanted) {
                return [pscustomobject]@{ kind = 'exact_fasta_record'; chain = $label }
            }
            $label = $line.Trim().Substring(1)
            if ($label.Length -gt 80) { $label = $label.Substring(0, 80) }
            $sequenceFound = ''; $active = $true
        } elseif ($active -and $sequenceFound.Length -le 30) {
            $sequenceFound += $line.Trim().ToUpperInvariant()
        }
    }
    if ($active -and $sequenceFound -ceq $Wanted) {
        return [pscustomobject]@{ kind = 'exact_fasta_record'; chain = $label }
    }
    return $null
}

function Get-RunInfo([IO.FileInfo]$GroFile) {
    $stem = $GroFile.BaseName
    $folder = $GroFile.DirectoryName
    $logPath = Join-Path $folder ($stem + '.log')
    $tprPath = Join-Path $folder ($stem + '.tpr')
    $hasLog = Test-Path -LiteralPath $logPath -PathType Leaf
    $hasTpr = Test-Path -LiteralPath $tprPath -PathType Leaf
    $tprInfo = $null
    if ($hasTpr) {
        $tpr = Get-Item -LiteralPath $tprPath
        $tprInfo = [pscustomobject]@{
            path = $tpr.FullName; size_bytes = $tpr.Length
            modified_utc = $tpr.LastWriteTimeUtc.ToString('o')
        }
    }
    if (-not $hasLog) {
        return [pscustomobject]@{ status = 'no_same_stem_log'; log = $null; tpr = $tprInfo; companions = @(); excerpt = @() }
    }
    $log = Get-Item -LiteralPath $logPath
    # Check the actual log, not just filenames or modification times. A GROMACS
    # EM log also says "Finished mdrun", so require an MD/SD/BD integrator.
    $head = @(Get-Content -LiteralPath $logPath -TotalCount 350 -ErrorAction Stop)
    $tail = @(Get-Content -LiteralPath $logPath -Tail 350 -ErrorAction Stop)
    $integrator = @($head | Where-Object { $_ -match '(?i)^\s*integrator\s*=\s*(md|md-vv|md-vv-avek|sd|bd)\b' }).Count -gt 0
    $complete = @($tail | Where-Object { $_ -match '(?i)^\s*(Finished mdrun\b|Performance\s*:)' }).Count -gt 0
    $fatal = @($tail | Where-Object { $_ -match '(?i)^\s*(Fatal error|Error in user input)\s*:' }).Count -gt 0
    $recent = $log.LastWriteTimeUtc -ge $cutoffUtc
    $structureRecent = $GroFile.LastWriteTimeUtc -ge $cutoffUtc
    $timesAligned = [Math]::Abs(($log.LastWriteTimeUtc - $GroFile.LastWriteTimeUtc).TotalDays) -le 3
    $excerpt = @($head + $tail | Where-Object {
        $_ -match '(?i)^\s*(GROMACS version|integrator\s*=|dt\s*=|nsteps\s*=|Started mdrun\b|Finished mdrun\b|Performance\s*:|Fatal error\s*:)' 
    } | Select-Object -Unique | Select-Object -Last 24 | ForEach-Object {
        if ($_.Length -gt 300) { $_.Substring(0, 300) } else { $_ }
    })
    $companions = @()
    foreach ($ext in @('.xtc', '.trr', '.edr', '.cpt', '.mdp')) {
        $path = Join-Path $folder ($stem + $ext)
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $info = Get-Item -LiteralPath $path
            $companions += [pscustomobject]@{
                path = $info.FullName; size_bytes = $info.Length
                modified_utc = $info.LastWriteTimeUtc.ToString('o')
            }
        }
    }
    $status = 'run_not_verified'
    if (-not $hasTpr) {
        $status = 'same_stem_log_missing_tpr'
    } elseif ($recent -and $structureRecent -and $timesAligned -and $complete -and $integrator -and -not $fatal) {
        $status = 'recent_completed_md'
    } elseif (-not $recent -or -not $structureRecent -or -not $timesAligned) {
        $status = 'log_or_structure_not_recent_or_aligned'
    } elseif ($fatal) {
        $status = 'log_reports_error'
    } elseif (-not $integrator) {
        $status = 'integrator_not_confirmed_as_md'
    } elseif (-not $complete) {
        $status = 'run_not_completed_in_log'
    }
    return [pscustomobject]@{
        status = $status
        log = [pscustomobject]@{ path = $log.FullName; size_bytes = $log.Length; modified_utc = $log.LastWriteTimeUtc.ToString('o') }
        tpr = $tprInfo
        companions = $companions; excerpt = $excerpt
    }
}

$hits = New-Object System.Collections.Generic.List[object]
$warnings = New-Object System.Collections.Generic.List[string]
$scanErrors = @()
$inspected = 0
$oversized = 0
$partial = $false
foreach ($file in (Get-ChildItem -LiteralPath $SearchRoot -Recurse -File -ErrorAction SilentlyContinue -ErrorVariable +scanErrors)) {
    if ($extensions -notcontains $file.Extension.ToLowerInvariant()) { continue }
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
    if ($file.Length -gt $limitBytes) { $oversized++; continue }
    $inspected++
    if ($inspected -gt $MaxStructures) { $partial = $true; break }
    try {
        $match = $null
        switch ($file.Extension.ToLowerInvariant()) {
            { $_ -in @('.pdb', '.pdbqt') } { $match = Get-PdbMatch $file $Sequence; break }
            '.gro' { $match = Get-GroMatch $file $Sequence; break }
            default { $match = Get-FastaMatch $file $Sequence }
        }
        if ($null -eq $match) { continue }
        $run = $null
        if ($file.Extension.ToLowerInvariant() -eq '.gro') {
            $run = Get-RunInfo $file
        }
        $hits.Add([pscustomobject]@{
            path = $file.FullName; format = $file.Extension.ToLowerInvariant().TrimStart('.')
            kind = $match.kind; chain = $match.chain; size_bytes = $file.Length
            modified_utc = $file.LastWriteTimeUtc.ToString('o'); run = $run
        })
    } catch {
        $partial = $true
        if ($warnings.Count -lt 12) { $warnings.Add(('Could not inspect ' + $file.FullName + ': ' + $_.Exception.Message)) }
    }
}
if ($scanErrors.Count -gt 0) {
    $partial = $true
    $warnings.Add(('Some subdirectories could not be scanned (' + $scanErrors.Count + ' errors); absence is NOT proven.'))
}
if ($oversized -gt 0) {
    $partial = $true
    $warnings.Add(('Skipped ' + $oversized + ' structures over the size limit; absence is NOT proven. Narrow SearchRoot if needed.'))
}

$ranked = @($hits | Sort-Object `
    @{ Expression = {
        if ($_.run -and $_.run.status -eq 'recent_completed_md' -and $_.kind -eq 'exact_gro_molecule') { 5 }
        elseif ($_.run -and $_.run.status -eq 'recent_completed_md') { 4 }
        elseif ($_.run -and $_.run.log -and $_.kind -eq 'exact_gro_molecule') { 3 }
        elseif ($_.kind -eq 'exact_pdb_chain') { 2 }
        elseif ($_.kind -match '^exact_') { 1 }
        else { 0 }
    }; Descending = $true },
    @{ Expression = { $_.modified_utc }; Descending = $true })
$status = 'target_not_found'
if ($partial) { $status = 'incomplete_scan_target_not_found' }
if ($hits.Count -gt 0) { $status = 'sequence_found_run_not_verified' }
$verified = @($ranked | Where-Object { $_.run -and $_.run.status -eq 'recent_completed_md' -and $_.kind -eq 'exact_gro_molecule' })
if ($verified.Count -gt 0) { $status = 'verified_recent_md' }
elseif (@($ranked | Where-Object { $_.run -and $_.run.status -eq 'recent_completed_md' }).Count -gt 0) {
    $status = 'sequence_in_recent_run_but_not_isolated_molecule'
}

$runId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$bundleName = 'Arena-' + $Sequence + '-evidence-' + $runId
$bundleDir = Join-Path $output $bundleName
$zipPath = Join-Path $output ($bundleName + '.zip')
if (-not (Test-Path -LiteralPath $output -PathType Container)) {
    $null = New-Item -ItemType Directory -Path $output -Force -ErrorAction Stop
}
$null = New-Item -ItemType Directory -Path $bundleDir -ErrorAction Stop
$copies = @()
$primary = $null
if ($ranked.Count -gt 0) {
    $primary = $ranked[0]
    $toCopy = @($primary)
    # Optional all-atom starting structure ONLY if it sits beside the selected
    # run's GRO. A same-name PDB elsewhere is not proof of this particular run.
    if ($primary.format -eq 'gro') {
        $pdb = @($ranked | Where-Object {
            $_.format -eq 'pdb' -and [IO.Path]::GetDirectoryName($_.path) -eq [IO.Path]::GetDirectoryName($primary.path)
        } | Select-Object -First 1)
        if ($pdb.Count -gt 0) { $toCopy += $pdb[0] }
    }
    $index = 0
    foreach ($candidate in $toCopy) {
        $index++
        $destName = 'structure-' + $index.ToString('00') + '.' + $candidate.format
        $dest = Join-Path $bundleDir $destName
        Copy-Item -LiteralPath $candidate.path -Destination $dest -ErrorAction Stop
        $copies += [pscustomobject]@{
            bundle_name = $destName; source_path = $candidate.path
            sha256 = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
            kind = $candidate.kind; note = 'Copied for inspection only; may contain solvent, other chains, or CG beads.'
        }
    }
    if ($primary.run -and $primary.run.log) {
        $log = $primary.run.log
        if ($log.size_bytes -le (100 * 1024 * 1024)) {
            $primary.run.log | Add-Member -NotePropertyName sha256 -NotePropertyValue (
                (Get-FileHash -LiteralPath $log.path -Algorithm SHA256).Hash.ToLowerInvariant()
            )
        }
        if ($log.size_bytes -le (5 * 1024 * 1024)) {
            Copy-Item -LiteralPath $log.path -Destination (Join-Path $bundleDir 'run-01.log') -ErrorAction Stop
            $copies += [pscustomobject]@{
                bundle_name = 'run-01.log'; source_path = $log.path
                sha256 = (Get-FileHash -LiteralPath (Join-Path $bundleDir 'run-01.log') -Algorithm SHA256).Hash.ToLowerInvariant()
                kind = 'same_stem_run_log'; note = 'Full log: review paths and host metadata before private upload.'
            }
        } else {
            $warnings.Add('Selected log is over 5 MB: only its evidence excerpt is included; request the original locally if needed.')
        }
        $text = "Selected run log: $($log.path)`r`nEvidence excerpt; review any included full run-01.log before uploading.`r`n" +
            (($primary.run.excerpt | Out-String).Trim()) + "`r`n"
        [IO.File]::WriteAllText((Join-Path $bundleDir 'log-excerpt.txt'), $text, [Text.UTF8Encoding]::new($false))
    }
}
$manifest = [ordered]@{
    schema = 'arena.peptide-evidence.v1'
    status = $status
    target_sequence = $Sequence
    search_root = $sourceRoot
    inspected_at_utc = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    recency_days = $DaysBack
    inspected_structure_count = [Math]::Min($inspected, $MaxStructures)
    skipped_oversized_count = $oversized
    scan_partial = $partial
    selected = $primary
    selected_copies = @($copies)
    matches = @($ranked | Select-Object -First 20)
    warnings = @($warnings.ToArray())
    cautions = @(
        'Only exact-chain/molecule hits with matching-stem GRO, TPR, completed recent MD log are labelled verified_recent_md.',
        'Only standard residue names are parsed. A negative search does not rule out modified/renamed peptides or unsupported formats.',
        'A matching peptide sequence does not establish terminal chemistry, atomistic detail, force field, or applicability of Martini 3.',
        'Selected structure and a small full log may be copied locally for private review; no trajectories are copied, no MD is run, and no network upload is performed.'
    )
}
$json = ConvertTo-Json -InputObject $manifest -Depth 9
[IO.File]::WriteAllText((Join-Path $bundleDir 'manifest.json'), ($json + "`n"), [Text.UTF8Encoding]::new($false))
$notice = "PRIVATE F: EVIDENCE. Review manifest.json, structure file(s), and log-excerpt.txt before sharing.`r`n" +
    "Upload this ZIP only to the owner-only Drive folder or attach privately; NEVER git add/commit/push it to this public repository.`r`n" +
    "Status $status is based on the local files actually read; it is not a new MD result.`r`n"
[IO.File]::WriteAllText((Join-Path $bundleDir 'README.txt'), $notice, [Text.UTF8Encoding]::new($false))
$bundleFiles = @(Get-ChildItem -LiteralPath $bundleDir -File | Select-Object -ExpandProperty FullName)
Compress-Archive -LiteralPath $bundleFiles -DestinationPath $zipPath -CompressionLevel Optimal -ErrorAction Stop
Write-Host ('STATUS: ' + $status)
Write-Host ('Structure files inspected: ' + [Math]::Min($inspected, $MaxStructures) + '; sequence hits: ' + $hits.Count + '; partial scan: ' + $partial)
Write-Host ('PRIVATE ZIP (review before uploading): ' + $zipPath)
Write-Host 'Do not put it in the public Git repository. No G: disk, git push, or new software is required.'
