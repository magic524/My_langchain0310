param(
    [string]$EnvPrefix = "E:\conda_envs\langchain",
    [string]$OutputRoot = "Contract_Review_System\dist",
    [switch]$IncludeRuntimeCache = $true
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Write-Step {
    param([string]$Message)
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] $Message"
}

function Assert-PathExists {
    param(
        [string]$TargetPath,
        [string]$Label
    )
    if (-not (Test-Path $TargetPath)) {
        throw "$Label not found: $TargetPath"
    }
}

function Expand-ZipToFreshDirectory {
    param(
        [string]$ArchivePath,
        [string]$DestinationPath
    )

    $destinationParent = Split-Path -Parent $DestinationPath
    if ($destinationParent -and -not (Test-Path $destinationParent)) {
        New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    }

    if (Test-Path $DestinationPath) {
        Remove-Item -LiteralPath $DestinationPath -Recurse -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 300
    }

    if (Test-Path $DestinationPath) {
        throw "Failed to clean destination before extraction: $DestinationPath"
    }

    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $DestinationPath -Force
}

function Copy-TreeIfExists {
    param(
        [string]$SourcePath,
        [string]$DestinationPath
    )

    if (-not (Test-Path $SourcePath)) {
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DestinationPath) | Out-Null
    & robocopy $SourcePath $DestinationPath /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD __pycache__ outputs tests dist .git .mypy_cache .pytest_cache | Out-Null
}

function Copy-FileIfExists {
    param(
        [string]$SourcePath,
        [string]$DestinationPath
    )

    if (-not (Test-Path $SourcePath)) {
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DestinationPath) | Out-Null
    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
}

$repoRoot = (Resolve-Path ".").Path
$contractReviewRoot = Join-Path $repoRoot "Contract_Review_System"
if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    $resolvedOutputRoot = $OutputRoot
} else {
    $resolvedOutputRoot = Join-Path $repoRoot $OutputRoot
}
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$bundleName = "crsv1_$timestamp"
$bundleRoot = Join-Path $resolvedOutputRoot $bundleName
$appRoot = Join-Path $bundleRoot "app"
$runtimeRoot = Join-Path $bundleRoot "runtime\langchain"
$artifactRoot = Join-Path $bundleRoot "_build_artifacts"
$envArchive = Join-Path $artifactRoot "langchain_env.zip"
$targetContractReviewRoot = Join-Path $appRoot "Contract_Review_System"

$envPython = Join-Path $EnvPrefix "python.exe"
$envPythonw = Join-Path $EnvPrefix "pythonw.exe"
$envCondaPack = Join-Path $EnvPrefix "Scripts\conda-pack.exe"

Assert-PathExists $contractReviewRoot "Project directory"
Assert-PathExists $envPython "langchain python.exe"
Assert-PathExists $envPythonw "langchain pythonw.exe"
Assert-PathExists $envCondaPack "conda-pack executable"

