#!/bin/bash
# build-mac.sh  — builds ClipReview-installer.pkg for macOS.
#
# What the installer does for teammates:
#   1. Drops ClipReview.app into /Applications
#   2. Strips the quarantine flag so macOS never blocks it again
#   3. First launch of the app auto-installs Python packages (notified via macOS)
#
# Requires: codesign, sips, iconutil, pkgbuild, productbuild  (all built-in on macOS)
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo " SPEC-OPS Clip Review — macOS Build"
echo " ====================================="
echo ""

APP="dist/ClipReview.app"
CONTENTS="$APP/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
PKG_ROOT="dist/pkg-root"
PKG_SCRIPTS="dist/pkg-scripts"

# ── Clean ──────────────────────────────────────────────────────────────────────
rm -rf dist/ClipReview.app ClipReview-mac.zip ClipReview-installer.pkg "$PKG_ROOT" "$PKG_SCRIPTS"
mkdir -p "$MACOS_DIR" "$RES" "$PKG_ROOT/Applications" "$PKG_SCRIPTS"

# ── Copy source files into bundle ──────────────────────────────────────────────
echo " Copying source files..."
cp server.py index.html spec-ops-logo.png "$RES/"

# ── Generate .icns icon ────────────────────────────────────────────────────────
if command -v sips >/dev/null && command -v iconutil >/dev/null; then
    echo " Generating icon..."
    IS="spec-ops-logo.iconset"
    mkdir -p "$IS"
    sips -z 16  16  spec-ops-logo.png --out "$IS/icon_16x16.png"      >/dev/null 2>&1
    sips -z 32  32  spec-ops-logo.png --out "$IS/icon_16x16@2x.png"   >/dev/null 2>&1
    sips -z 32  32  spec-ops-logo.png --out "$IS/icon_32x32.png"      >/dev/null 2>&1
    sips -z 64  64  spec-ops-logo.png --out "$IS/icon_32x32@2x.png"   >/dev/null 2>&1
    sips -z 128 128 spec-ops-logo.png --out "$IS/icon_128x128.png"    >/dev/null 2>&1
    sips -z 256 256 spec-ops-logo.png --out "$IS/icon_128x128@2x.png" >/dev/null 2>&1
    sips -z 256 256 spec-ops-logo.png --out "$IS/icon_256x256.png"    >/dev/null 2>&1
    sips -z 512 512 spec-ops-logo.png --out "$IS/icon_256x256@2x.png" >/dev/null 2>&1
    sips -z 512 512 spec-ops-logo.png --out "$IS/icon_512x512.png"    >/dev/null 2>&1
    iconutil -c icns "$IS" -o "$RES/AppIcon.icns"
    rm -rf "$IS"
fi

# ── Write the launcher shell script ───────────────────────────────────────────
echo " Writing launcher..."
cat > "$MACOS_DIR/ClipReview" << 'LAUNCHER'
#!/bin/bash
# ClipReview launcher — ClipReview.app/Contents/MacOS/ClipReview
# Venv lives in ~/.clipreview — App Translocation has zero effect here.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES="$(cd "$SCRIPT_DIR/../Resources" && pwd)"
VENV="$HOME/.clipreview/venv"
LOG="$HOME/.clipreview/server.log"

mkdir -p "$HOME/.clipreview"

# ── Find Python 3 ─────────────────────────────────────────────────────────────
PYTHON3=""
for candidate in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 /opt/homebrew/opt/python3/bin/python3; do
    if "$candidate" --version >/dev/null 2>&1; then
        PYTHON3="$candidate"
        break
    fi
done

if [ -z "$PYTHON3" ]; then
    osascript -e 'display alert "Python 3 required" message "Clip Review needs Python 3.\n\nOpen Terminal and run:\n  xcode-select --install\n\nThen relaunch Clip Review." buttons {"OK"} default button "OK"'
    exit 1
fi

# ── First-run: create venv + install deps (~30 sec, once only) ────────────────
if [ ! -f "$VENV/bin/python3" ]; then
    osascript -e 'display notification "Setting up Clip Review — takes ~30 sec on first launch…" with title "Clip Review"'
    echo "$(date): First-run setup using $PYTHON3" >> "$LOG"
    "$PYTHON3" -m venv "$VENV" >> "$LOG" 2>&1
    "$VENV/bin/pip" install --quiet imageio-ffmpeg >> "$LOG" 2>&1
    echo "$(date): Setup complete" >> "$LOG"
fi

# ── Stop any leftover server from a previous session ─────────────────────────
lsof -ti:8765 | xargs kill -9 2>/dev/null || true
sleep 0.2

