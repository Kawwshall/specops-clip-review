#!/bin/bash
set -e
cd "$(dirname "$0")"

echo ""
echo " SPEC-OPS Clip Review - macOS Build"
echo " ===================================="

# Create venv if missing
if [ ! -f ".venv/bin/python3" ]; then
    echo " Creating venv..."
    python3 -m venv .venv
    .venv/bin/pip install --quiet imageio-ffmpeg
fi

echo " Installing PyInstaller..."
.venv/bin/pip install --quiet pyinstaller

# Generate .icns from PNG (requires macOS built-in sips + iconutil)
if command -v sips >/dev/null && command -v iconutil >/dev/null; then
    echo " Generating .icns icon..."
    mkdir -p spec-ops-logo.iconset
    sips -z 16  16  spec-ops-logo.png --out spec-ops-logo.iconset/icon_16x16.png      >/dev/null 2>&1
    sips -z 32  32  spec-ops-logo.png --out spec-ops-logo.iconset/icon_16x16@2x.png   >/dev/null 2>&1
    sips -z 32  32  spec-ops-logo.png --out spec-ops-logo.iconset/icon_32x32.png      >/dev/null 2>&1
    sips -z 64  64  spec-ops-logo.png --out spec-ops-logo.iconset/icon_32x32@2x.png   >/dev/null 2>&1
    sips -z 128 128 spec-ops-logo.png --out spec-ops-logo.iconset/icon_128x128.png    >/dev/null 2>&1
    sips -z 256 256 spec-ops-logo.png --out spec-ops-logo.iconset/icon_128x128@2x.png >/dev/null 2>&1
    sips -z 256 256 spec-ops-logo.png --out spec-ops-logo.iconset/icon_256x256.png    >/dev/null 2>&1
    sips -z 512 512 spec-ops-logo.png --out spec-ops-logo.iconset/icon_256x256@2x.png >/dev/null 2>&1
    sips -z 512 512 spec-ops-logo.png --out spec-ops-logo.iconset/icon_512x512.png    >/dev/null 2>&1
    iconutil -c icns spec-ops-logo.iconset -o spec-ops-logo.icns
    rm -rf spec-ops-logo.iconset
fi

echo " Building..."
.venv/bin/pyinstaller specops.spec --noconfirm --clean

if [ ! -d "dist/ClipReview.app" ]; then
    echo " BUILD FAILED — check output above."
    echo ""
    exit 1
fi

# Ad-hoc sign with hardened runtime so Gatekeeper doesn't hard-block the app.
# --deep signs all nested dylibs (ffmpeg etc.) in one pass.
echo " Signing (ad-hoc + hardened runtime)..."
codesign --deep --force --sign - \
    --options runtime \
    --entitlements entitlements.plist \
    "dist/ClipReview.app"

# Verify the signature looks sane before packaging
codesign --verify --deep --strict "dist/ClipReview.app" \
    && echo " Signature: OK" \
    || echo " WARNING: codesign verify failed — check output"

# ditto preserves .app symlinks and resource forks; plain zip breaks them
echo " Packaging..."
ditto -c -k --keepParent "dist/ClipReview.app" "ClipReview-mac.zip"

echo ""
echo " BUILD SUCCESS"
echo " Output: ClipReview-mac.zip"
echo ""
echo " To install:"
echo "   Unzip → drag ClipReview.app to /Applications → double-click"
echo ""
echo " If macOS still says 'unverified developer', run once in Terminal:"
echo "   xattr -rd com.apple.quarantine /Applications/ClipReview.app"
echo ""
