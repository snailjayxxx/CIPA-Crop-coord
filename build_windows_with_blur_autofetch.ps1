# Kept for compatibility with earlier instructions.
# The calculation source is now checked into CIPA-Crop-coord/vendor/findsblur_v131.
# No GitHub login, external clone, or source ZIP merge is required.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
    & cmd.exe /d /c "build_windows_with_blur.bat"
    if ($LASTEXITCODE -ne 0) { throw "Integrated build failed: $LASTEXITCODE" }
} finally { Pop-Location }
