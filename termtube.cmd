@echo off
setlocal
rem Self-locate via %~dp0 so the launcher works regardless of install path
rem (Programs\TermTube\, a sync-mode junction, or the source repo directly).
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if "%~1"=="--uninstall" (
    if exist "%SCRIPT_DIR%\uninstall.ps1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\uninstall.ps1"
        exit /b %ERRORLEVEL%
    )
    if exist "%LOCALAPPDATA%\Programs\TermTube\uninstall.ps1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\Programs\TermTube\uninstall.ps1"
        exit /b %ERRORLEVEL%
    )
    echo Uninstaller not found.
    echo   Checked: %SCRIPT_DIR%\uninstall.ps1
    echo   Checked: %LOCALAPPDATA%\Programs\TermTube\uninstall.ps1
    exit /b 1
)

if not exist "%PYTHON%" goto :try_install_dir
goto :run

:try_install_dir
set "PYTHON=%LOCALAPPDATA%\Programs\TermTube\.venv\Scripts\python.exe"
set "SCRIPT_DIR=%LOCALAPPDATA%\Programs\TermTube"
if not exist "%PYTHON%" (
    echo TermTube is not set up. Run setup.ps1 first.
    echo   Looked for venv at: %~dp0.venv\Scripts\python.exe
    echo   Also tried:         %LOCALAPPDATA%\Programs\TermTube\.venv\Scripts\python.exe
    exit /b 1
)

:run
"%PYTHON%" "%SCRIPT_DIR%\src\main.py" %*
