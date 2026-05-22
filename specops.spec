# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

datas = [
    ('index.html',        '.'),
    ('spec-ops-logo.png', '.'),
    ('spec-ops-logo.ico', '.'),
]
datas += collect_data_files('imageio_ffmpeg')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=collect_dynamic_libs('imageio_ffmpeg'),
    datas=datas,
    hiddenimports=['imageio_ffmpeg'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'PIL', 'PyQt5', 'wx'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,       # bundled directly → single file
    a.zipfiles,
    a.datas,
    name='ClipReview',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    windowed=True,
    icon='spec-ops-logo.ico',
    onefile=True,
)

# macOS .app bundle (ignored on Windows)
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='ClipReview.app',
        icon=None,
        bundle_identifier='ai.build.specops.clipreview',
        info_plist={
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleName': 'ClipReview',
            'NSHighResolutionCapable': True,
        },
    )
