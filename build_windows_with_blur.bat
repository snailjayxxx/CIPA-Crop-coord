@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem No private repository clone and no source ZIP merge.
rem All calculation source is in vendor/findsblur_v131.
set "CIPA_BUILD_INTEGRATED=1"
set "CIPA_CALC_ROOT=%~dp0vendor\findsblur_v131"
if not exist "%CIPA_CALC_ROOT%\standalone_gui\core.py" (
  echo [ERROR] Missing repository-local FindsBlur calculation source.
  goto :error
)
if not defined FINDSBLUR_IJG8C_EXE (
  set "FINDSBLUR_IJG8C_EXE=%CIPA_CALC_ROOT%\_work\IJG8c\bin\ijg8c_rgb_probe.exe"
)
if not exist "%FINDSBLUR_IJG8C_EXE%" (
  echo [ERROR] IJG8c decoder not built: %FINDSBLUR_IJG8C_EXE%
  echo [INFO] GitHub Actions in CIPA-Crop-coord automatically builds it.
  echo [INFO] For local build, compile vendor\findsblur_v131\tools\ijg8c_rgb_probe.c against IJG 8c.
  goto :error
)
py -3.12 --version >nul 2>&1
if not errorlevel 1 (
  set "PY_LAUNCH=py -3.12"
) else (
  set "PY_LAUNCH=py -3.11"
)
%PY_LAUNCH% -m venv .venv-blur-build
if errorlevel 1 goto :error
call .venv-blur-build\Scripts\activate.bat
if errorlevel 1 goto :error
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements-dev.txt -r requirements-blur.txt
if errorlevel 1 goto :error
python scripts\check_calc_source_v131.py
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM=offscreen"
python -m pytest
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="
python -m PyInstaller --noconfirm --clean CIPA-Crop-Coord.spec
if errorlevel 1 goto :error
python scripts\verify_integrated_bundle.py dist\CIPA-Crop-Coord.exe
if errorlevel 1 goto :error
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath (Resolve-Path 'dist\CIPA-Crop-Coord.exe') -ArgumentList '--self-test-integrated' -PassThru -Wait; if ($p.ExitCode -ne 0) { Write-Error ('Integrated EXE self-test failed: ' + $p.ExitCode); exit 1 }"
if errorlevel 1 goto :error
echo Complete integrated EXE: dist\CIPA-Crop-Coord.exe
exit /b 0
:error
echo Integrated build FAILED. A crop-only EXE must not be named integrated.
exit /b 1