New-Item -ItemType Directory -Force -Path $resolvedOutputRoot | Out-Null
if (Test-Path $bundleRoot) {
    Remove-Item -LiteralPath $bundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bundleRoot, $appRoot, $artifactRoot, $targetContractReviewRoot | Out-Null

Write-Step "Packing the langchain runtime environment"
& $envCondaPack --prefix $EnvPrefix --output $envArchive --format zip

Write-Step "Expanding the portable runtime"
Expand-ZipToFreshDirectory -ArchivePath $envArchive -DestinationPath $runtimeRoot

Write-Step "Copying minimal application code"
$requiredDirectories = @(
    "GUI",
    "CRSv1",
    "contract_review_pipeline",
    "word2md",
    "common"
)
foreach ($relativeDir in $requiredDirectories) {
    Copy-TreeIfExists -SourcePath (Join-Path $contractReviewRoot $relativeDir) -DestinationPath (Join-Path $targetContractReviewRoot $relativeDir)
}

$requiredFiles = @(
    ".env",
    ".env.example",
    "README.md",
    "__init__.py"
)
foreach ($relativeFile in $requiredFiles) {
    Copy-FileIfExists -SourcePath (Join-Path $contractReviewRoot $relativeFile) -DestinationPath (Join-Path $targetContractReviewRoot $relativeFile)
}

Write-Step "Copying required data directories"
$dataSource = Join-Path $repoRoot "data"
$dataTarget = Join-Path $appRoot "data"
New-Item -ItemType Directory -Force -Path $dataTarget | Out-Null
if ($IncludeRuntimeCache -and (Test-Path (Join-Path $dataSource "contract_review_runtime_cache"))) {
    Copy-TreeIfExists -SourcePath (Join-Path $dataSource "contract_review_runtime_cache") -DestinationPath (Join-Path $dataTarget "contract_review_runtime_cache")
}
New-Item -ItemType Directory -Force -Path (Join-Path $dataTarget "contract_review_outputs\word2md") | Out-Null

Write-Step "Writing launchers and usage notes"
$startGuiBat = @"
@echo off
setlocal
cd /d "%~dp0"
set "BUNDLE_ROOT=%~dp0"
set "APP_ROOT=%BUNDLE_ROOT%app"
set "RUNTIME_ROOT=%BUNDLE_ROOT%runtime\langchain"
set "UNPACK_FLAG=%RUNTIME_ROOT%\.portable_runtime_ready"

if not exist "%RUNTIME_ROOT%\pythonw.exe" (
  echo Portable runtime is missing. Please keep runtime\langchain intact.
  pause
  exit /b 1
)

if not exist "%UNPACK_FLAG%" (
  echo Initializing the portable runtime. Please wait...
  call "%RUNTIME_ROOT%\Scripts\conda-unpack.exe" > "%BUNDLE_ROOT%runtime_init.log" 2>&1
  if errorlevel 1 (
    echo Runtime initialization failed. Please check runtime_init.log
    pause
    exit /b 1
  )
  type nul > "%UNPACK_FLAG%"
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%APP_ROOT%"
start "" "%RUNTIME_ROOT%\pythonw.exe" "%APP_ROOT%\Contract_Review_System\GUI\main.py"
exit /b 0
"@
Set-Content -Path (Join-Path $bundleRoot "start_contract_review_gui.bat") -Value $startGuiBat -Encoding UTF8

$startGuiConsoleBat = @"
@echo off
setlocal
cd /d "%~dp0"
set "BUNDLE_ROOT=%~dp0"
set "APP_ROOT=%BUNDLE_ROOT%app"
set "RUNTIME_ROOT=%BUNDLE_ROOT%runtime\langchain"
set "UNPACK_FLAG=%RUNTIME_ROOT%\.portable_runtime_ready"

if not exist "%UNPACK_FLAG%" (
  echo Initializing the portable runtime. Please wait...
  call "%RUNTIME_ROOT%\Scripts\conda-unpack.exe" > "%BUNDLE_ROOT%runtime_init.log" 2>&1
  if errorlevel 1 (
    echo Runtime initialization failed. Please check runtime_init.log
    pause
    exit /b 1
  )
  type nul > "%UNPACK_FLAG%"
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%APP_ROOT%"
"%RUNTIME_ROOT%\python.exe" "%APP_ROOT%\Contract_Review_System\GUI\main.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo GUI exited with code: %EXIT_CODE%
  pause
)
exit /b %EXIT_CODE%
"@
Set-Content -Path (Join-Path $bundleRoot "start_contract_review_gui_console.bat") -Value $startGuiConsoleBat -Encoding UTF8

$readmeText = @"
CRSv1 Portable Sample Bundle
============================

How to use
----------
1. Extract the whole folder to a short writable path, for example E:\CRSv1 or D:\CRSv1
2. Double-click start_contract_review_gui.bat
3. If startup fails, run start_contract_review_gui_console.bat to view the error output

Notes
-----
- This sample already includes a Python runtime. No separate conda or Python install is required.
- The app reads model settings from app\Contract_Review_System\.env
- Target users should be inside the company network and able to reach the same local_llm service.
- If .doc conversion still depends on Microsoft Office, Office should exist on the target machine.
- The first launch runs conda-unpack automatically, so startup will be slower once.
- Please do not unzip the bundle into a deeply nested folder, or Windows path length limits may still appear.

Directory layout
----------------
- app\ : minimal application code and required data directories
- runtime\langchain\ : packed runtime environment
"@
Set-Content -Path (Join-Path $bundleRoot "README_FIRST_USE.txt") -Value $readmeText -Encoding UTF8

Write-Step "Cleaning packaging artifacts"
if (Test-Path $artifactRoot) {
    Remove-Item -LiteralPath $artifactRoot -Recurse -Force
}

Write-Step "Creating a distributable zip archive"
$bundleZip = Join-Path $resolvedOutputRoot "$bundleName.zip"
if (Test-Path $bundleZip) {
    Remove-Item -LiteralPath $bundleZip -Force
}
Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $bundleZip -CompressionLevel Fastest

Write-Step "Portable sample bundle is ready"
Write-Host "BundleRoot: $bundleRoot"
Write-Host "BundleZip : $bundleZip"
