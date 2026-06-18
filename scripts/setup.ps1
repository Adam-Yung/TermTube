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
$script:DeferBootstrap = $false
$ErrorActionPreference = "Stop"

# Ensure the console can render Unicode box-drawing characters
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

# ── Constants ─────────────────────────────────────────────────────────────────
# Path conventions (matters! — getting this wrong causes the "mpv vanishes
# on reinstall" and "sync mode pollutes the source repo" bugs):
#
#   $AppDir   — code + .venv + launcher. May be a junction in sync mode.
#               Lives under \Programs\ so it is SEPARATE from $DataDir.
#   $DataDir  — bundled mpv binary + cache + history. Always a real dir.
#               Must NOT live inside $AppDir or sync-mode reinstalls will
#               wipe the bundled mpv and writes to cache will pollute the
#               user's source repo.
#   $ConfigDir — roaming config + cookies.
#
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

function Refresh-Path {
    <#
    .SYNOPSIS
        Merge Machine + User PATH into $env:PATH while preserving any entries
        added by the current process. Deduplicates while keeping first
        occurrence order so paths we added earlier (e.g. the standalone mpv
        dir) survive a refresh.
    #>
    $machine = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $combined = @($env:PATH, $machine, $user) -join ';'
    $seen = @{}
    $out  = New-Object System.Collections.Generic.List[string]
    foreach ($p in ($combined -split ';')) {
        if ($p -and -not $seen.ContainsKey($p)) {
            $seen[$p] = $true
            [void]$out.Add($p)
        }
    }
    $env:PATH = ($out -join ';')
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

function Test-MpvAvailable {
    <#
    .SYNOPSIS
        Return the path to a usable headless mpv.exe, or $null.
        Excludes mpv.net's mpvnet.exe — that build always pops a GUI window
        and is unsuitable for the audio worker.
    #>
    # Any mpv.exe on PATH (Get-Command resolves the exact exe name, so
    # mpvnet.exe will not match a "mpv.exe" lookup).
    $cmd = Get-Command "mpv.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # The standalone CLI build we install at Install-MpvCli's dest
    $local = Join-Path $env:LOCALAPPDATA "TermTube\mpv\mpv.exe"
    if (Test-Path -LiteralPath $local) { return $local }
    return $null
}

function Test-Tool {
    param([string]$Name)
    if ($Name -eq "mpv") {
        return $null -ne (Test-MpvAvailable)
    }
    if (Test-Command $Name) { return $true }
    switch ($Name) {
        "python" {
            return $null -ne (Find-Python)
        }
    }
    # Fallback: ask winget if the package is installed
    $pkg = $WinGetPackages[$Name]
    if ($pkg -and (Test-WinGet)) {
        $result = winget list --id $pkg --accept-source-agreements 2>$null
        if ($LASTEXITCODE -eq 0 -and $result -match [regex]::Escape($pkg)) {
            return $true
        }
    }
    return $false
}

# ── Dependency Installation ───────────────────────────────────────────────────
$WinGetPackages = @{
    "yt-dlp"  = "yt-dlp.yt-dlp"
    "deno"    = "DenoLand.Deno"
    # NOTE: mpv is intentionally NOT in this map. mpv.net opens a GUI window
    # even with --no-video / --force-window=no, which breaks the background
    # audio player. Install-MpvCli downloads the real upstream CLI build.
    "ffmpeg"  = "Gyan.FFmpeg"
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

function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Find-7Zip {
    foreach ($candidate in @("7z","7za","7zr")) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    foreach ($p in @(
        "C:\Program Files\7-Zip\7z.exe",
        "C:\Program Files (x86)\7-Zip\7z.exe"
    )) { if (Test-Path $p) { return $p } }
    $wingetPkgs = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetPkgs) {
        $hit = Get-ChildItem $wingetPkgs -Filter "7z.exe" -Recurse -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Ensure-7Zip {
    $found = Find-7Zip
    if ($found) { return $found }
    if (-not (Test-WinGet)) {
        Write-Warn "7-Zip not found and winget unavailable; cannot extract .7z archives."
        return $null
    }
    Write-Step "Installing 7-Zip (needed to extract mpv archive)..."
    winget install --id 7zip.7zip --accept-source-agreements --accept-package-agreements *>$null
    Refresh-Path
    return Find-7Zip
}

function Install-MpvCli {
    <#
    .SYNOPSIS
        Download a standalone mpv.exe for headless audio playback.
        mpv.net (winget) always opens a GUI window; this CLI build does not.
        Installs to %LOCALAPPDATA%\TermTube\mpv\mpv.exe and adds to user PATH.
    #>
    $destDir = Join-Path $DataDir "mpv"
    $dest    = Join-Path $destDir "mpv.exe"
    if (Test-Path $dest) {
        Write-Info "Standalone mpv.exe already present ($dest)."
        return $true
    }

    # Detect CPU architecture for the correct asset
    $arch = $env:PROCESSOR_ARCHITECTURE   # "AMD64", "x86", or "ARM64"; available on all Windows versions
    $assetPattern = if ($arch -eq "ARM64") { "^mpv-aarch64-\d" } else { "^mpv-x86_64-\d" }

    Write-Step "Downloading standalone mpv.exe for audio playback..."
    try {
        $release = Invoke-RestMethod `
            -Uri "https://api.github.com/repos/zhongfly/mpv-winbuild/releases/latest" `
            -UseBasicParsing -TimeoutSec 30
        $asset = $release.assets |
            Where-Object {
                $_.name -match $assetPattern -and
                $_.name -like "*.7z" -and
                $_.name -notlike "*debug*" -and
                $_.name -notlike "*dev*"
            } | Select-Object -First 1
        if (-not $asset) {
            Write-Err "Could not find a suitable mpv release asset (arch=$arch)."
            return $false
        }

        $sevenZip = Ensure-7Zip
        if (-not $sevenZip) {
            Write-Err "No .7z extractor available. Install manually: winget install 7zip.7zip"
            return $false
        }

        # Use an owned staging dir — never write into bare $env:TEMP.
        # System subdirs like WinSAT have restricted ACLs and will deny access.
        $tempDir     = Join-Path $DataDir "tmp"
        $tempArchive = Join-Path $tempDir "mpv-download.7z"
        $tempExtract = Join-Path $tempDir "mpv-extract"

        # Verify write access before starting the large download
        try {
            New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
            $probe = Join-Path $tempDir ".write-test"
            [System.IO.File]::WriteAllText($probe, "ok")
            Remove-Item $probe -Force
        } catch {
            Write-Err "Cannot write to staging directory ($tempDir): $_"
            if (-not (Test-IsAdmin)) {
                Write-Host ""
                Write-Warn "This looks like a permissions issue."
                Write-Host "  Re-run setup as Administrator:" -ForegroundColor Yellow
                Write-Host "    Start-Process powershell -Verb RunAs -ArgumentList '-File setup.ps1'" -ForegroundColor Cyan
                if (-not $NoPrompt) {
                    $reply = Read-Host "  Relaunch as Administrator now? [Y/n]"
                    if ($reply -notmatch '^[Nn]') {
                        Start-Process powershell -Verb RunAs `
                            -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Wait
                        exit 0
                    }
                }
            } else {
                Write-Warn "Already running as Administrator; path may be locked by another process."
            }
            return $false
        }

        $sizeMB = [math]::Round($asset.size / 1MB, 1)
        Write-Info "Downloading $($asset.name) (${sizeMB} MB)..."
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tempArchive `
            -UseBasicParsing -TimeoutSec 180

        if (Test-Path $tempExtract) { Remove-Item -Recurse -Force $tempExtract }
        New-Item -ItemType Directory -Path $tempExtract -Force | Out-Null

        Write-Info "Extracting with 7-Zip..."
        & $sevenZip x $tempArchive "-o$tempExtract" -y *>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Err "7-Zip extraction failed (exit $LASTEXITCODE)."
            return $false
        }

        $extracted = Get-ChildItem -Path $tempExtract -Filter "mpv.exe" -Recurse -File |
            Select-Object -First 1
        if (-not $extracted) {
            Write-Err "mpv.exe not found in extracted archive."
            return $false
        }

        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Copy-Item -Path $extracted.FullName -Destination $dest -Force
        Write-Success "Standalone mpv.exe installed to $dest"

        $userPath = [System.Environment]::GetEnvironmentVariable("PATH","User")
        if ($userPath -notlike "*$destDir*") {
            [System.Environment]::SetEnvironmentVariable("PATH","$userPath;$destDir","User")
            $env:PATH = "$env:PATH;$destDir"
            Write-Info "Added $destDir to user PATH."
        }
        return $true

    } catch {
        $errMsg = $_.Exception.Message
        Write-Err "Failed to install standalone mpv: $errMsg"
        if ($errMsg -like "*Access*denied*" -or $errMsg -like "*UnauthorizedAccess*") {
            Write-Host ""
            Write-Warn "Access was denied. This is a permissions issue."
            if (-not (Test-IsAdmin)) {
                Write-Host "  Re-run setup as Administrator:" -ForegroundColor Yellow
                Write-Host "    Start-Process powershell -Verb RunAs -ArgumentList '-File setup.ps1'" -ForegroundColor Cyan
                if (-not $NoPrompt) {
                    $reply = Read-Host "  Relaunch as Administrator now? [Y/n]"
                    if ($reply -notmatch '^[Nn]') {
                        Start-Process powershell -Verb RunAs `
                            -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Wait
                        exit 0
                    }
                }
            } else {
                Write-Warn "Already running as Administrator; path may be locked by another process."
            }
        }
        return $false
    } finally {
        Remove-Item -Path (Join-Path $DataDir "tmp") `
            -Recurse -Force -ErrorAction SilentlyContinue
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
            # Refresh PATH after Python install so Find-Python can locate it immediately
            if ($Tool -eq "python") { Refresh-Path }
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
    Refresh-Path
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
        Refresh-Path
        foreach ($tool in $missingRequired) {
            if (Test-Tool $tool) {
                $foundRequired += $tool
            } else {
                $stillMissing += $tool
                Write-Err "$tool still not found after install. May need a terminal restart."
            }
        }
        foreach ($tool in $missingOptional) {
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
        $currentHash = (Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash
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
        $legacyIsJunction = Test-IsReparsePoint $LegacyAppDir
        $legacyVenv       = Join-Path $LegacyAppDir ".venv"
        $legacyHasCode    = (Test-Path (Join-Path $LegacyAppDir "src")) -or `
                            (Test-Path (Join-Path $LegacyAppDir "termtube.cmd"))
        if ($legacyIsJunction) {
            Write-Warn "Removing legacy install junction at $LegacyAppDir."
            Remove-PathSafe $LegacyAppDir | Out-Null
        } elseif ($legacyHasCode) {
            Write-Info "Migrating from legacy layout at $LegacyAppDir."
            # Salvage .venv to the new $AppDir location below; then prune
            # the legacy code dir but PRESERVE mpv/, cache/, history.json, etc.
            if (Test-Path $legacyVenv) {
                $migrateStash = Join-Path $env:LOCALAPPDATA "TermTube.venv.stash"
                if (Test-Path $migrateStash) { Remove-PathSafe $migrateStash | Out-Null }
                try {
                    Move-Item -LiteralPath $legacyVenv -Destination $migrateStash -Force -ErrorAction Stop
                } catch {
                    Write-Warn "Could not preserve legacy .venv: $($_.Exception.Message)"
                }
            }
            # Remove only the code/launcher artifacts from the legacy dir
            foreach ($name in @("src", "termtube", "termtube.cmd", "setup.sh", "setup.ps1",
                                "uninstall.sh", "uninstall.ps1", "scripts", "requirements.txt")) {
                $p = Join-Path $LegacyAppDir $name
                if (Test-Path $p) { Remove-PathSafe $p | Out-Null }
            }
            Write-Success "Legacy code dir cleaned; data preserved at $LegacyAppDir."
        }
    }

    # Preserve the previous install's .venv across reinstalls so users don't
    # pay a 30-60s pip cost every time. Move it aside before tearing down the
    # install dir, then restore it after. Only valid in standard mode — in
    # sync mode the .venv lives inside the repo dir, not $AppDir.
    $stashedVenv = $null
    $appVenv     = Join-Path $AppDir ".venv"
    $existingIsJunction = (Test-Path $AppDir) -and (Test-IsReparsePoint $AppDir)
    # If migration above stashed a venv, treat that as the existing one to restore.
    $migrateStash = Join-Path $env:LOCALAPPDATA "TermTube.venv.stash"
    if ((Test-Path $migrateStash) -and -not (Test-Path $appVenv)) {
        $stashedVenv = $migrateStash
    }

    # Ensure $AppDir's parent dir (%LOCALAPPDATA%\Programs\) exists — New-Item
    # Junction will fail with an unhelpful error if it doesn't.
    $appParent = Split-Path -Parent $AppDir
    if ($appParent -and -not (Test-Path $appParent)) {
        New-Item -ItemType Directory -Path $appParent -Force | Out-Null
    }

    if ($SyncMode) {
        Write-Header "Developer Sync Mode"
        # IMPORTANT: Remove-PathSafe so that if $AppDir was a previous
        # standard install (a real dir) we recurse-delete it, but if it was
        # a junction from a prior sync run we delete only the junction —
        # NOT the user's source tree it points at.
        if (Test-Path $AppDir) {
            if (-not (Remove-PathSafe $AppDir)) { return }
        }
        # Junctions only work on same volume and cannot span network shares
        try {
            New-Item -ItemType Junction -Path $AppDir -Target $origDir -ErrorAction Stop | Out-Null
        } catch {
            Write-Err "Failed to create junction: $($_.Exception.Message)"
            Write-Warn "Falling back to standard copy install."
            $SyncMode = $false
        }
        if ($SyncMode) {
            Write-Success "Junction: $AppDir -> $origDir"
            return
        }
    }

    Write-Header "Standard Installation"

    # Stash .venv if it exists in the previous standard install (not a junction)
    if ((Test-Path $appVenv) -and -not $existingIsJunction -and -not (Test-IsReparsePoint $appVenv)) {
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
        Write-Header "Binary Dependencies"
        Bootstrap-Dependencies
    }

    # Install code first, THEN download bundled mpv.
    # mpv lives in $DataDir, which is intentionally outside $AppDir — so
    # the order is no longer load-bearing for correctness, but doing code
    # first matches the user-visible "set up the app, then add binaries"
    # mental model.
    Install-Files -SyncMode $syncMode

    # Download standalone mpv.exe for windowless audio playback (into
    # $DataDir, NOT $AppDir — safe across reinstalls and sync mode).
    Install-MpvCli | Out-Null

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