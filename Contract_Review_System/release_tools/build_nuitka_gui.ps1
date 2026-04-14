param(
    [string]$EnvPython = "E:\conda_envs\langchain\python.exe",
    [string]$OutputRoot = "E:\Magic_wu_python\nuitka_dist",
    [switch]$IncludeRuntimeCache = $false,
    [switch]$IncludeWordAutomation = $false,
    [ValidateSet("mingw64", "zig", "msvc")]
    [string]$CompilerBackend = "mingw64"
)

$ErrorActionPreference = "Stop"

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

function Test-PythonModule {
    param(
        [string]$PythonExe,
        [string]$ModuleName
    )

    $probe = "import importlib.util; print('1' if importlib.util.find_spec('$ModuleName') else '0')"
    $result = & $PythonExe -X utf8 -c $probe
    return ($result | Out-String).Trim() -eq "1"
}

$repoRoot = (Resolve-Path ".").Path
$entryScript = Join-Path $repoRoot "Contract_Review_System\GUI\main.py"
$contractReviewRoot = Join-Path $repoRoot "Contract_Review_System"
$dataRoot = Join-Path $repoRoot "data"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$bundleName = "crsv1_nuitka_$timestamp"
$bundleRoot = Join-Path $OutputRoot $bundleName
$nuitkaOutputRoot = Join-Path $bundleRoot "build"
$distRoot = Join-Path $bundleRoot "dist"

Assert-PathExists $EnvPython "Python executable"
Assert-PathExists $entryScript "GUI entry script"
Assert-PathExists $contractReviewRoot "Contract_Review_System root"

Write-Step "Checking Nuitka availability"
$nuitkaVersion = & $EnvPython -X utf8 -c "import nuitka; print(getattr(nuitka, '__version__', 'unknown'))"
if (-not $nuitkaVersion) {
    throw "Failed to import Nuitka from: $EnvPython"
}
Write-Step "Detected Nuitka version: $($nuitkaVersion | Select-Object -First 1)"

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
if (Test-Path $bundleRoot) {
    Remove-Item -LiteralPath $bundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $bundleRoot, $nuitkaOutputRoot | Out-Null

$nuitkaArgs = @(
    "-m",
    "nuitka",
    "--standalone",
    "--assume-yes-for-downloads",
    "--enable-plugin=pyqt6",
    "--module-parameter=torch-disable-jit=yes",
    "--windows-console-mode=disable",
    "--remove-output",
    "--output-dir=$nuitkaOutputRoot",
    "--output-filename=crsv1_gui.exe",
    "--include-package=Contract_Review_System.GUI",
    "--include-package=Contract_Review_System.CRSv1",
    "--include-package=Contract_Review_System.contract_review_pipeline",
    "--include-package=Contract_Review_System.word2md",
    "--include-package=Contract_Review_System.common",
    "--include-package=mammoth",
    "--include-package=pdf2docx",
    "--include-package=fitz",
    "--include-data-file=$contractReviewRoot\\.env=Contract_Review_System/.env",
    "--include-data-file=$contractReviewRoot\\.env.example=Contract_Review_System/.env.example",
    "--nofollow-import-to=pytest",
    "--nofollow-import-to=IPython",
    "--nofollow-import-to=jupyter",
    "--nofollow-import-to=matplotlib",
    "--nofollow-import-to=tkinter",
    $entryScript
)

switch ($CompilerBackend) {
    "mingw64" { $nuitkaArgs += "--mingw64" }
    "zig" { $nuitkaArgs += "--zig" }
    "msvc" { $nuitkaArgs += "--msvc=latest" }
}

if ($IncludeWordAutomation -and (Test-PythonModule -PythonExe $EnvPython -ModuleName "win32com")) {
    $nuitkaArgs += "--include-package=win32com"
}
if ($IncludeWordAutomation -and (Test-PythonModule -PythonExe $EnvPython -ModuleName "comtypes")) {
    $nuitkaArgs += "--include-package=comtypes"
}

if ($IncludeRuntimeCache -and (Test-Path (Join-Path $dataRoot "contract_review_runtime_cache"))) {
    $nuitkaArgs += "--include-data-dir=$(Join-Path $dataRoot 'contract_review_runtime_cache')=data/contract_review_runtime_cache"
}

Write-Step "Running Nuitka build"
& $EnvPython @nuitkaArgs
$nuitkaExitCode = $LASTEXITCODE

if ($nuitkaExitCode -ne 0) {
    throw "Nuitka build failed with exit code: $nuitkaExitCode"
}

$compiledDist = Join-Path $nuitkaOutputRoot "main.dist"
Assert-PathExists $compiledDist "Nuitka output directory"
Move-Item -LiteralPath $compiledDist -Destination $distRoot -Force

$readmeText = @"
CRSv1 Nuitka Build
==================

How to use
----------
1. Keep the whole `dist` folder together.
2. Run `dist\crsv1_gui.exe`.
3. If `.pdf` conversion is needed, make sure `pdf2docx` conversion works on the target machine.
4. If `.doc` conversion is needed, Microsoft Word automation may still be required.

Notes
-----
- This build only targets the current GUI entry chain: `python Contract_Review_System/GUI/main.py`
- This Light branch keeps the current GUI entry chain but removes the old `docling` packaging dependency.
- DOCX -> Markdown uses `mammoth`, while PDF still follows `pdf2docx -> docx -> markdown`.
"@
Set-Content -Path (Join-Path $bundleRoot "README_FIRST_USE.txt") -Value $readmeText -Encoding UTF8

Write-Step "Nuitka bundle is ready"
Write-Host "BundleRoot: $bundleRoot"
Write-Host "DistRoot  : $distRoot"
