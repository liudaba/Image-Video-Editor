# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('video_generator', 'video_generator'), ('config.json', '.'), ('启动.vbs', '.'), ('start.bat', '.'), ('README.md', '.'), ('快速上手指南.md', '.'), ('LICENSE', '.')]
binaries = []
hiddenimports = ['whisper', 'moviepy', 'torch', 'numpy', 'PIL', 'requests', 'json', 'threading', 'subprocess', 'datetime', 'queue', 'logging', 'tkinter', 'cryptography']
hiddenimports += collect_submodules('moviepy')
tmp_ret = collect_all('whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['test', 'tests', 'unittest', 'setuptools', 'pip', 'easy_install', 'pkg_resources', 'PyQt5', '.git', '.idea', '.vscode', '.venv', '__pycache__', '.env', 'license.json', '.secret_key', '.license_sign_key', '.license_verify_key', '.key_salt', '*.pem', '*.db', 'backend', 'models', 'model_aware_patch', 'output_project', '垃圾桶', 'build', 'dist', 'docs'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='短视频生成器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='短视频生成器',
)
