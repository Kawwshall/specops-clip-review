"""
PyInstaller entry point for Clip Review.
Starts the HTTP server, creates Desktop shortcut on first run, opens browser.
"""
import sys, os, threading, time, webbrowser, subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer

import server

PORT = int(os.environ.get('PORT', '8765'))


def _create_desktop_shortcut():
    """Create a Desktop shortcut on first run (Windows only, silent on failure)."""
    try:
        if sys.platform != 'win32':
            return

        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders')
            desktop = Path(winreg.QueryValueEx(key, 'Desktop')[0])
            winreg.CloseKey(key)
        except Exception:
            desktop = Path.home() / 'Desktop'

        shortcut = desktop / 'Clip Review.lnk'
        if shortcut.exists():
            return

        exe = Path(sys.executable)  # the .exe itself — icon is embedded inside it

        # PowerShell is more reliable than cscript on modern Windows
        ps = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$sc = $ws.CreateShortcut("{shortcut}"); '
            f'$sc.TargetPath = "{exe}"; '
            f'$sc.WorkingDirectory = "{exe.parent}"; '
            f'$sc.IconLocation = "{exe},0"; '
            f'$sc.Description = "Clip Review"; '
            f'$sc.Save()'
        )
        subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive',
             '-WindowStyle', 'Hidden', '-Command', ps],
            timeout=15,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except Exception:
        pass


def _open_browser():
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{PORT}')


if __name__ == '__main__':
    threading.Thread(target=_create_desktop_shortcut, daemon=True).start()
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        ThreadingHTTPServer(('127.0.0.1', PORT), server.Handler).serve_forever()
    except KeyboardInterrupt:
        pass
