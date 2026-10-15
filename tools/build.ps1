[CmdletBinding()]
param([string]$IdfPath = $env:IDF_PATH, [string]$IdfToolsPath = $env:IDF_TOOLS_PATH, [int]$Jobs = 0)
& "$PSScriptRoot/idf.ps1" build -IdfPath $IdfPath -IdfToolsPath $IdfToolsPath -Jobs $Jobs
