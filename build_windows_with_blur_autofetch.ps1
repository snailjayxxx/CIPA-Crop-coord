# Build a private, one-file CIPA Crop + FindsBlur v1.3.1 EXE locally.
# Requires Windows x64, Python 3.12 or 3.11, and GitHub CLI (gh auth login).
# Private CIPA-Calc source and diagnostic data remain on this machine.
[CmdletBinding()]
param(
    [string]$CalcRoot = $env:CIPA_CALC_ROOT
)
$ErrorActionPreference = 'Stop'
$cropRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'Install GitHub CLI (gh) and run: gh auth login'
}
& gh auth status
if ($LASTEXITCODE -ne 0) {
    throw 'GitHub CLI is not logged in: run gh auth login first.'
}
if ([string]::IsNullOrWhiteSpace($CalcRoot)) {
    $CalcRoot = Join-Path (Split-Path $cropRoot -Parent) 'CIPA-Calc'
}
$CalcRoot = [System.IO.Path]::GetFullPath($CalcRoot)
$coreFile = Join-Path $CalcRoot 'standalone_gui\core.py'
if (-not (Test-Path -LiteralPath $coreFile)) {
    if (Test-Path -LiteralPath $CalcRoot) {
        throw "CIPA-Calc folder exists but source was not found: $CalcRoot"
    }
    Write-Host "Cloning private CIPA-Calc checkout into $CalcRoot (no remote changes)..."
    & gh repo clone snailjayxxx/CIPA-Calc "$CalcRoot" -- --branch main
    if ($LASTEXITCODE -ne 0) {
        throw 'Cannot access private CIPA-Calc; verify your GitHub account permissions.'
    }
}
$env:CIPA_CALC_ROOT = $CalcRoot
$decoder = $env:FINDSBLUR_IJG8C_EXE
if (-not $decoder -or -not (Test-Path -LiteralPath $decoder)) {
    $decoder = Join-Path $CalcRoot '_work\IJG8c\bin\ijg8c_rgb_probe.exe'
}
if (-not (Test-Path -LiteralPath $decoder)) {
    $zipRoot = Join-Path $cropRoot '.integration_assets'
    $zipPath = Join-Path $zipRoot 'FindsBlur-v1.3.1-Windows-x64.zip'
    $unpack = Join-Path $zipRoot 'findsblur-v131'
    New-Item -ItemType Directory -Path $zipRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $zipPath)) {
        $json = & gh run list -R snailjayxxx/CIPA-Calc --workflow findsblur-windows-v1.3.1.yml --limit 10 --json databaseId,conclusion
        if ($LASTEXITCODE -ne 0) { throw 'Unable to locate private FindsBlur build runs.' }
        $runs = $json | ConvertFrom-Json
        $run = $runs | Where-Object { $_.conclusion -eq 'success' } | Select-Object -First 1
        if (-not $run) { throw 'No successful FindsBlur v1.3.1 build found.' }
        Write-Host "Downloading private v1.3.1 IJG decoder artifact from run $($run.databaseId)..."
        & gh run download $run.databaseId -R snailjayxxx/CIPA-Calc -n FindsBlur-v1.3.1-Windows-x64 -D "$zipRoot"
        if ($LASTEXITCODE -ne 0) {
            throw 'Unable to download the decoder artifact from the private repository.'
        }
    }
    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Expected FindsBlur artifact ZIP not found: $zipPath"
    }
    if (-not (Test-Path -LiteralPath $unpack)) {
        Expand-Archive -LiteralPath $zipPath -DestinationPath $unpack -Force
    }
    $native = Get-ChildItem -LiteralPath $unpack -File -Recurse -Filter 'ijg8c_rgb_probe.exe' | Select-Object -First 1
    if (-not $native) { throw 'IJG8c decoder was not present inside the ZIP.' }
    $decoder = $native.FullName
}
$env:FINDSBLUR_IJG8C_EXE = $decoder
Write-Host "Calculator source: $CalcRoot"
Write-Host "Native JPEG decoder: $decoder"
Write-Host "Building integrated EXE locally. No private source is uploaded."
Push-Location $cropRoot
try {
    & cmd.exe /d /c '"build_windows_with_blur.bat"'
    if ($LASTEXITCODE -ne 0) {
        throw "Integrated build failed with exit code $LASTEXITCODE"
    }
    $output = Join-Path $cropRoot 'dist\CIPA-Crop-Coord.exe'
    if (-not (Test-Path -LiteralPath $output)) {
        throw "No integrated EXE at $output"
    }
    Write-Host ''
    Write-Host "Verified Windows integrated executable: $output"
    Get-FileHash -Algorithm SHA256 -LiteralPath $output | Format-List
} finally {
    Pop-Location
}
