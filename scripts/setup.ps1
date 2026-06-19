#Requires -Version 5.1
<#
.SYNOPSIS
    TermTube installer for Windows.

.DESCRIPTION
    Installs TermTube, sets up a Python virtual environment, and bootstraps
    binary dependencies (yt-dlp, deno, ffmpeg, mpv) from GitHub releases.

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
    [switch]$NoDeps,
    [switch]$NoPrompt,
    [switch]$Help
)

Set-StrictMode -Version Latest
$script:DeferBootstrap = $false
$ErrorActionPreference = "Stop"

# Ensure the console can render Unicode box-drawing characters
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

# ── Constants ─────────────────────────────────────────────────────────────────
$Version = "0.2.0"
$AppName = "TermTube"
$AppDir = Join-Path $env:LOCALAPPDATA "Programs\TermTube"
$DataDir = Join-Path $env:LOCALAPPDATA $AppName
$ConfigDir = Join-Path $env:APPDATA "TermTube"
$PythonMin = "3.11"

# Legacy path: pre-architecture-fix installs put code at %LOCALAPPDATA%\TermTube.
# Used by migration code in Install-Files to clean up old layouts.
$LegacyAppDir = Join-Path $env:LOCALAPPDATA "TermTube"

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

  Usage: .\scripts\setup.ps1 [OPTIONS]

  Options:
    -NoDeps       Skip dependency checks.
    -NoPrompt     Non-interactive mode.
    -Help         Show this message.

  Paths:
    Install dir:  %LOCALAPPDATA%\Programs\TermTube   (code, .venv, launcher)
    Data dir:     %LOCALAPPDATA%\TermTube            (mpv binary, cache)
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

function Test-IsReparsePoint {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue)) { return $false }
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        return (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
    } catch { return $false }
}

function Remove-PathSafe {
    <#
    .SYNOPSIS
        Delete a file or directory; for junctions / symlinks, delete only the
        link itself (do NOT recurse into the target).
    .DESCRIPTION
        `Remove-Item -Recurse -Force` on a Windows junction follows the link
        and deletes the TARGET's contents. That would wipe the user's source
        repo when a sync-mode install is replaced. This helper detects
        reparse points and uses the .NET API to remove only the link.
    #>
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue)) { return $true }
    try {
        if (Test-IsReparsePoint $Path) {
            # Delete only the junction/symlink, never its target
            [System.IO.Directory]::Delete($Path, $false)
        } else {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        }
        return $true
    } catch {
        Write-Err "Failed to remove ${Path}: $($_.Exception.Message)"
        return $false
    }
}

# ── Python Detection ──────────────────────────────────────────────────────────
function Test-PythonVersion {
    param([string]$Version)
    if (-not $Version) { return $false }
    $parts = $Version.Trim().Split('.')
    if ($parts.Count -lt 2) { return $false }
    try {
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
    } catch { return $false }
    # >= 3.11 (accepts 3.11+, 4.x, etc.)
    return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 11)
}

