@echo off
setlocal

set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "DESKTOP=%USERPROFILE%\Desktop"

echo Installing SPEC-OPS Clip Review...

rem -- Copy hidden launcher to Startup folder so server starts with Windows
copy /Y "%APP_DIR%\start-hidden.vbs" "%STARTUP%\SPEC-OPS Clip Review.vbs" >nul
echo   [OK] Server will start automatically on login

rem -- Create desktop URL shortcut
(
  echo [InternetShortcut]
  echo URL=http://127.0.0.1:8765
  echo IconFile=%SystemRoot%\system32\shell32.dll
  echo IconIndex=13
) > "%DESKTOP%\SPEC-OPS Clip Review.url"
echo   [OK] Desktop shortcut created

rem -- Start server now (hidden)
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find /I "python.exe" >nul
if errorlevel 1 (
    cscript //nologo "%APP_DIR%\start-hidden.vbs"
    echo   [OK] Server started
) else (
    echo   [OK] Server already running
)

timeout /t 2 >nul
start "" "http://127.0.0.1:8765"

echo.
echo Done! From now on:
echo   - Server starts automatically when you log in to Windows
echo   - Open "SPEC-OPS Clip Review" from your desktop anytime
echo.
pause
