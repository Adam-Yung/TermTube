#Requires -Version 5.1
<#
.SYNOPSIS
    TermTube installer for Windows.

.DESCRIPTION
    Installs TermTube, sets up a Python virtual environment, and optionally
    installs system dependencies via winget.

.PARAMETER Sync
    Developer mode: symlinks install directory to the source.

.PARAMETER Deps
    Auto-install system dependencies via winget.

.PARAMETER NoDeps
    Skip all dependency checks.

.PARAMETER NoPrompt
    Non-interactive mode (accept all defaults).

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -Sync
    .\setup.ps1 -Deps -NoPrompt
#>

[CmdletBinding()]
param(
    [switch]$Sync,
    [switch]$Deps,
    [switch]$NoDeps,
    [switch]$NoPrompt,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Constants ─────────────────────────────────────────────────────────────────
$Version = "0.2.0"
$AppName = "TermTube"
$AppDir = Join-Path $env:LOCALAPPDATA $AppName
$BinDir = Join-Path $env:LOCALAPPDATA "Programs\TermTube"
$ConfigDir = Join-Path $env:APPDATA "TermTube"
$PythonMin = "3.11"

# ── Output Helpers ────────────────────────────────────────────────────────────
function Write-Info    { param($Msg) Write-Host "  > " -NoNewline -ForegroundColor Cyan; Write-Host $Msg }
function Write-Success { param($Msg) Write-Host "  + " -NoNewline -ForegroundColor Green; Write-Host $Msg }
function Write-Warn    { param($Msg) Write-Host "  ! " -NoNewline -ForegroundColor Yellow; Write-Host $Msg }
function Write-Err     { param($Msg) Write-Host "  x " -NoNewline -ForegroundColor Red; Write-Host $Msg }
function Write-Step    { param($Msg) Write-Host "  → " -NoNewline -ForegroundColor Blue; Write-Host $Msg }
function Write-Header  { param($Msg) Write-Host ""; Write-Host "  $Msg" -ForegroundColor White }

# ── Help ──────────────────────────────────────────────────────────────────────
if ($Help) {
    Write-Host @"

  TermTube Setup Script (Windows)
  ================================

  Usage: .\setup.ps1 [OPTIONS]

  Install Modes:
    (default)     Copy project to %LOCALAPPDATA%\TermTube.
    -Sync         Symlink (junction) to current directory for development.

  Options:
    -Deps         Auto-install dependencies via winget.
    -NoDeps       Skip dependency checks.
    -NoPrompt     Non-interactive mode.
    -Help         Show this message.

  Paths:
    Install dir:  %LOCALAPPDATA%\TermTube
    Config:       %APPDATA%\TermTube\config.yaml
    Cookies:      %APPDATA%\TermTube\cookies.txt

"@
    exit 0
}

# ── Utilities ─────────────────────────────────────────────────────────────────
function Test-Command {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-WinGet {
    Test-Command "winget"
}

# ── Dependency Installation ───────────────────────────────────────────────────
$WinGetPackages = @{
    "yt-dlp"  = "yt-dlp.yt-dlp"
    "mpv"     = "mpv.net"
    "ffmpeg"  = "Gyan.FFmpeg"
    "chafa"   = "hpjansson.Chafa"
}

function Install-Dependency {
    param([string]$Tool)
    $pkg = $WinGetPackages[$Tool]
    if (-not $pkg) {
        Write-Warn "$Tool is not available via winget. Install manually."
        return $false
    }
    Write-Step "Installing $Tool via winget ($pkg)..."
    try {
        winget install --id $pkg --accept-source-agreements --accept-package-agreements --silent
        if ($LASTEXITCODE -eq 0) {
            Write-Success "$Tool installed."
            return $true
        }
    } catch {}
    Write-Err "Failed to install $Tool."
    return $false
}

function Test-Dependencies {
    $required = @("yt-dlp", "mpv")
    $optional = @("ffmpeg", "chafa")
    $missingRequired = @()
    $missingOptional = @()

    foreach ($tool in $required) {
        if (Test-Command $tool) {
            Write-Success "$tool found"
        } else {
            $missingRequired += $tool
        }
    }
    foreach ($tool in $optional) {
        if (Test-Command $tool) {
            Write-Success "$tool found"
        } else {
            $missingOptional += $tool
        }
    }

    if ($missingRequired.Count -eq 0 -and $missingOptional.Count -eq 0) {
        Write-Success "All dependencies satisfied."
        return $true
    }

    if ($missingRequired.Count -gt 0) {
        Write-Warn "Missing required: $($missingRequired -join ', ')"
    }
    if ($missingOptional.Count -gt 0) {
        Write-Info "Missing optional: $($missingOptional -join ', ')"
    }

    if (-not (Test-WinGet)) {
        Write-Err "winget not found. Install dependencies manually."
        if ($missingRequired.Count -gt 0) { return $false }
        return $true
    }

    $shouldInstall = $false
    if ($Deps) {
        $shouldInstall = $true
    } elseif (-not $NoPrompt) {
        Write-Host ""
        $reply = Read-Host "  Install missing dependencies via winget? [Y/n]"
        if ($reply -notmatch '^[Nn]') { $shouldInstall = $true }
    }

    if ($shouldInstall) {
        foreach ($tool in ($missingRequired + $missingOptional)) {
            Install-Dependency $tool | Out-Null
        }
        # Re-check required
        foreach ($tool in $missingRequired) {
            # Refresh PATH
            $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("PATH", "User")
            if (-not (Test-Command $tool)) {
                Write-Err "$tool still not found after install. May need a terminal restart."
            }
        }
    } else {
        if ($missingRequired.Count -gt 0) {
            Write-Warn "Required tools missing. Install them to use TermTube:"
            foreach ($tool in $missingRequired) {
                $pkg = $WinGetPackages[$tool]
                if ($pkg) { Write-Host "    winget install $pkg" }
            }
        }
    }
    return $true
}

# ── Python Detection ──────────────────────────────────────────────────────────
function Find-Python {
    $candidates = @("python3", "python", "py")
    foreach ($c in $candidates) {
        if (Test-Command $c) {
            try {
                $ver = & $c -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                $parts = $ver.Split('.')
                if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) {
                    return $c
                }
            } catch {}
        }
    }
    # Try py launcher with version
    if (Test-Command "py") {
        try {
            $ver = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            $parts = $ver.Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) {
                return "py -3"
            }
        } catch {}
    }
    return $null
}

