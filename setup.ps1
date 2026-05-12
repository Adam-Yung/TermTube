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

# Ensure the console can render Unicode box-drawing characters
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

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

function Test-Tool {
    param([string]$Name)
    if (Test-Command $Name) { return $true }
    switch ($Name) {
        "mpv" {
            return Test-Path (Join-Path $env:LOCALAPPDATA "Programs\mpv.net\mpvnet.exe")
        }
        "python" {
            return $null -ne (Find-Python)
        }
    }
    return $false
}

# ── Dependency Installation ───────────────────────────────────────────────────
$WinGetPackages = @{
    "yt-dlp"  = "yt-dlp.yt-dlp"
    "deno"    = "DenoLand.Deno"
    "mpv"     = "mpv.net"
    "ffmpeg"  = "Gyan.FFmpeg"
    "chafa"   = "hpjansson.Chafa"
    "python"  = "Python.Python.3.13"
}

function Install-YtDlpGitHub {
    <#
    .SYNOPSIS
        Download the latest yt-dlp nightly .exe from GitHub nightly-builds as a
        fallback when winget is unavailable or fails.
    #>
    $destDir = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"
    $dest    = Join-Path $destDir "yt-dlp.exe"
    $url     = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe"
    Write-Step "Downloading yt-dlp nightly from GitHub nightly-builds..."
    try {
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -TimeoutSec 60
        Write-Success "yt-dlp (nightly) installed to $dest"
        return $true
    } catch {
        Write-Err "Failed to download yt-dlp from GitHub: $_"
        return $false
    }
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
        winget install --id $pkg --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -eq 0) {
            Write-Success "$Tool installed."
            # mpv.net does not add itself to PATH; probe its known install location
            if ($Tool -eq "mpv") {
                $mpvDir = Join-Path $env:LOCALAPPDATA "Programs\mpv.net"
                if (Test-Path (Join-Path $mpvDir "mpvnet.exe")) {
                    $env:PATH = "$env:PATH;$mpvDir"
                    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
                    if ($userPath -notlike "*$mpvDir*") {
                        [System.Environment]::SetEnvironmentVariable("PATH", "$userPath;$mpvDir", "User")
                    }
                }
            }
            # Refresh PATH after Python install so Find-Python can locate it immediately
            if ($Tool -eq "python") {
                $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                            [System.Environment]::GetEnvironmentVariable("PATH", "User")
            }
            return $true
        }
    } catch {}
    # Fallback: download yt-dlp directly from GitHub if winget failed
    if ($Tool -eq "yt-dlp") {
        return Install-YtDlpGitHub
    }
    Write-Err "Failed to install $Tool."
    return $false
}

function Test-Dependencies {
    $required = @("yt-dlp", "deno", "mpv", "python")
    $optional = @("ffmpeg", "chafa")
    $missingRequired = @()
    $missingOptional = @()
    $foundRequired   = @()
    $foundOptional   = @()

    foreach ($tool in $required) {
        if (Test-Tool $tool) {
            $foundRequired += $tool
        } else {
            $missingRequired += $tool
        }
    }
    foreach ($tool in $optional) {
        if (Test-Tool $tool) {
            $foundOptional += $tool
        } else {
            $missingOptional += $tool
        }
    }

    if ($missingRequired.Count -eq 0 -and $missingOptional.Count -eq 0) {
        Write-Header "Installed Dependencies"
        foreach ($tool in $foundRequired)  { Write-Success "$tool (required)" }
        foreach ($tool in $foundOptional)  { Write-Success "$tool (optional)" }
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

    $stillMissing = @()

    if ($shouldInstall) {
        foreach ($tool in ($missingRequired + $missingOptional)) {
            Install-Dependency $tool | Out-Null
        }
        # Re-check after install
        foreach ($tool in $missingRequired) {
            $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("PATH", "User")
            if (Test-Tool $tool) {
                $foundRequired += $tool
            } else {
                $stillMissing += $tool
                Write-Err "$tool still not found after install. May need a terminal restart."
            }
        }
        foreach ($tool in $missingOptional) {
            $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("PATH", "User")
            if (Test-Tool $tool) {
                $foundOptional += $tool
            } else {
                $stillMissing += $tool
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
        $stillMissing = $missingRequired + $missingOptional
    }

    # ── Dependency Summary ────────────────────────────────────────────────────
    Write-Header "Installed Dependencies"
    foreach ($tool in $foundRequired) {
        Write-Success "$tool (required)"
    }
    foreach ($tool in $foundOptional) {
        Write-Success "$tool (optional)"
    }
    foreach ($tool in $stillMissing) {
        $label = if ($required -contains $tool) { "required" } else { "optional" }
        Write-Err "$tool missing ($label)"
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
        Write-Host "  Or: winget install Python.Python.3.13"
        return $false
    }

    $pyArgs = $py -split ' '
    if ($pyArgs.Count -gt 1) {
        $version = & $pyArgs[0] $pyArgs[1..($pyArgs.Count - 1)] --version 2>&1
    } else {
        $version = & $py --version 2>&1
    }
    Write-Info "Using $version"

    $pipExe = Join-Path $VenvDir "Scripts\pip.exe"
    $pythonExe = Join-Path $VenvDir "Scripts\python.exe"

    if (Test-Path $pythonExe) {
        Write-Info "Virtual environment exists - upgrading..."
    } else {
        Write-Step "Creating virtual environment..."
        if ($pyArgs.Count -gt 1) {
            & $pyArgs[0] $pyArgs[1..($pyArgs.Count - 1)] -m venv $VenvDir
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

        $filesToCopy = @("requirements.txt", "termtube", "termtube.cmd", "setup.sh", "setup.ps1", "uninstall.sh", "uninstall.ps1")
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
    $origDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.ScriptName }
    $srcCmd  = Join-Path $origDir "termtube.cmd"

    if (-not (Test-Path $srcCmd)) {
        Write-Err "termtube.cmd not found in source directory ($origDir)."
        Write-Err "Ensure termtube.cmd exists in the repo root before running setup."
        return
    }

    if (-not $NoPrompt) {
        $reply = Read-Host "  Add 'termtube' command to PATH? [Y/n]"
        if ($reply -match '^[Nn]') {
            Write-Info "Skipped PATH installation."
            return
        }
    }

    if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir -Force | Out-Null }
    $batPath = Join-Path $BinDir "termtube.cmd"
    Copy-Item $srcCmd -Destination $batPath -Force

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
    $title    = "TermTube Installer"
    $subtitle = "Windows v$Version"
    $width    = 37
    $inner    = $width - 2

    function _Center {
        param([string]$Text, [int]$W)
        $len   = $Text.Length
        $pad   = [Math]::Floor(($W - $len) / 2)
        $right = $W - $len - $pad
        return (' ' * $pad) + $Text + (' ' * $right)
    }

    $line = [string][char]0x2500  # ─
    $bar  = $line * $inner
    Write-Host ("  " + [char]0x250C + $bar + [char]0x2510) -ForegroundColor White
    Write-Host ("  " + [char]0x2502 + (_Center $title    $inner) + [char]0x2502) -ForegroundColor White
    Write-Host ("  " + [char]0x2502 + (_Center $subtitle $inner) + [char]0x2502) -ForegroundColor White
    Write-Host ("  " + [char]0x2514 + $bar + [char]0x2518) -ForegroundColor White
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
