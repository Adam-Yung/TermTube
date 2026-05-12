@echo off
setlocal
set "SCRIPT_DIR=%LOCALAPPDATA%\TermTube"
set "PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if "%~1"=="--uninstall" (
    if exist "%SCRIPT_DIR%\uninstall.ps1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\uninstall.ps1"
        exit /b %ERRORLEVEL%
    )
    echo Uninstaller not found at %SCRIPT_DIR%\uninstall.ps1
    exit /b 1
)

if not exist "%PYTHON%" (
    echo TermTube is not set up. Run setup.ps1 first.
    exit /b 1
)
"%PYTHON%" "%SCRIPT_DIR%\src\main.py" %*