# ── Launch server ─────────────────────────────────────────────────────────────
export SPECOPS_DATA="$HOME/.clipreview"
cd "$RESOURCES"
"$VENV/bin/python3" server.py >> "$LOG" 2>&1 &
SERVER_PID=$!

# Wait until the server responds (up to 10 s)
for i in $(seq 1 20); do
    if curl -s --max-time 1 http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

open "http://127.0.0.1:8765"

# Keep the .app process alive so macOS knows it's running
wait "$SERVER_PID"
LAUNCHER
chmod +x "$MACOS_DIR/ClipReview"

# ── Write Info.plist ──────────────────────────────────────────────────────────
echo " Writing Info.plist..."
cat > "$CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>ClipReview</string>
    <key>CFBundleDisplayName</key>
    <string>Clip Review</string>
    <key>CFBundleIdentifier</key>
    <string>ai.build.specops.clipreview</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>ClipReview</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
</dict>
</plist>
PLIST

# ── Ad-hoc sign the .app ──────────────────────────────────────────────────────
echo " Signing .app (ad-hoc)..."
codesign --deep --force --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo " .app signature: OK" || echo " WARNING: verify failed (non-fatal)"

# ── Copy .app into pkg root (installer will place it in /Applications) ────────
echo " Preparing installer root..."
ditto "$APP" "$PKG_ROOT/Applications/ClipReview.app"

# ── Write postinstall script ──────────────────────────────────────────────────
# This runs after files are copied — strips the quarantine flag so macOS
# never blocks the app again, even on the very first double-click.
cat > "$PKG_SCRIPTS/postinstall" << 'POSTINSTALL'
#!/bin/bash
# Remove quarantine so the app opens without any Gatekeeper warning.
xattr -rd com.apple.quarantine /Applications/ClipReview.app 2>/dev/null || true
exit 0
POSTINSTALL
chmod +x "$PKG_SCRIPTS/postinstall"

# ── Build component package ───────────────────────────────────────────────────
echo " Building component package..."
pkgbuild \
    --root "$PKG_ROOT" \
    --scripts "$PKG_SCRIPTS" \
    --identifier "ai.build.specops.clipreview" \
    --version "1.0.0" \
    --install-location "/" \
    dist/ClipReview-component.pkg

# ── Write distribution XML (installer title + welcome text) ──────────────────
cat > dist/distribution.xml << 'DISTXML'
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>Clip Review</title>
    <welcome file="welcome.html" mime-type="text/html"/>
    <options customize="never" require-scripts="true"/>
    <pkg-ref id="ai.build.specops.clipreview"/>
    <choices-outline>
        <line choice="default">
            <line choice="ai.build.specops.clipreview"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="ai.build.specops.clipreview" visible="false">
        <pkg-ref id="ai.build.specops.clipreview"/>
    </choice>
    <pkg-ref id="ai.build.specops.clipreview" version="1.0.0" onConclusion="none">ClipReview-component.pkg</pkg-ref>
</installer-gui-script>
DISTXML

# ── Write welcome HTML shown inside the installer ─────────────────────────────
cat > dist/welcome.html << 'WELCOME'
<html>
<body style="font-family:-apple-system,sans-serif;padding:20px;color:#1a1a1a">
<h2 style="margin-top:0">Clip Review</h2>
<p>This installer will place <strong>ClipReview.app</strong> in your Applications folder.</p>
<p>After installing:</p>
<ol>
  <li>Double-click <strong>ClipReview</strong> in Applications</li>
  <li>First launch takes ~30 seconds to finish setup</li>
  <li>Your browser opens automatically — you're ready to review clips</li>
</ol>
<p style="color:#666;font-size:12px">Requires Python 3 (available on all modern Macs). No internet needed after install.</p>
</body>
</html>
WELCOME

# ── Build final distribution package ─────────────────────────────────────────
echo " Building installer package..."
productbuild \
    --distribution dist/distribution.xml \
    --resources dist \
    --package-path dist \
    ClipReview-installer.pkg

PKG_SIZE=$(du -sh ClipReview-installer.pkg | cut -f1)
echo ""
echo " BUILD SUCCESS"
echo " Output : ClipReview-installer.pkg  ($PKG_SIZE)"
echo ""
echo " Teammates:"
echo "   1. Download ClipReview-installer.pkg"
echo "   2. Double-click → click Continue → Install → enter password → Done"
echo "   3. If macOS blocks the .pkg itself:"
echo "      System Settings → Privacy & Security → Open Anyway (one-time only)"
echo "   4. Open ClipReview from Applications — browser opens automatically"
echo ""
