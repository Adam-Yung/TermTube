@echo off
setlocal
rem TermTube launcher — finds the Python venv and launches the app.
rem On first run from a cloned repo, automatically runs setup.
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "REPO_DIR=%SCRIPT_DIR%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem ── Handle Uninstall ──────────────────────────────────────────────────────
if "%~1"=="--uninstall" (
    if exist "%SCRIPT_DIR%\scripts\uninstall.ps1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\scripts\uninstall.ps1"
        exit /b %ERRORLEVEL%
    )
    if exist "%LOCALAPPDATA%\Programs\TermTube\scripts\uninstall.ps1" (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\Programs\TermTube\scripts\uninstall.ps1"
        exit /b %ERRORLEVEL%
    )
    echo Uninstaller not found.
    exit /b 1
)

rem ── 1. Venv next to this script ───────────────────────────────────────────
set "PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe"
if exist "%PYTHON%" goto :run

rem ── 2. Fallback to standard install location ──────────────────────────────
:try_install_dir
set "PYTHON=%LOCALAPPDATA%\Programs\TermTube\.venv\Scripts\python.exe"
set "SCRIPT_DIR=%LOCALAPPDATA%\Programs\TermTube"
if exist "%PYTHON%" goto :run

rem ── 3. Auto-install if still no venv ─────────────────────────────────────
:auto_install
set "SETUP=%REPO_DIR%\scripts\setup.ps1"
if not exist "%SETUP%" set "SETUP=%LOCALAPPDATA%\Programs\TermTube\scripts\setup.ps1"
if not exist "%SETUP%" goto :no_setup
echo.
echo   TermTube is not set up. Running setup...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SETUP%" -NoPrompt
set "PYTHON=%LOCALAPPDATA%\Programs\TermTube\.venv\Scripts\python.exe"
set "SCRIPT_DIR=%LOCALAPPDATA%\Programs\TermTube"
if exist "%PYTHON%" goto :run

rem ── 4. No setup script found ──────────────────────────────────────────────
:no_setup
echo TermTube is not set up and no setup script was found.
echo   Clone the repo and run: .\scripts\setup.ps1
exit /b 1

:run
"%PYTHON%" "%SCRIPT_DIR%\src\main.py" %*
