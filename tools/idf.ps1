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
$BuildDir = Join-Path $RepoRoot 'build\idf5.5.5'
$SdkConfig = Join-Path $RepoRoot 'build\sdkconfig.idf5.5.5'

if ([string]::IsNullOrWhiteSpace($IdfPath)) {
    throw 'Set IDF_PATH or pass -IdfPath pointing to ESP-IDF v5.5.5.'
}
if ([string]::IsNullOrWhiteSpace($IdfToolsPath)) {
    $IdfToolsPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.espressif'
}

if ($Action -in @('flash', 'monitor') -and [string]::IsNullOrWhiteSpace($Port)) { throw 'Pass -Port after identifying the physical ESP32-C3.' }
$env:PYTHONUTF8 = '1'
$IdfPath = (Resolve-Path -LiteralPath $IdfPath).Path
$IdfToolsPath = (Resolve-Path -LiteralPath $IdfToolsPath).Path
# A terminal may already contain another SDK. Remove its activation and host-test
# compiler overrides before exporting this SDK, then validate the actual tools.
$env:Path = (($env:Path -split ';') | Where-Object {
    $_ -notmatch '(?i)[\\/](esp-idf[^\\/]*|python_env|riscv32-esp-elf|xtensa-esp-elf)[\\/]'
}) -join ';'
foreach ($Name in @('IDF_PATH', 'IDF_PYTHON_ENV_PATH', 'IDF_VERSION', 'IDF_TARGET',
                    'VIRTUAL_ENV', 'PYTHONHOME', 'PYTHONPATH', 'CC', 'CXX',
                    'SDKCONFIG', 'IDF_TOOLS_EXPORT_CMD', 'IDF_TOOLS_INSTALL_CMD')) {
    [Environment]::SetEnvironmentVariable($Name, $null, 'Process')
}
$ExportScript = Join-Path $IdfPath 'export.ps1'
if (-not (Test-Path -LiteralPath $ExportScript)) {
    throw "ESP-IDF export script not found: $ExportScript"
}

New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

$env:IDF_TOOLS_PATH = $IdfToolsPath
. $ExportScript
$SdkVersion = (& python "$IdfPath/tools/idf.py" --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $SdkVersion -notmatch "^ESP-IDF v5\.5\.5(?:-dirty)?$") { throw "Expected ESP-IDF v5.5.5, found: $SdkVersion" }
$PythonPath = (Get-Command python -CommandType Application | Select-Object -First 1).Source
$CompilerPath = (Get-Command riscv32-esp-elf-gcc -CommandType Application | Select-Object -First 1).Source
$CompilerVersion = (& $CompilerPath --version | Select-Object -First 1)
if ($PythonPath -notmatch '[\\/]idf5\.5_py[^\\/]+[\\/]') { throw "Wrong IDF Python environment: $PythonPath" }
if ($CompilerVersion -notmatch 'esp-14\.2\.0_20260121.*14\.2\.0') { throw "Wrong C3 compiler: $CompilerVersion" }
Write-Host "SDK: $IdfPath ($SdkVersion)"
Write-Host "Python: $PythonPath"
Write-Host "Compiler: $CompilerPath ($CompilerVersion)"

# 在外部 ESP-IDF 源码上应用项目维护的兼容 patch；由 git apply 严格检查上下文。
python (Join-Path $RepoRoot 'tools\apply_idf_patches.py') --idf-path $IdfPath
if ($LASTEXITCODE -ne 0) {
    throw 'ESP-IDF patch application failed; refusing to build unpatched firmware'
}

# Release candidates compile directly; do not reuse a machine-wide ccache.
$IdfArgs = @('--no-ccache', '-B', $BuildDir, '-D', "SDKCONFIG=$SdkConfig")

Push-Location -LiteralPath $RepoRoot
try {
switch ($Action) {
    'build' {
        idf.py @IdfArgs reconfigure
        if ($LASTEXITCODE -ne 0) { throw "IDF reconfigure failed" }
        if ($Jobs -le 0) {
            $Jobs = [int]$env:NUMBER_OF_PROCESSORS
            if ($Jobs -le 0) { $Jobs = 4 }
        }
        ninja -C $BuildDir -j $Jobs
        if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed' }
        python (Join-Path $RepoRoot 'tools/verify_build.py') --build $BuildDir --idf-path $IdfPath
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
} finally {
    Pop-Location
}
