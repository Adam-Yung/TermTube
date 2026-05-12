# TermTube Website & Installer

## Overview

A modern, dark-themed static website deployed on Vercel that showcases TermTube to non-developers, plus a one-click installer for each platform that handles all dependencies and creates a desktop shortcut.

---

## Website

### Tech Stack

- **Framework:** Astro (static site generator — fast, minimal JS shipped to client)
- **Styling:** Tailwind CSS (dark theme by default)
- **Hosting:** Vercel (free tier, auto-deploy from GitHub, custom domain)
- **Location:** `website/` directory in the repo

### Pages and Layout

**Top Header (sticky, glass-blur background):**
- Logo + "TermTube" wordmark (left)
- Nav links: Home | Guide | GitHub (center)
- Download button (right) — rounded, highlighted with gradient accent

**Home Page (`/`)**
- Hero section: tagline + animated terminal demo (asciinema embed or CSS-animated mockup)
- Feature grid (3x2): thumbnails, playback, search, playlists, SponsorBlock, keyboard-driven
- Short "How it works" section: 3 steps (Download → Install → Enjoy)
- Footer with GitHub link + license

**Guide Page (`/guide`)**
- Sidebar navigation with sections:
  - Getting Started (first launch, cookies setup)
  - Home Feed (browsing, paging, suppression)
  - Search (/ shortcut, result caching)
  - Playback (audio player, video watch, seek, pause, queue)
  - Downloads (video/audio, quality selection, progress phases)
  - Playlists (create, add, browse)
  - Channel Browsing (channel screen, sort, tabs)
  - Keyboard Reference (full table of all bindings)
  - Settings (config.yaml options)
- Each section has annotated screenshots/gifs of the actual TUI
- Keybinding tables rendered as styled cards

**GitHub link** — external link to `https://github.com/Adam-Yung/TermTube`

### Download Button Behavior

Uses browser User-Agent detection (works in Safari, Chrome, Firefox):

```javascript
function getDownloadUrl() {
  const ua = navigator.userAgent.toLowerCase();
  const platform = navigator.platform.toLowerCase();
  
  if (platform.includes('mac') || ua.includes('macintosh')) {
    return '/downloads/termtube-install-macos.command';
  } else if (platform.includes('win') || ua.includes('windows')) {
    return '/downloads/termtube-install-windows.bat';
  } else {
    return '/downloads/termtube-install-linux.sh';
  }
}
```

Fallback: if detection fails, show a dropdown with all three options.

---

## Installer (One-Click TUI)

### Design Philosophy

- User downloads a single file from the website
- Double-clicking that file opens the system terminal and runs the installer
- The installer is a TUI (terminal-based UI) with colored output, progress indicators, and prompts
- After completion, a TermTube app icon appears on the desktop/Applications folder
- No prior knowledge of package managers, Python, or terminals required

### Per-Platform Installers

#### macOS: `termtube-install-macos.command`

A `.command` file (double-clickable, opens Terminal.app automatically):

```bash
#!/bin/bash
# TermTube Installer for macOS
# Double-click this file to install TermTube.

clear
echo "========================================"
echo "  TermTube Installer"
echo "========================================"
echo ""

# Check/install Homebrew
if ! command -v brew &>/dev/null; then
    echo "Installing Homebrew (package manager)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Install dependencies
echo "Installing dependencies..."
brew install python@3.12 yt-dlp mpv chafa ffmpeg

# Install TermTube
echo "Installing TermTube..."
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git ~/Applications/TermTube
cd ~/Applications/TermTube/main
pip3 install -r requirements.txt

# Create .app bundle (opens Terminal running TermTube)
# Uses an AppleScript-based approach to create a clickable app
mkdir -p ~/Applications/TermTube.app/Contents/MacOS
cat > ~/Applications/TermTube.app/Contents/MacOS/TermTube <<'LAUNCHER'
#!/bin/bash
open -a Terminal ~/Applications/TermTube/main/termtube
LAUNCHER
chmod +x ~/Applications/TermTube.app/Contents/MacOS/TermTube

# Set icon (Info.plist + .icns file)
# ... (bundled icon asset)

# Optional: desktop shortcut
read -p "Create Desktop shortcut? [Y/n] " yn
if [[ "$yn" != "n" && "$yn" != "N" ]]; then
    ln -sf ~/Applications/TermTube.app ~/Desktop/TermTube
fi

echo ""
echo "Installation complete! TermTube is ready."
echo "Launch from Applications or Desktop shortcut."
```

#### Windows: `termtube-install-windows.bat`

A `.bat` file (double-clickable, opens Command Prompt):

```batch
@echo off
title TermTube Installer
echo ========================================
echo   TermTube Installer for Windows
echo ========================================
echo.

:: Check for winget
where winget >nul 2>nul
if errorlevel 1 (
    echo Error: winget not found. Please install App Installer from Microsoft Store.
    pause
    exit /b 1
)

:: Install dependencies via winget
echo Installing Python...
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo Installing yt-dlp...
winget install yt-dlp.yt-dlp --accept-package-agreements
echo Installing mpv...
winget install mpv.net --accept-package-agreements
echo Installing ffmpeg...
winget install Gyan.FFmpeg --accept-package-agreements

:: Clone and setup
echo Installing TermTube...
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git "%LOCALAPPDATA%\TermTube"
cd /d "%LOCALAPPDATA%\TermTube\main"
pip install -r requirements.txt

:: Create desktop shortcut (.lnk via PowerShell)
set /p SHORTCUT="Create Desktop shortcut? [Y/n] "
if /i not "%SHORTCUT%"=="n" (
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\TermTube.lnk'); $sc.TargetPath = 'wt.exe'; $sc.Arguments = 'python %LOCALAPPDATA%\TermTube\main\src\main.py'; $sc.Save()"
)

echo.
echo Installation complete! Launch TermTube from your Desktop shortcut.
pause
```

