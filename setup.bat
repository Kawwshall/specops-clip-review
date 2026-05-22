@echo off
cd /d "%~dp0"
echo.
echo  SPEC-OPS Clip Review - One-time Setup
echo  =======================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo  First run: creating virtual environment...
    python -m venv .venv
    if errorlevel 1 ( echo  ERROR: Python not found. Install Python 3.9+ first. & pause & exit /b 1 )
    echo  Installing dependencies...
    .venv\Scripts\pip install --quiet imageio-ffmpeg
    echo  Done.
    echo.
)

.venv\Scripts\python.exe _setup_helper.py
if errorlevel 1 ( echo  Setup failed. & pause & exit /b 1 )

echo.
echo  Starting server and opening browser...
start "" ".venv\Scripts\python.exe" server.py
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8765"
echo.
pause
