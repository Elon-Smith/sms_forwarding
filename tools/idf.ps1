[CmdletBinding()]
param(
    [ValidateSet('build', 'flash', 'monitor', 'reconfigure', 'clean', 'fullclean')]
    [string]$Action = 'build',
    [string]$Port,
    [string]$IdfPath = $env:IDF_PATH,
    [string]$IdfToolsPath = $env:IDF_TOOLS_PATH,
    [int]$Jobs = 0
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BuildDir = Join-Path $RepoRoot 'build\idf6'
$SdkConfig = Join-Path $RepoRoot 'build\sdkconfig.idf6'

if ([string]::IsNullOrWhiteSpace($IdfPath)) {
    throw 'Set IDF_PATH or pass -IdfPath pointing to ESP-IDF v6.0.2.'
}
if ([string]::IsNullOrWhiteSpace($IdfToolsPath)) {
    $IdfToolsPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.espressif'
}

if ($Action -in @('flash', 'monitor') -and [string]::IsNullOrWhiteSpace($Port)) { throw 'Pass -Port after identifying the physical ESP32-C3.' }
$env:PYTHONUTF8 = '1'
$ExportScript = Join-Path $IdfPath 'export.ps1'
if (-not (Test-Path -LiteralPath $ExportScript)) {
    throw "ESP-IDF export script not found: $ExportScript"
}

New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

$env:IDF_TOOLS_PATH = $IdfToolsPath
. $ExportScript
$SdkVersion = (& python "$IdfPath/tools/idf.py" --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $SdkVersion -notmatch "^ESP-IDF v6\.0\.2(?:-dirty)?$") { throw "Expected ESP-IDF v6.0.2, found: $SdkVersion" }

# 在外部 ESP-IDF 源码上应用项目维护的兼容 patch；由 git apply 严格检查上下文。
python (Join-Path $RepoRoot 'tools\apply_idf_patches.py') --idf-path $IdfPath
if ($LASTEXITCODE -ne 0) {
    throw 'ESP-IDF patch application failed; refusing to build unpatched firmware'
}

$IdfArgs = @('-B', $BuildDir, '-D', "SDKCONFIG=$SdkConfig")

switch ($Action) {
    'build' {
        idf.py @IdfArgs reconfigure
        if ($LASTEXITCODE -ne 0) { throw "IDF reconfigure failed" }
        if ($Jobs -le 0) {
            $Jobs = [int]$env:NUMBER_OF_PROCESSORS
            if ($Jobs -le 0) { $Jobs = 4 }
        }
        ninja -C $BuildDir -j $Jobs
    }
    'flash' {
        idf.py @IdfArgs -p $Port flash
    }
    'monitor' {
        idf.py @IdfArgs -p $Port monitor
    }
    'reconfigure' {
        idf.py @IdfArgs reconfigure
    }
    'clean' {
        idf.py @IdfArgs clean
    }
    'fullclean' {
        idf.py @IdfArgs fullclean
    }
}

if ($LASTEXITCODE -ne 0) { throw "ESP-IDF $Action failed ($LASTEXITCODE)" }
