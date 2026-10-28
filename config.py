# --- 1. СИСТЕМНЫЕ НАСТРОЙКИ ---
import os
import sys
import shutil


def get_base_path():
    if "TFALER_HOME" in os.environ:
        return os.environ["TFALER_HOME"]
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_path()
CONFIG_FILE = os.path.join(BASE_DIR, "ScalpSettings_Py.json")
SOUNDS_DIR = os.path.join(BASE_DIR, "Sounds")
SOUND_DIR_VOICE = os.path.join(SOUNDS_DIR, "Voice")
SOUND_DIR_TICK = os.path.join(SOUNDS_DIR, "Tick")
SOUND_DIR_TRANSITION = os.path.join(SOUNDS_DIR, "Transition")
LOGO_DIR = os.path.join(BASE_DIR, "Logo")
LOGO_PATH = os.path.join(LOGO_DIR, "Logo.png")


def _validate_paths():
    if not os.path.exists(LOGO_PATH):
        print(f"⚠️ Логотип не найден: {LOGO_PATH}")
        print(f"BASE_DIR: {BASE_DIR}")
        print(f"LOGO_DIR: {LOGO_DIR}")
        alt_logo = os.path.join(BASE_DIR, "..", "..", "Logo", "Logo.png")
        if os.path.exists(alt_logo):
            return os.path.abspath(alt_logo)
    return LOGO_PATH


LOGO_PATH = _validate_paths()

# --- 2. НАСТРОЙКИ ПРИЛОЖЕНИЯ ---
APP_NAME = "TF-Alerter"
APP_VERSION = "1.6"
WINDOW_SIZE = (360, 500)

# --- ИНФОРМАЦИЯ ОБ АВТОРЕ ---
AUTHOR_NAME = "intronaft"

# --- КРИПТОАДРЕСА ДЛЯ ДОНАТОВ ---
CRYPTO_ADDRESSES = {
    "BTC": {
        "label": "Bitcoin (BTC)",
        "network": "Bitcoin",
        "address": "bc1qrzyz9j44hj0ex9q33fhghwxhg2clysxyq0ps9f",
    },
    "ETH": {
        "label": "Ethereum (ETH)",
        "network": "ERC20",
        "address": "0x416E6544D8DCD9C4dDa2C10D394480F89642FaD7",
    },
    "BNB": {
        "label": "BNB (Binance Coin)",
        "network": "BEP20 (BSC)",
        "address": "0x416E6544D8DCD9C4dDa2C10D394480F89642FaD7",
    },
    "USDT_BEP20": {
        "label": "USDT",
        "network": "BEP20 (BNB Smart Chain)",
        "address": "0x416E6544D8DCD9C4dDa2C10D394480F89642FaD7",
    },
    "USDT_TRC20": {
        "label": "USDT",
        "network": "TRC20 (Tron)",
        "address": "TPuCWaaHgdCJEjhRp1wG1wQbWHgkd9Rpdq",
    },
    "USDT_ERC20": {
        "label": "USDT",
        "network": "ERC20 (Ethereum)",
        "address": "0x416E6544D8DCD9C4dDa2C10D394480F89642FaD7",
    },
}

# --- 3. ЦВЕТОВАЯ СХЕМА ---
COLORS = {
    "background": "#121212",
    "panel": "#1e1e1e",
    "text": "#e0e0e0",
    "accent": "#1e90ff",
    "danger": "#e81123",
    "danger_hover": "#f1707a",
    "border": "#333333",
    "hover": "#3e3e42",
}

# --- 4. НАСТРОЙКИ ТАЙМЕРА И ЗВУКА ---
VOICE_LEAD_TIME = 10
SOUND_TICK = "tick.wav"
SOUND_TICK_LONG = "transition.wav"


def get_sound_dir(kind: str) -> str:
    if kind in ("main", "voice"):
        return SOUND_DIR_VOICE
    if kind == "tick":
        return SOUND_DIR_TICK
    if kind == "transition":
        return SOUND_DIR_TRANSITION
    return SOUNDS_DIR


