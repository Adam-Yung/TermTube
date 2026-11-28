#!/usr/bin/env bash
# The optional desktop shortcut or macOS app. Sourced by setup.sh, whose variables and print helpers it uses.

install_shortcut() {
    if [[ "$INTERACTIVE" == true ]]; then
        echo ""
        read -r -p "  Install TermTube outside the terminal? (creates a desktop shortcut/app) [Y/n] " reply
        if [[ "${reply}" =~ ^[Nn]$ ]]; then
            info "Skipped desktop shortcut."
            return
        fi
    else
        return 0
    fi

    if [[ "$(uname)" == "Darwin" ]]; then
        _install_macos_app
    else
        _install_linux_desktop
    fi
}

_install_linux_desktop() {
    local desktop_dir="$HOME/.local/share/applications"
    local desktop_file="$desktop_dir/termtube.desktop"
    mkdir -p "$desktop_dir"
    cat > "$desktop_file" <<EOF
[Desktop Entry]
Name=TermTube
Comment=YouTube in your terminal
Exec=${BIN_DIR}/termtube
Icon=${APP_DIR}/assets/termtube.png
Terminal=true
Type=Application
Categories=Network;Video;
EOF
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$desktop_dir" 2>/dev/null || true
    fi
    success "Desktop entry created: $desktop_file"
    info "TermTube will appear in your application launcher."
}

_install_macos_app() {
    local app_bundle="$HOME/Applications/TermTube.app"
    local macos_dir="$app_bundle/Contents/MacOS"
    local resources_dir="$app_bundle/Contents/Resources"

    mkdir -p "$macos_dir" "$resources_dir"

    # Executable: a Finder launch has no tty, so it hands off to launch-macos.sh, which opens a
    # Terminal window and copes with whatever the user's shell startup files do (tmux auto-attach...).
    cat > "$macos_dir/TermTube" <<EOF
#!/bin/bash
exec /bin/bash "${APP_DIR}/scripts/launch-macos.sh" "${BIN_DIR}/termtube"
EOF
    chmod +x "$macos_dir/TermTube"

    # Copy icon
    if [[ -f "${APP_DIR}/assets/termtube.icns" ]]; then
        cp "${APP_DIR}/assets/termtube.icns" "$resources_dir/termtube.icns"
    fi

    # Info.plist
    cat > "$app_bundle/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>TermTube</string>
    <key>CFBundleIdentifier</key>
    <string>com.termtube.app</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>TermTube</string>
    <key>CFBundleIconFile</key>
    <string>termtube</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
</dict>
</plist>
EOF
    success "macOS app bundle created: $app_bundle"
    warn "First launch: right-click → Open to bypass Gatekeeper (unsigned app)."
}
