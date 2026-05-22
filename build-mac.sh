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

echo " Building..."
.venv/bin/pyinstaller specops.spec --noconfirm --clean

echo ""
if [ -d "dist/SPEC-OPS Clip Review.app" ]; then
    echo " BUILD SUCCESS"
    echo " Output: dist/SPEC-OPS Clip Review.app"
    echo ""
    echo " To distribute:"
    echo "   cd dist && zip -r 'SPEC-OPS-Clip-Review-mac.zip' 'SPEC-OPS Clip Review.app'"
    echo ""
    echo " Teammates drag the .app to /Applications and double-click — no Python needed."
else
    echo " BUILD FAILED — check output above."
fi
echo ""
