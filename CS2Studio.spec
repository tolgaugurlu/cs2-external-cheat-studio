# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from runpy import run_path
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)
release = run_path(str(Path(SPECPATH) / 'app_version.py'))
version_tuple = tuple(int(part) for part in release['APP_VERSION'].split('.')) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple),
    kids=[
        StringFileInfo([StringTable('040904b0', [
            StringStruct('CompanyName', 'tolgaugurlu'),
            StringStruct('FileDescription', release['APP_NAME']),
            StringStruct('FileVersion', release['APP_VERSION']),
            StringStruct('InternalName', release['APP_SLUG']),
            StringStruct('OriginalFilename', release['EXE_NAME'] + '.exe'),
            StringStruct('ProductName', release['APP_NAME']),
            StringStruct('ProductVersion', release['APP_VERSION']),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

a = Analysis(
    ['memory_bot.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pygame.surfarray', 'pygame.sndarray', 'pygame.mixer', 'pygame.midi'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=release['EXE_NAME'],
    version=version_info,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
