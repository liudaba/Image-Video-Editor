# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('config.json', '.'), ('LICENSE', '.')]
# ECDSA公钥文件（如果存在则包含）
import os as _os
if _os.path.exists('.license_verify_pubkey.pem'):
    datas.append(('.license_verify_pubkey.pem', '.'))
if _os.path.exists('config.json.sig'):
    datas.append(('config.json.sig', '.'))
binaries = []
hiddenimports = ['whisper', 'moviepy', 'torch', 'torchaudio', 'numpy', 'PIL', 'requests', 'tkinter', 'cryptography', 'cryptography.fernet', 'cryptography.hazmat.primitives.serialization', 'cryptography.hazmat.primitives.asymmetric.ec', 'cryptography.hazmat.primitives.hashes', 'psutil', 'GPUtil', 'moviepy.video.io.ffmpeg_tools', 'moviepy.video.VideoClip', 'moviepy.video.compositing.CompositeVideoClip', 'moviepy.audio.AudioClip', 'moviepy.audio.io.AudioFileClip', 'moviepy.video.io.VideoFileClip', 'moviepy.editor', 'tiktoken', 'numba', 'llvmlite', 'regex', 'pydub', 'imageio', 'imageio_ffmpeg', 'proglog', 'tqdm']
hiddenimports += collect_submodules('moviepy')
hiddenimports += collect_submodules('torchaudio')
hiddenimports += collect_submodules('tiktoken')
hiddenimports += collect_submodules('numba')
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
    excludes=['test', 'tests', 'unittest', 'setuptools', 'pip', 'easy_install', 'pkg_resources', 'PyQt5', 'PyQt6', 'matplotlib', 'scipy', 'notebook', 'IPython', 'jupyter', 'tornado', 'fastapi', 'uvicorn', 'sqlalchemy', 'alembic', 'redis', 'asyncpg', 'aiosqlite', 'paramiko', 'bcrypt', 'passlib', 'python_jose', 'python_multipart', 'jose', 'httpx', 'websockets', 'starlette', 'anyio', 'httptools', 'pydantic', 'uvloop', 'sympy', 'networkx'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoGenerator',
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
    name='VideoGenerator',
)
