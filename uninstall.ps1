#Requires -Version 5.1
<#
.SYNOPSIS
    TermTube uninstaller for Windows.

.DESCRIPTION
    Completely removes TermTube installation, PATH entries, and optionally
    config/cache/logs.

.PARAMETER Purge
    Remove config, cookies, cache, and logs (complete removal).

.PARAMETER Force
    Skip confirmation prompt.

.EXAMPLE
    .\uninstall.ps1
    .\uninstall.ps1 -Purge
    .\uninstall.ps1 -Purge -Force
#>

[CmdletBinding()]
param(
    [switch]$Purge,
    [switch]$Force,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Constants ─────────────────────────────────────────────────────────────────
# New layout (post-2026-05): code lives under \Programs\TermTube, data under
# \TermTube. We also detect the legacy layout where code lived directly under
# \TermTube and conflicted with the data dir.
$AppDir       = Join-Path $env:LOCALAPPDATA "Programs\TermTube"
$DataDir      = Join-Path $env:LOCALAPPDATA "TermTube"   # cache, bundled mpv, history
$LegacyAppDir = $DataDir                                  # pre-fix code dir
$ConfigDir    = Join-Path $env:APPDATA "TermTube"
$CacheDir     = Join-Path $DataDir "cache"
$MpvDir       = Join-Path $DataDir "mpv"                  # bundled standalone mpv
$TempDir      = Join-Path $env:TEMP "TermTube"

# ── Output Helpers ────────────────────────────────────────────────────────────
function Write-Info    { param($Msg) Write-Host "  > " -NoNewline -ForegroundColor Cyan; Write-Host $Msg }
function Write-Success { param($Msg) Write-Host "  + " -NoNewline -ForegroundColor Green; Write-Host $Msg }
function Write-Warn    { param($Msg) Write-Host "  ! " -NoNewline -ForegroundColor Yellow; Write-Host $Msg }
function Write-Err     { param($Msg) Write-Host "  x " -NoNewline -ForegroundColor Red; Write-Host $Msg }

# ── Help ──────────────────────────────────────────────────────────────────────
if ($Help) {
    Write-Host @"

  TermTube Uninstaller (Windows)
  ===============================

  Usage: .\uninstall.ps1 [OPTIONS]

  Options:
    (default)     Remove app files and PATH entry.
                  Preserves config and cookies.

    -Purge        Also remove config, cookies, cache, and logs.

    -Force        Skip confirmation prompt.

    -Help         Show this message.

"@
    exit 0
}

# ── Discovery ─────────────────────────────────────────────────────────────────
Write-Host ""
$title = "TermTube Uninstaller"
$width = 37
$inner = $width - 2

try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
    $pad   = [Math]::Floor(($inner - $title.Length) / 2)
    $right = $inner - $title.Length - $pad
    $centered = (' ' * $pad) + $title + (' ' * $right)
    $bar = [string][char]0x2500 * $inner
    $top = "  " + [char]0x250C + $bar + [char]0x2510
    $mid = "  " + [char]0x2502 + $centered + [char]0x2502
    $bot = "  " + [char]0x2514 + $bar + [char]0x2518
    $testBytes = [Console]::OutputEncoding.GetBytes($top)
    Write-Host $top -ForegroundColor White
    Write-Host $mid -ForegroundColor White
    Write-Host $bot -ForegroundColor White
} catch {
    $bar = "-" * $inner
    $pad   = [Math]::Floor(($inner - $title.Length) / 2)
    $right = $inner - $title.Length - $pad
    $centered = (' ' * $pad) + $title + (' ' * $right)
    Write-Host ("  +" + $bar + "+") -ForegroundColor White
    Write-Host ("  |" + $centered + "|") -ForegroundColor White
    Write-Host ("  +" + $bar + "+") -ForegroundColor White
}
Write-Host ""

$itemsToRemove = @()

