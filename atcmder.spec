# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

def collect_resources():
    data_files = []
    resource_dir = 'resources'
    if os.path.exists(resource_dir):
        for fname in os.listdir(resource_dir):
            full_path = os.path.join(resource_dir, fname)
            if os.path.isfile(full_path):
                data_files.append((full_path, resource_dir))
    return data_files

def get_resources(resource_file):
    if hasattr(sys, '_MEIPASS'):
        path = os.path.join(sys._MEIPASS, "resources", resource_file)
    else:
        path = os.path.join("resources", resource_file)
    return path

if sys.platform == "win32":
    icon_file = "resources/app_icon.ico"
elif sys.platform == "darwin":
    icon_file = "resources/app_icon.icns"
else:
    icon_file = "resources/app_icon.png"


binaries = []
hiddenimports = ['serial_terminal', 'utils']
tmp_ret = collect_all('serial')
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ['atcmder.py'],
    pathex=['.'],
    binaries=binaries,
    datas=collect_resources() + [('serial_terminal.py', '.'), ('utils.py', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)


if sys.platform.startswith('darwin'):
    app = BUNDLE(
        EXE(
            pyz,
            a.scripts,
            a.binaries,
            a.datas,
            [],
            name='atcmder',
            debug=False,
            bootloader_ignore_signals=False,
            strip=False,
            upx=True,
            upx_exclude=[],
            runtime_tmpdir=None,
            console=False,
            windowed=True,
            icon=icon_file,
            disable_windowed_traceback=False,
            argv_emulation=False,
            target_arch=None,
            codesign_identity=None,
            entitlements_file=None,
        ),
        name='atcmder.app',
        icon=icon_file,
        bundle_identifier=None
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='atcmder',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        windowed=True,
        icon=icon_file,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )