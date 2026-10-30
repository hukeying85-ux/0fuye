#Requires -Version 5.1
<#
.SYNOPSIS
    Fixed-path F-drive migration and watcher handover for the CGMD hub.

.DESCRIPTION
    This script is the execution engine behind the mailbox job kind "files".
    It is intentionally not a generic file manager.  The only source directory
    it can read is the legacy hub state directory on C:, and the only targets
    it can populate are the fixed F: layout:

        F:\cgmd\0fuye               deployed watcher clone
        F:\cgmd\runs\<task>         heavy run data
        F:\cgmd\results\<task>      small results and receipts

    Actions:
      survey             read-only inventory, drive space, layout and hashes
      migrate            copy one validated legacy prefix and verify SHA-256
      deploy             clone/update the locked repository on F: and write
                         a target-local hub configuration
      handover_stage     back up tasks, build the silent launcher, register a
                         distinct F: poll task and leave it disabled
      handover_enable    disable the legacy task and enable the F: task
                         without stopping a poll that is currently running
      handover_rollback  disable the F: task and re-enable the legacy task
      status             compact layout/task/status snapshot

    Every mutating action requires -ConfirmText to be exactly
    CGMD_F_MIGRATION_CONFIRMED.  Legacy C: files are never deleted or
    overwritten by this script.  A conflicting F: destination aborts a
    migration before any new final file is created.

.PARAMETER Action
    One of survey, migrate, deploy, handover_stage, handover_enable,
    handover_rollback or status.

.PARAMETER TaskId
    Directory name below F:\cgmd\runs and F:\cgmd\results.

.PARAMETER SourcePrefix
    Legacy file prefix inside the fixed C: state directory.  The default is
    cgmd_100ns, which covers cgmd_100ns_prod.*, equilibration and minimisation
    files produced under that prefix.

.PARAMETER Branch
    Branch to deploy into the F: clone.  Defaults to the current hub config.

.PARAMETER CopyCredentials
    During deploy, copy a repository-local git credential file from the old
    clone state to the new F: clone state and point the target clone at it.
    The credential contents are never logged or returned.

.PARAMETER ResultFile
    Machine-readable cgmd.files.result.v1 output consumed by the mailbox.
#>
[CmdletBinding()]
param(
    [string]$Action = 'survey',
    [string]$TaskId = 'legacy-cgmd-100ns-20261030',
    [string]$SourcePrefix = 'cgmd_100ns',
    [string]$Branch = '',
    [string]$ConfirmText = '',
    [string]$RepoPath = '',
    [string]$ConfigPath = '',
    [string]$ResultFile = '',
    [string]$OldTaskName = '',
    [string]$NewTaskName = '',
    [switch]$CopyCredentials,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:HubRoot = Split-Path -Parent $PSScriptRoot
$script:ScriptDir = $PSScriptRoot
$script:StateDir = Join-Path $script:HubRoot 'state'
$script:LogDir = Join-Path $script:HubRoot 'logs'
$script:StartedAt = Get-Date
$script:ConfirmRequired = 'CGMD_F_MIGRATION_CONFIRMED'
$script:FixedSourceDir = 'C:\cgmd\0fuye\skills\cgmd-hub\state'
$script:FixedTargetRepo = 'F:\cgmd\0fuye'
$script:FixedRunRoot = 'F:\cgmd\runs'
$script:FixedResultRoot = 'F:\cgmd\results'
$script:LockedRepo = 'hukeying85-ux/0fuye'
$script:LockedRepoUrl = 'https://github.com/hukeying85-ux/0fuye.git'
$script:ReceiptPath = ''
$script:WriteFileLog = ($Action -and ($Action.ToLowerInvariant() -notin @('survey', 'status')))

function Get-BeijingStamp {
    $utc = [DateTime]::UtcNow
    foreach ($id in @('China Standard Time', 'Asia/Shanghai')) {
        try {
            $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById($id)
            return [System.TimeZoneInfo]::ConvertTimeFromUtc($utc, $tz).ToString('yyyy-MM-ddTHH:mm:sszzz')
        } catch { continue }
    }
    return $utc.AddHours(8).ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
}

function Write-Say {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    if ($script:WriteFileLog -and (Test-Path -LiteralPath $script:LogDir -PathType Container)) {
        try {
            $file = Join-Path $script:LogDir ('files-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))
            [System.IO.File]::AppendAllText($file, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        } catch { }
    }
    if (-not $Quiet) { Write-Host $line }
}

function Read-JsonFile {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        return ($raw | ConvertFrom-Json)
    } catch { return $null }
}

function Write-JsonFile {
    param([string]$Path, $Data)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, ($Data | ConvertTo-Json -Depth 14), (New-Object System.Text.UTF8Encoding($false)))
}

function Get-Property {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) {
            $value = $Object[$Name]
            if ($null -eq $value) { return $Default }
            return $value
        }
        return $Default
    }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    if ($null -eq $prop.Value) { return $Default }
    return $prop.Value
}

function ConvertTo-OrderedDictionary {
    param($Object)
    $dict = [ordered]@{}
    if ($null -eq $Object) { return $dict }
    if ($Object -is [System.Collections.IDictionary]) {
        foreach ($key in $Object.Keys) { $dict[$key] = $Object[$key] }
    } else {
        foreach ($prop in $Object.PSObject.Properties) { $dict[$prop.Name] = $prop.Value }
    }
    return $dict
}

function Get-HubConfigPath {
    $candidates = @()
    if ($ConfigPath) { $candidates += $ConfigPath }
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.local.json')
    $candidates += (Join-Path $script:HubRoot 'config\cgmd_hub.json')
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return (Join-Path $script:HubRoot 'config\cgmd_hub.local.json')
}

