# -*- mode: python ; coding: utf-8 -*-
"""
VideoGenerator PyInstaller Spec - 唯一打包配置源

所有 hiddenimports / datas / binaries / excludes 均在此文件定义，
01build_exe.py 不再通过命令行参数覆盖这些配置。
"""
import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_all

# ── 项目根目录 ──
BASE_DIR = os.path.abspath('.')

# ── 1. 数据文件 ──
datas = [
    ('config.json', '.'),
    ('.license_verify_pubkey.pem', '.'),
]

# config.json 签名（如存在）
if os.path.exists(os.path.join(BASE_DIR, 'config.json.sig')):
    datas.append(('config.json.sig', '.'))

# LICENSE
if os.path.exists(os.path.join(BASE_DIR, 'LICENSE')):
    datas.append(('LICENSE', '.'))

# PyArmor 运行时（如存在）
_pyarmor_dir = os.path.join(BASE_DIR, 'pyarmor_runtime_000000')
if os.path.isdir(_pyarmor_dir):
    datas.append((os.path.join(_pyarmor_dir, '__init__.py'), 'pyarmor_runtime_000000'))
    for _f in os.listdir(_pyarmor_dir):
        if _f.endswith('.pyd'):
            # pyd 文件放到 binaries
            pass

# ── 2. 二进制文件 ──
binaries = []
if os.path.isdir(_pyarmor_dir):
    for _f in os.listdir(_pyarmor_dir):
        if _f.endswith('.pyd'):
            binaries.append((os.path.join(_pyarmor_dir, _f), 'pyarmor_runtime_000000'))

# ── 3. 隐式导入 ──
hiddenimports = [
    # 第三方库
    'whisper', 'moviepy', 'torch', 'torchaudio', 'numpy', 'PIL', 'requests',
    'tkinter', 'cryptography', 'cryptography.fernet',
    'cryptography.hazmat.primitives.serialization',
    'cryptography.hazmat.primitives.asymmetric.ec',
    'cryptography.hazmat.primitives.hashes',
    'psutil', 'GPUtil',
    'moviepy.video.io.ffmpeg_tools', 'moviepy.video.VideoClip',
    'moviepy.video.compositing.CompositeVideoClip', 'moviepy.audio.AudioClip',
    'moviepy.audio.io.AudioFileClip', 'moviepy.video.io.VideoFileClip',
    'moviepy.editor',
    'tiktoken', 'numba', 'llvmlite', 'regex', 'pydub',
    'imageio', 'imageio_ffmpeg', 'proglog', 'tqdm', 'unittest',
    # PyArmor 运行时
    'pyarmor_runtime_000000',
]

# 自动收集 video_generator 包的所有子模块
_vg_dir = os.path.join(BASE_DIR, 'video_generator')
for _root, _dirs, _files in os.walk(_vg_dir):
    _dirs[:] = [d for d in _dirs if d != '__pycache__']
    for _f in _files:
        if _f.endswith('.py'):
            _rel = os.path.relpath(os.path.join(_root, _f), BASE_DIR)
            _mod = _rel.replace(os.sep, '.').replace('.py', '')
            hiddenimports.append(_mod)

# 收集子包
hiddenimports += collect_submodules('torchaudio')
hiddenimports += collect_submodules('tiktoken')
hiddenimports += collect_submodules('numba')

# collect_all 会同时收集 datas + binaries + hiddenimports
for _pkg in ['whisper', 'moviepy', 'imageio', 'imageio_ffmpeg', 'proglog', 'dotenv']:
    _ret = collect_all(_pkg)
    datas += _ret[0]
    binaries += _ret[1]
    hiddenimports += _ret[2]

# ── 4. 排除模块 ──
excludes = [
    'test', 'tests', 'setuptools', 'pip', 'easy_install', 'pkg_resources',
    'PyQt5', 'PyQt6', 'matplotlib', 'scipy', 'notebook', 'IPython',
    'jupyter', 'tornado', 'fastapi', 'uvicorn', 'sqlalchemy', 'alembic',
    'redis', 'asyncpg', 'aiosqlite', 'paramiko', 'bcrypt', 'passlib',
    'python_jose', 'python_multipart', 'jose', 'httpx', 'websockets',
    'starlette', 'anyio', 'httptools', 'pydantic', 'uvloop', 'sympy',
    'networkx',
]

# ── 5. Analysis ──
a = Analysis(
    ['run.py'],
    pathex=[BASE_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
