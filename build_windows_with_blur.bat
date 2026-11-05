@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem The original FindsBlur EXE is NOT included. This uses the reconstructed
rem computation modules from a separate local CIPA-Calc checkout only.
if not defined CIPA_CALC_ROOT (
    if exist "%~dp0..\CIPA-Calc\standalone_gui\core.py" (
        set "CIPA_CALC_ROOT=%~dp0..\CIPA-Calc"
    )
)
if not defined CIPA_CALC_ROOT (
    echo [ERROR] Set CIPA_CALC_ROOT to your local CIPA-Calc repository.
    goto :error
)
if not exist "%CIPA_CALC_ROOT%\standalone_gui\core.py" (
    echo [ERROR] Missing private calculation source at %CIPA_CALC_ROOT%.
    goto :error
)
if not defined FINDSBLUR_IJG8C_EXE (
    set "FINDSBLUR_IJG8C_EXE=%CIPA_CALC_ROOT%\_work\IJG8c\bin\ijg8c_rgb_probe.exe"
)
if not exist "%FINDSBLUR_IJG8C_EXE%" (
    echo [ERROR] IJG8c decoder missing: %FINDSBLUR_IJG8C_EXE%
    goto :error
)

rem FindsBlur v1.3.1 upstream Windows CI uses Python 3.12.
rem Accept 3.11 when 3.12 is not installed.
py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_LAUNCH=py -3.12"
) else (
    py -3.11 --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python 3.12 or 3.11 x64 is required.
        goto :error
    )
    set "PY_LAUNCH=py -3.11"
)
%PY_LAUNCH% -m venv .venv-blur-build
if errorlevel 1 goto :error
call .venv-blur-build\Scripts\activate.bat
if errorlevel 1 goto :error

rem Verify new v1.3.1 API, CalcDebug, and hidden IJG windows BEFORE packaging.
python scripts\check_calc_source_v131.py
if errorlevel 1 goto :error

python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements-dev.txt -r requirements-blur.txt
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM=offscreen"
python -m pytest
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="
python -m PyInstaller --noconfirm --clean CIPA-Crop-Coord.spec
if errorlevel 1 goto :error
python scripts\verify_integrated_bundle.py dist\CIPA-Crop-Coord.exe
if errorlevel 1 goto :error
echo.
echo Verified local integrated EXE: dist\CIPA-Crop-Coord.exe
echo Validate it on Windows with official FindsBlur input/output samples.
exit /b 0

:error
echo.
echo Integrated build failed. No standalone CIPA-Calc source was modified.
exit /b 1
