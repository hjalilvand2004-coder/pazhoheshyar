# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — ساخت نسخه اجرایی تک‌فایلی بدون نیاز به پایتون روی سیستم مقصد.
ساخت (داخل پوشه backend، روی سیستم هدف):
    pip install -r requirements-build.txt
    pyinstaller PazhoheshYar.spec
خروجی: dist/pazhoheshyar360-server (لینوکس/مک) یا dist/pazhoheshyar360-server.exe (ویندوز)
"""
import os

block_cipher = None

datas = [
    ('../frontend/dist', 'frontend_dist'),  # فرانت ساخته‌شده داخل بسته
]

hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'sqlalchemy.dialects.sqlite',
    'jwt',
    # آزمایشگاه شبیه‌سازی — واردات‌های داخل تابع هم دیده می‌شوند؛ این‌ها صریح شده‌اند
    'numpy',
    'scipy',
    'scipy.stats',
    'openpyxl',
    'sklearn',
    'sklearn.linear_model',
    'sklearn.tree',
    'sklearn.ensemble',
    'sklearn.naive_bayes',
    'sklearn.neighbors',
    'sklearn.cluster',
    'sklearn.decomposition',
    'sklearn.metrics',
    'sklearn.model_selection',
    'sklearn.preprocessing',
    'sklearn.utils._typedefs',
    'sklearn.utils._sorting',
    'sklearn.neighbors._partition_nodes',
]

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas'],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pazhoheshyar360-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # پنجره کنسول برای مشاهده لاگ سرور
    icon=None,
)
