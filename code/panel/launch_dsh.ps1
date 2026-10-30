$ErrorActionPreference='Stop'
$env:DSH_HOME='E:\0apps\DSH\data'
$env:npm_config_cache='E:\0apps\DSH\npm-cache'
$env:PATH='E:\hermes\node;'+$env:PATH
Set-Location 'E:\0apps\DSH'
& 'E:\hermes\node\node.exe' 'E:\0apps\DSH\node_modules\@deepseek-ai\dsh\lib\bin.js' web --no-open *> 'E:\0apps\ArenaDesk\data\dsh-runtime.log'
exit $LASTEXITCODE