# ── Venv Setup ────────────────────────────────────────────────────────────────
function Setup-Venv {
    param(
        [string]$VenvDir,
        [string]$Requirements
    )

    $py = Find-Python
    if (-not $py) {
        Write-Err "Python >= $PythonMin not found."
        Write-Host "  Install from: https://python.org/downloads/"
        Write-Host "  Or: winget install Python.Python.3.12"
        return $false
    }

    $version = & $py.Split(' ')[0] $py.Split(' ')[1..99] --version 2>&1
    Write-Info "Using $version"

    $pipExe = Join-Path $VenvDir "Scripts\pip.exe"
    $pythonExe = Join-Path $VenvDir "Scripts\python.exe"

    if (Test-Path $pythonExe) {
        Write-Info "Virtual environment exists - upgrading..."
    } else {
        Write-Step "Creating virtual environment..."
        $pyArgs = $py.Split(' ')
        if ($pyArgs.Count -gt 1) {
            & $pyArgs[0] $pyArgs[1..99] -m venv $VenvDir
        } else {
            & $py -m venv $VenvDir
        }
    }

    Write-Step "Installing Python packages..."
    & $pipExe install --quiet --upgrade pip 2>$null
    & $pipExe install --quiet -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Err "pip install failed."
        return $false
    }
    Write-Success "Python environment ready."
    return $true
}

# ── Sync Mode Prompt ──────────────────────────────────────────────────────────
function Prompt-SyncMode {
    if ($NoPrompt -or $Sync) { return $Sync }

    Write-Host ""
    Write-Host "  Choose installation mode:" -ForegroundColor White
    Write-Host ""
    Write-Host "    1) Standard (recommended)" -ForegroundColor Green
    Write-Host "       Copies files to $AppDir"
    Write-Host ""
    Write-Host "    2) Developer sync" -ForegroundColor Green
    Write-Host "       Junctions to current directory"
    Write-Host ""
    $choice = Read-Host "  Select [1/2]"
    return ($choice -eq "2")
}

