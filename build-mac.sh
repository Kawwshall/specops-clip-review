#!/bin/bash
# build-mac.sh  — builds ClipReview-mac.dmg  (standard macOS drag-to-install)
# Works on macOS 12 through 26+.  No PyInstaller, no compiled binary.
# Requires: codesign, sips, iconutil, hdiutil  (all built-in on macOS)
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo " SPEC-OPS Clip Review — macOS Build"
echo " ====================================="
echo ""

# Use /tmp so stale root-owned files from previous builds can't block clean
BUILD="/tmp/specops-mac-build"
APP="$BUILD/ClipReview.app"
CONTENTS="$APP/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
DMG_STAGE="$BUILD/dmg-stage"

# ── Clean ──────────────────────────────────────────────────────────────────────
chmod -R u+w "$BUILD" 2>/dev/null || true
rm -rf "$BUILD" ClipReview-mac.dmg
mkdir -p "$MACOS_DIR" "$RES" "$DMG_STAGE"

# ── Copy source files into bundle ──────────────────────────────────────────────
echo " Copying source files..."
cp server.py index.html spec-ops-logo.png "$RES/"

# ── Generate .icns icon ────────────────────────────────────────────────────────
if command -v sips >/dev/null && command -v iconutil >/dev/null; then
    echo " Generating icon..."
    IS="$BUILD/spec-ops-logo.iconset"
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
# Venv lives in ~/.clipreview so App Translocation has zero effect.

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

# ── Ad-hoc sign ───────────────────────────────────────────────────────────────
echo " Signing (ad-hoc)..."
codesign --deep --force --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo " Signature: OK" || echo " WARNING: verify failed (non-fatal)"

# ── Stage DMG contents ────────────────────────────────────────────────────────
echo " Staging DMG..."
ditto "$APP" "$DMG_STAGE/ClipReview.app"
# Symlink to /Applications = standard "drag here" target inside the DMG
ln -sf /Applications "$DMG_STAGE/Applications"

# ── Build DMG ─────────────────────────────────────────────────────────────────
echo " Building DMG..."
hdiutil create \
    -volname "Clip Review" \
    -srcfolder "$DMG_STAGE" \
    -ov -format UDZO \
    ClipReview-mac.dmg

DMG_SIZE=$(du -sh ClipReview-mac.dmg | cut -f1)
echo ""
echo " BUILD SUCCESS"
echo " Output : ClipReview-mac.dmg  ($DMG_SIZE)"
echo ""
echo " Teammates install:"
echo "   1. Open ClipReview-mac.dmg"
echo "   2. Drag ClipReview → Applications arrow"
echo "   3. Eject the DMG"
echo "   4. Applications → double-click ClipReview"
echo "   5. If macOS shows a security warning:"
echo "      System Settings → Privacy & Security → Open Anyway"
echo ""