function Get-HubConfig {
    $path = Get-HubConfigPath
    $cfg = Read-JsonFile -Path $path
    if ($null -ne $cfg) { return $cfg }
    return [pscustomobject]@{}
}

function Resolve-FullPath {
    param([string]$Path)
    if (-not $Path) { return '' }
    try { return [System.IO.Path]::GetFullPath($Path) } catch { return $Path }
}

function Test-PathsEqual {
    param([string]$Left, [string]$Right)
    if (-not $Left -or -not $Right) { return $false }
    $leftFull = (Resolve-FullPath -Path $Left).TrimEnd('\')
    $rightFull = (Resolve-FullPath -Path $Right).TrimEnd('\')
    return $leftFull.Equals($rightFull, [System.StringComparison]::OrdinalIgnoreCase)
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
    return (Test-Path -LiteralPath $Path -PathType Container)
}

function Get-Tail {
    param([string]$Path, [int]$Count = 40)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return @() }
    try {
        return @([System.IO.File]::ReadAllLines($Path, [System.Text.Encoding]::UTF8) |
                 Where-Object { $_ -ne '' } | Select-Object -Last $Count)
    } catch { return @() }
}

function Invoke-Git {
    param([string]$Directory, [string[]]$GitArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & git -C $Directory @GitArgs 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return [pscustomobject]@{ Code = $code; Output = $output.Trim() }
}

function Get-DriveSnapshot {
    param([string]$Root)
    $row = [ordered]@{
        root = $Root; ready = $false; total_bytes = 0; free_bytes = 0
        total_gb = 0; free_gb = 0; format = ''; label = ''
    }
    try {
        $drive = New-Object System.IO.DriveInfo($Root)
        $row['ready'] = [bool]$drive.IsReady
        if ($drive.IsReady) {
            $row['total_bytes'] = [int64]$drive.TotalSize
            $row['free_bytes'] = [int64]$drive.AvailableFreeSpace
            $row['total_gb'] = [math]::Round(([double]$drive.TotalSize / 1073741824.0), 3)
            $row['free_gb'] = [math]::Round(([double]$drive.AvailableFreeSpace / 1073741824.0), 3)
            $row['format'] = [string]$drive.DriveFormat
            $row['label'] = [string]$drive.VolumeLabel
        }
    } catch {
        $row['error'] = $_.Exception.Message
    }
    return $row
}

function Get-TaskSnapshot {
    param([string]$Name)
    $row = [ordered]@{
        name = $Name; exists = $false; state = ''; actions = @(); triggers = @()
        last_result = ''; last_run = ''; next_run = ''
    }
    if (-not $Name) { return $row }
    try {
        $task = Get-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction Stop
        $row['exists'] = $true
        $row['state'] = [string]$task.State
        foreach ($taskAction in @($task.Actions)) {
            $row['actions'] += (([string]$taskAction.Execute) + ' ' + ([string]$taskAction.Arguments) +
                                ' ' + ([string]$taskAction.WorkingDirectory)).Trim()
        }
        foreach ($taskTrigger in @($task.Triggers)) {
            if ($taskTrigger.CimClass -and $taskTrigger.CimClass.CimClassName) {
                $row['triggers'] += [string]$taskTrigger.CimClass.CimClassName
            } else {
                $row['triggers'] += 'unknown'
            }
        }
        try {
            $info = Get-ScheduledTaskInfo -TaskName $Name -TaskPath '\' -ErrorAction Stop
            $row['last_result'] = [string]$info.LastTaskResult
            if ($info.LastRunTime -and $info.LastRunTime.Year -gt 2000) {
                $row['last_run'] = ([datetime]$info.LastRunTime).ToString('yyyy-MM-dd HH:mm:ss')
            }
            if ($info.NextRunTime -and $info.NextRunTime.Year -gt 2000) {
                $row['next_run'] = ([datetime]$info.NextRunTime).ToString('yyyy-MM-dd HH:mm:ss')
            }
        } catch { }
    } catch {
        $row['error'] = $_.Exception.Message
    }
    return $row
}

function Get-Sha256 {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    try {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    } catch { return '' }
}

function Get-SourceInventory {
    param([string]$SourceDir, [string]$Prefix, [string]$TargetDir,
          [switch]$IncludeSourceHash, [switch]$IncludeTargetHash)
    $rows = @()
    $totalBytes = [int64]0
    if (Test-Path -LiteralPath $SourceDir -PathType Container) {
        $foundFiles = @(Get-ChildItem -LiteralPath $SourceDir -File -Filter ($Prefix + '*') |
                         Sort-Object Name)
        foreach ($foundFile in $foundFiles) {
            $destinationPath = Join-Path $TargetDir $foundFile.Name
            $destinationExists = Test-Path -LiteralPath $destinationPath -PathType Leaf
            $destinationBytes = [int64]0
            if ($destinationExists) {
                $destinationBytes = [int64](Get-Item -LiteralPath $destinationPath).Length
            }
            $sourceHash = ''
            if ($IncludeSourceHash) { $sourceHash = Get-Sha256 -Path $foundFile.FullName }
            $destinationHash = ''
            if ($destinationExists -and $IncludeTargetHash) {
                $destinationHash = Get-Sha256 -Path $destinationPath
            }
            $rows += [ordered]@{
                name = $foundFile.Name
                source = $foundFile.FullName
                target = $destinationPath
                bytes = [int64]$foundFile.Length
                sha256 = $sourceHash
                target_exists = [bool]$destinationExists
                target_bytes = $destinationBytes
                target_sha256 = $destinationHash
                target_matches = [bool]($destinationExists -and $sourceHash -and
                                         $destinationHash -and $sourceHash -eq $destinationHash -and
                                         $destinationBytes -eq [int64]$foundFile.Length)
            }
            $totalBytes += [int64]$foundFile.Length
        }
    }
    return [ordered]@{
        source_dir = $SourceDir; source_prefix = $Prefix; target_dir = $TargetDir
        files = $rows; file_count = $rows.Count; total_bytes = $totalBytes
        total_mb = [math]::Round(([double]$totalBytes / 1048576.0), 3)
    }
}

function Test-Confirmation {
    return ($ConfirmText -ceq $script:ConfirmRequired)
}

function Set-RestrictedAcl {
    param([string]$Path)
    try {
        $acl = New-Object System.Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME), 'FullControl', 'Allow')
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl
        return $true
    } catch { return $false }
}

