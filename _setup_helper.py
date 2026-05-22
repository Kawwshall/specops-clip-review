"""Run by setup.bat — creates auto-start entry and desktop shortcut."""
import os, shutil, sys

app = os.path.dirname(os.path.abspath(__file__))
python = os.path.join(app, '.venv', 'Scripts', 'python.exe')
server = os.path.join(app, 'server.py')

# Silent launcher VBS (runs the server with no console window)
vbs = (
    'Dim oShell\n'
    'Set oShell = CreateObject("WScript.Shell")\n'
    f'oShell.Run Chr(34) & "{python}" & Chr(34) & " " & Chr(34) & "{server}" & Chr(34), 0, False\n'
)
vbs_path = os.path.join(app, 'start-hidden.vbs')
with open(vbs_path, 'w') as f:
    f.write(vbs)

# Copy VBS to Windows Startup folder
startup = os.path.join(
    os.environ.get('APPDATA', ''),
    'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
)
if os.path.isdir(startup):
    dest = os.path.join(startup, 'zedrec-viewer.vbs')
    shutil.copy(vbs_path, dest)
    print('  Auto-start on login: OK')
else:
    print('  WARNING: Could not find Startup folder — skipping auto-start')

# Desktop shortcut (.url opens the browser directly)
desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
if os.path.isdir(desktop):
    url_file = os.path.join(desktop, 'SPEC-OPS Clip Review.url')
    with open(url_file, 'w') as f:
        f.write('[InternetShortcut]\nURL=http://127.0.0.1:8765\n')
    print('  Desktop shortcut: OK')

print()
print('  Setup complete.')
print('  Server auto-starts on every Windows login.')
print('  Click "SPEC-OPS Clip Review" on Desktop to open.')
