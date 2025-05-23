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

binaries = []
hiddenimports = []
tmp_ret = collect_all('serial')
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ['atcmder.py'],
    pathex=[],
    binaries=binaries,
    datas=collect_resources(),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

app = BUNDLE(
    EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='atcmder',
        debug=True,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,  # 콘솔창 숨김
        windowed=True,  # .app 번들 생성
        icon='app_icon.icns',  # .icns 아이콘 파일 사용 권장
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    ),
    name='atcmder.app',
    icon='./resources/app_icon.icns',  # .icns 아이콘 파일 사용 권장
    bundle_identifier=None
)