function Copy-RepositoryCredentials {
    param([string]$SourceRepo, [string]$TargetRepo)
    $credentialInfo = [ordered]@{
        identity_configured = $false; helper_configured = $false
        credential_file_copied = $false; credential_file_present = $false
        acl_restricted = $false; notes = @()
    }
    foreach ($key in @('user.name', 'user.email')) {
        $valueResult = Invoke-Git -Directory $SourceRepo -GitArgs @('config', '--get', $key)
        if ($valueResult.Code -eq 0 -and $valueResult.Output.Trim()) {
            $null = Invoke-Git -Directory $TargetRepo -GitArgs @('config', $key, $valueResult.Output.Trim())
            $credentialInfo['identity_configured'] = $true
        }
    }
    $helperResult = Invoke-Git -Directory $SourceRepo -GitArgs @('config', '--get', 'credential.helper')
    $helperValue = ''
    if ($helperResult.Code -eq 0) { $helperValue = $helperResult.Output.Trim() }
    if (-not $helperValue) {
        $credentialInfo['notes'] += 'source clone has no repository-local credential.helper; target push access remains unverified'
        return $credentialInfo
    }
    if ($helperValue -like 'store --file=*') {
        $sourceCredentialPath = $helperValue.Substring('store --file='.Length).Trim().Trim('"')
        $targetCredentialPath = Join-Path $TargetRepo 'skills\cgmd-hub\state\git-credentials'
        $credentialInfo['credential_file_present'] = Test-Path -LiteralPath $targetCredentialPath -PathType Leaf
        if (-not $CopyCredentials) {
            $credentialInfo['notes'] += 'source uses a credential file; rerun deploy with copy_credentials=true to migrate it locally'
            return $credentialInfo
        }
        if (-not (Test-Path -LiteralPath $sourceCredentialPath -PathType Leaf)) {
            $credentialInfo['notes'] += 'source credential file named by credential.helper was not found'
            return $credentialInfo
        }
        if (Test-Path -LiteralPath $targetCredentialPath -PathType Leaf) {
            $targetHelper = 'store --file=' + $targetCredentialPath
            $null = Invoke-Git -Directory $TargetRepo -GitArgs @('config', 'credential.helper', $targetHelper)
            $credentialInfo['helper_configured'] = $true
            $credentialInfo['notes'] += 'target credential file already exists and was not overwritten; target helper now points at it'
            return $credentialInfo
        }
        $null = Ensure-Directory -Path (Split-Path -Parent $targetCredentialPath)
        Copy-Item -LiteralPath $sourceCredentialPath -Destination $targetCredentialPath
        $credentialInfo['credential_file_copied'] = $true
        $credentialInfo['credential_file_present'] = $true
        $credentialInfo['acl_restricted'] = Set-RestrictedAcl -Path $targetCredentialPath
        $targetHelper = 'store --file=' + $targetCredentialPath
        $null = Invoke-Git -Directory $TargetRepo -GitArgs @('config', 'credential.helper', $targetHelper)
        $credentialInfo['helper_configured'] = $true
        $credentialInfo['notes'] += 'credential file copied workstation-locally; contents were not logged or returned'
        return $credentialInfo
    }
    $null = Invoke-Git -Directory $TargetRepo -GitArgs @('config', 'credential.helper', $helperValue)
    $credentialInfo['helper_configured'] = $true
    $credentialInfo['notes'] += 'non-file credential helper copied to target repository-local git config'
    return $credentialInfo
}

function Export-TaskBackup {
    param([string]$Name, [string]$BackupDir, [string]$Stamp)
    $row = [ordered]@{ name = $Name; exists = $false; backup = '' }
    try {
        $task = Get-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction Stop
        $row['exists'] = $true
        $null = Ensure-Directory -Path $BackupDir
        $safeName = ($Name -replace '[^A-Za-z0-9_.-]', '_')
        $backupPath = Join-Path $BackupDir ($Stamp + '-' + $safeName + '.xml')
        $xmlText = Export-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction Stop
        [System.IO.File]::WriteAllText($backupPath, [string]$xmlText, (New-Object System.Text.UTF8Encoding($false)))
        $row['backup'] = $backupPath
    } catch {
        $row['error'] = $_.Exception.Message
    }
    return $row
}

