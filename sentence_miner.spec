# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Spanish Sentence Miner GUI
This creates a standalone executable with a custom icon.

To build the EXE:
1. Save your custom icon as 'app_icon.ico' in the same folder as this file
2. Run: pyinstaller sentence_miner.spec
"""

block_cipher = None

a = Analysis(
    ['sentence_miner_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['googletrans', 'psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SpanishSentenceMiner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False for GUI app (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',  # Your custom icon file (must be .ico format)
)
