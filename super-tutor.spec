# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — 超级导师 Super-Tutor 桌面应用打包

使用方式:
    pyinstaller super-tutor.spec

产出:
    dist/super-tutor.exe  (单文件)
"""
import sys
from pathlib import Path

# ── 入口 ──
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # 模型文件外置（打包时通过 --add-data 包含）
        ('knowledge_base/models', 'knowledge_base/models'),
    ],
    hiddenimports=[
        'sentence_transformers',
        'sentence_transformers.models',
        'chromadb',
        'chromadb.db',
        'docling',
        'docling.document_converter',
        'pydantic_settings',
        'jieba',
        'rank_bm25',
        'loguru',
        'PIL',
        'PIL.Image',
        'pymupdf',
        'fitz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy.random._examples',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ── 过滤不必要的二进制 ──
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ── 单文件 exe ──
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='super-tutor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 无控制台窗口（桌面应用）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # 可后续添加 .ico 图标
)