#### Linux: `termtube-install-linux.sh`

A `.sh` file (user runs `chmod +x` + `./` or file managers may offer "Run in Terminal"):

```bash
#!/bin/bash
# TermTube Installer for Linux
clear
echo "========================================"
echo "  TermTube Installer for Linux"
echo "========================================"
echo ""

# Detect package manager
if command -v apt &>/dev/null; then
    PM="apt"
    sudo apt update && sudo apt install -y python3 python3-pip yt-dlp mpv chafa ffmpeg git
elif command -v pacman &>/dev/null; then
    PM="pacman"
    sudo pacman -Syu --noconfirm python python-pip yt-dlp mpv chafa ffmpeg git
elif command -v dnf &>/dev/null; then
    PM="dnf"
    sudo dnf install -y python3 python3-pip yt-dlp mpv chafa ffmpeg git
else
    echo "Unsupported package manager. Please install manually."
    exit 1
fi

# Install TermTube
git clone --depth 1 https://github.com/Adam-Yung/TermTube.git ~/.local/share/TermTube
cd ~/.local/share/TermTube/main
pip3 install --user -r requirements.txt

# Create .desktop file
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/termtube.desktop <<'DESKTOP'
[Desktop Entry]
Name=TermTube
Comment=YouTube TUI Client
Exec=x-terminal-emulator -e ~/.local/share/TermTube/main/termtube
Icon=~/.local/share/TermTube/main/assets/icon.png
Terminal=false
Type=Application
Categories=AudioVideo;Network;
DESKTOP

# Optional desktop shortcut
read -p "Create Desktop shortcut? [Y/n] " yn
if [[ "$yn" != "n" && "$yn" != "N" ]]; then
    cp ~/.local/share/applications/termtube.desktop ~/Desktop/
    chmod +x ~/Desktop/termtube.desktop
fi

echo ""
echo "Installation complete! Find TermTube in your application launcher."
```

---

## Vercel Deployment

### Setup Steps

1. Install Vercel CLI: `npm i -g vercel`
2. In the `website/` directory: `vercel` (follows prompts to link GitHub repo)
3. Configure build:
   - Framework: Astro
   - Build command: `npm run build`
   - Output directory: `dist`
4. Custom domain:
   - In Vercel dashboard → Project → Settings → Domains
   - Add your domain (e.g., `termtube.app` or `termtube.dev`)
   - Point DNS (A record to `76.76.21.21` or CNAME to `cname.vercel-dns.com`)
   - SSL certificate auto-provisioned by Vercel

### Auto-Deploy

Push to `main` branch → Vercel automatically rebuilds and deploys. The `website/` directory can be set as the root directory in Vercel project settings.

---

## Suggested Improvements

1. **Terminal demo on homepage** — embed an asciinema recording or a JS-based terminal animation showing TermTube in action (much more compelling than screenshots for a TUI app)

2. **"Try without installing" section** — link to a cloud-hosted terminal demo (e.g., via Gitpod or a WebSocket terminal) so users can try TermTube instantly in-browser

3. **Version badge + changelog link** — show current version in the header, link to GitHub releases for changelog

4. **Testimonials / stats section** — GitHub stars counter, "X videos played", or user quotes

5. **SEO metadata** — Open Graph tags, Twitter cards, structured data for search engines

6. **Analytics** — Vercel Analytics (privacy-respecting, no cookies) to track download counts

7. **Installer auto-update** — the installer could check for existing installations and offer to update instead of reinstall

8. **App icon** — design a proper TermTube icon (.icns for Mac, .ico for Windows, .png for Linux) to make the desktop shortcut look professional

---

## Concerns and Open Questions

1. **macOS Gatekeeper** — `.command` files downloaded from the internet are quarantined. Users will see "cannot be opened because it is from an unidentified developer." Fix: either sign the script (requires Apple Developer account, $99/yr) or include instructions to right-click → Open, which bypasses Gatekeeper once.

2. **Windows SmartScreen** — `.bat` files from the internet trigger SmartScreen warnings. Signing requires an EV code signing certificate (~$200-400/yr). Alternative: host a `.msi` or `.exe` installer built with NSIS/Inno Setup (more trusted by Windows).

3. **Linux double-click** — most file managers don't execute `.sh` files on double-click by default; they open them in a text editor. Users need to either: set "executable" permission in file properties, or open a terminal and run `bash termtube-install-linux.sh`. Consider providing a `.desktop` file as the download instead.

4. **Dependency installation failures** — Homebrew/winget installs can fail (no internet, corporate firewalls, disk full). The installer needs proper error handling and clear messages.

5. **Python version conflicts** — systems may have Python 3.8/3.9 pre-installed. The installer should ensure Python 3.11+ specifically.

6. **Domain choice** — `.dev` domains enforce HTTPS (good), `.app` is recognizable. Both cost ~$12-15/yr. Register via Google Domains, Namecheap, or Cloudflare Registrar.

---

## Implementation Order

1. Register domain and set up Vercel project
2. Scaffold Astro site in `website/` with Tailwind
3. Build Home page (hero, features, download button)
4. Build Guide page (sidebar nav, content sections)
5. Create installer scripts for all 3 platforms
6. Test installers on clean VMs (macOS, Windows, Ubuntu)
7. Design app icon
8. Record asciinema terminal demo
9. Deploy to Vercel, configure custom domain
10. Add download files to Vercel static assets or GitHub Releases
