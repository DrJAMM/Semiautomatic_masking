# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Semiautomatic_masking.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.')],
    hiddenimports=['matplotlib.backends.backend_macosx'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'IPython', 'PyQt5', 'PyQt6', 'PySide6', 'pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Semiautomatic_masking',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Semiautomatic_masking',
)
app = BUNDLE(
    coll,
    name='Semiautomatic_masking.app',
    icon='icon.icns',
    bundle_identifier=None,
)