def get_sound_path(kind: str, filename: str) -> str:
    if not filename:
        return ""
    preferred = os.path.join(get_sound_dir(kind), filename)
    if os.path.exists(preferred):
        return preferred
    fallback = os.path.join(SOUNDS_DIR, filename)
    return fallback


def _ensure_sound_dirs():
    for path in (SOUNDS_DIR, SOUND_DIR_VOICE, SOUND_DIR_TICK, SOUND_DIR_TRANSITION):
        os.makedirs(path, exist_ok=True)


def _migrate_sound_file(kind: str, filename: str):
    if not filename:
        return
    src = os.path.join(SOUNDS_DIR, filename)
    dst = os.path.join(get_sound_dir(kind), filename)
    if not os.path.exists(src):
        return
    if os.path.exists(dst):
        return
    try:
        shutil.move(src, dst)
    except Exception:
        pass


def migrate_sounds_to_subdirs():
    _ensure_sound_dirs()
    items = set()
    for data in TIMEFRAMES.values():
        items.add(("main", data.get("file")))
    for filename in SOUND_TICK_BY_TF.values():
        items.add(("tick", filename))
    for filename in SOUND_TRANSITION_BY_TF.values():
        items.add(("transition", filename))
    items.add(("tick", SOUND_TICK))
    items.add(("transition", SOUND_TICK_LONG))
    for kind, filename in items:
        _migrate_sound_file(kind, filename)


TIMEFRAMES = {
    "1m": {"file": "1m_voice.wav", "seconds": 60, "label": "1 Минута"},
    "5m": {"file": "5m_voice.wav", "seconds": 300, "label": "5 Минут"},
    "15m": {"file": "15m_voice.wav", "seconds": 900, "label": "15 Минут"},
    "1h": {"file": "1h_voice.wav", "seconds": 3600, "label": "1 Час"},
    "4h": {"file": "4h_voice.wav", "seconds": 14400, "label": "4 Часа"},
    "1d": {"file": "1d_voice.wav", "seconds": 86400, "label": "1 День"},
    "1w": {"file": "1w_voice.wav", "seconds": 604800, "label": "1 Неделя"},
    "1M": {"file": "1Mo_voice.wav", "seconds": 2592000, "label": "1 Месяц"},
}

TIMEFRAME_LABELS = {
    "RU": {
        "1m": "1 Минута",
        "5m": "5 Минут",
        "15m": "15 Минут",
        "1h": "1 Час",
        "4h": "4 Часа",
        "1d": "1 День",
        "1w": "1 Неделя",
        "1M": "1 Месяц",
    },
    "EN": {
        "1m": "1 Minute",
        "5m": "5 Minutes",
        "15m": "15 Minutes",
        "1h": "1 Hour",
        "4h": "4 Hours",
        "1d": "1 Day",
        "1w": "1 Week",
        "1M": "1 Month",
    },
}


def get_timeframe_label(tf_key, lang="RU"):
    return TIMEFRAME_LABELS.get(lang, {}).get(tf_key, TIMEFRAMES[tf_key]["label"])


for tf_key in TIMEFRAMES.keys():
    if tf_key == "1M":
        TIMEFRAMES[tf_key]["file"] = "1Mo_voice.wav"
    else:
        TIMEFRAMES[tf_key]["file"] = f"{tf_key}_voice.wav"

SOUND_TICK_BY_TF = {}
for tf_key in TIMEFRAMES.keys():
    if tf_key == "1M":
        SOUND_TICK_BY_TF[tf_key] = "1Mo_tick.wav"
    else:
        SOUND_TICK_BY_TF[tf_key] = f"{tf_key}_tick.wav"

SOUND_TRANSITION_BY_TF = {}
for tf_key in TIMEFRAMES.keys():
    if tf_key == "1M":
        SOUND_TRANSITION_BY_TF[tf_key] = "1Mo_transition.wav"
    else:
        SOUND_TRANSITION_BY_TF[tf_key] = f"{tf_key}_transition.wav"

OVERLAY_SHOW_MODE = "custom"
OVERLAY_WINDOWS = ["Profit Forge", "TF-Alerter"]
