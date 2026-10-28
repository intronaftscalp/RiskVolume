# -*- mode: python ; coding: utf-8 -*-

import json
import os
import sys


_SPEC_PATH = globals().get('__file__', os.path.join(os.getcwd(), 'RiskVolume.spec'))
_ROOT = os.path.dirname(os.path.abspath(_SPEC_PATH))
sys.path.insert(0, _ROOT)
from calibration_state import CALIBRATION_RESET_VERSION, reset_terminal_calibration_state


_SRC_SETTINGS = os.path.join(_ROOT, 'ScalpSettings_Py.json')
_SANITIZED_SETTINGS = os.path.join(_ROOT, 'build', 'ScalpSettings_Py.json')


def _build_sanitized_settings(src_path, dst_path):
    try:
        with open(src_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}

    if not isinstance(data, dict):
        data = {}

    credentials = data.get('auto_dep_credentials', {})
    if isinstance(credentials, dict):
        for exchange_id, exchange_credentials in credentials.items():
            if isinstance(exchange_credentials, dict):
                exchange_credentials['api_key'] = ''
                exchange_credentials['api_secret'] = ''
                exchange_credentials['api_passphrase'] = ''
    data['auto_dep_credentials'] = credentials
    data['auto_dep_api_key'] = ''
    data['auto_dep_api_secret'] = ''
    data['auto_dep_api_passphrase'] = ''
    data['auto_dep_enabled'] = False
    data['auto_dep_connected'] = False
    data['auto_dep_connected_exchange'] = ''
    data['auto_dep_connected_market'] = ''
    reset_terminal_calibration_state(
        data,
        expected_version=CALIBRATION_RESET_VERSION,
    )

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


_build_sanitized_settings(_SRC_SETTINGS, _SANITIZED_SETTINGS)


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('Logo', 'Logo'),
        (_SANITIZED_SETTINGS, '.'),
    ],
    hiddenimports=[
        'keyboard',
        'pyautogui',
        'pyperclip',
        'qrcode',
        'PIL',
        'mouseinfo',
        'pyscreeze',
        'pygetwindow',
        'pymsgbox',
        'pytweening',
        'pyrect',
        'ccxt',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RiskVolume',
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
    version='file_version_info.txt',
    icon=['Logo\\Logo.png'],
    contents_directory='internal',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RiskVolume',
)
