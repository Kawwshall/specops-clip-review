@echo off
cd /d "%~dp0"
echo.
echo  SPEC-OPS Clip Review - Windows Build
echo  ======================================

if not exist ".venv\Scripts\python.exe" (
    echo  Creating venv...
    python -m venv .venv
    .venv\Scripts\pip install --quiet imageio-ffmpeg
)

echo  Installing PyInstaller...
.venv\Scripts\pip install --quiet pyinstaller

echo  Building...
.venv\Scripts\pyinstaller specops.spec --noconfirm --clean

echo.
if exist "dist\SPEC-OPS Clip Review\SPEC-OPS Clip Review.exe" (
    echo  BUILD SUCCESS
    echo  Output: dist\SPEC-OPS Clip Review\
    echo.
    echo  Zip that folder and send to teammates.
    echo  They double-click "SPEC-OPS Clip Review.exe" — no Python needed.
) else (
    echo  BUILD FAILED — check output above.
)
echo.
pause
