# TermTube v2 — Windows Setup (PLACEHOLDER)
#
# This is a non-functional skeleton for future Windows support.
# TermTube currently requires macOS or Linux.
# Contributions welcome!
#
# Prerequisites:
#   - Windows 10/11 with winget
#   - Python 3.11+ (winget install Python.Python.3.12)
#   - mpv (winget install mpv-player.mpv)
#   - ffmpeg (winget install Gyan.FFmpeg)

Write-Host "TermTube v2 — Windows Setup" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor DarkGray
Write-Host ""
Write-Host "⚠  Windows support is not yet implemented." -ForegroundColor Yellow
Write-Host "   This script is a placeholder for future development." -ForegroundColor Yellow
Write-Host ""
Write-Host "To use TermTube on Windows today, try WSL2:" -ForegroundColor White
Write-Host "  1. wsl --install" -ForegroundColor Gray
Write-Host "  2. Open Ubuntu from Start Menu" -ForegroundColor Gray
Write-Host "  3. git clone <repo> && cd TermTube && bash setup.sh" -ForegroundColor Gray
Write-Host ""

# ── Dependency skeleton (for future implementation) ────────────────────────

function Test-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

Write-Host "Checking prerequisites..." -ForegroundColor Cyan

# Python
if (Test-Command "python") {
    $pyVer = python --version 2>&1
    Write-Host "  ✓ Python: $pyVer" -ForegroundColor Green
} else {
    Write-Host "  ✗ Python not found" -ForegroundColor Red
    Write-Host "    Install: winget install Python.Python.3.12" -ForegroundColor Gray
}

# mpv
if (Test-Command "mpv") {
    Write-Host "  ✓ mpv found" -ForegroundColor Green
} else {
    Write-Host "  ✗ mpv not found" -ForegroundColor Red
    Write-Host "    Install: winget install mpv-player.mpv" -ForegroundColor Gray
}

# ffmpeg
if (Test-Command "ffmpeg") {
    Write-Host "  ✓ ffmpeg found" -ForegroundColor Green
} else {
    Write-Host "  ✗ ffmpeg not found (optional)" -ForegroundColor Yellow
    Write-Host "    Install: winget install Gyan.FFmpeg" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Full Windows setup is not yet available." -ForegroundColor Yellow
Write-Host "Please use WSL2 or contribute Windows support!" -ForegroundColor Yellow