function Test-TargetDeployment {
    param([string]$TargetRepo, [string]$ExpectedBranch)
    $checks = [ordered]@{
        repo_exists = (Test-Path -LiteralPath (Join-Path $TargetRepo '.git'))
        config_exists = $false; config_repo_matches = $false; config_branch = ''
        poll_script = $false; mailbox_script = $false; files_script = $false
        register_script = $false; build_script = $false
    }
    $configFile = Join-Path $TargetRepo 'skills\cgmd-hub\config\cgmd_hub.local.json'
    $checks['config_exists'] = Test-Path -LiteralPath $configFile -PathType Leaf
    if ($checks['config_exists']) {
        $targetConfig = Read-JsonFile -Path $configFile
        $checks['config_repo_matches'] = Test-PathsEqual -Left ([string](Get-Property $targetConfig 'repo_path' '')) -Right $TargetRepo
        $checks['config_branch'] = [string](Get-Property $targetConfig 'branch' '')
    }
    $runnerDir = Join-Path $TargetRepo 'skills\cgmd-hub\runner'
    $checks['poll_script'] = Test-Path -LiteralPath (Join-Path $runnerDir 'Invoke-CgmdPoll.ps1') -PathType Leaf
    $checks['mailbox_script'] = Test-Path -LiteralPath (Join-Path $runnerDir 'Invoke-CgmdMailbox.ps1') -PathType Leaf
    $checks['files_script'] = Test-Path -LiteralPath (Join-Path $runnerDir 'Invoke-CgmdFiles.ps1') -PathType Leaf
    $checks['register_script'] = Test-Path -LiteralPath (Join-Path $runnerDir 'Register-CgmdHubTask.ps1') -PathType Leaf
    $checks['build_script'] = Test-Path -LiteralPath (Join-Path $runnerDir 'Build-SilentLauncher.ps1') -PathType Leaf
    $checks['ready'] = [bool]($checks['repo_exists'] -and $checks['config_exists'] -and
                               $checks['config_repo_matches'] -and $checks['poll_script'] -and
                               $checks['mailbox_script'] -and $checks['files_script'] -and
                               $checks['register_script'] -and
                               ((-not $ExpectedBranch) -or ($checks['config_branch'] -eq $ExpectedBranch)))
    return $checks
}

$result = [ordered]@{
    schema = 'cgmd.files.result.v1'
    status = 'fail'
    summary = ''
    detail = [ordered]@{}
    logs_tail = @()
}
$detail = [ordered]@{}
$result['detail'] = $detail
$actionValue = $Action.ToLowerInvariant()
$logPath = Join-Path $script:LogDir ('files-{0}.log' -f (Get-Date -Format 'yyyyMMdd'))

