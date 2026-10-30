$ErrorActionPreference='Stop'
$root='E:\0apps\DSHPet'
$env:APPDATA=Join-Path $root 'data'
$env:LOCALAPPDATA=Join-Path $root 'local-data'
New-Item -ItemType Directory -Force $env:APPDATA,$env:LOCALAPPDATA | Out-Null
$exe=Get-ChildItem $root -Filter 'dsh-pet-standalone-webm.exe' -Recurse -File | Select-Object -First 1
if (-not $exe) { throw 'Verified non-chat pet executable not found' }
Set-Location $exe.DirectoryName
$p=Start-Process -FilePath $exe.FullName -WorkingDirectory $exe.DirectoryName -PassThru
$p.WaitForExit()
exit $p.ExitCode