function Find-Python {
    foreach ($c in @("python3", "python", "py")) {
        if (Test-Command $c) {
            try {
                $ver = & $c -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                if (Test-PythonVersion $ver) { return $c }
            } catch {}
        }
    }
    # Try py launcher with explicit -3
    if (Test-Command "py") {
        try {
            $ver = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if (Test-PythonVersion $ver) { return "py -3" }
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

    $pipExe    = Join-Path $VenvDir "Scripts\pip.exe"
    $pythonExe = Join-Path $VenvDir "Scripts\python.exe"
    $hashFile  = Join-Path $VenvDir ".requirements.sha256"

    $venvExists = Test-Path $pythonExe
    if ($venvExists) {
        # Detect stale venv (interpreter moved/uninstalled)
        $venvOk = $false
        try {
            & $pythonExe --version *>$null
            $venvOk = ($LASTEXITCODE -eq 0)
        } catch { $venvOk = $false }
        if (-not $venvOk) {
            Write-Warn "Existing venv is stale (interpreter changed). Recreating..."
            Remove-PathSafe $VenvDir | Out-Null
            $venvExists = $false
        } else {
            Write-Info "Virtual environment exists."
        }
    }

    if (-not $venvExists) {
        Write-Step "Creating virtual environment..."
        if ($pyArgs.Count -gt 1) {
            & $pyArgs[0] $pyArgs[1..($pyArgs.Count - 1)] -m venv $VenvDir
        } else {
            & $py -m venv $VenvDir
        }
        if (-not (Test-Path $pythonExe)) {
            Write-Err "Failed to create virtual environment."
            return $false
        }
    }

    # Hash-based cache: skip pip install when requirements.txt unchanged
    $currentHash = $null
    if (Test-Path $Requirements) {
        $sha256       = [System.Security.Cryptography.SHA256]::Create()
        $currentHash  = [BitConverter]::ToString(
            $sha256.ComputeHash([System.IO.File]::ReadAllBytes($Requirements))
        ).Replace("-", "")
    }
    $cachedHash = $null
    if (Test-Path $hashFile) {
        try { $cachedHash = (Get-Content -LiteralPath $hashFile -Raw).Trim() } catch {}
    }

    if ($currentHash -and $cachedHash -eq $currentHash) {
        Write-Info "Requirements unchanged — skipping pip install."
        Write-Success "Python environment ready."
        return $true
    }

    Write-Step "Installing Python packages..."
    & $pythonExe -m pip install --quiet --upgrade pip 2>$null
    & $pythonExe -m pip install --quiet -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        Write-Err "pip install failed."
        return $false
    }
    if ($currentHash) {
        try { Set-Content -LiteralPath $hashFile -Value $currentHash -NoNewline } catch {}
    }
    Write-Success "Python environment ready."
    return $true
}

# ── File Installation ─────────────────────────────────────────────────────────
function Install-Files {
    $origDir = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.ScriptName) }
    if ($origDir -eq $AppDir) {
        Write-Info "Already running from install directory."
        return
    }

    # ── Migrate from legacy layout (pre-2026-05) ──────────────────────────
    # Old installs put code at %LOCALAPPDATA%\TermTube, conflicting with the
    # data dir. If we detect that old layout, salvage its .venv and clean it
    # up so the data dir (mpv binary, cache) is left intact at the same path.
    if (Test-Path $LegacyAppDir) {
        $legacyVenv    = Join-Path $LegacyAppDir ".venv"
        $legacyHasCode = (Test-Path (Join-Path $LegacyAppDir "src")) -or `
                         (Test-Path (Join-Path $LegacyAppDir "termtube.cmd"))
        if ($legacyHasCode) {
            Write-Info "Migrating from legacy layout at $LegacyAppDir."
            if (Test-Path $legacyVenv) {
                $migrateStash = Join-Path $env:LOCALAPPDATA "TermTube.venv.stash"
                if (Test-Path $migrateStash) { Remove-PathSafe $migrateStash | Out-Null }
                try {
                    Move-Item -LiteralPath $legacyVenv -Destination $migrateStash -Force -ErrorAction Stop
                } catch {
                    Write-Warn "Could not preserve legacy .venv: $($_.Exception.Message)"
                }
            }
            foreach ($name in @("src", "termtube", "termtube.cmd", "setup.sh", "setup.ps1",
                                "uninstall.sh", "uninstall.ps1", "scripts", "requirements.txt")) {
                $p = Join-Path $LegacyAppDir $name
                if (Test-Path $p) { Remove-PathSafe $p | Out-Null }
            }
            Write-Success "Legacy code dir cleaned; data preserved at $LegacyAppDir."
        }
    }

    # Preserve the previous install's .venv across reinstalls so users don't
    # pay a 30-60s pip cost every time.
    $stashedVenv = $null
    $appVenv     = Join-Path $AppDir ".venv"
    $migrateStash = Join-Path $env:LOCALAPPDATA "TermTube.venv.stash"
    if ((Test-Path $migrateStash) -and -not (Test-Path $appVenv)) {
        $stashedVenv = $migrateStash
    }

    $appParent = Split-Path -Parent $AppDir
    if ($appParent -and -not (Test-Path $appParent)) {
        New-Item -ItemType Directory -Path $appParent -Force | Out-Null
    }

    Write-Header "Standard Installation"

    # Stash .venv if it exists in the previous standard install
    if ((Test-Path $appVenv) -and -not (Test-IsReparsePoint $appVenv)) {
        $stashedVenv = Join-Path $env:LOCALAPPDATA "TermTube.venv.stash"
        if (Test-Path $stashedVenv) { Remove-PathSafe $stashedVenv | Out-Null }
        try {
            Move-Item -LiteralPath $appVenv -Destination $stashedVenv -Force -ErrorAction Stop
            Write-Info "Preserving existing virtual environment."
        } catch {
            Write-Warn "Could not stash existing .venv ($($_.Exception.Message)); it will be recreated."
            $stashedVenv = $null
        }
    }

    if (Test-Path $AppDir) {
        if (-not (Remove-PathSafe $AppDir)) { return }
    }
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null

    $filesToCopy = @(
        "requirements.txt", "termtube", "termtube.cmd"
    )
    $srcDir = Join-Path $origDir "src"
    if (Test-Path $srcDir) {
        Copy-Item $srcDir -Destination $AppDir -Recurse -Force
    }
    $scriptsDir = Join-Path $origDir "scripts"
    if (Test-Path $scriptsDir) {
        Copy-Item $scriptsDir -Destination $AppDir -Recurse -Force
    }
    $assetsDir = Join-Path $origDir "assets"
    if (Test-Path $assetsDir) {
        Copy-Item $assetsDir -Destination $AppDir -Recurse -Force
    }
    foreach ($f in $filesToCopy) {
        $src = Join-Path $origDir $f
        if (Test-Path $src) {
            Copy-Item $src -Destination $AppDir -Force
        }
    }

    # Restore the preserved .venv
    if ($stashedVenv -and (Test-Path $stashedVenv)) {
        try {
            Move-Item -LiteralPath $stashedVenv -Destination $appVenv -Force -ErrorAction Stop
            Write-Success "Restored existing virtual environment."
        } catch {
            Write-Warn "Failed to restore .venv: $($_.Exception.Message)"
        }
    }

    Write-Success "Installed to $AppDir"
}

# ── Create Launcher Batch File ────────────────────────────────────────────────
function Install-Launcher {
    $origDir = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { Split-Path -Parent (Split-Path -Parent $MyInvocation.ScriptName) }
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

    # termtube.cmd is already inside $AppDir (Install-Files copied it for
    # standard mode; in sync mode it's reachable via the junction). All we
    # have to do is put $AppDir on user PATH.
    $batPath = Join-Path $AppDir "termtube.cmd"
    if (-not (Test-Path $batPath)) {
        # Defensive: ensure the launcher exists. Useful if user ran with -NoDeps
        # and Install-Files didn't run, or if termtube.cmd was missing from source.
        Copy-Item $srcCmd -Destination $batPath -Force
    }

    # Add to user PATH if not present
    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -notlike "*$AppDir*") {
        [System.Environment]::SetEnvironmentVariable("PATH", "$userPath;$AppDir", "User")
        $env:PATH = "$env:PATH;$AppDir"
        Write-Success "Added $AppDir to user PATH."
        Write-Warn "Restart your terminal for PATH changes to take effect."
    } else {
        Write-Success "termtube launcher available at $batPath"
    }
}


# ── Bootstrap Dependencies (via Python) ──────────────────────────────────────
function Bootstrap-Dependencies {
    <#
    .SYNOPSIS
        Download all binary dependencies (yt-dlp, deno, ffmpeg, mpv) from GitHub
        releases using src/bootstrap.py. This replaces the old winget-based install.
    #>
    Write-Info "Downloading yt-dlp, deno, ffmpeg, mpv from GitHub releases..."
    Write-Info "Install path: $env:LOCALAPPDATA\termtube-deps\bin"
    Write-Host ""

    $venvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        # Venv not set up yet — will bootstrap after venv creation
        Write-Warn "Python venv not ready yet; dependencies will be installed after venv setup."
        $script:DeferBootstrap = $true
        return
    }

    try {
        & $venvPython -m src.bootstrap
        if ($LASTEXITCODE -eq 0) {
            Write-Success "All dependencies installed."
        } else {
            Write-Warn "Some dependencies failed. Run 'termtube --update' to retry."
        }
    } catch {
        Write-Err "Bootstrap failed: $($_.Exception.Message)"
        Write-Warn "Run 'termtube --update' to retry later."
    }
}

# ── Write VERSION ────────────────────────────────────────────────────────────
function Write-Version {
    $versionFile = Join-Path $AppDir "VERSION"
    $tag = "dev"
    try {
        $gitExe = Get-Command git -ErrorAction SilentlyContinue
        if ($gitExe) {
            $origDir = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { $AppDir }
            $tag = & git -C $origDir describe --tags --exact-match 2>$null
            if (-not $tag) { $tag = "dev" }
        }
    } catch {}
    try { Set-Content -LiteralPath $versionFile -Value $tag.Trim() -NoNewline } catch {}
    Write-Info "Version: $($tag.Trim())"
}

# ── Desktop Shortcut ─────────────────────────────────────────────────────────
function Install-Shortcut {
    if ($NoPrompt) { return }
    Write-Host ""
    $reply = Read-Host "  Install TermTube outside the terminal? (creates a Desktop shortcut) [Y/n]"
    if ($reply -match '^[Nn]') {
        Write-Info "Skipped desktop shortcut."
        return
    }
    $icoPath = Join-Path $AppDir "assets\termtube.ico"
    if (-not (Test-Path $icoPath)) {
        Write-Warn "Icon file not found at $icoPath — shortcut will use default icon."
        $icoPath = ""
    }
    $venvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
    try {
        $wsh = New-Object -ComObject WScript.Shell
        $sc  = $wsh.CreateShortcut("$HOME\Desktop\TermTube.lnk")
        $wt  = Get-Command wt.exe -ErrorAction SilentlyContinue
        $batPath = Join-Path $AppDir "termtube.cmd"
        if ($wt) {
            $sc.TargetPath = "wt.exe"
            $sc.Arguments  = "-- `"$batPath`""
        } else {
            $sc.TargetPath = "cmd.exe"
            $sc.Arguments  = "/k `"$batPath`""
        }
        if ($icoPath) { $sc.IconLocation = "$icoPath,0" }
        $sc.Save()
        Write-Success "Desktop shortcut created: $HOME\Desktop\TermTube.lnk"
    } catch {
        Write-Warn "Could not create desktop shortcut: $($_.Exception.Message)"
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

    if (-not $NoDeps) {
        Write-Header "Binary Dependencies"
        Bootstrap-Dependencies
    }

    Install-Files

    Write-Header "Python Environment"
    $venvDir      = Join-Path $AppDir ".venv"
    $requirements = Join-Path $AppDir "requirements.txt"
    $result = Setup-Venv -VenvDir $venvDir -Requirements $requirements
    if (-not $result) { exit 1 }

    # Run deferred bootstrap now that venv is ready
    if ($script:DeferBootstrap) {
        Write-Header "Binary Dependencies"
        Bootstrap-Dependencies
    }

    if (-not (Test-Path $ConfigDir)) {
        New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
        Write-Info "Created config directory: $ConfigDir"
    }

    Write-Header "Finishing Up"
    Install-Launcher

    Write-Version
    Install-Shortcut

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