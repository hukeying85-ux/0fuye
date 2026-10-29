$action='hide'
if (Test-Path 'E:\0apps\ArenaDesk\data\pet-hidden.flag') { $action='show' }
& (Join-Path $PSScriptRoot 'control.ps1') -Action $action -Name 'arena-desktop-pet'
