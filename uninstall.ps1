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

# Ensure the console can render Unicode box-drawing characters
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

# ── Constants ─────────────────────────────────────────────────────────────────
$AppDir = Join-Path $env:LOCALAPPDATA "TermTube"
$BinDir = Join-Path $env:LOCALAPPDATA "Programs\TermTube"
$ConfigDir = Join-Path $env:APPDATA "TermTube"
$CacheDir = Join-Path $env:LOCALAPPDATA "TermTube\cache"
$TempDir = Join-Path $env:TEMP "TermTube"

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
$pad   = [Math]::Floor(($inner - $title.Length) / 2)
$right = $inner - $title.Length - $pad
$centered = (' ' * $pad) + $title + (' ' * $right)
$bar = [string][char]0x2500 * $inner
Write-Host ("  " + [char]0x250C + $bar + [char]0x2510) -ForegroundColor White
Write-Host ("  " + [char]0x2502 + $centered           + [char]0x2502) -ForegroundColor White
Write-Host ("  " + [char]0x2514 + $bar + [char]0x2518) -ForegroundColor White
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
Check-Item $BinDir "Launcher directory"

if ($Purge) {
    Check-Item $ConfigDir "Configuration & cookies"
    Check-Item $CacheDir  "Cache data"
    Check-Item $TempDir   "Temp/log files"
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

Remove-SafeItem $BinDir  "Launcher"
Remove-SafeItem $AppDir  "Application files"

if ($Purge) {
    Remove-SafeItem $ConfigDir "Configuration & cookies"
    Remove-SafeItem $CacheDir  "Cache data"
    Remove-SafeItem $TempDir   "Temp/log files"
}

# ── Clean PATH ────────────────────────────────────────────────────────────────
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -and $userPath -like "*$BinDir*") {
    $cleanPath = ($userPath.Split(';') | Where-Object { $_ -ne $BinDir -and $_ -ne "" }) -join ';'
    [System.Environment]::SetEnvironmentVariable("PATH", $cleanPath, "User")
    Write-Success "Removed $BinDir from user PATH."
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor White
Write-Host "  TermTube uninstalled successfully." -ForegroundColor Green
Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor White
if (-not $Purge -and (Test-Path $ConfigDir)) {
    Write-Host ""
    Write-Host "  Config preserved at: $ConfigDir" -ForegroundColor DarkGray
    Write-Host "  Run with -Purge to remove all traces." -ForegroundColor DarkGray
}
Write-Host ""
exit 0