try {
    $allowedActions = @('survey', 'migrate', 'deploy', 'handover_stage',
                        'handover_enable', 'handover_rollback', 'status')
    if ($allowedActions -notcontains $actionValue -or
        $TaskId -notmatch '^[A-Za-z0-9_-]+$' -or
        $SourcePrefix -notmatch '^[A-Za-z0-9_.-]+$' -or
        ($Branch -and ($Branch -notmatch '^[A-Za-z0-9_./-]+$' -or $Branch.Contains('..') -or
         $Branch.StartsWith('-'))) -or
        ($OldTaskName -and $OldTaskName -notmatch '^[A-Za-z0-9_ -]+$') -or
        ($NewTaskName -and $NewTaskName -notmatch '^[A-Za-z0-9_ -]+$')) {
        $result['status'] = 'unsupported'
        $result['summary'] = 'invalid files action, task_id, source_prefix, branch or task name'
        throw 'invalid files arguments'
    }

    $cfg = Get-HubConfig
    if (-not $RepoPath) { $RepoPath = [string](Get-Property $cfg 'repo_path' '') }
    if (-not $RepoPath -or -not (Test-Path -LiteralPath $RepoPath)) {
        $RepoPath = Split-Path -Parent (Split-Path -Parent $script:HubRoot)
    }
    $RepoPath = Resolve-FullPath -Path $RepoPath
    $branchEffective = $Branch
    if (-not $branchEffective) { $branchEffective = [string](Get-Property $cfg 'branch' '') }
    $oldTaskEffective = $OldTaskName
    if (-not $oldTaskEffective) { $oldTaskEffective = [string](Get-Property $cfg 'task_name' 'CGMD-Hub-Poll') }
    if (-not $oldTaskEffective) { $oldTaskEffective = 'CGMD-Hub-Poll' }
    $newTaskEffective = $NewTaskName
    if (-not $newTaskEffective) { $newTaskEffective = [string](Get-Property $cfg 'f_task_name' 'CGMD-Hub-Poll-F') }
    if (-not $newTaskEffective) { $newTaskEffective = 'CGMD-Hub-Poll-F' }

    $sourceDir = Resolve-FullPath -Path $script:FixedSourceDir
    $targetRepo = Resolve-FullPath -Path $script:FixedTargetRepo
    $runRoot = Resolve-FullPath -Path $script:FixedRunRoot
    $resultRoot = Resolve-FullPath -Path $script:FixedResultRoot
    $targetRunDir = Join-Path $runRoot $TaskId
    $targetResultDir = Join-Path $resultRoot $TaskId

    $detail['action'] = $actionValue
    $detail['worker'] = $env:COMPUTERNAME
    $detail['script'] = $PSCommandPath
    $detail['hub_root'] = $script:HubRoot
    $detail['state_dir'] = $script:StateDir
    $detail['log_dir'] = $script:LogDir
    $detail['repo_path'] = $RepoPath
    $detail['config_path'] = Get-HubConfigPath
    $detail['branch'] = $branchEffective
    $detail['source_dir'] = $sourceDir
    $detail['target_repo'] = $targetRepo
    $detail['run_root'] = $runRoot
    $detail['result_root'] = $resultRoot
    $detail['task_id'] = $TaskId
    $detail['target_run_dir'] = $targetRunDir
    $detail['target_result_dir'] = $targetResultDir
    $detail['old_task_name'] = $oldTaskEffective
    $detail['new_task_name'] = $newTaskEffective
    $detail['drives'] = [ordered]@{
        C = Get-DriveSnapshot -Root 'C:\'
        F = Get-DriveSnapshot -Root 'F:\'
    }
    $detail['layout'] = [ordered]@{
        source_dir_exists = (Test-Path -LiteralPath $sourceDir -PathType Container)
        target_repo_exists = (Test-Path -LiteralPath $targetRepo -PathType Container)
        target_repo_is_git = (Test-Path -LiteralPath (Join-Path $targetRepo '.git'))
        run_root_exists = (Test-Path -LiteralPath $runRoot -PathType Container)
        result_root_exists = (Test-Path -LiteralPath $resultRoot -PathType Container)
        target_run_dir_exists = (Test-Path -LiteralPath $targetRunDir -PathType Container)
        target_result_dir_exists = (Test-Path -LiteralPath $targetResultDir -PathType Container)
    }
    $detail['tasks'] = [ordered]@{
        legacy = Get-TaskSnapshot -Name $oldTaskEffective
        f_drive = Get-TaskSnapshot -Name $newTaskEffective
    }
    $detail['source_retained'] = $true
    $detail['notes'] = @()

    switch ($actionValue) {
        'survey' {
            $inventory = Get-SourceInventory -SourceDir $sourceDir -Prefix $SourcePrefix `
                -TargetDir $targetRunDir -IncludeSourceHash -IncludeTargetHash
            $detail['inventory'] = $inventory
            $conflicts = @($inventory['files'] | Where-Object {
                $_['target_exists'] -and -not $_['target_matches'] })
            $detail['target_conflicts'] = $conflicts
            $result['status'] = 'ok'
            $result['summary'] = ('survey: {0} source file(s), {1} bytes; F ready {2}; target conflicts {3}' -f
                $inventory['file_count'], $inventory['total_bytes'],
                $detail['drives']['F']['ready'], $conflicts.Count)
        }

        'status' {
            $inventory = Get-SourceInventory -SourceDir $sourceDir -Prefix $SourcePrefix -TargetDir $targetRunDir
            $detail['inventory'] = $inventory
            $detail['deployment'] = Test-TargetDeployment -TargetRepo $targetRepo -ExpectedBranch $branchEffective
            $result['status'] = 'ok'
            $result['summary'] = ('status: script {0}; state {1}; F deployment ready {2}' -f
                $PSCommandPath, $script:StateDir, $detail['deployment']['ready'])
        }

        'migrate' {
            if (-not (Test-Confirmation)) {
                $result['status'] = 'unsupported'
                $result['summary'] = 'migrate requires confirm=CGMD_F_MIGRATION_CONFIRMED'
                throw 'migration confirmation required'
            }
            $beforeDrive = Get-DriveSnapshot -Root 'F:\'
            if (-not $beforeDrive['ready']) {
                $result['status'] = 'fail'
                $result['summary'] = 'F: drive is not ready; migration not started'
                throw 'F drive not ready'
            }
            $inventoryBefore = Get-SourceInventory -SourceDir $sourceDir -Prefix $SourcePrefix `
                -TargetDir $targetRunDir -IncludeSourceHash -IncludeTargetHash
            $detail['inventory_before'] = $inventoryBefore
            if ([int]$inventoryBefore['file_count'] -eq 0) {
                $result['status'] = 'fail'
                $result['summary'] = ('no source files matching {0}* in {1}' -f $SourcePrefix, $sourceDir)
                throw 'no migration source files'
            }
            $conflicts = @($inventoryBefore['files'] | Where-Object {
                $_['target_exists'] -and -not $_['target_matches'] })
            $detail['target_conflicts'] = $conflicts
            if ($conflicts.Count -gt 0) {
                $result['status'] = 'conflict'
                $result['summary'] = ('migration aborted before copy: {0} target file(s) differ from C: sources' -f $conflicts.Count)
                break
            }
            $totalBytes = [int64]$inventoryBefore['total_bytes']
            $reserveBytes = [int64][math]::Max(1073741824.0, [math]::Ceiling([double]$totalBytes * 0.05))
            $requiredFree = $totalBytes + $reserveBytes
            $detail['required_free_bytes'] = $requiredFree
            if ([int64]$beforeDrive['free_bytes'] -lt $requiredFree) {
                $result['status'] = 'fail'
                $result['summary'] = ('insufficient F: free space: need {0} bytes including reserve, have {1}' -f
                    $requiredFree, $beforeDrive['free_bytes'])
                throw 'insufficient F free space'
            }
            $null = Ensure-Directory -Path $targetRunDir
            $null = Ensure-Directory -Path $targetResultDir
            $stampText = Get-Date -Format 'yyyyMMdd-HHmmss'
            $copiedRows = @()
            $failureCount = 0
            foreach ($inventoryRow in @($inventoryBefore['files'])) {
                $copyRow = [ordered]@{
                    name = $inventoryRow['name']; source = $inventoryRow['source']
                    target = $inventoryRow['target']; bytes = $inventoryRow['bytes']
                    sha256 = $inventoryRow['sha256']; status = ''
                }
                if ($inventoryRow['target_matches']) {
                    $copyRow['status'] = 'already_verified'
                    $copiedRows += $copyRow
                    continue
                }
                $partialPath = $inventoryRow['target'] + '.partial-' + $stampText
                if (Test-Path -LiteralPath $partialPath) {
                    $copyRow['status'] = 'partial_target_conflict'
                    $copyRow['partial'] = $partialPath
                    $failureCount++
                    $copiedRows += $copyRow
                    continue
                }
                try {
                    Copy-Item -LiteralPath $inventoryRow['source'] -Destination $partialPath
                    $partialBytes = [int64](Get-Item -LiteralPath $partialPath).Length
                    $partialHash = Get-Sha256 -Path $partialPath
                    if ($partialBytes -ne [int64]$inventoryRow['bytes'] -or
                        $partialHash -ne [string]$inventoryRow['sha256']) {
                        $copyRow['status'] = 'partial_verification_failed'
                        $copyRow['partial'] = $partialPath
                        $copyRow['target_sha256'] = $partialHash
                        $failureCount++
                    } else {
                        Move-Item -LiteralPath $partialPath -Destination $inventoryRow['target']
                        $finalHash = Get-Sha256 -Path $inventoryRow['target']
                        $copyRow['target_sha256'] = $finalHash
                        if ($finalHash -eq [string]$inventoryRow['sha256']) {
                            $copyRow['status'] = 'copied_verified'
                        } else {
                            $copyRow['status'] = 'final_verification_failed'
                            $failureCount++
                        }
                    }
                } catch {
                    $copyRow['status'] = 'copy_failed'
                    $copyRow['error'] = $_.Exception.Message
                    $failureCount++
                }
                $copiedRows += $copyRow
            }
            $inventoryAfter = Get-SourceInventory -SourceDir $sourceDir -Prefix $SourcePrefix `
                -TargetDir $targetRunDir -IncludeSourceHash -IncludeTargetHash
            $detail['files'] = $copiedRows
            $detail['inventory_after'] = $inventoryAfter
            $detail['drive_after'] = Get-DriveSnapshot -Root 'F:\'
            $receiptPath = Join-Path $targetResultDir ('migration-receipt-' + $stampText + '.json')
            $detail['receipt'] = $receiptPath
            $script:ReceiptPath = $receiptPath
            if ($failureCount -eq 0) {
                $result['status'] = 'ok'
                $result['summary'] = ('migrated and SHA-256 verified {0} file(s), {1} bytes to {2}; C: originals retained' -f
                    $copiedRows.Count, $totalBytes, $targetRunDir)
            } else {
                $result['status'] = 'fail'
                $result['summary'] = ('migration incomplete: {0} of {1} file(s) failed verification or copy' -f
                    $failureCount, $copiedRows.Count)
            }
        }

        'deploy' {
            if (-not (Test-Confirmation)) {
                $result['status'] = 'unsupported'
                $result['summary'] = 'deploy requires confirm=CGMD_F_MIGRATION_CONFIRMED'
                throw 'deploy confirmation required'
            }
            if (-not $branchEffective) {
                $result['status'] = 'unsupported'
                $result['summary'] = 'deploy needs a branch in args or the current hub config'
                throw 'deploy branch required'
            }
            $fDrive = Get-DriveSnapshot -Root 'F:\'
            if (-not $fDrive['ready']) {
                $result['status'] = 'fail'
                $result['summary'] = 'F: drive is not ready; deploy not started'
                throw 'F drive not ready'
            }
            $parentDir = Split-Path -Parent $targetRepo
            $null = Ensure-Directory -Path $parentDir
            $null = Ensure-Directory -Path $runRoot
            $null = Ensure-Directory -Path $resultRoot
            $gitNotes = @()
            if (-not (Test-Path -LiteralPath $targetRepo)) {
                $cloneResult = Invoke-Git -Directory $parentDir -GitArgs @(
                    'clone', '--branch', $branchEffective, '--single-branch',
                    $script:LockedRepoUrl, $targetRepo)
                $gitNotes += ('clone exit ' + $cloneResult.Code)
                if ($cloneResult.Code -ne 0) {
                    $detail['git_output'] = $cloneResult.Output
                    $result['status'] = 'fail'
                    $result['summary'] = 'git clone to F: failed'
                    throw 'git clone failed'
                }
            } else {
                if (-not (Test-Path -LiteralPath (Join-Path $targetRepo '.git'))) {
                    $result['status'] = 'conflict'
                    $result['summary'] = 'F: target exists but is not a git clone; nothing overwritten'
                    break
                }
                $originResult = Invoke-Git -Directory $targetRepo -GitArgs @('remote', 'get-url', 'origin')
                if ($originResult.Code -ne 0 -or $originResult.Output -notmatch [regex]::Escape($script:LockedRepo)) {
                    $result['status'] = 'conflict'
                    $result['summary'] = 'F: target origin is not the locked repository; nothing overwritten'
                    break
                }
                $statusResult = Invoke-Git -Directory $targetRepo -GitArgs @('status', '--porcelain')
                if ($statusResult.Output.Trim()) {
                    $detail['target_dirty_status'] = $statusResult.Output
                    $result['status'] = 'conflict'
                    $result['summary'] = 'F: target clone has uncommitted work; deploy refused to reset it'
                    break
                }
                $fetchRefspec = '+refs/heads/' + $branchEffective + ':refs/remotes/origin/' + $branchEffective
                foreach ($gitStep in @(
                    @('fetch', '--quiet', 'origin', $fetchRefspec),
                    @('checkout', '--quiet', '--force', '-B', $branchEffective, ('origin/' + $branchEffective)),
                    @('reset', '--hard', ('origin/' + $branchEffective)))) {
                    $stepResult = Invoke-Git -Directory $targetRepo -GitArgs $gitStep
                    $gitNotes += (($gitStep -join ' ') + ' -> ' + $stepResult.Code)
                    if ($stepResult.Code -ne 0) {
                        $detail['git_output'] = $stepResult.Output
                        $result['status'] = 'fail'
                        $result['summary'] = 'updating the existing F: clone failed'
                        throw 'git update failed'
                    }
                }
            }
            $targetHub = Join-Path $targetRepo 'skills\cgmd-hub'
            foreach ($targetDir in @((Join-Path $targetHub 'state'), (Join-Path $targetHub 'logs'),
                                      (Join-Path $targetHub 'config'), $targetRunDir, $targetResultDir)) {
                $null = Ensure-Directory -Path $targetDir
            }
            $targetCfg = ConvertTo-OrderedDictionary -Object $cfg
            $targetCfg['repo_path'] = $targetRepo
            $targetCfg['branch'] = $branchEffective
            $targetCfg['locked_repo'] = $script:LockedRepo
            $targetCfg['run_root'] = $runRoot
            $targetCfg['result_root'] = $resultRoot
            $targetCfg['f_repo_path'] = $targetRepo
            $targetCfg['migration_source_dir'] = $sourceDir
            $targetCfg['wsl_workdir_root'] = '/mnt/f/cgmd/runs'
            $targetCfg['task_name'] = $newTaskEffective
            $targetCfg['legacy_task_name'] = $oldTaskEffective
            $targetCfg['f_task_name'] = $newTaskEffective
            $targetCfg['mailbox_ref'] = [string](Get-Property $cfg 'mailbox_ref' 'hub/mailbox')
            $targetConfigPath = Join-Path $targetHub 'config\cgmd_hub.local.json'
            Write-JsonFile -Path $targetConfigPath -Data $targetCfg
            $detail['target_config'] = $targetConfigPath
            $detail['git_notes'] = $gitNotes
            $detail['credentials'] = Copy-RepositoryCredentials -SourceRepo $RepoPath -TargetRepo $targetRepo
            $headResult = Invoke-Git -Directory $targetRepo -GitArgs @('rev-parse', 'HEAD')
            $remoteResult = Invoke-Git -Directory $targetRepo -GitArgs @('rev-parse', ('origin/' + $branchEffective))
            $detail['target_head'] = $headResult.Output.Trim()
            $detail['target_origin_head'] = $remoteResult.Output.Trim()
            $detail['deployment'] = Test-TargetDeployment -TargetRepo $targetRepo -ExpectedBranch $branchEffective
            if ($detail['deployment']['ready'] -and $headResult.Output.Trim() -eq $remoteResult.Output.Trim()) {
                if ($detail['credentials']['helper_configured'] -or $detail['credentials']['credential_file_present']) {
                    $result['status'] = 'ok'
                    $result['summary'] = ('deployed locked repository at {0} on {1} / {2}' -f
                        $targetRepo, $branchEffective, $detail['target_head'])
                } else {
                    $result['status'] = 'partial'
                    $result['summary'] = ('deployed F: clone and config, but target push credentials are not verified' )
                }
            } else {
                $result['status'] = 'fail'
                $result['summary'] = 'F: deployment verification failed; scheduled task was not changed'
            }
        }

        'handover_stage' {
            if (-not (Test-Confirmation)) {
                $result['status'] = 'unsupported'
                $result['summary'] = 'handover_stage requires confirm=CGMD_F_MIGRATION_CONFIRMED'
                throw 'handover confirmation required'
            }
            $deployment = Test-TargetDeployment -TargetRepo $targetRepo -ExpectedBranch $branchEffective
            $detail['deployment_before'] = $deployment
            if (-not $deployment['ready']) {
                $result['status'] = 'fail'
                $result['summary'] = 'F: deployment is not verified ready; no scheduled task was registered'
                break
            }
            $null = Ensure-Directory -Path $targetResultDir
            $stampText = Get-Date -Format 'yyyyMMdd-HHmmss'
            $backupDir = Join-Path $targetResultDir 'scheduled-task-backups'
            $detail['task_backups'] = @(
                Export-TaskBackup -Name $oldTaskEffective -BackupDir $backupDir -Stamp $stampText
                Export-TaskBackup -Name $newTaskEffective -BackupDir $backupDir -Stamp $stampText
            )
            $targetRunner = Join-Path $targetRepo 'skills\cgmd-hub\runner'
            $buildScript = Join-Path $targetRunner 'Build-SilentLauncher.ps1'
            $launcherPath = ''
            try {
                $builtLauncher = & $buildScript
                if ($builtLauncher) { $launcherPath = [string]$builtLauncher }
                if ($launcherPath -and (Test-Path -LiteralPath $launcherPath -PathType Leaf)) {
                    $detail['notes'] += ('silent launcher ready: ' + $launcherPath)
                } else {
                    $launcherPath = ''
                    $detail['notes'] += 'silent launcher was not built; task will use the windowless wscript fallback'
                }
            } catch {
                $launcherPath = ''
                $detail['notes'] += ('silent launcher build failed; wscript fallback remains available: ' + $_.Exception.Message)
            }
            $registerScript = Join-Path $targetRunner 'Register-CgmdHubTask.ps1'
            $pollSeconds = [int](Get-Property $cfg 'poll_seconds' 60)
            if ($pollSeconds -le 0) { $pollSeconds = 60 }
            if ($launcherPath) {
                & $registerScript -TaskName $newTaskEffective -IntervalSeconds $pollSeconds -UseWrapperExe -SkipFirstRun
            } else {
                & $registerScript -TaskName $newTaskEffective -IntervalSeconds $pollSeconds -SkipFirstRun
            }
            Disable-ScheduledTask -TaskName $newTaskEffective -TaskPath '\' -ErrorAction Stop | Out-Null
            $detail['tasks_after'] = [ordered]@{
                legacy = Get-TaskSnapshot -Name $oldTaskEffective
                f_drive = Get-TaskSnapshot -Name $newTaskEffective
            }
            $newActions = ($detail['tasks_after']['f_drive']['actions'] -join ' ')
            $actionMatchesTarget = $newActions.Contains($targetRepo)
            $detail['new_task_action_matches_target'] = $actionMatchesTarget
            if ($actionMatchesTarget -and $detail['tasks_after']['f_drive']['state'] -eq 'Disabled') {
                $result['status'] = 'ok'
                $result['summary'] = ('F: watcher task staged and left disabled; legacy watcher unchanged; backups in {0}' -f $backupDir)
            } else {
                $result['status'] = 'fail'
                $result['summary'] = 'F: watcher task staging verification failed; legacy watcher was not disabled'
            }
        }

        'handover_enable' {
            if (-not (Test-Confirmation)) {
                $result['status'] = 'unsupported'
                $result['summary'] = 'handover_enable requires confirm=CGMD_F_MIGRATION_CONFIRMED'
                throw 'handover confirmation required'
            }
            $deployment = Test-TargetDeployment -TargetRepo $targetRepo -ExpectedBranch $branchEffective
            $detail['deployment_before'] = $deployment
            $newBefore = Get-TaskSnapshot -Name $newTaskEffective
            $newActions = ($newBefore['actions'] -join ' ')
            if (-not $deployment['ready'] -or -not $newBefore['exists'] -or -not $newActions.Contains($targetRepo)) {
                $result['status'] = 'fail'
                $result['summary'] = 'F: watcher is not staged and verified; enable refused and legacy task unchanged'
                break
            }
            $null = Ensure-Directory -Path $targetResultDir
            $stampText = Get-Date -Format 'yyyyMMdd-HHmmss'
            $backupDir = Join-Path $targetResultDir 'scheduled-task-backups'
            $detail['task_backups'] = @(
                Export-TaskBackup -Name $oldTaskEffective -BackupDir $backupDir -Stamp $stampText
                Export-TaskBackup -Name $newTaskEffective -BackupDir $backupDir -Stamp $stampText
            )
            Disable-ScheduledTask -TaskName $oldTaskEffective -TaskPath '\' -ErrorAction Stop | Out-Null
            Enable-ScheduledTask -TaskName $newTaskEffective -TaskPath '\' -ErrorAction Stop | Out-Null
            $detail['tasks_after'] = [ordered]@{
                legacy = Get-TaskSnapshot -Name $oldTaskEffective
                f_drive = Get-TaskSnapshot -Name $newTaskEffective
            }
            $detail['notes'] += 'the currently running legacy poll was not stopped; verify two later files status receipts report the F: script and state paths'
            if ($detail['tasks_after']['legacy']['state'] -eq 'Disabled' -and
                $detail['tasks_after']['f_drive']['state'] -ne 'Disabled') {
                $result['status'] = 'ok'
                $result['summary'] = 'F: watcher enabled and legacy watcher disabled; current running poll was not stopped'
            } else {
                $result['status'] = 'fail'
                $result['summary'] = 'watcher handover state verification failed; inspect task snapshots and backups'
            }
        }

        'handover_rollback' {
            if (-not (Test-Confirmation)) {
                $result['status'] = 'unsupported'
                $result['summary'] = 'handover_rollback requires confirm=CGMD_F_MIGRATION_CONFIRMED'
                throw 'handover confirmation required'
            }
            $legacyBefore = Get-TaskSnapshot -Name $oldTaskEffective
            if (-not $legacyBefore['exists']) {
                $result['status'] = 'fail'
                $result['summary'] = 'legacy watcher task does not exist; rollback refused'
                break
            }
            Disable-ScheduledTask -TaskName $newTaskEffective -TaskPath '\' -ErrorAction SilentlyContinue | Out-Null
            Enable-ScheduledTask -TaskName $oldTaskEffective -TaskPath '\' -ErrorAction Stop | Out-Null
            $detail['tasks_after'] = [ordered]@{
                legacy = Get-TaskSnapshot -Name $oldTaskEffective
                f_drive = Get-TaskSnapshot -Name $newTaskEffective
            }
            if ($detail['tasks_after']['legacy']['state'] -ne 'Disabled') {
                $result['status'] = 'ok'
                $result['summary'] = 'watcher rollback complete: legacy task enabled and F: task disabled where present'
            } else {
                $result['status'] = 'fail'
                $result['summary'] = 'watcher rollback verification failed'
            }
        }
    }
} catch {
    if (-not $result['summary']) {
        $result['status'] = 'error'
        $result['summary'] = ('files action failed: ' + $_.Exception.Message)
    }
    Write-Say $result['summary'] 'ERROR'
}

$result['finished_at'] = Get-BeijingStamp
$result['seconds'] = [math]::Round(((Get-Date) - $script:StartedAt).TotalSeconds, 2)
$result['worker'] = $env:COMPUTERNAME
$result['logs_tail'] = @(Get-Tail -Path $logPath -Count 40)

if ($ResultFile) {
    try { Write-JsonFile -Path $ResultFile -Data $result } catch { }
}
if ($script:ReceiptPath) {
    try { Write-JsonFile -Path $script:ReceiptPath -Data $result } catch { }
}
if (-not $Quiet) { Write-Output ($result | ConvertTo-Json -Depth 14) }

if ($result['status'] -eq 'ok' -or $result['status'] -eq 'partial') { exit 0 }
exit 1