# ── File Installation ─────────────────────────────────────────────────────────
function Install-Files {
    param([bool]$SyncMode)

    $origDir = Split-Path -Parent $MyInvocation.ScriptName
    if (-not $origDir) { $origDir = $PSScriptRoot }

    if ($origDir -eq $AppDir) {
        Write-Info "Already running from install directory."
        return
    }

    if ($SyncMode) {
        Write-Header "Developer Sync Mode"
        if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
        New-Item -ItemType Junction -Path $AppDir -Target $origDir | Out-Null
        Write-Success "Junction: $AppDir -> $origDir"
    } else {
        Write-Header "Standard Installation"
        if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
        New-Item -ItemType Directory -Path $AppDir -Force | Out-Null

        $filesToCopy = @("requirements.txt", "termtube", "setup.sh", "setup.ps1", "uninstall.sh", "uninstall.ps1")
        $srcDir = Join-Path $origDir "src"
        if (Test-Path $srcDir) {
            Copy-Item $srcDir -Destination $AppDir -Recurse -Force
        }
        foreach ($f in $filesToCopy) {
            $src = Join-Path $origDir $f
            if (Test-Path $src) {
                Copy-Item $src -Destination $AppDir -Force
            }
        }
        Write-Success "Installed to $AppDir"
    }
}

# ── Create Launcher Batch File ────────────────────────────────────────────────
function Install-Launcher {
    $batContent = @"
@echo off
setlocal
set "SCRIPT_DIR=%LOCALAPPDATA%\TermTube"
set "PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo TermTube is not set up. Run setup.ps1 first.
    exit /b 1
)
"%PYTHON%" "%SCRIPT_DIR%\src\main.py" %*
"@

    if (-not $NoPrompt) {
        $reply = Read-Host "  Add 'termtube' command to PATH? [Y/n]"
        if ($reply -match '^[Nn]') {
            Write-Info "Skipped PATH installation."
            return
        }
    }

    if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir -Force | Out-Null }
    $batPath = Join-Path $BinDir "termtube.cmd"
    Set-Content -Path $batPath -Value $batContent -Encoding ASCII

    # Add to user PATH if not present
    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -notlike "*$BinDir*") {
        [System.Environment]::SetEnvironmentVariable("PATH", "$userPath;$BinDir", "User")
        $env:PATH = "$env:PATH;$BinDir"
        Write-Success "Added $BinDir to user PATH."
        Write-Warn "Restart your terminal for PATH changes to take effect."
    } else {
        Write-Success "termtube.cmd installed to $BinDir"
    }
}

# ── Main ──────────────────────────────────────────────────────────────────────
function Main {
    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────┐" -ForegroundColor White
    Write-Host "  │         TermTube Installer           │" -ForegroundColor White
    Write-Host "  │         Windows v$Version             │" -ForegroundColor White
    Write-Host "  └─────────────────────────────────────┘" -ForegroundColor White
    Write-Host ""

    Write-Info "Platform: Windows / $(if (Test-WinGet) {'winget available'} else {'winget not found'})"

    $syncMode = Prompt-SyncMode

    if (-not $NoDeps) {
        Write-Header "System Dependencies"
        Test-Dependencies | Out-Null
    }

    Install-Files -SyncMode $syncMode

    Write-Header "Python Environment"
    $venvDir = Join-Path $AppDir ".venv"
    $requirements = Join-Path $AppDir "requirements.txt"
    $result = Setup-Venv -VenvDir $venvDir -Requirements $requirements
    if (-not $result) { exit 1 }

    if (-not (Test-Path $ConfigDir)) {
        New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
        Write-Info "Created config directory: $ConfigDir"
    }

    Write-Header "Finishing Up"
    Install-Launcher

    Write-Host ""
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor White
    Write-Host "  Setup complete!" -ForegroundColor Green
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor White
    Write-Host ""
    Write-Host "  Run:     termtube" -ForegroundColor Green
    Write-Host "  Config:  $ConfigDir\config.yaml"
    Write-Host "  Cookies: $ConfigDir\cookies.txt"
    Write-Host ""
}

Main