function Check-Item {
    param([string]$Path, [string]$Label)

    if (Test-Path $Path) {
        $script:itemsToRemove += $Path
        $isJunction = (Get-Item $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint
        if ($isJunction) {
            $target = (Get-Item $Path).Target
            Write-Host "  x " -NoNewline -ForegroundColor Red
            Write-Host "$Label (junction -> $target)"
        } else {
            $size = ""
            if (Test-Path $Path -PathType Container) {
                try {
                    $bytes = (Get-ChildItem $Path -Recurse -File | Measure-Object -Property Length -Sum).Sum
                    if ($bytes -gt 1MB) { $size = " ({0:N1} MB)" -f ($bytes / 1MB) }
                    elseif ($bytes -gt 1KB) { $size = " ({0:N0} KB)" -f ($bytes / 1KB) }
                } catch {}
            }
            Write-Host "  x " -NoNewline -ForegroundColor Red
            Write-Host "$Label$size"
        }
        Write-Host "      $Path" -ForegroundColor DarkGray
    }
}

Write-Host "  The following will be removed:" -ForegroundColor White
Write-Host ""

Check-Item $AppDir "Application files"
# Legacy install dir from before the architectural split — show it only if
# it has code in it (don't flag a pure data dir as "legacy install").
if ((Test-Path $LegacyAppDir) -and -not ($LegacyAppDir -eq $AppDir)) {
    $legacyHasCode = (Test-Path (Join-Path $LegacyAppDir "src")) -or `
                     (Test-Path (Join-Path $LegacyAppDir "termtube.cmd"))
    if ($legacyHasCode) {
        Check-Item $LegacyAppDir "Legacy application files"
    }
}
Check-Item $MpvDir "Bundled mpv binary"

if ($Purge) {
    Check-Item $ConfigDir "Configuration & cookies"
    Check-Item $CacheDir  "Cache data"
    Check-Item $TempDir   "Temp/log files"
    # On -Purge we also nuke the entire data dir (which contains mpv/, cache/,
    # history.json, etc.) — already-listed children get deduped during removal.
    if ((Test-Path $DataDir) -and -not ((Get-Item $DataDir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Check-Item $DataDir "Data directory (history, etc.)"
    }
}

if ($itemsToRemove.Count -eq 0) {
    Write-Host ""
    Write-Success "Nothing to remove. TermTube is not installed."
    exit 0
}

if (-not $Purge) {
    Write-Host ""
    Write-Host "  Will be preserved:" -ForegroundColor White
    if (Test-Path $ConfigDir) {
        Write-Host "  + " -NoNewline -ForegroundColor Green
        Write-Host "Config & cookies ($ConfigDir)"
    }
    Write-Host "      Use -Purge to remove everything." -ForegroundColor DarkGray
}

# ── Confirmation ──────────────────────────────────────────────────────────────
if (-not $Force) {
    Write-Host ""
    $reply = Read-Host "  Proceed with uninstall? [y/N]"
    if ($reply -notmatch '^[Yy]') {
        Write-Host ""
        Write-Info "Uninstall cancelled."
        exit 0
    }
}

# ── Kill Running Processes ────────────────────────────────────────────────────
$procs = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*TermTube*" }
if ($procs) {
    Write-Warn "Stopping TermTube processes..."
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# ── Removal ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Removing..." -ForegroundColor White

function Remove-SafeItem {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path $Path)) { return }
    try {
        $item = Get-Item $Path -Force
        $isJunction = $item.Attributes -band [IO.FileAttributes]::ReparsePoint
        if ($isJunction) {
            $item.Delete()
        } else {
            Remove-Item $Path -Recurse -Force
        }
        Write-Success "Removed: $Label"
    } catch {
        Write-Warn "Could not remove: $Path ($($_.Exception.Message))"
    }
}

Remove-SafeItem $AppDir  "Application files"
# Legacy code dir (preserve any data files inside — mpv/, cache/, history.json
# — by removing only the code/launcher artifacts).
if ((Test-Path $LegacyAppDir) -and -not ($LegacyAppDir -eq $AppDir) -and `
    -not ((Get-Item $LegacyAppDir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    foreach ($name in @("src", "termtube", "termtube.cmd", "setup.sh", "setup.ps1",
                        "uninstall.sh", "uninstall.ps1", "requirements.txt", ".venv")) {
        $p = Join-Path $LegacyAppDir $name
        if (Test-Path $p) { Remove-SafeItem $p "Legacy: $name" }
    }
}
Remove-SafeItem $MpvDir "Bundled mpv binary"

if ($Purge) {
    Remove-SafeItem $ConfigDir "Configuration & cookies"
    Remove-SafeItem $CacheDir  "Cache data"
    Remove-SafeItem $TempDir   "Temp/log files"
    Remove-SafeItem $DataDir   "Data directory"
}

# ── Clean PATH ────────────────────────────────────────────────────────────────
# Strip both the new $AppDir and the historical $BinDir from user PATH.
$legacyBinDir = Join-Path $env:LOCALAPPDATA "Programs\TermTube"   # same as $AppDir today
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath) {
    $entries = $userPath.Split(';') | Where-Object {
        $_ -and $_ -ne $AppDir -and $_ -ne $legacyBinDir
    }
    $cleanPath = $entries -join ';'
    if ($cleanPath -ne $userPath) {
        [System.Environment]::SetEnvironmentVariable("PATH", $cleanPath, "User")
        Write-Success "Removed TermTube entries from user PATH."
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host ("  " + ("=" * 41)) -ForegroundColor White
Write-Host "  TermTube uninstalled successfully." -ForegroundColor Green
Write-Host ("  " + ("=" * 41)) -ForegroundColor White
if (-not $Purge -and (Test-Path $ConfigDir)) {
    Write-Host ""
    Write-Host "  Config preserved at: $ConfigDir" -ForegroundColor DarkGray
    Write-Host "  Run with -Purge to remove all traces." -ForegroundColor DarkGray
}
Write-Host ""
exit 0
