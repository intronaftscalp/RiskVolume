import ctypes
from ctypes import wintypes
import os
import sys

# Early console hide for Windows: run before heavy imports to avoid startup flash.
if sys.platform == "win32":
    try:
        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)  # SW_HIDE
    except Exception:
        pass

# Setup logging to debug file before any heavy operations
import logging
_log_file = os.path.join(os.path.dirname(__file__), "rv_debug.log")
logging.basicConfig(
    filename=_log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)
logging.debug("Application startup begin")

import json
import time
import hmac
import hashlib
import subprocess
import requests
import pyperclip
import threading
import importlib
from urllib.parse import urlencode
import config
from auto_deposit import build_ccxt_balance_request_variants
from PyQt6.QtWidgets import (
    QApplication,
    QStyleFactory,
    QMainWindow,
    QDialog,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QTabWidget,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import (
    Qt,
    QPoint,
    QRegularExpression,
    QTimer,
    QEasingCurve,
    QVariantAnimation,
    pyqtSignal,
    QObject,
    QSharedMemory,
)
from PyQt6.QtGui import (
    QIcon,
    QRegularExpressionValidator,
    QColor,
    QBrush,
    QPalette,
    QPixmap,
    QPainter,
    QPen,
    QCursor,
)

from config import *
from settings_dialog import SettingsDialog
from logic import calculate_risk_data, calculate_position_adjustment, get_info_html
from translations import TRANS
from calculator_tab import init_calculator_tab
from cascade_tab import CascadeTab
from secure_credentials import protect_secret, unprotect_secret
from calibration_state import reset_terminal_calibration_state, CALIBRATION_RESET_MARKER_KEY

try:
    myappid = "riskvolume.app"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """Глобальный обработчик исключений — не даёт приложению упасть тихо."""
    import traceback

    try:
        traceback.print_exception(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _thread_exception_handler(args):
    """Обработчик исключений в потоках (keyboard хуки и т.д.)."""
    import traceback

    try:
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    except Exception:
        pass


sys.excepthook = _global_exception_handler
threading.excepthook = _thread_exception_handler

_app_shared_memory_guard = None
keyboard = None
pyautogui = None


def _configure_windows_multiprocessing_executable():
    """Disabled: multiprocessing setup on Windows causes phantom windows at startup."""
    pass


def _hide_console_window_on_windows():
    """Hide/detach console window for GUI startup to avoid transient black console flashes."""
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            # SW_HIDE = 0
            user32.ShowWindow(hwnd, 0)
            try:
                kernel32.FreeConsole()
            except Exception:
                pass
    except Exception:
        pass


def _relaunch_with_pythonw_if_needed():
    """When running from source on Windows, relaunch via pythonw to avoid console flashes."""
    if sys.platform != "win32":
        return
    if getattr(sys, "frozen", False):
        return
    if os.environ.get("RV_PYTHONW_RELAUNCHED", "") == "1":
        return
    try:
        current_exe = os.path.basename(sys.executable or "").lower()
        if current_exe == "pythonw.exe":
            return

        exe_dir = os.path.dirname(sys.executable or "")
        pythonw_path = os.path.join(exe_dir, "pythonw.exe")
        if not os.path.exists(pythonw_path):
            return

        entry_script = os.path.abspath(sys.argv[0])
        env = dict(os.environ)
        env["RV_PYTHONW_RELAUNCHED"] = "1"

        # CREATE_NO_WINDOW keeps bootstrap launch silent while pythonw takes over.
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            [pythonw_path, entry_script, *sys.argv[1:]],
            cwd=os.getcwd(),
            env=env,
            close_fds=True,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=_hidden_subprocess_startupinfo(),
        )
        sys.exit(0)
    except Exception:
        # If relaunch fails, continue normal startup.
        return


def _hidden_subprocess_startupinfo():
    if sys.platform != "win32":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


def _binance_response_json(response):
    try:
        data = response.json()
    except ValueError:
        data = None

    try:
        response.raise_for_status()
    except requests.HTTPError:
        if isinstance(data, dict) and data.get("msg"):
            code = data.get("code")
            raise RuntimeError(f"Binance API error {code}: {data['msg']}") from None
        raise RuntimeError(
            f"Binance API returned HTTP {response.status_code}"
        ) from None

    if (
        isinstance(data, dict)
        and data.get("code") not in (None, 0, "0")
        and data.get("msg")
    ):
        raise RuntimeError(f"Binance API error {data['code']}: {data['msg']}")
    return data


def _binance_server_timestamp_ms(base_url, time_path, timeout=4):
    request_started = time.time() * 1000
    response = requests.get(f"{base_url}{time_path}", timeout=timeout)
    data = _binance_response_json(response)
    request_finished = time.time() * 1000
    if not isinstance(data, dict) or data.get("serverTime") is None:
        raise RuntimeError("Binance server-time response is missing serverTime")
    try:
        server_time = float(data["serverTime"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Binance returned an invalid serverTime") from exc

    return int(server_time + (request_finished - request_started) / 2)


def _bybit_server_timestamp_ms(timeout=4):
    request_started = time.time() * 1000
    response = requests.get("https://api.bybit.com/v5/market/time", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    request_finished = time.time() * 1000
    if not isinstance(data, dict) or int(data.get("retCode", -1)) != 0:
        message = (
            data.get("retMsg", "Invalid server-time response")
            if isinstance(data, dict)
            else "Invalid server-time response"
        )
        raise RuntimeError(f"Bybit: {message}")

    server_time = data.get("time")
    if server_time is None:
        result = data.get("result", {})
        time_nano = result.get("timeNano") if isinstance(result, dict) else None
        if time_nano is not None:
            server_time = float(time_nano) / 1_000_000
    try:
        server_time = float(server_time)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Bybit: server-time response is missing a valid time") from exc

    return int(server_time + (request_finished - request_started) / 2)


def _fetch_balance_with_ccxt(payload):
    try:
        ccxt = importlib.import_module("ccxt")
    except Exception as exc:
        raise RuntimeError(f"Failed to import ccxt: {exc}")

    exchange_id = str(payload.get("exchange_id", "") or "").strip().lower()
    api_key = str(payload.get("api_key", "") or "").strip()
    api_secret = str(payload.get("api_secret", "") or "").strip()
    market_type = str(payload.get("market_type", "spot") or "spot").strip().lower()
    asset = str(payload.get("asset", "USDT") or "USDT").strip().upper()
    passphrase = str(payload.get("passphrase", "") or "").strip()

    ex_class = getattr(ccxt, exchange_id, None)
    if ex_class is None:
        raise RuntimeError(f"Unsupported exchange: {exchange_id}")

    variants = build_ccxt_balance_request_variants(
        exchange_id=exchange_id,
        market_type=market_type,
        api_key=api_key,
        api_secret=api_secret,
        asset=asset,
        passphrase=passphrase,
    )

    last_error = None
    for variant in variants:
        try:
            auth = dict(variant.get("auth", {}))
            params = {
                "apiKey": auth.get("apiKey", api_key),
                "secret": auth.get("secret", api_secret),
                "enableRateLimit": True,
                "timeout": 3000,
            }
            params.update({k: v for k, v in auth.items() if k not in {"apiKey", "secret"}})
            if passphrase:
                params["password"] = passphrase

            exchange = ex_class(params)
            try:
                balance = exchange.fetch_balance(variant.get("params", {}))
            finally:
                try:
                    exchange.close()
                except Exception:
                    pass

            total = balance.get("total", {}) if isinstance(balance, dict) else {}
            free = balance.get("free", {}) if isinstance(balance, dict) else {}
            used = balance.get("used", {}) if isinstance(balance, dict) else {}

            free_val = float(free.get(asset, 0.0) or 0.0)
            used_val = float(used.get(asset, 0.0) or 0.0)

            if market_type == "futures":
                equity = _extract_cross_margin_equity(
                    exchange_id, balance, asset
                )
                if equity is not None:
                    return equity
                raise RuntimeError(
                    f"{exchange_id}: realized wallet balance is missing; "
                    "refusing a value that may include unrealized PnL"
                )

            if asset in total and total[asset] is not None:
                return float(total[asset])

            return free_val + used_val
        except Exception as exc:
            last_error = str(exc)

    raise RuntimeError(last_error or "Balance fetch failed")


def _extract_cross_margin_equity(exchange_id, balance, asset):
    """Return futures wallet balance without unrealized PnL from CCXT data."""
    if not isinstance(balance, dict):
        return None

    info = balance.get("info")
    exchange_id = str(exchange_id or "").lower()
    wallet_fields = {
        "bybit": ("totalWalletBalance", "walletBalance"),
        "binance": (
            "totalCrossWalletBalance",
            "totalWalletBalance",
            "crossWalletBalance",
            "walletBalance",
        ),
        "okx": ("cashBal",),
        "bitget": ("balance", "walletBalance"),
        "gate": ("total", "walletBalance"),
        "mexc": ("walletBalance", "balance"),
        "kucoin": (
            "accountEquityWithoutUnrealisedPNL",
            "walletBalance",
            "balance",
        ),
    }.get(
        exchange_id,
        ("walletBalance", "wallet_balance", "cashBal", "cash_balance", "balance"),
    )
    equity_fields = {
        "bybit": ("totalEquity", "totalMarginBalance"),
        "binance": ("totalMarginBalance",),
        "okx": ("totalEq", "eq", "equity"),
        "bitget": ("accountEquity", "equity"),
        "gate": ("equity",),
        "mexc": ("equity",),
        "kucoin": ("accountEquity", "marginBalance"),
    }.get(exchange_id, ("equity", "totalEquity", "marginBalance"))
    unrealized_fields = (
        "totalUnrealizedProfit",
        "totalPerpUPL",
        "crossUnPnl",
        "unrealizedPnl",
        "unrealisedPnl",
        "unrealizedPL",
        "unrealisedPNL",
        "unrealized_pnl",
        "upl",
    )

    def parse_number(value):
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def parse_amount(value):
        parsed = parse_number(value)
        return parsed if parsed is not None and parsed >= 0 else None

    def find_value(value, keys):
        if isinstance(value, dict):
            for key in keys:
                parsed = parse_amount(value.get(key))
                if parsed is not None:
                    return parsed
            for nested in value.values():
                found = find_value(nested, keys)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = find_value(nested, keys)
                if found is not None:
                    return found
        return None

    wallet_balance = find_value(info, wallet_fields)
    if wallet_balance is not None:
        return wallet_balance

    def find_realized_equity(value):
        if isinstance(value, dict):
            equity = next(
                (
                    parsed
                    for key in equity_fields
                    if (parsed := parse_amount(value.get(key))) is not None
                ),
                None,
            )
            unrealized = next(
                (
                    parsed
                    for key in unrealized_fields
                    if (parsed := parse_number(value.get(key))) is not None
                ),
                None,
            )
            if equity is not None and unrealized is not None:
                return max(0.0, equity - unrealized)
            for nested in value.values():
                found = find_realized_equity(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = find_realized_equity(nested)
                if found is not None:
                    return found
        return None

    adjusted_equity = find_realized_equity(info)
    if adjusted_equity is not None:
        return adjusted_equity

    # Unknown exchange responses have no exchange-specific field mapping;
    # CCXT's normalized total is retained only for that compatibility case.
    if exchange_id not in {
        "bybit",
        "binance",
        "okx",
        "bitget",
        "gate",
        "mexc",
        "kucoin",
    }:
        total = balance.get("total", {})
        if isinstance(total, dict):
            parsed_total = parse_amount(total.get(asset))
            if parsed_total is not None:
                return parsed_total
    return None


def _fetch_balance_with_ccxt_process(payload, result_queue):
    """Legacy: no longer used. Thread-based approach is in _fetch_non_binance_balance_light."""
    pass


def _force_consistent_qt_theme(app: QApplication):
    """Фиксирует единый тёмный вид на разных ПК/версиях Windows."""
    try:
        fusion_style = QStyleFactory.create("Fusion")
        if fusion_style is not None:
            app.setStyle(fusion_style)
    except Exception:
        pass

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#121212"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E0E0E0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#121212"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1A1A1A"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#E0E0E0"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#E0E0E0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#252525"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#E0E0E0"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#38BE1D"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
    app.setPalette(palette)


class HotkeySignaler(QObject):
    toggle_sig = pyqtSignal()
    calibrate_sig = pyqtSignal()
    apply_sig = pyqtSignal()  # Новый сигнал для применения


class AutoDepositSignaler(QObject):
    fetch_finished = pyqtSignal(object, object)


class CellsLabelDarkDelegate(QStyledItemDelegate):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app

    def paint(self, painter, option, index):
        if index.column() == 0:
            try:
                selected_rows = set(self.app._get_active_rows_for_table())
            except Exception:
                selected_rows = set()

            if index.row() not in selected_rows:
                bg = QColor("#000000")
                fg = QColor("#161616")
                painter.save()
                painter.fillRect(option.rect, bg)
                painter.setPen(fg)
                text = index.data(Qt.ItemDataRole.DisplayRole)
                if text:
                    painter.drawText(
                        option.rect, Qt.AlignmentFlag.AlignCenter, str(text)
                    )
                painter.restore()
                return

        super().paint(painter, option, index)


class GlassPreviewFrame(QWidget):
    """Overlay window that draws a highlighted rectangle over a calibrated glass area."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._border_color = QColor(56, 190, 29, 230)
        self._fill_color = QColor(56, 190, 29, 30)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.fillRect(rect, self._fill_color)
        pen = QPen(self._border_color)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 6, 6)


class RiskVolumeApp(QMainWindow):
    def __init__(self):
        logging.debug("RiskVolumeApp.__init__ START")
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        logging.debug("QMainWindow.__init__ done")
        self._startup_reveal_done = False
        self.base_scale = 100
        logging.debug("About to load_settings")
        self.load_settings()
        logging.debug("load_settings done")
        self._create_posmode_checkmark_icon()
        logging.debug("checkmark icon created")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        try:
            self.setWindowOpacity(0.0)
        except Exception:
            pass

        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))

        self._hotkey_bindings = {}
        self._windows_hotkey_actions = {}
        # Флаг, чтобы отправка не запускалась дважды одновременно (Enter + горячая клавиша)
        self.apply_running = False
        self.signaler = HotkeySignaler()
        self.signaler.toggle_sig.connect(self.toggle_window)
        self.signaler.calibrate_sig.connect(self.handle_hotkey_calibration)
        self.signaler.apply_sig.connect(
            self.handle_hotkey_apply
        )  # Единая точка входа для горячей клавиши
        self._auto_dep_signaler = AutoDepositSignaler()
        self._auto_dep_signaler.fetch_finished.connect(self._on_auto_dep_fetch_finished)

        self.old_pos = None
        self._startup_window_size = None
        self._lock_dynamic_resize = False
        self._window_size_anim = None
        self._window_size_anim_target = None
        self._resize_len_baseline = {}
        self._resize_step_chars = 5
        self._last_applied_resize_pressure = 0
        self._force_resize_pending = False
        self._suppress_content_resize_until = 0.0
        self.current_vol = 0.0
        self.position_target_volume = 0.0
        self.table_volume_override = float(
            self.settings.get("pos_table_volume_override", 0.0) or 0.0
        )
        # Restore selected transfer rows using mode-aware key (pos-mode vs normal)
        try:
            raw_selected = self.settings.get(self._selected_rows_setting_key(), None)
        except Exception:
            raw_selected = None
        if raw_selected is None:
            raw_selected = self.settings.get("selected_cells", [])
        self.selected_transfer_rows = set(
            int(i) for i in (raw_selected or []) if str(i).isdigit()
        )
        self.position_target_row_active = None
        self._cells_count_before_target_mode = None
        self._ghost_input = None
        self.calc_calibration_active = False
        self._hotkey_ids = {}
        self._cells_layout_reflow_pending = False
        self._api_read_only_check_cache = {}
        self._status_neutral_token = 0
        self._pf_preview_frames = []
        self._pf_preview_token = 0
        self._settings_dialog = None
        self._hotkeys_initialized = False
        self._startup_window_suppress_timer = None
        self._startup_window_suppress_deadline = 0.0

        self.init_ui()
        logging.debug("init_ui completed, setting up timers")
        self._calc_update_timer = QTimer(self)
        self._calc_update_timer.setSingleShot(True)
        self._calc_update_timer.timeout.connect(self.update_calc)
        self._min_order_live_timer = QTimer(self)
        self._min_order_live_timer.setSingleShot(True)
        self._min_order_live_timer.timeout.connect(self._apply_min_order_live)
        self._smooth_resize_idle_timer = QTimer(self)
        self._smooth_resize_idle_timer.setSingleShot(True)
        self._smooth_resize_idle_timer.timeout.connect(self._apply_idle_smooth_resize)
        self.update_calc()
        logging.debug("timers setup done")

        # Периодически перерегистрируем keyboard-хуки (Windows убивает их при простое/сне)
        self._hotkey_keepalive_timer = QTimer(self)
        self._hotkey_keepalive_timer.timeout.connect(self._keepalive_hotkeys)
        self._hotkey_keepalive_timer.start(30 * 1000)  # каждые 30 секунд
        QTimer.singleShot(1000, self._delayed_rebind_hotkeys)
        
        # ОТКЛЮЧЕНО: Инициализация keyboard модуля создаёт фоновые окна на Windows при старте.
        # Клавиши будут инициализированы лениво при первом использовании вместо этого.
        # self._hotkey_init_timer = QTimer(self)
        # self._hotkey_init_timer.setSingleShot(True)
        # self._hotkey_init_timer.timeout.connect(self._delayed_init_keyboard_module)
        # self._hotkey_init_timer.start(3500)
        logging.debug("RiskVolumeApp.__init__ COMPLETE")

        # Периодическая синхронизация депозита через API (если включено)
        self._auto_dep_sync_busy = False
        self._auto_dep_timer = QTimer(self)
        self._auto_dep_timer.setSingleShot(False)
        self._auto_dep_timer.timeout.connect(self._sync_deposit_from_exchange)
        # Запускаем автообновление после полной загрузки окна и настроек.
        QTimer.singleShot(1000, lambda: self._apply_auto_deposit_sync(force_now=True))

        # Сохраняем настройки при закрытии приложения любым способом
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._on_app_about_to_quit)

        # Восстанавливаем позицию окна
        pos = self.settings.get("window_pos", None)
        restored_anchor = None
        if pos and len(pos) == 2:
            try:
                self.move(int(pos[0]), int(pos[1]))
                restored_anchor = (int(pos[0]), int(pos[1]))
            except Exception:
                pass

        # Восстанавливаем размер окна, чтобы стартовая геометрия была одинаковой
        saved_size = self.settings.get("window_size", None)
        saved_size_scale = self.settings.get("window_size_scale", None)
        size_persist_v2 = bool(self.settings.get("window_size_v2", False))
        current_scale = int(self.settings.get("scale", self.base_scale) or self.base_scale)
        if (
            size_persist_v2
            and isinstance(saved_size, (list, tuple))
            and len(saved_size) == 2
            and str(saved_size_scale or "") == str(current_scale)
        ):
            try:
                saved_w = int(saved_size[0])
                saved_h = int(saved_size[1])
                fit_w, fit_h, fit_x, fit_y = self._fit_window_geometry_to_screen(
                    saved_w,
                    saved_h,
                    margin=6,
                    anchor_pos=restored_anchor,
                    prefer_active=True,
                )
                self.setFixedSize(int(fit_w), int(fit_h))
                if fit_x is not None and fit_y is not None:
                    self.move(int(fit_x), int(fit_y))
            except Exception:
                pass

        # Recompute geometry from current content after restore.
        # This prevents stale saved heights from keeping the window oversized.
        try:
            self._set_window_size_with_extra_height(grow_only=False)
        except Exception:
            pass

        self._ensure_window_on_screen(
            margin=6,
            anchor_pos=restored_anchor,
            prefer_active=True,
        )

    def _create_posmode_checkmark_icon(self):
        import tempfile

        path = os.path.join(tempfile.gettempdir(), "rv_posmode_checkmark_black.png")
        if not os.path.exists(path):
            pix = QPixmap(12, 12)
            pix.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pix)
            pen = QPen(QColor(0, 0, 0))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(2, 6, 5, 9)
            painter.drawLine(5, 9, 10, 3)
            painter.end()
            pix.save(path, "PNG")
        self._posmode_checkmark_path_css = path.replace("\\", "/")

    @staticmethod
    def _normalize_fee_settings(settings):
        if not isinstance(settings, dict):
            settings = {}

        def parse_float(value, fallback):
            try:
                return max(0.0, float(value))
            except Exception:
                return float(fallback)

        default_total = 0.1
        try:
            default_total = max(0.0, float(settings.get("fee_percent", 0.1) or 0.1))
        except Exception:
            default_total = 0.1

        fee_total = default_total
        fee_taker = parse_float(settings.get("fee_taker"), fee_total / 2.0)
        fee_maker = parse_float(settings.get("fee_maker"), fee_total / 2.0)

        if settings.get("fee_taker") is None and settings.get("fee_maker") is None:
            fee_taker = fee_total / 2.0
            fee_maker = fee_total / 2.0

        normalized = dict(settings)
        normalized["fee_taker"] = fee_taker
        normalized["fee_maker"] = fee_maker
        normalized["fee_percent"] = fee_taker + fee_maker
        return normalized

    def load_settings(self):
        default = {
            "deposit": 1000.0,
            "lang": "ru",
            "risk": 1.0,
            "stop": 1.0,
            "scale": 100,
            "hk_show": "f1",
            "hk_coords": "f2",
            "hk_send": "f3",
            "points": [],
            "prec_dep": 2,
            "prec_risk": 2,
            "prec_fee": 3,
            "prec_vol": 0,
            "prec_lev": 1,
            "prec_min_order": 0,
            "fee_percent": 0.1,
            "fee_taker": 0.05,
            "fee_maker": 0.05,
            "use_fee": True,
            "cas_p_gear": None,
            "cas_p_book": None,
            "cas_p_scrollbar": None,
            "cas_p_vol1": None,
            "cas_p_dist1": None,
            "cas_p_vol2": None,
            "cas_p_dist2": None,
            "cas_p_close_x": None,
            "cas_p_btn_add": None,
            "cas_p_btn_del": None,
            "cas_p_combo_vol": None,
            "cas_use_custom_vol": False,
            "cas_custom_total_vol": 100.0,
            "cas_use_custom_percent": False,
            "cas_custom_percent": 100.0,
            "cas_max_count_enabled": False,
            "cas_max_count": 0,
            "cas_type_index": 0,
            "cas_dist_step": 0.1,
            "cas_range_mode": False,
            "cas_range_width": 0.0,
            "cas_manual_k": 2.0,
            "last_cascade_count": 1,
            "scalp_cells_count": 4,
            "metascalp_cells_count": 5,
            "scalp_multipliers": [100, 50, 25, 10],
            "scalp_manual_multipliers": [100, 50, 25, 10, 0],
            "scalp_min_order": 6,
            "cells_reversed": False,
            "cells_reversed_pos": False,
            "pos_current_vol": "0",
            "pos_risk": "1",
            "pos_stop": "0",
            "pos_stop_now": "0",
            "pos_target_cell": 1,
            "pos_mode_enabled": False,
            "pos_table_volume_override": 0.0,
            "selected_cells": [0],
            "minimize_after_apply": True,
            "auto_dep_enabled": False,
            "auto_dep_exchange": "binance",
            "auto_dep_market": "futures",
            "auto_dep_asset": "USDT",
            "auto_dep_connected": False,
            "auto_dep_connected_exchange": "",
            "auto_dep_connected_market": "",
            "auto_dep_allow_unverified": False,
            "auto_apply_terminal": "metascalp",
            "calc_points_profit_forge": [],
            "calc_points_metascalp": [],
            "calc_points_tigertrade": [],
            "calc_points_surf": [],
            "surf_hover_cells_calibration_v1_applied": False,
            "calc_points_vataga": [],
            "pf_glasses_count": 1,
            "pf_glasses_points": {},
            "metascalp_glasses_points": {},
            "tiger_glasses_points": {},
            "tiger_glasses_open_points": {},
            "tiger_glasses_close_points": {},
            "surf_glasses_points": {},
            "surf_glasses_hover_points": {},
            "surf_glasses_open_points": {},
            "surf_glasses_accept_points": {},
            "vataga_glasses_points": {},
            "vataga_glasses_open_points": {},
            "pf_active_glass": 1,
            "pf_selected_glasses": [1],
            "pf_show_preview_frames": False,
            "tiger_open_point": None,
            "tiger_close_point": None,
            "surf_open_point": None,
            "surf_accept_point": None,
            "vataga_open_point": None,
            "auto_dep_api_key": "",
            "auto_dep_api_secret": "",
            "auto_dep_api_passphrase": "",
            "auto_dep_credentials": {},
            "window_size": None,
            "window_size_scale": None,
            "window_size_v2": False,
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.settings = json.load(f)
            except:
                self.settings = default
        else:
            self.settings = default
        for key, val in default.items():
            if key not in self.settings:
                self.settings[key] = val

        self.settings = self._normalize_fee_settings(self.settings)

        # Fresh builds should clear all old calibration points so the first launch
        # requires a single capture per terminal for all related modes.
        reset_changed = reset_terminal_calibration_state(self.settings)
        pf_settings_changed = self._normalize_pf_multi_glass_settings() or reset_changed

        # Migration: preserve existing calculator calibration points as Profit Forge points.
        if (
            not self.settings.get("calc_points_profit_forge")
            and isinstance(self.settings.get("points", None), list)
            and self.settings.get("points")
        ):
            self.settings["calc_points_profit_forge"] = list(self.settings.get("points", []))
            pf_settings_changed = self._normalize_pf_multi_glass_settings() or pf_settings_changed

        # One-time fix: clear legacy auto-copied points for non-PF terminals.
        # They could falsely complete calibration after 1-2 hotkey presses.
        non_pf_points_fix_changed = False
        if not bool(self.settings.get("non_pf_points_fix_v1_applied", False)):
            pf_points = self.settings.get("calc_points_profit_forge", [])
            if not isinstance(pf_points, list):
                pf_points = []

            for non_pf_key in [
                "calc_points_metascalp",
                "calc_points_surf",
                "calc_points_vataga",
            ]:
                pts = self.settings.get(non_pf_key, [])
                if isinstance(pts, list) and isinstance(pf_points, list) and pts == pf_points:
                    self.settings[non_pf_key] = []
                    non_pf_points_fix_changed = True

            self.settings["non_pf_points_fix_v1_applied"] = True
            non_pf_points_fix_changed = True

        # SURF now edits the five cells directly from the hover-expanded selector;
        # points captured from its former menu are no longer valid.
        surf_calibration_migration_changed = False
        if not bool(self.settings.get("surf_hover_cells_calibration_v1_applied", False)):
            self.settings["calc_points_surf"] = []
            self.settings["surf_glasses_points"] = {}
            self.settings["surf_glasses_open_points"] = {}
            self.settings["surf_glasses_accept_points"] = {}
            self.settings["surf_open_point"] = None
            self.settings["surf_accept_point"] = None
            self.settings["surf_hover_cells_calibration_v1_applied"] = True
            surf_calibration_migration_changed = True

        if (
            non_pf_points_fix_changed
            or pf_settings_changed
            or surf_calibration_migration_changed
        ):
            self.save_settings()

        self.settings["prec_min_order"] = 0

        if "fee_taker" not in self.settings or "fee_maker" not in self.settings:
            fee_total = float(self.settings.get("fee_percent", 0.1))
            self.settings["fee_taker"] = float(
                self.settings.get("fee_taker", fee_total / 2)
            )
            self.settings["fee_maker"] = float(
                self.settings.get("fee_maker", fee_total / 2)
            )
            self.settings["fee_percent"] = (
                self.settings["fee_taker"] + self.settings["fee_maker"]
            )
            self.save_settings()

        if self._migrate_auto_dep_credentials_secure_storage():
            self.save_settings()

        # Migration: old internal scale mapping was 130-170 for displayed 100-140.
        # Convert once to real values so scaling behaves predictably.
        raw_scale = self.settings.get("scale", self.base_scale)
        try:
            scale = int(raw_scale)
        except Exception:
            scale = self.base_scale

        migrated = False
        if not bool(self.settings.get("scale_mapping_v2", False)):
            legacy_to_real = {
                130: 100,
                140: 110,
                150: 120,
                160: 130,
                170: 140,
            }
            if scale in legacy_to_real:
                scale = legacy_to_real[scale]
                self.settings["scale"] = scale
                migrated = True
            self.settings["scale_mapping_v2"] = True
            migrated = True

        clamped_scale = max(60, min(120, scale))
        if self.settings.get("scale", None) != clamped_scale:
            self.settings["scale"] = clamped_scale
            self.save_settings()
        elif migrated:
            self.save_settings()

    def save_settings(self):
        # Only sync UI state if we're already initialized (tabs exist)
        if hasattr(self, "tabs"):
            self._sync_ui_state_to_settings()
        self.settings["auto_dep_api_key"] = ""
        self.settings["auto_dep_api_secret"] = ""
        self.settings["auto_dep_api_passphrase"] = ""
        if not isinstance(self.settings.get("auto_dep_credentials", {}), dict):
            self.settings["auto_dep_credentials"] = {}
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.settings, f)

    def _sync_ui_state_to_settings(self):
        """Синхронизирует состояние UI виджетов в settings перед сохранением."""
        if hasattr(self, "chk_pos_mode"):
            self.settings["pos_mode_enabled"] = bool(self.chk_pos_mode.isChecked())

        if hasattr(self, "chk_pf_show_frames"):
            self.settings["pf_show_preview_frames"] = bool(
                self.chk_pf_show_frames.isChecked()
            )

        if hasattr(self, "cb_pf_calib_glass"):
            try:
                active_glass = int(self.cb_pf_calib_glass.currentData() or 1)
            except Exception:
                active_glass = 1
            self.settings["pf_active_glass"] = active_glass
            self.settings[self._get_shared_active_points_key()] = self._get_pf_points_for_glass(
                active_glass
            )

        if hasattr(self, "_pf_target_checkboxes"):
            selected_glasses = [
                int(g)
                for g, cb in self._pf_target_checkboxes.items()
                if cb and cb.isChecked() and not bool(cb.property("uncalibrated"))
            ]
            self.settings["pf_selected_glasses"] = selected_glasses

        if hasattr(self, "chk_range_mode"):
            self.settings["cas_range_mode"] = bool(self.chk_range_mode.isChecked())

    def _secure_encrypt_field(self, value):
        value = str(value or "").strip()
        if not value:
            return ""
        return f"dpapi:{protect_secret(value)}"

    def _secure_decrypt_field(self, value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        if not raw.startswith("dpapi:"):
            return raw
        try:
            return unprotect_secret(raw[6:])
        except Exception:
            return ""

    def _normalize_auto_dep_credentials_shape(self, raw):
        if not isinstance(raw, dict):
            raw = {}
        result = {}
        for exchange_id in [
            "binance",
            "bybit",
            "okx",
            "gate",
            "bitget",
            "mexc",
            "kucoin",
        ]:
            src = raw.get(exchange_id, {})
            if not isinstance(src, dict):
                src = {}
            result[exchange_id] = {
                "api_key": str(src.get("api_key", "") or ""),
                "api_secret": str(src.get("api_secret", "") or ""),
                "api_passphrase": str(src.get("api_passphrase", "") or ""),
            }

        return result

    def get_auto_dep_credentials_plain(self):
        creds_map = self._normalize_auto_dep_credentials_shape(
            self.settings.get("auto_dep_credentials", {})
        )

        for exchange_id, creds in creds_map.items():
            creds_map[exchange_id] = {
                "api_key": self._secure_decrypt_field(creds.get("api_key", "")),
                "api_secret": self._secure_decrypt_field(creds.get("api_secret", "")),
                "api_passphrase": self._secure_decrypt_field(
                    creds.get("api_passphrase", "")
                ),
            }

        if not any(creds_map.get("binance", {}).values()):
            legacy_key = str(self.settings.get("auto_dep_api_key", "") or "").strip()
            legacy_secret = str(self.settings.get("auto_dep_api_secret", "") or "").strip()
            legacy_passphrase = str(
                self.settings.get("auto_dep_api_passphrase", "") or ""
            ).strip()
            if legacy_key or legacy_secret or legacy_passphrase:
                creds_map["binance"] = {
                    "api_key": legacy_key,
                    "api_secret": legacy_secret,
                    "api_passphrase": legacy_passphrase,
                }

        return creds_map

    def set_auto_dep_credentials_plain(self, plain_map):
        plain_map = self._normalize_auto_dep_credentials_shape(plain_map)
        encrypted_map = {}
        for exchange_id, creds in plain_map.items():
            encrypted_map[exchange_id] = {
                "api_key": self._secure_encrypt_field(creds.get("api_key", "")),
                "api_secret": self._secure_encrypt_field(creds.get("api_secret", "")),
                "api_passphrase": self._secure_encrypt_field(
                    creds.get("api_passphrase", "")
                ),
            }
        self.settings["auto_dep_credentials"] = encrypted_map
        self.settings["auto_dep_api_key"] = ""
        self.settings["auto_dep_api_secret"] = ""
        self.settings["auto_dep_api_passphrase"] = ""

    def _migrate_auto_dep_credentials_secure_storage(self):
        raw = self.settings.get("auto_dep_credentials", {})
        raw = self._normalize_auto_dep_credentials_shape(raw)
        has_unprotected = any(
            (
                str(creds.get("api_key", "") or "").strip()
                and not str(creds.get("api_key", "")).startswith("dpapi:")
            )
            or (
                str(creds.get("api_secret", "") or "").strip()
                and not str(creds.get("api_secret", "")).startswith("dpapi:")
            )
            or (
                str(creds.get("api_passphrase", "") or "").strip()
                and not str(creds.get("api_passphrase", "")).startswith("dpapi:")
            )
            for creds in raw.values()
        )

        has_legacy_plain = bool(
            str(self.settings.get("auto_dep_api_key", "") or "").strip()
            or str(self.settings.get("auto_dep_api_secret", "") or "").strip()
            or str(self.settings.get("auto_dep_api_passphrase", "") or "").strip()
        )

        if not has_unprotected and not has_legacy_plain:
            return False

        try:
            plain_map = self.get_auto_dep_credentials_plain()
            self.set_auto_dep_credentials_plain(plain_map)
            return True
        except Exception:
            return False

    def validate_auto_dep_credentials_read_only(
        self,
        exchange_id,
        api_key,
        api_secret,
        market_type,
        passphrase="",
        use_cache=True,
    ):
        exchange_id = str(exchange_id or "").strip().lower()
        market_type = str(market_type or "futures").strip().lower()
        api_key = str(api_key or "").strip()
        api_secret = str(api_secret or "").strip()
        passphrase = str(passphrase or "").strip()

        if not api_key or not api_secret:
            return False, "Empty API key/secret"

        mapped_exchange_id = self._map_auto_dep_exchange_id(exchange_id)
        if mapped_exchange_id != "binance":
            # For non-Binance exchanges we cannot reliably infer permissions via one unified API.
            return True, ""

        cache_hash = hashlib.sha256(
            f"{exchange_id}|{market_type}|{api_key}|{api_secret}|{passphrase}".encode("utf-8")
        ).hexdigest()
        cache_key = (exchange_id, market_type, cache_hash)
        if use_cache and cache_key in self._api_read_only_check_cache:
            return self._api_read_only_check_cache[cache_key]

        result = self._validate_binance_read_only_key(
            api_key,
            api_secret,
            market_type,
        )
        self._api_read_only_check_cache[cache_key] = result
        return result

    def _validate_binance_read_only_key(self, api_key, api_secret, market_type):
        def _signed_get_json(base_url, path, timeout_sec=5):
            time_path = (
                "/fapi/v1/time"
                if base_url.startswith("https://fapi.")
                else "/api/v3/time"
            )
            timestamp_ms = _binance_server_timestamp_ms(
                base_url, time_path, timeout=timeout_sec
            )
            params = {"timestamp": timestamp_ms, "recvWindow": 5000}
            query = urlencode(params)
            signature = hmac.new(
                str(api_secret).encode("utf-8"),
                query.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers = {"X-MBX-APIKEY": str(api_key)}
            url = f"{base_url}{path}?{query}&signature={signature}"
            response = requests.get(url, headers=headers, timeout=timeout_sec)
            return _binance_response_json(response)

        try:
            # First verify credentials against the selected market endpoint.
            if market_type == "spot":
                _signed_get_json("https://api.binance.com", "/api/v3/account")
            else:
                _signed_get_json("https://fapi.binance.com", "/fapi/v3/account")

            # /account canTrade is account-level and does not reliably reflect
            # API-key permissions. Do not treat an unavailable restrictions
            # endpoint as proof that the key is read-only.
            restrictions = _signed_get_json(
                "https://api.binance.com", "/sapi/v1/account/apiRestrictions"
            )
            if not isinstance(restrictions, dict):
                raise RuntimeError("Binance returned invalid API restrictions")

            trading_permission_fields = (
                "enableSpotAndMarginTrading",
                "enableMargin",
                "enableFutures",
            )
            if not any(field in restrictions for field in trading_permission_fields):
                raise RuntimeError("Binance API restrictions do not include permissions")

            has_trading_permission = any(
                bool(restrictions.get(field, False))
                for field in trading_permission_fields
            )

            if has_trading_permission:
                t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                return False, t.get(
                    "api_key_not_read_only",
                    "API-ключ имеет право торговли. Используйте ключ только для чтения.",
                )

            return True, ""
        except Exception as exc:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            return False, t.get(
                "api_key_check_failed",
                "Не удалось проверить права API-ключа. Проверьте ключи и сеть.",
            ) + f" ({exc})"

    def toggle_window(self):
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
            self.activateWindow()
            self.raise_()
        else:
            self.showMinimized()

    def nativeEvent(self, _event_type, message):
        if sys.platform == "win32":
            try:
                native_message = ctypes.cast(
                    int(message), ctypes.POINTER(wintypes.MSG)
                ).contents
                if native_message.message == 0x0312:
                    callbacks = self._windows_hotkey_actions.get(
                        int(native_message.wParam), ()
                    )
                    if callbacks:
                        for callback in callbacks:
                            callback()
                        return True, 0
            except (TypeError, ValueError, OSError):
                logging.exception("Failed to process WM_HOTKEY message")
        return False, 0

    def open_settings(self):
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        # Иногда при открытии диалога настроек Windows кратковременно показывает
        # консольное окно другого дочернего окна процесса. Попробуем скрыть
        # все лишние окна прямо перед созданием диалога и ещё раз через короткую
        # задержку после показа, чтобы погасить возможные импульсные консоли.
        try:
            _hide_console_window_on_windows()
        except Exception:
            pass

        dlg = SettingsDialog(self)
        dlg.setModal(False)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.finished.connect(self._on_settings_dialog_finished)
        self._settings_dialog = dlg
        dlg.show()
        try:
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(50, _hide_console_window_on_windows)
        except Exception:
            pass
        dlg.raise_()
        dlg.activateWindow()

    def _on_settings_dialog_finished(self, result):
        if result == QDialog.DialogCode.Accepted:
            # Настройки уже применяются внутри save_and_close() диалога.
            # Здесь только мягко синхронизируем расчеты/таблицу.
            self.schedule_update_calc()
            self._apply_auto_deposit_sync(force_now=True)
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()

        self._settings_dialog = None

    def _apply_auto_deposit_sync(self, force_now=False):
        if not hasattr(self, "_auto_dep_timer"):
            return

        enabled = bool(self.settings.get("auto_dep_enabled", False))
        connected = self._is_auto_dep_connection_ready()
        if hasattr(self, "btn_dep_refresh"):
            self.btn_dep_refresh.setVisible(enabled)
        if enabled and connected:
            self._auto_dep_timer.start(30 * 1000)
            self._set_auto_dep_status("loading")
            if force_now:
                QTimer.singleShot(100, self._sync_deposit_from_exchange)
        elif enabled:
            self._auto_dep_timer.stop()
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            selected_exchange = str(
                self.settings.get("auto_dep_exchange", "binance") or "binance"
            ).strip().lower()
            api_key, api_secret, _ = self._get_auto_dep_credentials(selected_exchange)
            if not api_key or not api_secret:
                message = (
                    f"Для {selected_exchange} не указаны API Key и API Secret."
                )
            else:
                message = t.get(
                    "auto_dep_connect_required",
                    "Press Connect and complete API validation first.",
                )
            self._set_auto_dep_status(
                "error",
                message,
            )
        else:
            self._auto_dep_timer.stop()
            self._set_auto_dep_status("off")

    def refresh_quick_deposit_controls(self):
        if not hasattr(self, "cb_quick_dep_exchange"):
            return
        enabled = bool(self.settings.get("auto_dep_enabled", False))
        available = ["binance", "bybit", "okx", "gate", "bitget", "mexc", "kucoin"]
        names = {
            "binance": "Binance",
            "bybit": "Bybit",
            "okx": "OKX",
            "gate": "Gate",
            "bitget": "Bitget",
            "mexc": "MEXC",
            "kucoin": "KuCoin",
        }
        current = str(self.settings.get("auto_dep_exchange", "binance")).lower()
        self.cb_quick_dep_exchange.blockSignals(True)
        self.cb_quick_dep_exchange.clear()
        for exchange_id in available:
            if exchange_id in names:
                self.cb_quick_dep_exchange.addItem(names[exchange_id], exchange_id)
        for item_index in range(self.cb_quick_dep_exchange.count()):
            self.cb_quick_dep_exchange.setItemData(
                item_index,
                Qt.AlignmentFlag.AlignCenter,
                Qt.ItemDataRole.TextAlignmentRole,
            )
        index = self.cb_quick_dep_exchange.findData(current)
        if index >= 0:
            self.cb_quick_dep_exchange.setCurrentIndex(index)
        self.cb_quick_dep_exchange.blockSignals(False)
        self.cb_quick_dep_exchange.setVisible(enabled)
        if current == "bybit":
            self.settings["auto_dep_market"] = "futures"
            self.cb_quick_dep_market.setCurrentIndex(0)
        self.cb_quick_dep_market.setVisible(enabled and current != "bybit")
        self.cb_quick_dep_market.blockSignals(True)
        self.cb_quick_dep_market.setCurrentIndex(
            1 if str(self.settings.get("auto_dep_market", "futures")).lower() == "spot" else 0
        )
        self.cb_quick_dep_market.blockSignals(False)

    def on_quick_deposit_source_changed(self):
        if not bool(self.settings.get("auto_dep_enabled", False)):
            return
        exchange_id = self.cb_quick_dep_exchange.currentData()
        if not exchange_id:
            return
        market = (
            "futures"
            if str(exchange_id).lower() == "bybit"
            else ("spot" if self.cb_quick_dep_market.currentIndex() == 1 else "futures")
        )
        self.settings["auto_dep_exchange"] = str(exchange_id)
        self.settings["auto_dep_market"] = market
        self.settings["auto_dep_connected"] = False
        self.settings["auto_dep_connected_exchange"] = ""
        self.settings["auto_dep_connected_market"] = ""
        self.settings["auto_dep_allow_unverified"] = False
        api_key, api_secret, _ = self._get_auto_dep_credentials(str(exchange_id))
        if not api_key or not api_secret:
            self.save_settings()
            self._set_auto_dep_status(
                "error",
                f"Для {self.cb_quick_dep_exchange.currentText()} не указаны API Key и API Secret.",
            )
            return

        is_read_only, reason = self.validate_auto_dep_credentials_read_only(
            exchange_id,
            api_key,
            api_secret,
            market,
            use_cache=False,
        )
        if not is_read_only:
            self.save_settings()
            self.refresh_quick_deposit_controls()
            self._set_auto_dep_status("error", reason)
            return

        self.settings["auto_dep_connected"] = True
        self.settings["auto_dep_connected_exchange"] = str(exchange_id)
        self.settings["auto_dep_connected_market"] = market
        self.save_settings()
        self.refresh_quick_deposit_controls()
        self._apply_auto_deposit_sync(force_now=True)

    def _is_auto_dep_connection_ready(self):
        if not bool(self.settings.get("auto_dep_enabled", False)):
            return False

        if not bool(self.settings.get("auto_dep_connected", False)):
            return False

        selected_exchange = str(
            self.settings.get("auto_dep_exchange", "binance") or "binance"
        ).strip().lower()
        selected_market = str(
            self.settings.get("auto_dep_market", "futures") or "futures"
        ).strip().lower()

        connected_exchange = str(
            self.settings.get("auto_dep_connected_exchange", "") or ""
        ).strip().lower()
        connected_market = str(
            self.settings.get("auto_dep_connected_market", "") or ""
        ).strip().lower()

        if selected_exchange != connected_exchange or selected_market != connected_market:
            return False

        api_key, api_secret, _ = self._get_auto_dep_credentials(selected_exchange)
        return bool(api_key and api_secret)

    def _set_auto_dep_status(self, state, message=None):
        if not hasattr(self, "lbl_dep_api_status"):
            return

        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        if state == "ok":
            text = t.get("dep_api_status_ok", "API: OK")
            style = "color: #38BE1D; font-size: 8pt;"
        elif state == "loading":
            text = t.get("dep_api_status_loading", "API: обновление...")
            style = "color: #8CB4FF; font-size: 8pt;"
        elif state == "error":
            text = t.get("dep_api_status_error", "API: ошибка")
            style = "color: #FF6B6B; font-size: 8pt;"
        else:
            text = t.get("dep_api_status_off", "API: выкл")
            style = "color: #666; font-size: 8pt;"

        self.lbl_dep_api_status.setText(text)
        self.lbl_dep_api_status.setStyleSheet(style)
        if message:
            self.lbl_dep_api_status.setToolTip(str(message))
        else:
            self.lbl_dep_api_status.setToolTip("")

    def manual_refresh_deposit(self):
        if not bool(self.settings.get("auto_dep_enabled", False)):
            return
        if not self._is_auto_dep_connection_ready():
            exchange_id = str(
                self.settings.get("auto_dep_exchange", "binance") or "binance"
            ).strip().lower()
            market_type = str(
                self.settings.get("auto_dep_market", "futures") or "futures"
            ).strip().lower()
            api_key, api_secret, api_passphrase = self._get_auto_dep_credentials(
                exchange_id
            )
            if not api_key or not api_secret:
                self._set_auto_dep_status("error", "Empty API key/secret")
                return

            is_read_only, reason = self.validate_auto_dep_credentials_read_only(
                exchange_id,
                api_key,
                api_secret,
                market_type,
                api_passphrase,
                use_cache=False,
            )
            if not is_read_only:
                self._set_auto_dep_status("error", reason)
                return

            self.settings["auto_dep_connected"] = True
            self.settings["auto_dep_connected_exchange"] = exchange_id
            self.settings["auto_dep_connected_market"] = market_type
            self.settings["auto_dep_allow_unverified"] = False
            self.save_settings()
            self._apply_auto_deposit_sync(force_now=True)
            return
        self._sync_deposit_from_exchange(manual=True)

    def _map_auto_dep_exchange_id(self, exchange_id):
        return str(exchange_id or "").strip().lower()

    def _get_auto_dep_credentials(self, exchange_id):
        creds_map = self.get_auto_dep_credentials_plain()
        ex_creds = creds_map.get(self._map_auto_dep_exchange_id(exchange_id), {})
        api_key = str(ex_creds.get("api_key", "") or "").strip()
        api_secret = str(ex_creds.get("api_secret", "") or "").strip()
        api_passphrase = str(ex_creds.get("api_passphrase", "") or "").strip()

        return api_key, api_secret, api_passphrase

    def _run_auto_dep_fetch(self, exchange_id, api_key, api_secret, market_type, asset, passphrase):
        try:
            balance = self._fetch_exchange_balance(
                exchange_id,
                api_key,
                api_secret,
                market_type,
                asset,
                passphrase,
            )
            self._auto_dep_signaler.fetch_finished.emit(balance, None)
        except Exception as exc:
            self._auto_dep_signaler.fetch_finished.emit(None, str(exc))

    def _on_auto_dep_fetch_finished(self, balance, error_message):
        try:
            if error_message:
                self._set_auto_dep_status("error", error_message)
                return

            if balance is None:
                self._set_auto_dep_status("error", "No balance value")
                return

            if hasattr(self, "inp_dep") and self.inp_dep is not None:
                new_text = self._format_deposit_input_value(balance)
                if (self.inp_dep.text() or "").strip() != new_text:
                    self.inp_dep.setText(new_text)
            self._set_auto_dep_status("ok")
        finally:
            self._auto_dep_sync_busy = False

    def _format_deposit_input_value(self, value):
        try:
            num = float(value)
        except Exception:
            num = 0.0

        # Максимум 2 знака после запятой для автозаполнения.
        text = f"{num:.2f}".rstrip("0").rstrip(".")
        if not text:
            text = "0"
        return text.replace(".", ",")

    def _fetch_exchange_balance(
        self,
        exchange_id,
        api_key,
        api_secret,
        market_type,
        asset,
        passphrase="",
    ):
        mapped_exchange_id = self._map_auto_dep_exchange_id(exchange_id)
        if mapped_exchange_id == "binance":
            return self._fetch_binance_balance_light(
                api_key,
                api_secret,
                market_type,
                asset,
            )
        if mapped_exchange_id == "bybit":
            return self._fetch_bybit_unified_balance(
                api_key,
                api_secret,
                asset,
            )

        return self._fetch_non_binance_balance_light(
            mapped_exchange_id,
            api_key,
            api_secret,
            market_type,
            asset,
            passphrase,
        )


    def _fetch_non_binance_balance_light(
        self,
        exchange_id,
        api_key,
        api_secret,
        market_type,
        asset,
        passphrase="",
    ):
        payload = {
            "exchange_id": exchange_id,
            "api_key": api_key,
            "api_secret": api_secret,
            "market_type": market_type,
            "asset": asset,
            "passphrase": passphrase,
        }

        result = {}
        exception_holder = []

        def _worker():
            try:
                result["balance"] = _fetch_balance_with_ccxt(payload)
            except Exception as exc:
                exception_holder.append(exc)

        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()
        worker.join(timeout=8.0)

        if worker.is_alive():
            raise RuntimeError("Balance request timed out after 8 seconds")

        if exception_holder:
            raise exception_holder[0]

        if "balance" not in result:
            raise RuntimeError("No balance returned")

        return float(result.get("balance", 0.0) or 0.0)

    def _fetch_bybit_unified_balance(self, api_key, api_secret, asset):
        """Fetch wallet balance from Bybit Unified, excluding perpetual UPL."""
        timestamp = str(_bybit_server_timestamp_ms())
        recv_window = "5000"
        query = urlencode({"accountType": "UNIFIED", "coin": asset})
        signature_payload = timestamp + str(api_key) + recv_window + query
        signature = hmac.new(
            str(api_secret).encode("utf-8"),
            signature_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "X-BAPI-API-KEY": str(api_key),
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window,
        }
        response = requests.get(
            "https://api.bybit.com/v5/account/wallet-balance",
            params={"accountType": "UNIFIED", "coin": asset},
            headers=headers,
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or int(data.get("retCode", -1)) != 0:
            message = data.get("retMsg", "Unknown Bybit API error") if isinstance(data, dict) else "Invalid Bybit response"
            raise RuntimeError(f"Bybit: {message}")
        result = data.get("result", {})
        rows = result.get("list", []) if isinstance(result, dict) else []
        if not rows:
            raise RuntimeError("Bybit: Unified wallet balance is empty")
        wallet_balance = rows[0].get("totalWalletBalance")
        if wallet_balance in (None, ""):
            raise RuntimeError("Bybit: totalWalletBalance is missing")
        return float(wallet_balance)

    def _fetch_binance_balance_light(self, api_key, api_secret, market_type, asset, base_url=None):
        if market_type == "futures":
            api_base = base_url.rstrip("/") if base_url else "https://fapi.binance.com"
            time_path = "/fapi/v1/time"
        else:
            api_base = base_url.rstrip("/") if base_url else "https://api.binance.com"
            time_path = "/api/v3/time"
        timestamp_ms = _binance_server_timestamp_ms(api_base, time_path)
        params = {
            "timestamp": timestamp_ms,
            "recvWindow": 5000,
        }
        query = urlencode(params)
        signature = hmac.new(
            api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {"X-MBX-APIKEY": api_key}
        if market_type == "futures":
            url = f"{api_base}/fapi/v3/account?{query}&signature={signature}"
            response = requests.get(url, headers=headers, timeout=4)
            data = _binance_response_json(response)
            if isinstance(data, dict):
                for field in ("totalCrossWalletBalance", "totalWalletBalance"):
                    value = data.get(field)
                    if value not in (None, ""):
                        return float(value or 0.0)
            assets = data.get("assets", []) if isinstance(data, dict) else []
            for row in assets:
                if str(row.get("asset", "")).upper() == asset:
                    for field in ("crossWalletBalance", "walletBalance"):
                        value = row.get(field)
                        if value not in (None, ""):
                            return float(value or 0.0)
            raise RuntimeError(
                f"Binance futures: realized wallet balance for {asset} is missing"
            )

        url = f"{api_base}/api/v3/account?{query}&signature={signature}"
        response = requests.get(url, headers=headers, timeout=4)
        data = _binance_response_json(response)
        balances = data.get("balances", []) if isinstance(data, dict) else []
        for row in balances:
            if str(row.get("asset", "")).upper() == asset:
                free_val = float(row.get("free", 0.0) or 0.0)
                locked_val = float(row.get("locked", 0.0) or 0.0)
                return free_val + locked_val
        return 0.0

    def _sync_deposit_from_exchange(self, manual=False):
        if self._auto_dep_sync_busy:
            return
        if not bool(self.settings.get("auto_dep_enabled", False)) and not manual:
            return
        if not self._is_auto_dep_connection_ready():
            self._apply_auto_deposit_sync(force_now=False)
            return
        if not hasattr(self, "inp_dep") or self.inp_dep is None:
            return
        if self.inp_dep.hasFocus() and not manual:
            return

        exchange_id = str(
            self.settings.get("auto_dep_exchange", "binance") or "binance"
        ).strip().lower()
        api_key, api_secret, api_passphrase = self._get_auto_dep_credentials(exchange_id)
        market_type = str(
            self.settings.get("auto_dep_market", "futures") or "futures"
        ).lower()
        asset = str(self.settings.get("auto_dep_asset", "USDT") or "USDT").strip().upper()

        if not api_key or not api_secret:
            self._set_auto_dep_status("error", "Empty API key/secret")
            return

        allow_unverified = bool(self.settings.get("auto_dep_allow_unverified", False))
        if not allow_unverified:
            is_read_only, reason = self.validate_auto_dep_credentials_read_only(
                exchange_id,
                api_key,
                api_secret,
                market_type,
                api_passphrase,
                use_cache=True,
            )
            if not is_read_only:
                self._set_auto_dep_status("error", reason)
                return

        self._auto_dep_sync_busy = True
        self._set_auto_dep_status("loading")
        worker = threading.Thread(
            target=self._run_auto_dep_fetch,
            args=(
                exchange_id,
                api_key,
                api_secret,
                market_type,
                asset,
                api_passphrase,
            ),
            daemon=True,
        )
        worker.start()

    def init_ui(self):
        logging.debug("init_ui START")
        self.central_widget = QWidget()
        self.central_widget.setObjectName("Root")
        self.setCentralWidget(self.central_widget)
        logging.debug("central widget set")

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(5)

        # --- ЗАГОЛОВОК ---
        # Единая полоска с градиентом и скругленными углами
        header_container = QWidget()
        header_container.setStyleSheet(
            """
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(56, 190, 29, 0.15),
                    stop:1 rgba(56, 190, 29, 0.05));
                border: 1px solid rgba(56, 190, 29, 0.3);
                border-radius: 8px;
            }
        """
        )
        self.header_container = header_container

        header = QHBoxLayout(header_container)
        header.setContentsMargins(10, 5, 10, 5)
        header.setSpacing(10)
        self.header_layout = header

        self.lbl_logo_small = QLabel()
        if os.path.exists(LOGO_PATH):
            pix = QIcon(LOGO_PATH).pixmap(24, 24)
            self.lbl_logo_small.setPixmap(pix)
        self.lbl_logo_small.setStyleSheet("background: transparent; border: none;")

        # ВЕРНУЛИ RiskVolume с улучшенным стилем
        title = QLabel("RiskVolume")
        title.setStyleSheet(
            """
            color: #38BE1D; 
            font-weight: bold; 
            font-style: italic; 
            font-size: 11pt;
            border: none; 
            background: transparent;
        """
        )
        self.title_label = title

        self.btn_set = QPushButton("⚙")
        self.btn_min = QPushButton("_")
        self.btn_close = QPushButton("X")
        self.btn_set.clicked.connect(self.open_settings)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_close.clicked.connect(QApplication.quit)

        for b in [self.btn_set, self.btn_min, self.btn_close]:
            b.setObjectName("HeadBtn")
            b.setFixedSize(22, 22)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 4px;
                    color: #38BE1D;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: rgba(56, 190, 29, 0.3);
                }
                QPushButton:pressed {
                    background: rgba(56, 190, 29, 0.5);
                }
            """
            )

        # Делаем кнопку свернуть более жирной
        self.btn_min.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #38BE1D;
                font-weight: 900;
                font-size: 14pt;
            }
            QPushButton:hover {
                background: rgba(56, 190, 29, 0.3);
            }
            QPushButton:pressed {
                background: rgba(56, 190, 29, 0.5);
            }
        """
        )

        # Красный крестик при наведении
        self.btn_close.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #38BE1D;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ff3333;
            }
            QPushButton:pressed {
                background: rgba(255, 51, 51, 0.3);
            }
        """
        )

        header.addWidget(self.lbl_logo_small)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.btn_set)
        header.addWidget(self.btn_min)
        header.addWidget(self.btn_close)

        self.main_layout.addWidget(header_container)

        # Добавляем промежуток между заголовком и вкладками
        self.main_layout.addSpacing(10)

        # --- ВКЛАДКИ ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane { border: none; }
            QTabBar::tab { background: #333; color: #888; padding: 5px 10px; border-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background: #38BE1D; color: black; font-weight: bold; }
            """
        )
        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        self.tab_calculator = QWidget()
        self.init_calculator_tab()
        self.tab_calculator.installEventFilter(self)
        self.tabs.addTab(self.tab_calculator, t.get("tab_calc", "Калькулятор"))

        self.tab_cascade = CascadeTab(self)
        self.tab_cascade.installEventFilter(self)
        self.tabs.addTab(self.tab_cascade, t.get("tab_casc", "Каскады"))
        self.installEventFilter(self)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.main_layout.addWidget(self.tabs)
        self._apply_terminal_mode()

        self.apply_min_order_precision()
        self.refresh_labels()
        self.apply_styles()
        # Finalize geometry before the first show to avoid startup flicker.
        self.finalize_startup_layout()
        logging.debug("init_ui DONE - UI fully initialized")

    def on_tab_changed(self, index):
        if index == 1 and not self._is_profit_forge_terminal():
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(0)
            self.tabs.blockSignals(False)
            return
        if index == 1 and hasattr(self, "tab_cascade"):
            self.tab_cascade.recalc_table()

    def _is_profit_forge_terminal(self):
        return (
            str(self.settings.get("auto_apply_terminal", "metascalp") or "metascalp")
            .strip()
            .lower()
            == "profit_forge"
        )

    def _is_tigertrade_terminal(self):
        return (
            str(self.settings.get("auto_apply_terminal", "metascalp") or "metascalp")
            .strip()
            .lower()
            == "tigertrade"
        )

    def _is_metascalp_terminal(self):
        return (
            str(self.settings.get("auto_apply_terminal", "metascalp") or "metascalp")
            .strip()
            .lower()
            == "metascalp"
        )

    def _is_surf_terminal(self):
        return (
            str(self.settings.get("auto_apply_terminal", "metascalp") or "metascalp")
            .strip()
            .lower()
            == "surf"
        )

    def _is_vataga_terminal(self):
        return (
            str(self.settings.get("auto_apply_terminal", "metascalp") or "metascalp")
            .strip()
            .lower()
            == "vataga"
        )

    def _menu_terminal_kind(self):
        if self._is_tigertrade_terminal():
            return "tiger"
        if self._is_surf_terminal():
            return "surf"
        if self._is_vataga_terminal():
            return "vataga"
        return None

    def _is_menu_terminal(self):
        # SURF's five editable cells are now revealed by hovering, not by opening a menu.
        return self._menu_terminal_kind() in ("tiger", "vataga")

    def _get_terminal_cells_count(self):
        if self._is_metascalp_terminal():
            current_pos_mode = bool(self.settings.get("pos_mode_enabled", False))
            key = self._cells_count_setting_key(current_pos_mode)
            raw = self.settings.get(key, self.settings.get("scalp_cells_count", 5))
            try:
                value = int(raw)
            except Exception:
                value = 5
            value = max(1, min(5, value))
            # Persist normalized value to the chosen mode-aware key.
            self.settings[key] = value
            if not current_pos_mode:
                self.settings["metascalp_cells_count"] = value
                self.settings["scalp_cells_count"] = value
            return value

        return 5

    def _set_terminal_cells_count(self, value):
        if self._is_metascalp_terminal():
            try:
                value = int(value)
            except Exception:
                value = 5
            value = max(1, min(5, value))
            current_pos_mode = bool(self.settings.get("pos_mode_enabled", False))
            key = self._cells_count_setting_key(current_pos_mode)
            self.settings[key] = value
            if not current_pos_mode:
                self.settings["metascalp_cells_count"] = value
            return value

        self.settings["scalp_cells_count"] = 5
        return 5

    def _cells_count_setting_key(self, pos_mode_enabled=None):
        """Return settings key for storing cells count depending on terminal kind and pos-mode."""
        if pos_mode_enabled is None:
            pos_mode_enabled = bool(self.settings.get("pos_mode_enabled", False))
        if self._is_metascalp_terminal():
            return "metascalp_cells_count_pos" if bool(pos_mode_enabled) else "metascalp_cells_count"
        return "scalp_cells_count_pos" if bool(pos_mode_enabled) else "scalp_cells_count"

    def _save_cells_count_state(self, pos_mode_enabled):
        """Save current lbl_cells_count into mode-aware key (if metascalp terminal)."""
        if not hasattr(self, "lbl_cells_count"):
            return
        if not self._is_metascalp_terminal():
            # non-metascalp always 5, nothing to save
            return
        try:
            val = int(self.lbl_cells_count.text())
        except Exception:
            val = self._get_terminal_cells_count()
        key = self._cells_count_setting_key(pos_mode_enabled)
        self.settings[key] = max(1, min(5, int(val)))

    def _restore_cells_count(self, enabled):
        """Restore lbl_cells_count from mode-aware key and refresh table if changed."""
        if not hasattr(self, "lbl_cells_count"):
            return
        if not self._is_metascalp_terminal():
            # non-metascalp UI always shows 5
            self.lbl_cells_count.setText("5")
            return
        key = self._cells_count_setting_key(enabled)
        val = int(self.settings.get(key, self.settings.get("metascalp_cells_count", 5)) or 5)
        val = max(1, min(5, val))
        try:
            current = int(self.lbl_cells_count.text())
        except Exception:
            current = None
        if current != val:
            self.lbl_cells_count.setText(str(val))
            if hasattr(self, "on_cells_changed"):
                self.on_cells_changed()

    def _sync_cells_count_controls(self, refresh_table=False):
        if not hasattr(self, "lbl_cells_count"):
            return

        is_meta = self._is_metascalp_terminal()
        desired = self._get_terminal_cells_count() if is_meta else 5

        if not is_meta:
            self.settings["scalp_cells_count"] = 5

        if self.position_target_row_active is None:
            try:
                current = int(self.lbl_cells_count.text())
            except Exception:
                current = desired
            if current != desired:
                self.lbl_cells_count.setText(str(desired))
                if refresh_table and hasattr(self, "cells_table"):
                    self.on_cells_changed()

        for name in (
            "lbl_cells_count_title",
            "btn_cells_minus",
            "lbl_cells_count",
            "btn_cells_plus",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(False)

        can_edit_count = is_meta and self.position_target_row_active is None
        if hasattr(self, "btn_cells_minus") and self.btn_cells_minus is not None:
            try:
                self.btn_cells_minus.setEnabled(
                    can_edit_count and int(self.lbl_cells_count.text()) > 1
                )
            except Exception:
                self.btn_cells_minus.setEnabled(can_edit_count)
        if hasattr(self, "btn_cells_plus") and self.btn_cells_plus is not None:
            try:
                self.btn_cells_plus.setEnabled(
                    can_edit_count and int(self.lbl_cells_count.text()) < 5
                )
            except Exception:
                self.btn_cells_plus.setEnabled(can_edit_count)

    def _get_menu_terminal_point_keys(self):
        kind = self._menu_terminal_kind()
        if kind == "tiger":
            return ("tiger_open_point", "tiger_close_point")
        if kind == "surf":
            return ("surf_open_point", "surf_accept_point")
        if kind == "vataga":
            return ("vataga_open_point", None)
        return (None, None)

    def _menu_terminal_requires_final_point(self):
        kind = self._menu_terminal_kind()
        return kind == "tiger"

    def _normalize_calc_points(self, points):
        normalized = []
        if not isinstance(points, list):
            return normalized
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                x = int(point[0])
                y = int(point[1])
            except Exception:
                continue
            normalized.append([x, y])
        return normalized

    def _normalize_point_pair(self, point):
        normalized = self._normalize_calc_points([point])
        return normalized[0] if normalized else None

    def _uses_shared_preset_controls(self):
        return (
            self._is_profit_forge_terminal()
            or self._is_metascalp_terminal()
            or self._is_tigertrade_terminal()
            or self._is_surf_terminal()
            or self._is_vataga_terminal()
        )

    def _is_shared_menu_preset_terminal(self):
        return self._is_tigertrade_terminal() or self._is_surf_terminal() or self._is_vataga_terminal()

    def _get_menu_glass_map_keys(self):
        if self._is_tigertrade_terminal():
            return ("tiger_glasses_open_points", "tiger_glasses_close_points")
        if self._is_surf_terminal():
            return ("surf_glasses_open_points", "surf_glasses_accept_points")
        if self._is_vataga_terminal():
            return ("vataga_glasses_open_points", None)
        return (None, None)

    def _get_shared_preset_points_storage_key(self):
        if self._is_metascalp_terminal():
            return "metascalp_glasses_points"
        if self._is_tigertrade_terminal():
            return "tiger_glasses_points"
        if self._is_surf_terminal():
            return "surf_glasses_points"
        if self._is_vataga_terminal():
            return "vataga_glasses_points"
        return "pf_glasses_points"

    def _get_shared_active_points_key(self):
        if self._is_metascalp_terminal():
            return "calc_points_metascalp"
        if self._is_tigertrade_terminal():
            return "calc_points_tigertrade"
        if self._is_surf_terminal():
            return "calc_points_surf"
        if self._is_vataga_terminal():
            return "calc_points_vataga"
        return "calc_points_profit_forge"

    def _get_menu_points_for_glass(self, glass=None):
        open_key, close_key = self._get_menu_terminal_point_keys()
        if not open_key:
            return (None, None)

        if not self._is_shared_menu_preset_terminal():
            return (
                self._normalize_point_pair(self.settings.get(open_key)),
                self._normalize_point_pair(self.settings.get(close_key)),
            )

        if glass is None:
            glass = self._get_pf_active_glass()
        try:
            glass = int(glass)
        except Exception:
            glass = 1

        open_map_key, close_map_key = self._get_menu_glass_map_keys()
        open_map = self.settings.get(open_map_key, {}) if open_map_key else {}
        close_map = self.settings.get(close_map_key, {}) if close_map_key else {}
        open_point = None
        close_point = None
        if isinstance(open_map, dict):
            open_point = self._normalize_point_pair(open_map.get(str(glass)))
        if close_map_key and isinstance(close_map, dict):
            close_point = self._normalize_point_pair(close_map.get(str(glass)))

        if open_point is None and glass == 1:
            open_point = self._normalize_point_pair(self.settings.get(open_key))
        if close_key and close_point is None and glass == 1:
            close_point = self._normalize_point_pair(self.settings.get(close_key))

        return (open_point, close_point)

    def _set_menu_point_for_glass(self, point, is_close=False, glass=None):
        open_key, close_key = self._get_menu_terminal_point_keys()
        key = close_key if is_close else open_key
        if not key:
            return

        normalized_point = self._normalize_point_pair(point)

        if not self._is_shared_menu_preset_terminal():
            self.settings[key] = normalized_point
            return

        if glass is None:
            glass = self._get_pf_active_glass()
        try:
            glass = int(glass)
        except Exception:
            glass = 1

        open_map_key, close_map_key = self._get_menu_glass_map_keys()
        map_key = close_map_key if is_close else open_map_key
        if not map_key:
            self.settings[key] = list(normalized_point) if normalized_point else None
            return

        point_map = self.settings.get(map_key, {})
        if not isinstance(point_map, dict):
            point_map = {}
        point_map = dict(point_map)
        if normalized_point:
            point_map[str(glass)] = list(normalized_point)
        else:
            point_map.pop(str(glass), None)
        self.settings[map_key] = point_map

        if glass == self._get_pf_active_glass():
            self.settings[key] = list(normalized_point) if normalized_point else None

    def _is_menu_glass_ready(self, glass=None):
        if not self._is_menu_terminal():
            return True

        requires_final_point = self._menu_terminal_requires_final_point()
        menu_open, menu_close = self._get_menu_points_for_glass(glass)
        return menu_open is not None and ((not requires_final_point) or (menu_close is not None))

    def _clamp_pf_glasses_count(self, value):
        try:
            value = int(value)
        except Exception:
            value = 1
        return max(1, min(12, value))

    def _normalize_pf_multi_glass_settings(self):
        changed = False
        points_storage_key = self._get_shared_preset_points_storage_key()

        count = self._clamp_pf_glasses_count(self.settings.get("pf_glasses_count", 1))
        if self.settings.get("pf_glasses_count") != count:
            self.settings["pf_glasses_count"] = count
            changed = True

        raw_map = self.settings.get(points_storage_key, {})
        points_map = {}
        if isinstance(raw_map, dict):
            for raw_key, raw_points in raw_map.items():
                try:
                    glass = int(raw_key)
                except Exception:
                    continue
                if glass < 1 or glass > 12:
                    continue
                points_map[str(glass)] = self._normalize_calc_points(raw_points)

        if not points_map:
            legacy_key = self._get_shared_active_points_key()
            legacy_points = self._normalize_calc_points(self.settings.get(legacy_key, []))
            if legacy_points:
                points_map = {"1": legacy_points}
                changed = True

        if self.settings.get(points_storage_key) != points_map:
            self.settings[points_storage_key] = points_map
            changed = True

        active_glass = self._clamp_pf_glasses_count(
            self.settings.get("pf_active_glass", 1)
        )
        active_glass = min(active_glass, count)
        if self.settings.get("pf_active_glass") != active_glass:
            self.settings["pf_active_glass"] = active_glass
            changed = True

        raw_selected = self.settings.get("pf_selected_glasses", [])
        selected = []
        if isinstance(raw_selected, list):
            for raw_glass in raw_selected:
                try:
                    glass = int(raw_glass)
                except Exception:
                    continue
                if 1 <= glass <= count and glass not in selected:
                    selected.append(glass)

        if self.settings.get("pf_selected_glasses") != selected:
            self.settings["pf_selected_glasses"] = selected
            changed = True

        active_points = self._normalize_calc_points(
            self.settings.get(points_storage_key, {}).get(str(active_glass), [])
        )
        active_points_key = self._get_shared_active_points_key()
        if self.settings.get(active_points_key) != active_points:
            self.settings[active_points_key] = list(active_points)
            changed = True

        if self._is_shared_menu_preset_terminal():
            open_key, close_key = self._get_menu_terminal_point_keys()
            open_map_key, close_map_key = self._get_menu_glass_map_keys()

            open_map = self.settings.get(open_map_key, {}) if open_map_key else {}
            if open_map_key and not isinstance(open_map, dict):
                open_map = {}
                changed = True

            close_map = self.settings.get(close_map_key, {}) if close_map_key else {}
            if close_map_key and not isinstance(close_map, dict):
                close_map = {}
                changed = True

            normalized_open_map = {}
            if isinstance(open_map, dict):
                for raw_key, raw_point in open_map.items():
                    try:
                        glass = int(raw_key)
                    except Exception:
                        continue
                    if glass < 1 or glass > 12:
                        continue
                    normalized_point = self._normalize_point_pair(raw_point)
                    if normalized_point:
                        normalized_open_map[str(glass)] = normalized_point

            normalized_close_map = {}
            if close_map_key and isinstance(close_map, dict):
                for raw_key, raw_point in close_map.items():
                    try:
                        glass = int(raw_key)
                    except Exception:
                        continue
                    if glass < 1 or glass > 12:
                        continue
                    normalized_point = self._normalize_point_pair(raw_point)
                    if normalized_point:
                        normalized_close_map[str(glass)] = normalized_point

            if not normalized_open_map:
                legacy_open = self._normalize_point_pair(self.settings.get(open_key)) if open_key else None
                if legacy_open:
                    normalized_open_map["1"] = legacy_open
                    changed = True

            if close_map_key and not normalized_close_map:
                legacy_close = self._normalize_point_pair(self.settings.get(close_key)) if close_key else None
                if legacy_close:
                    normalized_close_map["1"] = legacy_close
                    changed = True

            if open_map_key and self.settings.get(open_map_key) != normalized_open_map:
                self.settings[open_map_key] = normalized_open_map
                changed = True
            if close_map_key and self.settings.get(close_map_key) != normalized_close_map:
                self.settings[close_map_key] = normalized_close_map
                changed = True

            active_open = normalized_open_map.get(str(active_glass))
            if open_key and self.settings.get(open_key) != active_open:
                self.settings[open_key] = list(active_open) if active_open else None
                changed = True

            if close_key:
                active_close = normalized_close_map.get(str(active_glass))
                if self.settings.get(close_key) != active_close:
                    self.settings[close_key] = list(active_close) if active_close else None
                    changed = True

        if not isinstance(self.settings.get("pf_show_preview_frames", False), bool):
            self.settings["pf_show_preview_frames"] = bool(
                self.settings.get("pf_show_preview_frames")
            )
            changed = True

        return changed

    def _get_pf_glasses_count(self):
        return self._clamp_pf_glasses_count(self.settings.get("pf_glasses_count", 1))

    def _get_pf_active_glass(self):
        count = self._get_pf_glasses_count()
        active = self._clamp_pf_glasses_count(self.settings.get("pf_active_glass", 1))
        return min(active, count)

    def _set_pf_active_glass(self, glass, save=False):
        count = self._get_pf_glasses_count()
        glass = max(1, min(count, self._clamp_pf_glasses_count(glass)))
        self.settings["pf_active_glass"] = glass
        self.settings[self._get_shared_active_points_key()] = self._get_pf_points_for_glass(glass)
        if self._is_shared_menu_preset_terminal():
            open_key, close_key = self._get_menu_terminal_point_keys()
            menu_open, menu_close = self._get_menu_points_for_glass(glass)
            if open_key:
                self.settings[open_key] = list(menu_open) if menu_open else None
            if close_key:
                self.settings[close_key] = list(menu_close) if menu_close else None
        if save:
            self.save_settings()

    def _get_pf_selected_glasses(self):
        count = self._get_pf_glasses_count()
        selected = []
        raw = self.settings.get("pf_selected_glasses", [])
        if isinstance(raw, list):
            for item in raw:
                try:
                    glass = int(item)
                except Exception:
                    continue
                if 1 <= glass <= count and glass not in selected:
                    selected.append(glass)
        return selected

    def _set_pf_selected_glasses(self, glasses, save=False):
        count = self._get_pf_glasses_count()
        selected = []
        for item in (glasses or []):
            try:
                glass = int(item)
            except Exception:
                continue
            if 1 <= glass <= count and glass not in selected:
                selected.append(glass)
        self.settings["pf_selected_glasses"] = selected
        if save:
            self.save_settings()

    def _get_pf_points_for_glass(self, glass):
        try:
            glass = int(glass)
        except Exception:
            glass = 1
        points_storage_key = self._get_shared_preset_points_storage_key()
        points_map = self.settings.get(points_storage_key, {})
        if not isinstance(points_map, dict):
            points_map = {}
        return self._normalize_calc_points(points_map.get(str(glass), []))

    def _set_pf_points_for_glass(self, glass, points):
        try:
            glass = int(glass)
        except Exception:
            glass = 1
        normalized_points = self._normalize_calc_points(points)

        points_storage_key = self._get_shared_preset_points_storage_key()
        points_map = self.settings.get(points_storage_key, {})
        if not isinstance(points_map, dict):
            points_map = {}
        points_map = dict(points_map)
        points_map[str(glass)] = normalized_points
        self.settings[points_storage_key] = points_map

        if glass == self._get_pf_active_glass():
            self.settings[self._get_shared_active_points_key()] = list(normalized_points)

    def _get_pf_required_cells_count(self):
        return self._get_terminal_cells_count()

    def _is_pf_glass_calibrated(self, glass):
        points = self._get_pf_points_for_glass(glass)
        if len(points) < self._get_pf_required_cells_count():
            return False
        if self._is_surf_terminal():
            return self._get_surf_hover_point(glass) is not None
        if self._is_menu_terminal():
            return self._is_menu_glass_ready(glass)
        return True

    def _get_pf_uncalibrated_glasses(self, count=None):
        if count is None:
            count = self._get_pf_glasses_count()
        uncalibrated = []
        for glass in range(1, int(count) + 1):
            if not self._is_pf_glass_calibrated(glass):
                uncalibrated.append(glass)
        return uncalibrated

    def _get_active_calc_points_key(self):
        if self._is_tigertrade_terminal():
            return "calc_points_tigertrade"
        if self._is_surf_terminal():
            return "calc_points_surf"
        if self._is_vataga_terminal():
            return "calc_points_vataga"
        if self._is_metascalp_terminal():
            return "calc_points_metascalp"
        return "calc_points_profit_forge"

    def _get_active_calc_points(self):
        if self._uses_shared_preset_controls():
            return self._get_pf_points_for_glass(self._get_pf_active_glass())
        key = self._get_active_calc_points_key()
        points = self.settings.get(key, [])
        return self._normalize_calc_points(points)

    def _get_shared_active_calibration_points(self):
        if self._uses_shared_preset_controls():
            return self._get_pf_points_for_glass(self._get_pf_active_glass())
        return self._get_active_calc_points()

    def _set_shared_active_calibration_points(self, points):
        if self._uses_shared_preset_controls():
            self._set_pf_points_for_glass(self._get_pf_active_glass(), points)
            return
        self._set_active_calc_points(points)

    def _get_standard_volume_precision(self):
        try:
            precision = int(self.settings.get("prec_dep", 2))
        except Exception:
            precision = 2

        return max(0, min(6, precision))

    def _get_calc_volume_precision(self):
        if self._is_tigertrade_terminal():
            return 0

        return self._get_standard_volume_precision()

    def _scaled_pt(self, base_pt):
        try:
            ratio = int(self.settings.get("scale", self.base_scale)) / float(self.base_scale)
        except Exception:
            ratio = 1.0
        return max(7, int(base_pt * ratio))

    def _scale_ratio(self):
        try:
            return int(self.settings.get("scale", self.base_scale)) / float(self.base_scale)
        except Exception:
            return 1.0

    def _top_info_font_pt(self):
        return self._scaled_pt(8)

    def _position_hint_font_pt(self, base_pt=8):
        return self._scaled_pt(base_pt)

    def _position_hint_style(self, color="#888", base_pt=8, with_padding=False):
        style = f"color: {color}; font-size: {self._position_hint_font_pt(base_pt)}pt;"
        if with_padding:
            ratio = self._scale_ratio()
            pad_left = 0
            pad_right = max(6, int(8 * ratio))
            style += f" padding-left: {pad_left}px; padding-right: {pad_right}px;"
        return style

    def _volume_title_text(self):
        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        return str(t.get("vol", "")).upper()

    def _apply_volume_title_style(self, dimmed=False):
        if not hasattr(self, "lbl_vol_title"):
            return
        ratio = self._scale_ratio()
        font_pt = max(6, int(8 * ratio))
        margin_top = max(1, int(2 * ratio))
        color = "#FF9F0A" if not dimmed else "#555"
        self.lbl_vol_title.setText(self._volume_title_text())
        self.lbl_vol_title.setStyleSheet(
            f"color: {color}; font-size: {font_pt}pt; font-weight: 700; margin-top: {margin_top}px;"
        )

    def _animate_window_size(self, target_w, target_h, duration_ms=180):
        target_w = int(target_w)
        target_h = int(target_h)
        cur_w = int(self.width())
        cur_h = int(self.height())
        target_key = (target_w, target_h)

        if self._window_size_anim is not None and self._window_size_anim_target == target_key:
            return

        if cur_w == target_w and cur_h == target_h:
            self.setFixedSize(target_w, target_h)
            self._window_size_anim_target = None
            return

        if self._window_size_anim is not None:
            old_anim = self._window_size_anim
            self._window_size_anim = None
            self._window_size_anim_target = None
            try:
                old_anim.stop()
            except Exception:
                pass

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(max(60, min(180, int(duration_ms))))
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def _apply(progress):
            if self._window_size_anim is not anim:
                return
            k = float(progress)
            nw = int(cur_w + (target_w - cur_w) * k)
            nh = int(cur_h + (target_h - cur_h) * k)
            self.setFixedSize(nw, nh)

        def _finish():
            if self._window_size_anim is not anim:
                return
            self.setFixedSize(target_w, target_h)
            self._window_size_anim = None
            self._window_size_anim_target = None

        anim.valueChanged.connect(_apply)
        anim.finished.connect(_finish)
        self._window_size_anim = anim
        self._window_size_anim_target = target_key
        anim.start()

    def _set_window_size_with_extra_height(self, grow_only=False, smooth=False):
        if getattr(self, "_lock_dynamic_resize", False):
            return

        try:
            if hasattr(self, "tabs") and self.tabs is not None:
                current_tab = self.tabs.currentWidget()
                if current_tab is not None and current_tab.layout() is not None:
                    current_tab.layout().activate()
                    tab_bar_h = int(self.tabs.tabBar().sizeHint().height()) if self.tabs.tabBar() else 0
                    tab_padding = max(6, int(10 * self._scale_ratio()))
                    current_tab_h = int(
                        max(
                            current_tab.layout().sizeHint().height(),
                            current_tab.layout().minimumSize().height(),
                        )
                    )
                    required_tabs_h = current_tab_h + tab_bar_h + tab_padding
                    # Keep minimum height in sync both ways (grow and shrink),
                    # otherwise a previously larger scale can lock the window tall.
                    if abs(int(self.tabs.minimumHeight()) - int(required_tabs_h)) > 1:
                        self.tabs.setMinimumHeight(required_tabs_h)

            if hasattr(self, "main_layout") and self.main_layout is not None:
                self.main_layout.activate()
            self.central_widget.updateGeometry()
        except Exception:
            pass

        self.adjustSize()
        size = self.sizeHint()
        try:
            central_hint = self.central_widget.sizeHint()
            size_w = max(int(size.width()), int(central_hint.width()))
            size_h = max(int(size.height()), int(central_hint.height()))

            if self.central_widget.layout() is not None:
                layout_hint = self.central_widget.layout().totalSizeHint()
                layout_min = self.central_widget.layout().totalMinimumSize()
                size_w = max(size_w, int(layout_hint.width()), int(layout_min.width()))
                size_h = max(size_h, int(layout_hint.height()), int(layout_min.height()))
        except Exception:
            size_w = int(size.width())
            size_h = int(size.height())
        ratio = self._scale_ratio()
        extra_h = max(20, int(26 * ratio))
        target_w = int(size_w)
        target_h = int(size_h + extra_h)

        # Keep enough room for scaled controls so lower blocks never overlap the cells table.
        target_w = max(target_w, int(620 * ratio))
        target_h = max(target_h, int(700 * ratio))

        if grow_only:
            target_w = max(int(self.width()), target_w)
            target_h = max(int(self.height()), target_h)

        requested_w = int(target_w)
        requested_h = int(target_h)

        target_w, target_h, fit_x, fit_y = self._fit_window_geometry_to_screen(
            target_w,
            target_h,
            margin=6,
        )

        # For larger calculator scales keep full content visible even if it exceeds the
        # available monitor area: better a bigger window than controls overlapping table rows.
        allow_oversize = False
        try:
            scale_now = int(self.settings.get("scale", self.base_scale))
            allow_oversize = (
                hasattr(self, "tabs")
                and self.tabs is not None
                and self.tabs.currentIndex() == 0
                and scale_now >= 120
            )
        except Exception:
            allow_oversize = False

        if allow_oversize and (int(target_h) < requested_h or int(target_w) < requested_w):
            target_w = requested_w
            target_h = requested_h
            fit_x = None
            fit_y = None

        if smooth and self.isVisible():
            self._animate_window_size(target_w, target_h)
        else:
            self.setFixedSize(target_w, target_h)

        if self.isVisible() and fit_x is not None and fit_y is not None:
            self.move(fit_x, fit_y)

    def _freeze_window_size_temporarily(self, width, height, duration_ms=700):
        """Keep current window geometry stable for short UI update bursts."""
        try:
            w = int(width)
            h = int(height)
            if w <= 0 or h <= 0:
                return
            self._lock_dynamic_resize = True
            self.setFixedSize(w, h)
            self._ensure_window_on_screen(margin=6)
        except Exception:
            return

        delay = max(120, int(duration_ms))

        def _unlock_resize():
            try:
                self._lock_dynamic_resize = False
            except Exception:
                pass

        QTimer.singleShot(delay, _unlock_resize)

    def _fit_window_geometry_to_screen(
        self,
        width,
        height,
        margin=6,
        anchor_pos=None,
        prefer_active=False,
    ):
        """Clamp window size and target position to available screen geometry."""
        try:
            app = QApplication.instance()
            screen = None

            if app is not None and anchor_pos is not None:
                try:
                    ax = int(anchor_pos[0])
                    ay = int(anchor_pos[1])
                    screen = app.screenAt(QPoint(ax, ay))
                except Exception:
                    screen = None

            if screen is None and app is not None and prefer_active:
                try:
                    screen = app.screenAt(QCursor.pos())
                except Exception:
                    screen = None

            if screen is None:
                screen = self.screen() or QApplication.primaryScreen()

            if screen is None:
                return int(width), int(height), None, None

            available = screen.availableGeometry()
            margin = max(0, int(margin))

            max_w = max(220, int(available.width()) - margin * 2)
            max_h = max(180, int(available.height()) - margin * 2)

            safe_w = max(180, min(int(width), max_w))
            safe_h = max(160, min(int(height), max_h))

            if safe_w > max_w:
                safe_w = max_w
            if safe_h > max_h:
                safe_h = max_h

            min_x = int(available.left()) + margin
            min_y = int(available.top()) + margin
            max_x = int(available.right()) - safe_w - margin + 1
            max_y = int(available.bottom()) - safe_h - margin + 1

            if max_x < min_x:
                max_x = min_x
            if max_y < min_y:
                max_y = min_y

            cur_x = int(self.x())
            cur_y = int(self.y())
            fit_x = max(min_x, min(max_x, cur_x))
            fit_y = max(min_y, min(max_y, cur_y))
            return safe_w, safe_h, fit_x, fit_y
        except Exception:
            return int(width), int(height), None, None

    def _ensure_window_on_screen(self, margin=6, anchor_pos=None, prefer_active=False):
        """Move window into visible area without changing current logical layout state."""
        try:
            safe_w, safe_h, fit_x, fit_y = self._fit_window_geometry_to_screen(
                int(self.width()),
                int(self.height()),
                margin=margin,
                anchor_pos=anchor_pos,
                prefer_active=prefer_active,
            )
            if int(self.width()) != int(safe_w) or int(self.height()) != int(safe_h):
                self.setFixedSize(int(safe_w), int(safe_h))
            if fit_x is not None and fit_y is not None:
                self.move(int(fit_x), int(fit_y))
        except Exception:
            pass

    def _schedule_smooth_content_resize(self, force=False):
        if getattr(self, "_lock_dynamic_resize", False):
            return
        try:
            if time.time() < float(getattr(self, "_suppress_content_resize_until", 0.0) or 0.0):
                return
        except Exception:
            pass
        if force:
            self._force_resize_pending = True
        # Resize after a short pause, not on every keystroke.
        if hasattr(self, "_smooth_resize_idle_timer"):
            self._smooth_resize_idle_timer.start(80)
        else:
            self._apply_idle_smooth_resize()

    def _current_resize_pressure_chars(self):
        if not self._resize_len_baseline:
            return 0
        extra_chars = 0
        for name, base_len in self._resize_len_baseline.items():
            widget = getattr(self, name, None)
            if not widget:
                continue
            cur_len = len((widget.text() or "").strip())
            extra_chars = max(extra_chars, max(0, cur_len - int(base_len)))
        return int(extra_chars)

    def _apply_idle_smooth_resize(self):
        pressure = self._current_resize_pressure_chars()
        step = max(1, int(getattr(self, "_resize_step_chars", 5) or 1))

        force = bool(getattr(self, "_force_resize_pending", False))
        if force:
            self._force_resize_pending = False

        # Quantize pressure to step boundaries so window jumps only every N chars
        quantized = (pressure // step) * step
        last_quantized = (self._last_applied_resize_pressure // step) * step

        force_back_to_base = (
            pressure == 0 and self._last_applied_resize_pressure != 0
        )
        if (
            not force_back_to_base
            and quantized == last_quantized
        ):
            return

        self._last_applied_resize_pressure = pressure
        self._adapt_window_width_to_content(grow_only=False, smooth=True)

    def _set_active_calc_points(self, points):
        if self._uses_shared_preset_controls():
            self._set_pf_points_for_glass(self._get_pf_active_glass(), points)
            return
        key = self._get_active_calc_points_key()
        self.settings[key] = list(points)

    def _get_surf_hover_point(self, glass=None):
        if glass is None:
            glass = self._get_pf_active_glass()
        try:
            glass = int(glass)
        except Exception:
            glass = 1
        hover_points = self.settings.get("surf_glasses_hover_points", {})
        if not isinstance(hover_points, dict):
            return None
        return self._normalize_point_pair(hover_points.get(str(glass)))

    def _set_surf_hover_point(self, point, glass=None):
        if glass is None:
            glass = self._get_pf_active_glass()
        try:
            glass = int(glass)
        except Exception:
            glass = 1
        hover_points = self.settings.get("surf_glasses_hover_points", {})
        if not isinstance(hover_points, dict):
            hover_points = {}
        hover_points = dict(hover_points)
        normalized_point = self._normalize_point_pair(point)
        if normalized_point:
            hover_points[str(glass)] = normalized_point
        else:
            hover_points.pop(str(glass), None)
        self.settings["surf_glasses_hover_points"] = hover_points

    def _reset_active_calc_calibration(self):
        self._set_shared_active_calibration_points([])
        if self._is_surf_terminal():
            self._set_surf_hover_point(None)
        if self._is_menu_terminal():
            self._set_menu_point_for_glass(None, is_close=False)
            if self._menu_terminal_requires_final_point():
                self._set_menu_point_for_glass(None, is_close=True)
        self.save_settings()

    def _apply_terminal_mode(self):
        if hasattr(self, "update_calc"):
            self.update_calc()
        if hasattr(self, "update_position_adjustment_info"):
            self.update_position_adjustment_info()
        if hasattr(self, "update_cell_volumes"):
            self.update_cell_volumes()
        self._sync_cells_count_controls(refresh_table=True)
        self._update_pf_multi_glass_ui()
        if hasattr(self, "tab_cascade") and hasattr(self, "tabs"):
            is_profit_forge = self._is_profit_forge_terminal()
            self.tab_cascade.setEnabled(is_profit_forge)
            if not is_profit_forge and self.tabs.currentIndex() == 1:
                self.tabs.setCurrentIndex(0)
            self.tabs.setTabVisible(1, is_profit_forge)

    def _pf_glass_label(self, glass_num):
        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        return t.get("calc_glass_short", "Пресет {n}").format(n=int(glass_num))

    def _update_pf_multi_glass_ui(self):
        if not hasattr(self, "pf_controls_widget"):
            return

        self.pf_controls_widget.setVisible(True)
        if hasattr(self, "btn_pf_preview"):
            self.btn_pf_preview.setVisible(True)

        settings_changed = self._normalize_pf_multi_glass_settings()
        if settings_changed:
            self.save_settings()

        count = self._get_pf_glasses_count()
        active_glass = self._get_pf_active_glass()
        selected_glasses = self._get_pf_selected_glasses()

        if hasattr(self, "sb_pf_count") and not self.sb_pf_count.hasFocus():
            self.sb_pf_count.blockSignals(True)
            self.sb_pf_count.setValue(int(count))
            self.sb_pf_count.blockSignals(False)

        if hasattr(self, "cb_pf_calib_glass"):
            self.cb_pf_calib_glass.blockSignals(True)
            self.cb_pf_calib_glass.clear()
            for glass in range(1, count + 1):
                self.cb_pf_calib_glass.addItem(self._pf_glass_label(glass), glass)
            self.cb_pf_calib_glass.setCurrentIndex(max(0, active_glass - 1))
            self.cb_pf_calib_glass.blockSignals(False)

        if hasattr(self, "pf_targets_layout"):
            while self.pf_targets_layout.count():
                item = self.pf_targets_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            # Reset previous stretch factors so spacing stays uniform after count changes.
            max_cols = self._clamp_pf_glasses_count(999) + 2
            for col in range(max_cols):
                self.pf_targets_layout.setColumnStretch(col, 0)

            self._pf_target_checkboxes = {}
            required_cells = self._get_pf_required_cells_count()
            actual_selected = []
            for glass in range(1, count + 1):
                checkbox = QCheckBox(str(glass))
                is_calibrated = self._is_pf_glass_calibrated(glass)
                label = self._pf_glass_label(glass)
                checkbox.setProperty("uncalibrated", not is_calibrated)
                if is_calibrated:
                    checkbox.setToolTip(label)
                    checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                    checkbox.setToolTip(
                        t.get(
                            "calc_glass_need_calib",
                            "{glass}: сначала откалибруй {cells} ячеек",
                        ).format(glass=label, cells=required_cells)
                    )
                    checkbox.setCursor(Qt.CursorShape.ForbiddenCursor)
                checked = bool(glass in selected_glasses and is_calibrated)
                checkbox.setChecked(checked)
                if checked:
                    actual_selected.append(glass)
                checkbox.clicked.connect(
                    lambda checked, g=glass: self._on_pf_target_glass_toggled(g, checked)
                )
                row = 0
                col = glass - 1
                self.pf_targets_layout.addWidget(
                    checkbox,
                    row,
                    col,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                )
                self._pf_target_checkboxes[glass] = checkbox
            self.pf_targets_layout.setColumnStretch(count, 1)

            if actual_selected != selected_glasses:
                self.settings["pf_selected_glasses"] = list(actual_selected)
                selected_glasses = list(actual_selected)
                self.save_settings()

        self._update_pf_targets_summary(selected=len(selected_glasses), total=count)

        if hasattr(self, "chk_pf_show_frames"):
            self.chk_pf_show_frames.blockSignals(True)
            self.chk_pf_show_frames.setChecked(
                bool(self.settings.get("pf_show_preview_frames", False))
            )
            self.chk_pf_show_frames.blockSignals(False)

        self._style_pf_multi_glass_controls()
        self._schedule_smooth_content_resize(force=True)

    def _update_pf_targets_summary(self, selected=None, total=None):
        if not hasattr(self, "lbl_pf_targets_summary"):
            return

        if total is None:
            total = self._get_pf_glasses_count()
        if selected is None:
            selected = len(self._get_pf_selected_glasses())

        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        text = t.get(
            "calc_targets_selected",
            "Включено пресетов: {selected}/{total}",
        ).format(selected=int(selected), total=int(total))

        uncalibrated = self._get_pf_uncalibrated_glasses(total)
        if uncalibrated:
            text += " | " + t.get(
                "calc_targets_need_calib_short",
                "Не откалиброваны пресеты: {glasses}",
            ).format(glasses=", ".join(str(g) for g in uncalibrated))

        self.lbl_pf_targets_summary.setText(text)

    def _style_pf_multi_glass_controls(self):
        scale = self.settings.get("scale", self.base_scale)
        scale = max(60, min(120, int(scale)))
        ratio = scale / float(self.base_scale)
        sc = scale / 100.0
        compact_mode = scale < 100
        label_pt = max(7, int(8 * ratio))
        input_pt = max(7, int(8 * ratio))
        radius = max(4, int(4 * ratio))
        wrap_w = max(62 if compact_mode else 72, int(82 * sc))
        btn_w = max(12 if compact_mode else 14, int(15 * sc))
        field_h = max(18 if compact_mode else 24, int(24 * sc))
        btn_h = max(16 if compact_mode else 20, int(field_h - 2))
        inner_w = max(26, wrap_w - (btn_w * 2) - 6)

        for name in (
            "lbl_pf_glasses_title",
            "lbl_pf_calib_glass_title",
            "lbl_pf_targets_title",
            "lbl_pf_targets_summary",
        ):
            widget = getattr(self, name, None)
            if widget:
                color = "#666" if name == "lbl_pf_targets_summary" else "#888"
                widget.setStyleSheet(f"color: {color}; font-size: {label_pt}pt;")

        if hasattr(self, "sb_pf_count_wrap"):
            self.sb_pf_count_wrap.setStyleSheet(
                "QFrame#PfSpinWrap { background: #1A1A1A; border: 1px solid #333; border-radius: 4px; }"
                "QFrame#PfSpinWrap:disabled { background: #0F0F0F; border: 1px solid #222; }"
            )

        if hasattr(self, "sb_pf_count"):
            self.sb_pf_count.setStyleSheet(
                "QSpinBox#pfSpinInner { background: transparent; color: white; border: none; padding: 0px 2px; selection-background-color: transparent; selection-color: white; }"
                "QSpinBox#pfSpinInner:focus { outline: none; }"
                "QSpinBox#pfSpinInner:disabled { color: #555; }"
            )

            self.sb_pf_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sb_pf_count.setFixedHeight(field_h)
            self.sb_pf_count.setMinimumWidth(inner_w)
            self.sb_pf_count.setMaximumWidth(inner_w)

            if hasattr(self, "sb_pf_count_wrap"):
                self.sb_pf_count_wrap.setFixedHeight(field_h)
                self.sb_pf_count_wrap.setFixedWidth(wrap_w)

            if hasattr(self, "lbl_pf_glasses_title"):
                self.lbl_pf_glasses_title.setMinimumHeight(field_h)

            if hasattr(self, "lbl_pf_calib_glass_title"):
                self.lbl_pf_calib_glass_title.setMinimumHeight(field_h)

        for btn_name in ("btn_pf_count_dec", "btn_pf_count_inc"):
            btn = getattr(self, btn_name, None)
            if btn:
                btn.setStyleSheet(
                    "QPushButton#PfSpinStepBtn { background: #2a2a2a; color: #cfcfcf; border: 1px solid #333; border-radius: 3px; padding: 0px; font-weight: bold; font-size: 9pt; }"
                    "QPushButton#PfSpinStepBtn:hover { background: #3a3a3a; }"
                    "QPushButton#PfSpinStepBtn:disabled { background: #1a1a1a; color: #555; border: 1px solid #222; }"
                )
                btn.setFixedSize(btn_w, btn_h)

        if hasattr(self, "cb_pf_calib_glass"):
            self.cb_pf_calib_glass.setStyleSheet(
                f"QComboBox {{ background: #1A1A1A; color: white; border: 1px solid #333; border-radius: {radius}px; font-size: {input_pt}pt; padding: 1px 4px; }}"
                "QComboBox:focus { border: 1px solid #333; outline: none; }"
                "QComboBox::drop-down { border: none; }"
            )
            self.cb_pf_calib_glass.setFixedHeight(field_h)

        if hasattr(self, "chk_pf_show_frames"):
            self.chk_pf_show_frames.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.chk_pf_show_frames.setStyleSheet(
                f"QCheckBox {{ color: #888; font-size: {label_pt}pt; spacing: 5px; margin: 0px; padding: 0px; }}"
                "QCheckBox:focus { outline: none; }"
                "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; margin-right: 5px; }"
                f"QCheckBox::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({self._posmode_checkmark_path_css}); }}"
                "QCheckBox::indicator:unchecked { background: #2A2A2A; border: 1px solid #444; image: none; }"
            )

        if hasattr(self, "btn_pf_preview"):
            self.btn_pf_preview.setStyleSheet(
                f"background: #2A2A2A; color: #8E8E8E; border: 1px solid #3A3A3A; border-radius: {radius}px; font-size: {label_pt}pt; padding: 2px 6px;"
            )

        for checkbox in getattr(self, "_pf_target_checkboxes", {}).values():
            if checkbox:
                checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                if bool(checkbox.property("uncalibrated")):
                    checkbox.setStyleSheet(
                        f"QCheckBox {{ color: #4E4E4E; font-size: {label_pt}pt; spacing: 4px; margin: 0px; padding: 0px; }}"
                        "QCheckBox:focus { outline: none; }"
                        "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #2A2A2A; background: #101010; margin-right: 4px; }"
                        "QCheckBox::indicator:checked { background: #101010; border: 1px solid #2A2A2A; image: none; }"
                    )
                else:
                    checkbox.setStyleSheet(
                        f"QCheckBox {{ color: #888; font-size: {label_pt}pt; spacing: 4px; margin: 0px; padding: 0px; }}"
                        "QCheckBox:focus { outline: none; }"
                        "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #444; background: #2A2A2A; margin-right: 4px; }"
                        f"QCheckBox::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({self._posmode_checkmark_path_css}); }}"
                        "QCheckBox::indicator:unchecked { image: none; }"
                    )

                # Size from actual rendered hint so double-digit labels (10-12) stay fully visible.
                try:
                    min_w = max(34, int(34 * ratio))
                    hint_w = int(checkbox.sizeHint().width())
                    target_w = max(min_w, hint_w + max(4, int(6 * ratio)))
                    checkbox.setFixedWidth(target_w)

                    hint_h = int(checkbox.sizeHint().height())
                    checkbox.setFixedHeight(max(18, hint_h))
                except Exception:
                    checkbox.setFixedWidth(max(34, int(34 * ratio)))

    def _on_pf_glasses_count_changed(self, value):
        old_count = self._get_pf_glasses_count()
        prev_status_text = self.lbl_status.text() if hasattr(self, "lbl_status") else ""
        count = self._clamp_pf_glasses_count(value)
        self.settings["pf_glasses_count"] = count

        active_glass = self._get_pf_active_glass()
        if active_glass > count:
            active_glass = count
            self.settings["pf_active_glass"] = active_glass

        selected = [g for g in self._get_pf_selected_glasses() if g <= count]
        self.settings["pf_selected_glasses"] = selected

        self.settings[self._get_shared_active_points_key()] = self._get_pf_points_for_glass(active_glass)
        if self._is_shared_menu_preset_terminal():
            open_key, close_key = self._get_menu_terminal_point_keys()
            menu_open, menu_close = self._get_menu_points_for_glass(active_glass)
            if open_key:
                self.settings[open_key] = list(menu_open) if menu_open else None
            if close_key:
                self.settings[close_key] = list(menu_close) if menu_close else None
        self.save_settings()

        self._update_pf_multi_glass_ui()
        self.update_calibration_status()
        self._schedule_smooth_content_resize(force=True)

        if count > old_count:
            new_uncalibrated = [
                g
                for g in range(old_count + 1, count + 1)
                if not self._is_pf_glass_calibrated(g)
            ]
            if new_uncalibrated:
                t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                self._set_transient_status_then_neutral(
                    t.get(
                        "calc_new_glasses_need_calib",
                        "Новые пресеты не откалиброваны: {glasses}",
                    ).format(glasses=", ".join(str(g) for g in new_uncalibrated)),
                    prev_status_text
                    or t.get("calc_ready_to_apply", "Готово к выставлению"),
                    status_color="#FF9F0A",
                    delay_ms=6000,
                )

        if bool(self.settings.get("pf_show_preview_frames", False)):
            self._flash_pf_preview_frames(self._get_pf_selected_glasses())

    def _on_pf_calibration_glass_changed(self, index):
        if not hasattr(self, "cb_pf_calib_glass"):
            return
        glass = self.cb_pf_calib_glass.currentData()
        if glass is None:
            glass = index + 1
        self._set_pf_active_glass(glass, save=True)
        self.update_calibration_status()

        if bool(self.settings.get("pf_show_preview_frames", False)):
            self._flash_pf_preview_frames([int(glass)])

    def _on_pf_target_glass_toggled(self, glass, checked):
        checkboxes = getattr(self, "_pf_target_checkboxes", {})
        clicked_cb = checkboxes.get(int(glass))
        if clicked_cb and bool(clicked_cb.property("uncalibrated")):
            clicked_cb.blockSignals(True)
            clicked_cb.setChecked(False)
            clicked_cb.blockSignals(False)

            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            neutral = self.lbl_status.text() if hasattr(self, "lbl_status") else ""
            self._set_transient_status_then_neutral(
                t.get(
                    "calc_glass_click_need_calib",
                    "Чтобы включить {glass}, сначала откалибруй его",
                ).format(glass=self._pf_glass_label(glass)),
                neutral or t.get("calc_ready_to_apply", "Готово к выставлению"),
                status_color="#FF9F0A",
                delay_ms=3000,
            )
            return

        selected = [
            g
            for g, cb in checkboxes.items()
            if cb and cb.isChecked() and not bool(cb.property("uncalibrated"))
        ]

        self._set_pf_selected_glasses(selected, save=True)
        self._update_pf_targets_summary(selected=len(selected), total=self._get_pf_glasses_count())
        self._schedule_smooth_content_resize(force=True)

        if bool(self.settings.get("pf_show_preview_frames", False)):
            self._flash_pf_preview_frames(selected)

    def _toggle_all_pf_target_glasses(self):
        checkboxes = getattr(self, "_pf_target_checkboxes", {})
        if not checkboxes:
            return

        uncalibrated = [
            int(g)
            for g, cb in checkboxes.items()
            if cb and bool(cb.property("uncalibrated"))
        ]
        eligible = [
            int(g)
            for g, cb in checkboxes.items()
            if cb and not bool(cb.property("uncalibrated"))
        ]

        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        if not eligible:
            neutral = self.lbl_status.text() if hasattr(self, "lbl_status") else ""
            missing = ", ".join(self._pf_glass_label(g) for g in sorted(uncalibrated))
            self._set_transient_status_then_neutral(
                t.get(
                    "calc_status_missing_glasses",
                    "Не откалиброваны пресеты: {glasses}",
                ).format(glasses=missing or "-"),
                neutral or t.get("calc_ready_to_apply", "Готово к выставлению"),
                status_color="#FF9F0A",
                delay_ms=3000,
            )
            return

        all_selected = bool(eligible) and all(
            checkboxes[g].isChecked() for g in eligible if g in checkboxes
        )
        new_selected = [] if all_selected else sorted(eligible)

        for g, cb in checkboxes.items():
            if not cb:
                continue
            should_check = int(g) in new_selected and not bool(cb.property("uncalibrated"))
            cb.blockSignals(True)
            cb.setChecked(bool(should_check))
            cb.blockSignals(False)

        self._set_pf_selected_glasses(new_selected, save=True)
        self._update_pf_targets_summary(
            selected=len(new_selected), total=self._get_pf_glasses_count()
        )
        self._schedule_smooth_content_resize(force=True)

        if uncalibrated and new_selected:
            neutral = self.lbl_status.text() if hasattr(self, "lbl_status") else ""
            skipped = ", ".join(self._pf_glass_label(g) for g in sorted(uncalibrated))
            self._set_transient_status_then_neutral(
                t.get(
                    "calc_status_skip_missing_glasses",
                    "Пропускаю не откалиброванные пресеты: {glasses}",
                ).format(glasses=skipped),
                neutral or t.get("calc_ready_to_apply", "Готово к выставлению"),
                status_color="#FF9F0A",
                delay_ms=2500,
            )

        if bool(self.settings.get("pf_show_preview_frames", False)):
            if new_selected:
                self._flash_pf_preview_frames(new_selected)
            else:
                self._clear_pf_preview_frames()

    def _on_pf_preview_toggle_changed(self, checked):
        self.settings["pf_show_preview_frames"] = bool(checked)
        self.save_settings()
        if checked:
            self._flash_pf_preview_frames(self._get_pf_selected_glasses())
        else:
            self._clear_pf_preview_frames()

    def _clear_pf_preview_frames(self):
        self._pf_preview_token += 1
        for frame in self._pf_preview_frames:
            try:
                frame.hide()
            except Exception:
                pass

    def _get_native_monitor_rects(self):
        rects = []
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            MONITORENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(RECT),
                ctypes.c_longlong,
            )

            def _enum_monitor(_monitor, _hdc, lprc, _data):
                try:
                    r = lprc.contents
                    rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
                except Exception:
                    pass
                return 1

            cb = MONITORENUMPROC(_enum_monitor)
            user32.EnumDisplayMonitors(0, 0, cb, 0)
        except Exception:
            pass
        return rects

    def _native_to_qt_global(self, x, y):
        try:
            px = float(x)
            py = float(y)
        except Exception:
            return int(x), int(y)

        try:
            native_rects = self._get_native_monitor_rects()
            qt_screens = list(QApplication.screens() or [])
            if native_rects and qt_screens and len(native_rects) == len(qt_screens):
                native_sorted = sorted(native_rects, key=lambda r: (int(r[1]), int(r[0])))
                qt_sorted = sorted(
                    qt_screens,
                    key=lambda s: (int(s.geometry().y()), int(s.geometry().x())),
                )

                for native_rect, screen in zip(native_sorted, qt_sorted):
                    left, top, right, bottom = native_rect
                    if left <= px < right and top <= py < bottom:
                        geom = screen.geometry()
                        native_w = max(1.0, float(right - left))
                        native_h = max(1.0, float(bottom - top))
                        qx = float(geom.x()) + (px - float(left)) * (
                            float(geom.width()) / native_w
                        )
                        qy = float(geom.y()) + (py - float(top)) * (
                            float(geom.height()) / native_h
                        )
                        return int(round(qx)), int(round(qy))
        except Exception:
            pass

        try:
            for screen in QApplication.screens() or []:
                geom = screen.geometry()
                dpr = float(screen.devicePixelRatio() or 1.0)
                native_x = geom.x() * dpr
                native_y = geom.y() * dpr
                native_w = geom.width() * dpr
                native_h = geom.height() * dpr
                if (
                    native_x <= px <= native_x + native_w
                    and native_y <= py <= native_y + native_h
                ):
                    qx = geom.x() + (px - native_x) / max(0.1, dpr)
                    qy = geom.y() + (py - native_y) / max(0.1, dpr)
                    return int(round(qx)), int(round(qy))
        except Exception:
            pass

        try:
            screen = QApplication.primaryScreen()
            geom = screen.geometry() if screen is not None else None
            if not self._ensure_pyautogui_module():
                native = None
            else:
                native = pyautogui.size()
            if geom and native and geom.width() > 0 and geom.height() > 0:
                ratio_x = float(native.width) / float(geom.width())
                ratio_y = float(native.height) / float(geom.height())
                qx = float(geom.x()) + px / max(0.1, ratio_x)
                qy = float(geom.y()) + py / max(0.1, ratio_y)
                return int(round(qx)), int(round(qy))
        except Exception:
            pass

        return int(round(px)), int(round(py))

    def _flash_pf_preview_frames(self, glasses=None):
        target_glasses = [int(g) for g in (glasses or []) if str(g).isdigit()]
        if not target_glasses:
            target_glasses = self._get_pf_selected_glasses()

        geometries = []
        for glass in target_glasses:
            if self._is_menu_terminal():
                menu_open, _ = self._get_menu_points_for_glass(glass)
                points = self._get_pf_points_for_glass(glass)
                if not menu_open or not points:
                    continue
                qt_points = [self._native_to_qt_global(int(p[0]), int(p[1])) for p in points]
                xs = [int(p[0]) for p in qt_points]
                ys = [int(p[1]) for p in qt_points]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                pad_x = 34
                pad_y = 8 if self._is_vataga_terminal() else 16
                frame_w = max(34, (max_x - min_x) + pad_x * 2)
                frame_h = max(20, (max_y - min_y) + pad_y * 2)

                cx, cy = self._native_to_qt_global(int(menu_open[0]), int(menu_open[1]))
                # For Tiger/Vataga: center the menu frame on the captured order-book cell.
                x = int(cx - frame_w / 2)
                y_shift = 6 if self._is_vataga_terminal() else 0
                y = int(cy - frame_h / 2 + y_shift)
                w = int(frame_w)
                h = int(frame_h)
                geometries.append((x, y, w, h))
            else:
                points = self._get_pf_points_for_glass(glass)
                if not points:
                    continue
                qt_points = [self._native_to_qt_global(int(p[0]), int(p[1])) for p in points]
                xs = [int(p[0]) for p in qt_points]
                ys = [int(p[1]) for p in qt_points]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                pad_x = 34
                pad_y = 16
                x = min_x - pad_x
                y = min_y - pad_y
                w = max(34, (max_x - min_x) + pad_x * 2)
                h = max(20, (max_y - min_y) + pad_y * 2)
                geometries.append((x, y, w, h))

        if not geometries:
            return

        while len(self._pf_preview_frames) < len(geometries):
            self._pf_preview_frames.append(GlassPreviewFrame())

        token = self._pf_preview_token + 1
        self._pf_preview_token = token

        def _toggle(show):
            if token != self._pf_preview_token:
                return
            for idx, frame in enumerate(self._pf_preview_frames):
                if idx < len(geometries):
                    if show:
                        x, y, w, h = geometries[idx]
                        frame.setGeometry(int(x), int(y), int(w), int(h))
                        frame.show()
                        frame.raise_()
                    else:
                        frame.hide()
                else:
                    frame.hide()

        blink_pattern = [True, False, True, False, True, False]
        delay_step = 130
        for idx, visible in enumerate(blink_pattern):
            QTimer.singleShot(idx * delay_step, lambda v=visible: _toggle(v))
        QTimer.singleShot(len(blink_pattern) * delay_step + 50, lambda: _toggle(False))

    def _on_pf_preview_clicked(self):
        self._flash_pf_preview_frames(self._get_pf_selected_glasses())

    def init_calculator_tab(self):
        init_calculator_tab(self)
        if hasattr(self, "cells_table"):
            self.cells_table.setItemDelegateForColumn(
                0, CellsLabelDarkDelegate(self, self.cells_table)
            )

    def refresh_labels(self):
        lang = self.settings.get("lang", "ru")
        t = TRANS.get(lang, TRANS["ru"])
        self.lbl_dep_title.setText(t["dep"])
        self.lbl_risk_title.setText(t["risk"])
        self.lbl_stop_title.setText(t["stop"])
        self._apply_volume_title_style(
            dimmed=bool(self.settings.get("pos_mode_enabled", False))
        )
        if hasattr(self, "tabs"):
            self.tabs.setTabText(0, t.get("tab_calc", "Калькулятор"))
            self.tabs.setTabText(1, t.get("tab_casc", "Каскады"))
        self.refresh_calculator_labels()
        if hasattr(self, "tab_cascade"):
            self.tab_cascade.refresh_labels()

    def refresh_calculator_labels(self):
        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        if hasattr(self, "chk_pos_mode"):
            self.chk_pos_mode.setText(t["calc_pos_mode"])
        if hasattr(self, "lbl_pos_vol_title"):
            self.lbl_pos_vol_title.setText(t["calc_in_position"])
        if hasattr(self, "lbl_pos_risk_title"):
            self.lbl_pos_risk_title.setText(t["calc_risk_percent"])
        if hasattr(self, "lbl_pos_stop_title"):
            self.lbl_pos_stop_title.setText(t["calc_stop_percent_entry"])
        if hasattr(self, "lbl_pos_stop_now_title"):
            self.lbl_pos_stop_now_title.setText(t["calc_stop_percent_now"])
        if hasattr(self, "lbl_pos_adjust"):
            self.lbl_pos_adjust.setText(t["calc_recommendation"])
        if hasattr(self, "btn_reverse_cells"):
            self.btn_reverse_cells.setToolTip(t["calc_reverse_cells"])
        if hasattr(self, "btn_toggle_all_cells"):
            self.btn_toggle_all_cells.setText(t["calc_toggle_all_btn"])
            self.btn_toggle_all_cells.setToolTip(t["calc_toggle_all"])
        if hasattr(self, "lbl_cells_count_title"):
            self.lbl_cells_count_title.setText(t.get("calc_cells_count", "Ячеек:"))
        if hasattr(self, "btn_pf_targets_toggle_all"):
            self.btn_pf_targets_toggle_all.setText(
                t.get("calc_targets_toggle_all_btn", t.get("calc_toggle_all_btn", "Все"))
            )
            self.btn_pf_targets_toggle_all.setToolTip(
                t.get("calc_targets_toggle_all", "Вкл/выкл все пресеты")
            )
        if hasattr(self, "lbl_min_order_title"):
            self.lbl_min_order_title.setText(t["calc_min_order"])
        if hasattr(self, "lbl_calc_type_title"):
            self.lbl_calc_type_title.setText(t["calc_type"])
        if hasattr(self, "cb_distribution"):
            current_idx = self.cb_distribution.currentIndex()
            self.cb_distribution.blockSignals(True)
            self.cb_distribution.clear()
            self.cb_distribution.addItems(
                [
                    t["calc_dist_uniform"],
                    t["calc_dist_desc"],
                    t["calc_dist_manual"],
                ]
            )
            self.cb_distribution.setCurrentIndex(max(0, current_idx))
            self.cb_distribution.blockSignals(False)
        if hasattr(self, "cells_table"):
            self.cells_table.setHorizontalHeaderLabels(
                [
                    t["calc_table_cells"],
                    t["calc_table_volumes"],
                    t["calc_table_percent"],
                ]
            )
            self.update_cells_labels()
        if hasattr(self, "btn_submit"):
            self.btn_submit.setText(t["calc_apply"])
        if hasattr(self, "lbl_pf_glasses_title"):
            self.lbl_pf_glasses_title.setText(t.get("calc_glasses_count", "Пресетов объёмов:"))
        if hasattr(self, "lbl_pf_calib_glass_title"):
            self.lbl_pf_calib_glass_title.setText(
                t.get("calc_calib_glass", "Калибровать пресет:")
            )
        if hasattr(self, "lbl_pf_targets_title"):
            self.lbl_pf_targets_title.setText(t.get("calc_targets", "Выставить в:"))
        if hasattr(self, "lbl_pf_targets_summary"):
            self._update_pf_targets_summary()
        if hasattr(self, "chk_pf_show_frames"):
            self.chk_pf_show_frames.setText(
                t.get("calc_show_frames", "Показать рамку")
            )
        if hasattr(self, "btn_pf_preview"):
            self.btn_pf_preview.setText(t.get("calc_preview_btn", "ПРЕВЬЮ"))
        if hasattr(self, "btn_dep_refresh"):
            self.btn_dep_refresh.setText(t.get("dep_refresh", "↻"))
            self.btn_dep_refresh.setToolTip(
                t.get("dep_refresh_tip", "Обновить депозит с биржи")
            )
        self._update_pf_multi_glass_ui()
        self._sync_cells_count_controls(refresh_table=False)
        self.update_position_adjustment_info()
        self.update_calibration_status()

    # Метод format_deposit_input удален - депозит не форматируется автоматически

    def apply_min_order_precision(self):
        prec_min_order = 0

        if hasattr(self, "inp_min_order"):
            if prec_min_order == 0:
                rx = r"[0-9]*"
            else:
                rx = rf"[0-9]*([.,][0-9]{{0,{prec_min_order}}})?"
            self.inp_min_order.setValidator(
                QRegularExpressionValidator(QRegularExpression(rx))
            )

            # Используем текущее значение из поля, если оно не пусто
            # Иначе - из settings, иначе - дефолтное 6
            try:
                text_val = self.inp_min_order.text().strip()
                if text_val:
                    # Если текст не пуст, используем его
                    current_val = float(text_val.replace(",", "."))
                else:
                    # Если текст пуст, используем значение из settings
                    current_val = float(self.settings.get("scalp_min_order", 6))
            except Exception:
                current_val = float(self.settings.get("scalp_min_order", 6))

            self.inp_min_order.setText(str(int(round(current_val))))

        if hasattr(self, "tab_cascade") and hasattr(
            self.tab_cascade, "apply_min_order_precision"
        ):
            self.tab_cascade.apply_min_order_precision(prec_min_order)

    def update_calc(self):
        try:
            p_dep = self.settings.get("prec_dep", 2)
            p_risk = self.settings.get("prec_risk", 2)
            p_fee = self.settings.get("prec_fee", 3)
            p_vol = self._get_standard_volume_precision()
            p_lev = self.settings.get("prec_lev", 1)

            d = float(self.inp_dep.text().replace(",", ".") or 0)
            r = float(self.inp_risk.text().replace(",", ".") or 0)
            s = float(self.inp_stop.text().replace(",", ".") or 0)

            f_perc, use_fee = self._get_effective_fee_percent()
            cash_risk, vol, lev, comm_usd = calculate_risk_data(d, r, s, f_perc)

            self.current_vol = vol
            # Форматирование депозита с сокращениями
            hint_text = self.format_hint_no_decimals(d)
            self.lbl_hint.setText(hint_text)

            vol_str = f"{vol:,.{p_vol}f}".replace(",", " ").replace(".", ",")
            self.lbl_vol.setText(vol_str)

            t = TRANS[self.settings.get("lang", "ru")]
            dimmed = self.settings.get("pos_mode_enabled", False)
            info_font_pt = self._top_info_font_pt()
            self.lbl_info.setText(
                get_info_html(
                    cash_risk,
                    lev,
                    comm_usd,
                    t,
                    p_risk,
                    p_fee,
                    p_lev,
                    font_size=info_font_pt,
                    dimmed=dimmed,
                    fee_enabled=use_fee,
                )
            )
            self._update_risk_recommendation(r, s, lev, use_fee)

            # Обновляем объемы в таблице ячеек
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()

            sc = self.settings.get("scale", 100) / 100.0
            color = "#FF3B30" if r >= 10.0 else "#FF9F0A"
            if self.settings.get("pos_mode_enabled", False):
                self.lbl_vol.setStyleSheet(
                    "color: #555; font-size: 11pt; font-weight: bold; border: 1px solid #222; "
                    "border-radius: 4px; padding: 4px; background: #0F0F0F;"
                )
            else:
                self.lbl_vol.setStyleSheet(
                    f"color: {color}; font-size: 11pt; font-weight: bold; border: 1px solid #333; "
                    "border-radius: 4px; padding: 4px; background: #1A1A1A;"
                )

            if (
                hasattr(self, "tab_cascade")
                and hasattr(self, "tabs")
                and self.tabs.currentIndex() == 1
            ):
                self.tab_cascade.recalc_table()

            self.update_position_adjustment_info()
            self._schedule_smooth_content_resize()

            self.settings.update({"deposit": d, "risk": r, "stop": s})
            self.save_settings()
        except Exception as e:
            print(f"Error: {e}")

    def _get_effective_fee_percent(self):
        use_fee = bool(self.settings.get("use_fee", True))
        if not use_fee:
            return 0.0, False

        try:
            fee_taker = float(self.settings.get("fee_taker", 0.0) or 0.0)
        except Exception:
            fee_taker = 0.0

        try:
            fee_maker = float(self.settings.get("fee_maker", 0.0) or 0.0)
        except Exception:
            fee_maker = 0.0

        fee_taker = max(0.0, fee_taker)
        fee_maker = max(0.0, fee_maker)
        return fee_taker + fee_maker, True

    def _build_risk_warning_text(self, risk_percent, stop_percent, leverage, use_fee):
        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        warnings = []

        try:
            risk_value = float(risk_percent)
        except Exception:
            risk_value = 0.0

        try:
            stop_value = float(stop_percent)
        except Exception:
            stop_value = 0.0

        try:
            lev_value = float(leverage)
        except Exception:
            lev_value = 0.0

        fee_total = 0.0
        if bool(use_fee):
            try:
                fee_total = float(self.settings.get("fee_taker", 0.0)) + float(
                    self.settings.get("fee_maker", 0.0)
                )
            except Exception:
                fee_total = 0.0
        effective_stop = abs(max(0.0, stop_value + fee_total))

        if risk_value >= 10.0:
            warnings.append(t["risk_warn_high"])
            target_risk = min(5.0, max(1.0, risk_value / 2.0))
            target_text = f"{target_risk:.2f}".rstrip("0").rstrip(".")
            warnings.append(t["risk_warn_reduce"].format(target=target_text))

        liq_move_est = abs(100.0 / lev_value) if lev_value > 0 else 0.0
        liq_warn_threshold = liq_move_est * 0.95
        if liq_move_est > 0 and effective_stop >= liq_warn_threshold:
            liq_text = f"{liq_move_est:.2f}".rstrip("0").rstrip(".")
            warnings.append(t["risk_warn_liq"].format(liq=liq_text))

        if (not bool(use_fee)) and risk_value >= 10.0:
            warnings.append(t["risk_warn_fee_off"])

        if warnings:
            intro = t.get("risk_warn_intro", "⚠")
            return f"{intro}  " + "  ".join(warnings)

        return ""

    def _update_risk_recommendation(self, risk_percent, stop_percent, leverage, use_fee):
        if not hasattr(self, "lbl_risk_warning"):
            return

        warning_text = self._build_risk_warning_text(
            risk_percent, stop_percent, leverage, use_fee
        )
        try:
            risk_value = float(risk_percent)
        except Exception:
            risk_value = 0.0
        warn_pt = self._scaled_pt(8.8 if risk_value >= 10.0 else 7.5)
        self.lbl_risk_warning.setStyleSheet(f"color: #FF6B6B; font-size: {warn_pt}pt;")
        if warning_text:
            self.lbl_risk_warning.setText(warning_text)
            self.lbl_risk_warning.setVisible(True)
        else:
            self.lbl_risk_warning.setText("")
            self.lbl_risk_warning.setVisible(False)

    def _update_position_risk_recommendation(
        self, risk_percent, stop_percent, leverage, use_fee
    ):
        if not hasattr(self, "lbl_pos_warning"):
            return

        warning_text = self._build_risk_warning_text(
            risk_percent, stop_percent, leverage, use_fee
        )
        try:
            risk_value = float(risk_percent)
        except Exception:
            risk_value = 0.0
        warn_pt = self._scaled_pt(8.8 if risk_value >= 10.0 else 7.5)
        self.lbl_pos_warning.setStyleSheet(f"color: #FF6B6B; font-size: {warn_pt}pt;")
        if warning_text:
            self.lbl_pos_warning.setText(warning_text)
            self.lbl_pos_warning.setVisible(True)
        else:
            self.lbl_pos_warning.setText("")
            self.lbl_pos_warning.setVisible(False)

    def _build_position_risk_cash_html(
        self,
        target_risk_cash_text,
        current_risk_cash_text="",
        current_risk_pct_text="",
    ):
        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        font_pt = self._position_hint_font_pt(8)
        label_color = "#FFFFFF"
        risk_value_color = "#FF453A"
        current_risk_value_color = "#FF453A"
        sep_color = "#666"

        risk_label = t.get("pos_risk_cash_label", "Риск сделки в $:")
        current_risk_label = t.get("pos_current_risk_label", "Текущий риск:")

        if current_risk_cash_text:
            current_risk_right = f"${current_risk_cash_text}"
            if current_risk_pct_text:
                current_risk_right += f" ({current_risk_pct_text}%)"
            left_html = (
                f"<span style='color: {label_color}; font-size: {font_pt}pt;'>{risk_label} </span>"
                f"<b style='color: {risk_value_color}; font-size: {font_pt}pt;'>${target_risk_cash_text}</b>"
                f"<span style='color: {sep_color};'>  |  </span>"
                f"<span style='color: {label_color}; font-size: {font_pt}pt;'>{current_risk_label} </span>"
                f"<b style='color: {current_risk_value_color}; font-size: {font_pt}pt;'>{current_risk_right}</b>"
            )
        else:
            left_html = (
                f"<span style='color: {label_color}; font-size: {font_pt}pt;'>{risk_label} </span>"
                f"<b style='color: {risk_value_color}; font-size: {font_pt}pt;'>${target_risk_cash_text}</b>"
            )

        return (
            "<div style='line-height: 120%; white-space: nowrap;'>"
            f"{left_html}"
            "</div>"
        )

    def _set_position_action_chip(self, action=None, delta_text=""):
        if not hasattr(self, "lbl_pos_action_chip"):
            return

        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        ratio = self._scale_ratio()
        font_pt = self._position_hint_font_pt(8)
        border_radius = max(3, int(3 * ratio))
        pad_h = max(3, int(4 * ratio))

        if action == "add":
            label = t.get("pos_add_label", "Добор:")
            color = "#38BE1D"
        elif action == "reduce":
            label = t.get("pos_reduce_label", "Сокращение:")
            color = "#FF453A"
        else:
            self.lbl_pos_action_chip.setText("")
            self.lbl_pos_action_chip.setVisible(False)
            return

        self.lbl_pos_action_chip.setText(f"{label} {delta_text}")
        self.lbl_pos_action_chip.setStyleSheet(
            f"color: {color}; font-size: {font_pt}pt; border: 1px solid {color}; "
            f"border-radius: {border_radius}px; padding: 0px {pad_h}px;"
        )
        self.lbl_pos_action_chip.setVisible(True)

    def _build_position_target_html(self, target_vol_text, target_lev_text):
        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        font_pt = self._position_hint_font_pt(8)
        label_color = "#FFFFFF"
        target_value_color = "#FF9F0A"
        leverage_value_color = "#B388FF"
        sep_color = "#666"

        target_label = t.get("pos_target_label", "Целевой объём:")
        leverage_label = t.get("lev", "Плечо:")

        return (
            "<div style='line-height: 120%; white-space: nowrap;'>"
            f"<span style='color: {label_color}; font-size: {font_pt}pt;'>{target_label} </span>"
            f"<b style='color: {target_value_color}; font-size: {font_pt}pt;'>{target_vol_text}</b>"
            f"<span style='color: {sep_color};'>  |  </span>"
            f"<span style='color: {label_color}; font-size: {font_pt}pt;'>{leverage_label} </span>"
            f"<b style='color: {leverage_value_color}; font-size: {font_pt}pt;'>{target_lev_text}x</b>"
            "</div>"
        )

    def schedule_update_calc(self):
        if hasattr(self, "_calc_update_timer"):
            self._calc_update_timer.start(40)
        else:
            self.update_calc()

    def update_position_adjustment_info(self):
        if not hasattr(self, "lbl_pos_adjust"):
            return

        self.position_target_volume = 0.0

        if not bool(self.settings.get("pos_mode_enabled", False)):
            self.table_volume_override = 0.0
            self.pos_adjust_delta = 0.0
            self.pos_adjust_action = None
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_pos_adjust.setText(t["pos_mode_off"])
            self.lbl_pos_adjust.setStyleSheet(
                self._position_hint_style("#555", base_pt=7)
            )
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(t["pos_risk_cash_na"])
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style("#555", base_pt=7, with_padding=True)
                )
            self._set_position_action_chip(None)
            if hasattr(self, "lbl_pos_warning"):
                self.lbl_pos_warning.setText("")
                self.lbl_pos_warning.setVisible(False)
            if hasattr(self, "lbl_pos_stop_delta"):
                self.lbl_pos_stop_delta.setText("")
                self.lbl_pos_stop_delta.setVisible(False)
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()
            return

        self.pos_adjust_delta = 0.0
        self.pos_adjust_action = None

        p_vol = self._get_standard_volume_precision()
        p_adjust_vol = self._get_calc_volume_precision()
        p_risk = self.settings.get("prec_risk", 2)
        p_lev = self.settings.get("prec_lev", 1)

        try:
            pos_vol = float(self.inp_pos_vol.text().replace(",", ".") or 0)
        except Exception:
            pos_vol = 0.0

        if hasattr(self, "lbl_pos_vol_hint"):
            self.lbl_pos_vol_hint.setText(self.format_hint_no_decimals(pos_vol))

        try:
            pos_risk = float(self.inp_pos_risk.text().replace(",", ".") or 0)
        except Exception:
            pos_risk = 0.0

        try:
            pos_stop = float(self.inp_pos_stop.text().replace(",", ".") or 0)
        except Exception:
            pos_stop = 0.0

        try:
            pos_stop_now = float(self.inp_pos_stop_now.text().replace(",", ".") or 0)
        except Exception:
            pos_stop_now = 0.0

        try:
            deposit = float(self.inp_dep.text().replace(",", ".") or 0)
        except Exception:
            deposit = 0.0

        pos_vol = max(0.0, float(pos_vol))

        if pos_risk <= 0:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_pos_adjust.setText(t["pos_rec_risk"])
            self.lbl_pos_adjust.setStyleSheet(
                self._position_hint_style("#888", base_pt=7)
            )
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(t["pos_risk_cash_need"])
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style("#888", base_pt=8, with_padding=True)
                )
            self._set_position_action_chip(None)
            self.settings["pos_current_vol"] = self.inp_pos_vol.text()
            self.settings["pos_risk"] = self.inp_pos_risk.text()
            self.settings["pos_stop"] = self.inp_pos_stop.text()
            self.settings["pos_stop_now"] = self.inp_pos_stop_now.text()
            self.save_settings()
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()
            if hasattr(self, "lbl_pos_stop_delta"):
                self.lbl_pos_stop_delta.setText("")
                self.lbl_pos_stop_delta.setVisible(False)
            if hasattr(self, "lbl_pos_warning"):
                self.lbl_pos_warning.setText("")
                self.lbl_pos_warning.setVisible(False)
            return

        if pos_stop <= 0:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_pos_adjust.setText(t.get("pos_rec_stop_entry", t["pos_rec_stop"]))
            self.lbl_pos_adjust.setStyleSheet(
                self._position_hint_style("#888", base_pt=7)
            )
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(t["pos_risk_cash_need"])
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style("#888", base_pt=8, with_padding=True)
                )
            self._set_position_action_chip(None)
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()
            if hasattr(self, "lbl_pos_stop_delta"):
                self.lbl_pos_stop_delta.setText("")
                self.lbl_pos_stop_delta.setVisible(False)
            if hasattr(self, "lbl_pos_warning"):
                self.lbl_pos_warning.setText("")
                self.lbl_pos_warning.setVisible(False)
            return

        if pos_stop_now <= 0:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_pos_adjust.setText(t.get("pos_rec_stop_now", t["pos_rec_stop"]))
            self.lbl_pos_adjust.setStyleSheet(
                self._position_hint_style("#888", base_pt=7)
            )
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(t["pos_risk_cash_need"])
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style("#888", base_pt=8, with_padding=True)
                )
            self._set_position_action_chip(None)
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()
            if hasattr(self, "lbl_pos_stop_delta"):
                self.lbl_pos_stop_delta.setText("")
                self.lbl_pos_stop_delta.setVisible(False)
            if hasattr(self, "lbl_pos_warning"):
                self.lbl_pos_warning.setText("")
                self.lbl_pos_warning.setVisible(False)
            return

        f_perc, use_fee = self._get_effective_fee_percent()

        if deposit <= 0:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_pos_adjust.setText(t.get("pos_need_deposit", "Укажите депозит"))
            self.lbl_pos_adjust.setStyleSheet(
                self._position_hint_style("#888", base_pt=7)
            )
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(t["pos_risk_cash_need"])
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style("#888", base_pt=8, with_padding=True)
                )
            self._set_position_action_chip(None)
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()
            if hasattr(self, "lbl_pos_warning"):
                self.lbl_pos_warning.setText("")
                self.lbl_pos_warning.setVisible(False)
            return

        tolerance = max(1e-9, 10 ** (-(max(0, int(p_risk)) + 1)))

        # Deterministic in-position model:
        # - current risk is estimated by entry->stop distance
        # - add sizing is estimated by current->stop distance
        # - reduce sizing cuts existing position risk profile
        try:
            pos_calc = calculate_position_adjustment(
                deposit=deposit,
                target_risk_percent=pos_risk,
                current_volume=pos_vol,
                stop_entry_percent=pos_stop,
                stop_now_percent=pos_stop_now,
                fee_percent=f_perc,
                tolerance_cash=tolerance,
            )
        except Exception:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_pos_adjust.setText(t["pos_calc_error"])
            self.lbl_pos_adjust.setStyleSheet(
                self._position_hint_style("#FF9F0A", base_pt=7)
            )
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(t["pos_risk_cash_need"])
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style("#888", base_pt=8, with_padding=True)
                )
            self._set_position_action_chip(None)
            if hasattr(self, "cells_table"):
                self.update_cell_volumes()
            if hasattr(self, "lbl_pos_warning"):
                self.lbl_pos_warning.setText("")
                self.lbl_pos_warning.setVisible(False)
            return

        risk_cash = float(pos_calc.get("target_risk_cash", 0.0) or 0.0)
        current_risk_cash = float(pos_calc.get("current_risk_cash", 0.0) or 0.0)
        current_risk_percent = float(pos_calc.get("current_risk_percent", 0.0) or 0.0)
        max_vol_at_stop = float(pos_calc.get("target_volume", 0.0) or 0.0)
        action = str(pos_calc.get("action", "in_limit") or "in_limit")
        delta_abs = float(pos_calc.get("delta_abs", 0.0) or 0.0)

        risk_cash_text = f"{risk_cash:,.{p_risk}f}".replace(",", " ").replace(".", ",")
        current_risk_cash_text = f"{current_risk_cash:,.{p_risk}f}".replace(",", " ").replace(".", ",")
        current_risk_pct_text = (
            f"{current_risk_percent:,.2f}".replace(",", " ").replace(".", ",")
        )

        self.position_target_volume = float(max_vol_at_stop)
        target_vol_text = f"{max_vol_at_stop:,.{p_vol}f}".replace(",", " ").replace(
            ".", ","
        )
        target_lev = (max_vol_at_stop / deposit) if deposit > 0 else 0.0
        target_lev_text = f"{target_lev:,.{p_lev}f}".replace(",", " ").replace(
            ".", ","
        )
        target_with_lev_text = self._build_position_target_html(
            target_vol_text, target_lev_text
        )
        self._update_position_risk_recommendation(
            pos_risk, pos_stop_now, target_lev, use_fee
        )

        if hasattr(self, "lbl_pos_stop_delta"):
            self.lbl_pos_stop_delta.setText("")
            self.lbl_pos_stop_delta.setVisible(False)

        if action == "add":
            self.pos_adjust_delta = float(delta_abs)
            self.pos_adjust_action = "add"
            delta_text = f"{delta_abs:,.{p_adjust_vol}f}".replace(",", " ").replace(".", ",")
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(
                    self._build_position_risk_cash_html(
                        risk_cash_text,
                        current_risk_cash_text,
                        current_risk_pct_text,
                    )
                )
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style(with_padding=True)
                )
            self._set_position_action_chip("add", delta_text)
            self.lbl_pos_adjust.setText(target_with_lev_text)
            self.lbl_pos_adjust.setStyleSheet(self._position_hint_style())
        elif action == "reduce":
            self.pos_adjust_delta = float(delta_abs)
            self.pos_adjust_action = "reduce"
            delta_text = f"{delta_abs:,.{p_adjust_vol}f}".replace(",", " ").replace(".", ",")
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(
                    self._build_position_risk_cash_html(
                        risk_cash_text,
                        current_risk_cash_text,
                        current_risk_pct_text,
                    )
                )
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style(with_padding=True)
                )
            self._set_position_action_chip("reduce", delta_text)
            self.lbl_pos_adjust.setText(target_with_lev_text)
            self.lbl_pos_adjust.setStyleSheet(self._position_hint_style())
        else:
            self.pos_adjust_delta = 0.0
            self.pos_adjust_action = None
            if hasattr(self, "lbl_pos_risk_cash"):
                self.lbl_pos_risk_cash.setText(
                    self._build_position_risk_cash_html(
                        risk_cash_text,
                        current_risk_cash_text,
                        current_risk_pct_text,
                    )
                )
                self.lbl_pos_risk_cash.setStyleSheet(
                    self._position_hint_style(with_padding=True)
                )
            self._set_position_action_chip(None)
            self.lbl_pos_adjust.setText(target_with_lev_text)
            self.lbl_pos_adjust.setStyleSheet(self._position_hint_style())
        self.settings["pos_current_vol"] = self.inp_pos_vol.text()
        self.settings["pos_risk"] = self.inp_pos_risk.text()
        self.settings["pos_stop"] = self.inp_pos_stop.text()
        self.settings["pos_stop_now"] = self.inp_pos_stop_now.text()
        self.save_settings()

        if hasattr(self, "cells_table"):
            self.update_cell_volumes()

        self._schedule_smooth_content_resize(force=True)

    def select_position_target_cell(self, cell_num):
        if not hasattr(self, "pos_target_cell_buttons"):
            return
        cell_num = max(1, min(5, int(cell_num)))
        for idx, btn in enumerate(self.pos_target_cell_buttons, start=1):
            btn.setChecked(idx == cell_num)
        self.settings["pos_target_cell"] = cell_num
        self.save_settings()

    def apply_position_adjustment_to_cell(self):
        """Compatibility wrapper for legacy callers.

        The current UI applies the in-position adjustment automatically and does not
        expose a dedicated transfer button. This helper keeps old code/tests working
        while preserving the live auto-update behavior used by the app.
        """
        if not hasattr(self, "cells_table"):
            return

        try:
            if not bool(self.settings.get("pos_mode_enabled", False)):
                return
        except RuntimeError:
            return

        try:
            selected = set(getattr(self, "selected_transfer_rows", set()))
        except RuntimeError:
            selected = set()

        try:
            target_row = getattr(self, "position_target_row_active", None)
            if not selected and target_row is not None:
                selected = {int(target_row)}
        except RuntimeError:
            target_row = None

        if not selected:
            selected = {0}

        try:
            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
        except Exception:
            pass

        try:
            row_count = getattr(self.cells_table, "rowCount", lambda: 5)()
            for i in range(row_count):
                item = self.cells_table.item(i, 2)
                if not item:
                    continue
                if i in selected:
                    item.setText("100")
                else:
                    item.setText("")
        finally:
            try:
                self.cells_table.itemChanged.connect(self.on_table_item_changed)
            except Exception:
                pass

        try:
            self._capture_current_manual_distribution(pos_mode=True)
            self.update_cell_volumes()
            self.save_cell_settings()
        except RuntimeError:
            pass

    def _set_position_target_row_mask(self, target_row=None, lock_controls=True):
        if not hasattr(self, "cells_table") or not hasattr(self, "lbl_cells_count"):
            return

        cells_count = self._get_terminal_cells_count()

        if target_row is None:
            self.position_target_row_active = None
            if self._cells_count_before_target_mode is not None and hasattr(
                self, "lbl_cells_count"
            ):
                self.lbl_cells_count.setText(str(self._cells_count_before_target_mode))
            self._cells_count_before_target_mode = None
            if lock_controls:
                if hasattr(self, "btn_cells_minus"):
                    self.btn_cells_minus.setEnabled(True)
                if hasattr(self, "btn_cells_plus"):
                    self.btn_cells_plus.setEnabled(True)
                if hasattr(self, "btn_reverse_cells"):
                    self.btn_reverse_cells.setEnabled(True)
            self._sync_cells_count_controls(refresh_table=False)
        else:
            self.position_target_row_active = int(target_row)
            if self._cells_count_before_target_mode is None:
                try:
                    self._cells_count_before_target_mode = int(
                        self.lbl_cells_count.text()
                    )
                except Exception:
                    self._cells_count_before_target_mode = cells_count
            if lock_controls:
                if hasattr(self, "lbl_cells_count"):
                    self.lbl_cells_count.setText("1")
                if hasattr(self, "btn_cells_minus"):
                    self.btn_cells_minus.setEnabled(False)
                if hasattr(self, "btn_cells_plus"):
                    self.btn_cells_plus.setEnabled(False)
                if hasattr(self, "btn_reverse_cells"):
                    self.btn_reverse_cells.setEnabled(False)

        mask_rows_count = 5 if target_row is not None else cells_count

        default_flags = QTableWidgetItem().flags()

        for i in range(mask_rows_count):
            for col in range(3):
                item = self.cells_table.item(i, col)
                if not item:
                    continue

                if target_row is None:
                    if col in (0, 1):
                        item.setFlags(
                            default_flags
                            & ~Qt.ItemFlag.ItemIsEditable
                            & ~Qt.ItemFlag.ItemIsSelectable
                        )
                    else:
                        item.setFlags(default_flags)
                else:
                    if i == target_row:
                        if col in (0, 1):
                            item.setFlags(
                                default_flags
                                & ~Qt.ItemFlag.ItemIsEditable
                                & ~Qt.ItemFlag.ItemIsSelectable
                            )
                        else:
                            item.setFlags(default_flags)
                    else:
                        item.setFlags(Qt.ItemFlag.NoItemFlags)

    def _dim_top_controls(self, dim):
        """Затемняет или освещает верхние элементы (риск, стоп, объем) — депозит всегда активен"""
        elements = [
            ("inp_risk", True),
            ("inp_stop", True),
            ("lbl_vol", False),
            ("lbl_risk_title", False),
            ("lbl_stop_title", False),
            ("lbl_hint", False),
            ("lbl_info", False),
            ("lbl_vol_title", False),
        ]

        for name, is_input in elements:
            widget = getattr(self, name, None)
            if widget:
                if isinstance(widget, QLineEdit):
                    if dim:
                        widget.setEnabled(False)
                        widget.setStyleSheet(
                            "QLineEdit:disabled { background: #0F0F0F; color: #333; border: 1px solid #222; }"
                        )
                    else:
                        widget.setEnabled(True)
                        widget.setStyleSheet(
                            "QLineEdit { background: #1A1A1A; color: white; border: 1px solid #252525; padding: 3px; border-radius: 4px; font-size: 9pt; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }"
                            "QLineEdit:focus { border: 1px solid #FFFFFF; }"
                        )
                elif isinstance(widget, QLabel):
                    if dim:
                        if name == "lbl_vol_title":
                            self._apply_volume_title_style(dimmed=True)
                            continue
                        if name == "lbl_vol":
                            widget.setStyleSheet(
                                "color: #555; font-size: 11pt; font-weight: bold; border: 1px solid #222; "
                                "border-radius: 4px; padding: 4px; background: #0F0F0F;"
                            )
                            continue
                        current_style = widget.styleSheet()
                        import re

                        new_style = re.sub(
                            r"color:\s*#[0-9A-Fa-f]{3,6}",
                            "color: #555",
                            current_style,
                        )
                        widget.setStyleSheet(new_style)
                    else:
                        current_style = widget.styleSheet()
                        # Восстанавливаем оригинальные цвета
                        if (
                            name == "lbl_dep_title"
                            or name == "lbl_risk_title"
                            or name == "lbl_stop_title"
                        ):
                            import re

                            new_style = re.sub(
                                r"color:\s*#[0-9A-Fa-f]{3,6}",
                                "color: #888",
                                current_style,
                            )
                            widget.setStyleSheet(new_style)
                        elif name == "lbl_vol_title":
                            self._apply_volume_title_style(dimmed=False)
                            continue
                        elif name == "lbl_hint":
                            import re

                            new_style = re.sub(
                                r"color:\s*#[0-9A-Fa-f]{3,6}",
                                "color: #666",
                                current_style,
                            )
                            widget.setStyleSheet(new_style)
                        elif name == "lbl_info":
                            import re

                            new_style = re.sub(
                                r"color:\s*#[0-9A-Fa-f]{3,6}",
                                "color: #888",
                                current_style,
                            )
                            widget.setStyleSheet(new_style)
                        elif name == "lbl_vol":
                            widget.setStyleSheet(
                                "color: #FF9F0A; font-size: 11pt; font-weight: bold; border: 1px solid #333; "
                                "border-radius: 4px; padding: 4px; background: #1A1A1A;"
                            )

    def on_position_mode_toggled(self, checked, is_startup=False):
        enabled = bool(checked)
        if not is_startup and hasattr(self, "cb_distribution"):
            current_mode = bool(self.settings.get("pos_mode_enabled", False))
            self._save_current_distribution_state(current_mode)
            # also preserve the current cells count for the active mode
            try:
                self._save_cells_count_state(current_mode)
            except Exception:
                pass
            try:
                self._save_selected_rows_state(current_mode)
            except Exception:
                pass
        self.settings["pos_mode_enabled"] = enabled

        # Сохраняем текущий размер окна перед изменениями
        current_w = None
        current_h = None
        if not is_startup:
            current_w = int(self.width())
            current_h = int(self.height())
            self._suppress_content_resize_until = max(
                float(getattr(self, "_suppress_content_resize_until", 0.0) or 0.0),
                time.time() + 0.9,
            )
            self._lock_dynamic_resize = True

        pos_controls = []
        for name in (
            "inp_pos_vol",
            "inp_pos_risk",
            "inp_pos_stop",
            "inp_pos_stop_now",
            "lbl_pos_vol_title",
            "lbl_pos_risk_title",
            "lbl_pos_stop_title",
            "lbl_pos_stop_now_title",
            "lbl_pos_vol_hint",
            "lbl_pos_risk_cash",
            "lbl_pos_action_chip",
            "lbl_pos_adjust",
            "lbl_pos_stop_delta",
            "lbl_pos_warning",
        ):
            widget = getattr(self, name, None)
            if widget:
                pos_controls.append(widget)

        if not enabled and not is_startup:
            # User disabled position mode.
            self.table_volume_override = 0.0
            self.settings["pos_table_volume_override"] = 0.0
            if (
                hasattr(self, "position_target_row_active")
                and self.position_target_row_active is not None
            ):
                self._set_position_target_row_mask(None)

        if hasattr(self, "cb_distribution"):
            try:
                self._restore_selected_rows_state(enabled)
            except Exception:
                pass
            try:
                self._restore_cells_count(enabled)
            except Exception:
                pass
            self._startup_restore_suppressed = bool(is_startup)
            try:
                self._restore_distribution_state(enabled)
            finally:
                self._startup_restore_suppressed = False

        if not is_startup:
            self.save_settings()

        # Затемняем/включаем верхнюю часть в зависимости от позиции режима
        self._dim_top_controls(enabled)

        # Пересчитываем для обновления lbl_info с правильным значением dimmed
        self.schedule_update_calc()

        for widget in pos_controls:
            widget.setEnabled(enabled)

        dim_opacity = 1.0 if enabled else 0.35
        for widget in pos_controls:
            if enabled:
                widget.setGraphicsEffect(None)
            else:
                fx = QGraphicsOpacityEffect(widget)
                fx.setOpacity(dim_opacity)
                widget.setGraphicsEffect(fx)

        if hasattr(self, "pos_target_cell_buttons"):
            for btn in self.pos_target_cell_buttons:
                btn.setEnabled(enabled)
                if not enabled:
                    btn.setChecked(False)
                if enabled:
                    btn.setGraphicsEffect(None)
                else:
                    fx = QGraphicsOpacityEffect(btn)
                    fx.setOpacity(dim_opacity)
                    btn.setGraphicsEffect(fx)

            if enabled:
                selected_cell = int(self.settings.get("pos_target_cell", 1) or 1)
                selected_cell = max(1, min(5, selected_cell))
                for idx, btn in enumerate(self.pos_target_cell_buttons, start=1):
                    btn.setChecked(idx == selected_cell)

        if hasattr(self, "lbl_pos_vol_hint"):
            self.lbl_pos_vol_hint.setStyleSheet(
                self._position_hint_style("#666", base_pt=8)
                if enabled
                else self._position_hint_style("#555", base_pt=8)
            )
        if hasattr(self, "lbl_pos_vol_title"):
            self.lbl_pos_vol_title.setStyleSheet(
                f"color: {'#888' if enabled else '#555'}; font-size: {self._scaled_pt(8)}pt;"
            )
        if hasattr(self, "lbl_pos_risk_cash"):
            self.lbl_pos_risk_cash.setStyleSheet(
                self._position_hint_style("#888", base_pt=8, with_padding=True)
                if enabled
                else self._position_hint_style("#555", base_pt=8, with_padding=True)
            )
        if hasattr(self, "lbl_pos_action_chip"):
            if enabled and self.lbl_pos_action_chip.isVisible():
                # Keep current chip color/border that is set by action state.
                pass
            elif not enabled:
                self.lbl_pos_action_chip.setVisible(False)
        if hasattr(self, "lbl_pos_adjust"):
            self.lbl_pos_adjust.setStyleSheet(
                "color: #888; font-size: 8pt;"
                if enabled
                else "color: #555; font-size: 8pt;"
            )
        if hasattr(self, "lbl_pos_warning"):
            self.lbl_pos_warning.setStyleSheet(
                "color: #FF6B6B; font-size: 7pt;"
                if enabled
                else "color: #555; font-size: 7pt;"
            )

        self._set_position_target_row_mask(None)
        self.update_position_adjustment_info()

        # Восстанавливаем исходный размер окна, чтобы избежать "прыжков"
        if not is_startup:
            if current_w is not None and current_h is not None:
                self.setFixedSize(int(current_w), int(current_h))
            self._ensure_window_on_screen(margin=6)

            def _unlock_resize_after_toggle():
                self._lock_dynamic_resize = False
                self._suppress_content_resize_until = 0.0

            QTimer.singleShot(420, _unlock_resize_after_toggle)

    def _get_active_rows_for_table(self):
        selected_rows = sorted(
            i for i in getattr(self, "selected_transfer_rows", set()) if 0 <= int(i) < 5
        )
        return selected_rows

    def _sync_selected_rows_with_cells_count(self):
        selected = {
            int(i)
            for i in getattr(self, "selected_transfer_rows", set())
            if 0 <= int(i) < 5
        }

        self.selected_transfer_rows = selected
        key = self._selected_rows_setting_key()
        self.settings[key] = sorted(selected)
        if not bool(self.settings.get("pos_mode_enabled", False)):
            self.settings["selected_cells"] = sorted(selected)

    def _update_selected_rows_visuals(self):
        if not hasattr(self, "cells_table"):
            return

        prev_block_state = self.cells_table.blockSignals(True)
        selected = set(self._get_active_rows_for_table())
        preset_index = (
            int(self.cb_distribution.currentIndex())
            if hasattr(self, "cb_distribution")
            else 2
        )
        default_flags = QTableWidgetItem().flags()
        for i in range(5):
            for col in range(3):
                item = self.cells_table.item(i, col)
                if not item:
                    continue

                if col == 0:
                    t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                    base_text = item.text() or t["calc_cell_label"].format(num=i + 1)
                    if base_text.startswith("● "):
                        base_text = base_text[2:]
                    item.setText(base_text)

                if i in selected:
                    bg = QColor("#3a3a3a")
                    fg = QColor("#ffffff")
                    item.setBackground(bg)
                    item.setForeground(fg)
                    item.setData(Qt.ItemDataRole.BackgroundRole, QBrush(bg))
                    item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(fg))
                    if col == 0:
                        item.setFlags(default_flags & ~Qt.ItemFlag.ItemIsEditable)
                    elif col == 1:
                        item.setFlags(
                            default_flags
                            & ~Qt.ItemFlag.ItemIsEditable
                            & ~Qt.ItemFlag.ItemIsSelectable
                        )
                    else:
                        if preset_index == 2:
                            item.setFlags(default_flags)
                        else:
                            item.setFlags(
                                default_flags
                                & ~Qt.ItemFlag.ItemIsEditable
                                & ~Qt.ItemFlag.ItemIsSelectable
                            )
                else:
                    bg = QColor("#000000")
                    fg = QColor("#000000") if col == 0 else QColor("#161616")
                    item.setBackground(bg)
                    item.setForeground(fg)
                    item.setData(Qt.ItemDataRole.BackgroundRole, QBrush(bg))
                    item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(fg))
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.cells_table.blockSignals(prev_block_state)

    def _adapt_window_width_to_content(self, grow_only=False, smooth=False):
        if getattr(self, "_lock_dynamic_resize", False):
            return
        if not self.isVisible():
            return

        try:
            scale = int(self.settings.get("scale", self.base_scale))
        except Exception:
            scale = int(self.base_scale)
        ratio = scale / float(self.base_scale)
        base_w = max(90, int(105 * ratio))
        max_w = max(280, int(560 * ratio))

        for name in (
            "inp_dep",
            "inp_risk",
            "inp_stop",
            "inp_pos_vol",
            "inp_pos_risk",
            "inp_pos_stop",
            "inp_pos_stop_now",
            "inp_min_order",
        ):
            widget = getattr(self, name, None)
            if not widget:
                continue

            try:
                text = widget.text() if widget.text() else "0"
                desired = widget.fontMetrics().horizontalAdvance(text + " 000") + 18
                desired_w = max(base_w, min(max_w, desired))
                if grow_only:
                    desired_w = max(int(widget.minimumWidth()), desired_w)
                widget.setMinimumWidth(desired_w)
            except Exception:
                pass

        # Width baseline remains stable across UI mode toggles.
        # Extra width appears only for long numeric values in editable fields.
        try:
            base_min_window = max(620, int(620 * ratio))
            target_min_window = int(base_min_window)

            if smooth:
                char_step_px = max(3, int(5 * ratio))
                extra_chars = self._current_resize_pressure_chars()
                step = max(1, int(getattr(self, "_resize_step_chars", 5) or 1))
                quantized = (extra_chars // step) * step
                target_min_window += quantized * char_step_px

            if grow_only:
                target_min_window = max(int(self.minimumWidth()), int(target_min_window))
            self.setMinimumWidth(int(target_min_window))
        except Exception:
            pass

        self._set_window_size_with_extra_height(grow_only=grow_only, smooth=smooth)


    def format_with_abbreviations(self, value, precision):
        """Форматирует число с одним сокращением"""
        try:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            # Основное форматированное значение
            main = f"{value:,.{precision}f}".replace(",", " ").replace(".", ",")

            # Одно сокращение
            if value >= 1_000_000_000:
                abbr = f"{value / 1_000_000_000:.1f}{t['abbr_billion']}"
            elif value >= 1_000_000:
                abbr = f"{value / 1_000_000:.1f}{t['abbr_million']}"
            elif value >= 1_000:
                abbr = f"{value / 1_000:.0f}{t['abbr_thousand']}"
            else:
                return main

            return f"{main} / {abbr}"
        except:
            return str(value)

    def format_hint_no_decimals(self, value):
        """Формат подсказок без дробной части и без зависимости от настроек точности."""
        try:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            value = float(value)
            main = f"{value:,.0f}".replace(",", " ")

            def fmt_abbr(val, div, suffix):
                short = f"{val / div:.1f}".rstrip("0").rstrip(".")
                return f"{short}{suffix}"

            if abs(value) >= 1_000_000_000:
                abbr = fmt_abbr(value, 1_000_000_000, t["abbr_billion"])
            elif abs(value) >= 1_000_000:
                abbr = fmt_abbr(value, 1_000_000, t["abbr_million"])
            elif abs(value) >= 1_000:
                abbr = fmt_abbr(value, 1_000, t["abbr_thousand"])
            else:
                return main

            return f"{main} / {abbr}"
        except Exception:
            return "0"

    def apply_styles(self):
        logging.debug("apply_styles START")
        scale = self.settings.get("scale", self.base_scale)
        scale = max(60, min(120, int(scale)))
        ratio = scale / float(self.base_scale)
        compact_mode = scale < 100
        compact_60 = scale <= 60
        base_font = int(11 * (self.base_scale / 100.0))
        f_main = max(8, int(base_font * ratio))
        input_font = max(8, int(9 * ratio))
        if compact_60:
            input_font = max(input_font, 9)
        f_small = max(7, int(8.5 * ratio))
        logging.debug("apply_styles scales calculated")
        # Compress padding growth for large scales to avoid oversized inner gaps.
        pad_ratio = 1.0 + max(0.0, ratio - 1.0) * 0.55
        pad_main = max(1, int(3 * pad_ratio))
        combo_pad = max(1, int(3 * pad_ratio))
        table_header_pad = max(2, int(4 * pad_ratio))
        table_item_pad = max(2, int(5 * pad_ratio))
        table_edit_pad = max(1, int(3 * pad_ratio))
        radius_main = max(4, int(6 * ratio))
        self.central_widget.setStyleSheet(
            f"""
            QWidget#Root {{ background: #121212; border: 2px solid #333; border-radius: {int(12*ratio)}px; }}
            QLineEdit {{ background: #1A1A1A; color: white; border: 1px solid #252525; padding: {pad_main}px; border-radius: {radius_main}px; font-size: {input_font}pt; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }}
            QLineEdit:disabled {{ background: #0F0F0F; color: #555; border: 1px solid #222; }}
            QLineEdit:focus {{ border: 1px solid #FFFFFF; }}
            QLabel {{ color: #888; border: none; font-size: {max(6, f_main-2)}pt; }}
            QPushButton#HeadBtn {{ color: #555; border: none; background: transparent; font-size: {f_main}pt; font-weight: bold; }}
            QPushButton#HeadBtn:hover {{ color: #38BE1D; }}
            QPushButton {{ background: #333; color: #9A9A9A; border: 1px solid #444; border-radius: {max(4, int(4*ratio))}px; font-weight: bold; }}
            QPushButton:disabled {{ background: #0F0F0F; color: #555; border: 1px solid #222; }}
            QPushButton:hover {{ background: #444; border-color: #38BE1D; }}
            QPushButton:pressed {{ background: #38BE1D; color: black; }}
            QComboBox, QSpinBox, QDoubleSpinBox {{ background: #1A1A1A; color: white; border: 1px solid #333; padding: {combo_pad}px; border-radius: {max(4, int(4*ratio))}px; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }}
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid #FFFFFF; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #888; width: 0; height: 0; margin-right: 5px; }}
            QComboBox QAbstractItemView {{ background: #1A1A1A; color: white; selection-background-color: #38BE1D; selection-color: black; border: 1px solid #333; }}
            QTableWidget {{ background: #1A1A1A; gridline-color: #333; color: white; border: none; }}
            QHeaderView::section {{ background: #252525; color: #888; border: 1px solid #333; }}
        """
        )

        # Global context menu styling for right-click menus in line edits and other widgets.
        app = QApplication.instance()
        if app is not None:
            menu_style = (
                "\n/* RV_GLOBAL_QMENU_STYLE */\n"
                "QMenu { background-color: #121212; border: 1px solid #333; padding: 4px; }\n"
                "QMenu::item { color: #EAEAEA; background: transparent; padding: 6px 18px; }\n"
                "QMenu::item:selected { background: #2A7F4A; color: #FFFFFF; }\n"
                "QMenu::separator { height: 1px; background: #2F2F2F; margin: 4px 8px; }\n"
                "/* RV_GLOBAL_QMENU_STYLE_END */\n"
            )
            current_style = app.styleSheet() or ""
            marker_start = "/* RV_GLOBAL_QMENU_STYLE */"
            marker_end = "/* RV_GLOBAL_QMENU_STYLE_END */"
            if marker_start in current_style and marker_end in current_style:
                start = current_style.find(marker_start)
                end = current_style.find(marker_end)
                if start != -1 and end != -1 and end >= start:
                    end = end + len(marker_end)
                    current_style = current_style[:start] + current_style[end:]
            app.setStyleSheet((current_style.rstrip() + "\n" + menu_style).strip())
        # Масштабируем размеры элементов равномерно относительно базового масштаба
        if hasattr(self, "main_layout"):
            self.main_layout.setContentsMargins(
                int(8 * ratio), int(8 * ratio), int(8 * ratio), int(8 * ratio)
            )
            self.main_layout.setSpacing(max(2, int(4 * ratio)))
        if hasattr(self, "calc_layout"):
            calc_margin = max(2, int(4 * ratio))
            self.calc_layout.setContentsMargins(
                calc_margin,
                calc_margin,
                calc_margin,
                calc_margin,
            )
            self.calc_layout.setSpacing(max(2, int(4 * ratio)))
        if hasattr(self, "header_layout"):
            self.header_layout.setContentsMargins(
                int(10 * ratio), int(5 * ratio), int(10 * ratio), int(5 * ratio)
            )
            self.header_layout.setSpacing(int(10 * ratio))
        if hasattr(self, "header_container"):
            self.header_container.setStyleSheet(
                f"""
                QWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(56, 190, 29, 0.15),
                        stop:1 rgba(56, 190, 29, 0.05));
                    border: 1px solid rgba(56, 190, 29, 0.3);
                    border-radius: {int(8 * ratio)}px;
                }}
            """
            )
        if hasattr(self, "lbl_logo_small") and os.path.exists(LOGO_PATH):
            size = max(12, int(24 * ratio))
            pix = QIcon(LOGO_PATH).pixmap(size, size)
            self.lbl_logo_small.setPixmap(pix)
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(
                f"color: #38BE1D; font-weight: bold; font-style: italic; font-size: {max(8, int(11*ratio))}pt; border: none; background: transparent;"
            )

        btn_size = max(14 if compact_mode else 18, int(22 * ratio))
        for b in [self.btn_set, self.btn_min, self.btn_close]:
            b.setFixedSize(btn_size, btn_size)

        if compact_mode:
            input_height = max(int(26 * ratio), int(10 * ratio + 10))
        else:
            input_height = max(int(28 * ratio), int(12 * ratio + 14))
        if compact_60:
            input_height = max(input_height, 22)
        if hasattr(self, "inp_dep"):
            self.inp_dep.setFixedHeight(input_height)
            self.inp_dep.setStyleSheet(
                f"QLineEdit {{ background: #1A1A1A; color: white; border: 1px solid #252525; padding: {pad_main}px; border-radius: {radius_main}px; font-size: {input_font}pt; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }}"
                "QLineEdit:focus { border: 1px solid #FFFFFF; }"
            )
        if hasattr(self, "inp_risk"):
            self.inp_risk.setFixedHeight(input_height)
            self.inp_risk.setStyleSheet(
                f"QLineEdit {{ background: #1A1A1A; color: white; border: 1px solid #252525; padding: {pad_main}px; border-radius: {radius_main}px; font-size: {input_font}pt; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }}"
                "QLineEdit:focus { border: 1px solid #FFFFFF; }"
            )
        if hasattr(self, "inp_stop"):
            self.inp_stop.setFixedHeight(input_height)
            self.inp_stop.setStyleSheet(
                f"QLineEdit {{ background: #1A1A1A; color: white; border: 1px solid #252525; padding: {pad_main}px; border-radius: {radius_main}px; font-size: {input_font}pt; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }}"
                "QLineEdit:focus { border: 1px solid #FFFFFF; }"
            )
        if hasattr(self, "lbl_vol"):
            vol_h = max(18 if compact_mode else 24, int(36 * ratio))
            if compact_60:
                vol_h = max(vol_h, 28)
            self.lbl_vol.setFixedHeight(vol_h)
        self._apply_volume_title_style(
            dimmed=bool(self.settings.get("pos_mode_enabled", False))
        )

        if hasattr(self, "cb_distribution"):
            self.cb_distribution.setStyleSheet(
                f"""
                QComboBox {{ background: #1A1A1A; color: white; border: 1px solid #333; padding: {combo_pad}px; border-radius: {max(4, int(4*ratio))}px; font-size: {f_small}pt; }}
                """
            )
        if hasattr(self, "tabs"):
            tab_pad_v = max(2 if compact_mode else 3, int(5 * ratio))
            tab_pad_h = max(4 if compact_mode else 6, int(10 * ratio))
            self.tabs.setStyleSheet(
                f"""
                QTabWidget::pane {{ border: none; }}
                QTabBar::tab {{ background: #333; color: #888; padding: {tab_pad_v}px {tab_pad_h}px; border-radius: {max(4, int(4*ratio))}px; margin-right: {max(2, int(2*ratio))}px; }}
                QTabBar::tab:selected {{ background: #38BE1D; color: black; font-weight: bold; }}
                QTabBar::tab:disabled {{ background: #0F0F0F; color: #444; border: 1px solid #222; }}
                """
            )

        if hasattr(self, "cells_table"):
            self.cells_table.setStyleSheet(
                f"""
                QTableWidget {{
                    background: #1A1A1A;
                    gridline-color: #333;
                    color: white;
                    border: 1px solid #333;
                    border-radius: {max(4, int(4*ratio))}px;
                    show-decoration-selected: 0;
                }}
                QHeaderView::section {{
                    background: #252525;
                    color: #888;
                    border: 1px solid #333;
                    padding: {table_header_pad}px;
                    font-size: {f_small}pt;
                }}
                QTableWidget::item {{
                    padding: {table_item_pad}px;
                    border: none;
                    color: #A8A8A8;
                    background: #1A1A1A;
                    outline: none;
                    font-size: {max(5 if compact_mode else 6, int(6*ratio))}pt;
                }}
                QTableWidget::item:focus {{
                    border: none;
                    outline: none;
                }}
                QTableWidget::item:selected {{
                    background: #1A1A1A;
                    border: none;
                }}
                QTableWidget::item:disabled {{
                    color: #161616;
                    background: #000000;
                }}
                QLineEdit {{
                    background: #1A1A1A !important;
                    color: white;
                    border: 1px solid #333 !important;
                    border-radius: {max(4, int(4*ratio))}px;
                    padding: {table_edit_pad}px;
                    font-size: {max(6 if compact_mode else 8, int(9*ratio))}pt;
                    selection-background-color: rgba(90, 205, 80, 150);
                    selection-color: white;
                }}
            """
            )
            self.update_cells_table_height()

        btn_pad = max(2 if compact_mode else 4, int(7 * ratio))
        pos_toggle_pad_v = max(1, int(2 * ratio))
        pos_toggle_min_h = max(14, int(16 * ratio))
        if hasattr(self, "btn_submit"):
            self.btn_submit.setStyleSheet(
                f"background: #38BE1D; color: black; font-weight: bold; padding: {btn_pad}px;"
            )
        if hasattr(self, "chk_pos_mode"):
            self.chk_pos_mode.setStyleSheet(
                (
                    f"QCheckBox#PosModeToggle {{ font-size: {f_small}pt; spacing: 5px; margin: 0px; padding: 0px; background: transparent; border: none; }}"
                    "QCheckBox#PosModeToggle:checked { color: #AAA; }"
                    "QCheckBox#PosModeToggle:unchecked { color: #666; }"
                    "QCheckBox#PosModeToggle::indicator { width: 14px; height: 14px; border-radius: 3px; margin-right: 6px; }"
                    f"QCheckBox#PosModeToggle::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({self._posmode_checkmark_path_css}); }}"
                    "QCheckBox#PosModeToggle::indicator:unchecked { background: #2A2A2A; border: 1px solid #444; image: none; }"
                )
            )

        pos_lbl_pt = max(7, int(8 * ratio))
        pos_input_pt = max(7, int(8 * ratio))
        pos_hint_pt = max(7, int(8 * ratio))
        pos_input_h = max(16 if compact_mode else 20, int(22 * ratio))

        for name in (
            "lbl_pos_vol_title",
            "lbl_pos_risk_title",
            "lbl_pos_stop_title",
            "lbl_pos_stop_now_title",
            "lbl_min_order_title",
            "lbl_calc_type_title",
        ):
            widget = getattr(self, name, None)
            if widget:
                if name == "lbl_pos_vol_title":
                    pos_enabled = bool(self.settings.get("pos_mode_enabled", False))
                    color = "#888" if pos_enabled else "#555"
                    widget.setStyleSheet(f"color: {color}; font-size: {pos_lbl_pt}pt;")
                else:
                    widget.setStyleSheet(f"font-size: {pos_lbl_pt}pt;")

        for name in (
            "inp_pos_vol",
            "inp_pos_risk",
            "inp_pos_stop",
            "inp_pos_stop_now",
            "inp_min_order",
        ):
            widget = getattr(self, name, None)
            if widget:
                widget.setFixedHeight(pos_input_h)
                widget.setStyleSheet(
                    f"QLineEdit {{ background: #1A1A1A; color: white; border: 1px solid #252525; border-radius: {max(4, int(4 * ratio))}px; font-size: {pos_input_pt}pt; padding: {max(1, int(1 * ratio))}px; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }}"
                    "QLineEdit:focus { border: 1px solid #FFFFFF; }"
                )

        for name in ("lbl_pos_vol_hint", "lbl_pos_risk_cash", "lbl_pos_adjust", "lbl_pos_stop_delta"):
            widget = getattr(self, name, None)
            if widget:
                color = "#888"
                if name == "lbl_pos_vol_hint":
                    color = "#666"
                elif name == "lbl_pos_stop_delta":
                    color = "#777"
                if name == "lbl_pos_risk_cash":
                    widget.setStyleSheet(
                        self._position_hint_style(color, base_pt=8, with_padding=True)
                    )
                else:
                    widget.setStyleSheet(f"color: {color}; font-size: {pos_hint_pt}pt;")

        for name in (
            "btn_reverse_cells",
            "btn_toggle_all_cells",
            "btn_cells_minus",
            "btn_cells_plus",
            "btn_pf_targets_toggle_all",
        ):
            widget = getattr(self, name, None)
            if widget:
                widget.setFixedSize(
                    max(22 if compact_mode else 28, int(34 * ratio)),
                    max(18 if compact_mode else 22, int(25 * ratio)),
                )

        if hasattr(self, "w_cells_bottom_guard"):
            self.w_cells_bottom_guard.setFixedHeight(
                max(1 if compact_mode else 2, int((6 if compact_mode else 10) * ratio))
            )

        if hasattr(self, "lbl_status"):
            self.lbl_status.setStyleSheet(f"color: #666; font-size: {self._scaled_pt(7)}pt;")

        self._style_pf_multi_glass_controls()

        self._set_window_size_with_extra_height()

        # Обновляем масштаб элементов на вкладке каскадов
        if hasattr(self, "tab_cascade"):
            self.tab_cascade.apply_scale()

        # Второй проход после применения стилей/DPI-метрик,
        # чтобы таблица калькулятора гарантированно не заходила под кнопку.
        self._schedule_cells_layout_reflow()

    def _ensure_keyboard_module(self):
        global keyboard
        if keyboard is not None:
            return True
        try:
            import keyboard as keyboard_module

            keyboard = keyboard_module
            return True
        except Exception:
            return False

    def _ensure_pyautogui_module(self):
        global pyautogui
        if pyautogui is not None:
            return True
        try:
            import pyautogui as pyautogui_module

            pyautogui = pyautogui_module
            return True
        except Exception:
            return False

    def _schedule_cells_layout_reflow(self):
        if self._cells_layout_reflow_pending:
            return
        self._cells_layout_reflow_pending = True

        def _run():
            self._cells_layout_reflow_pending = False
            if not hasattr(self, "cells_table"):
                return
            try:
                self.update_cells_table_height()
                self._schedule_smooth_content_resize(force=True)
            except Exception:
                pass

        QTimer.singleShot(0, _run)

    # --- УПРАВЛЕНИЕ ГОРЯЧИМИ КЛАВИШАМИ (ИСПРАВЛЕНО) ---
    def _clear_windows_hotkeys(self):
        if sys.platform != "win32":
            self._windows_hotkey_actions = {}
            return

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        hwnd = wintypes.HWND(int(self.winId()))
        for hotkey_id in self._windows_hotkey_actions:
            if not user32.UnregisterHotKey(hwnd, int(hotkey_id)):
                error_code = ctypes.get_last_error()
                if error_code:
                    logging.warning(
                        "Failed to unregister Windows hotkey %s: error %s",
                        hotkey_id,
                        error_code,
                    )
        self._windows_hotkey_actions = {}

    def _parse_windows_hotkey(self, hotkey_text):
        modifiers = 0x4000  # MOD_NOREPEAT
        modifier_flags = {
            "alt": 0x0001,
            "ctrl": 0x0002,
            "control": 0x0002,
            "shift": 0x0004,
            "win": 0x0008,
            "windows": 0x0008,
        }
        key_names = {
            "backspace": 0x08,
            "tab": 0x09,
            "enter": 0x0D,
            "esc": 0x1B,
            "escape": 0x1B,
            "space": 0x20,
            "backslash": 0xDC,
            "pageup": 0x21,
            "home": 0x24,
            "left": 0x25,
            "up": 0x26,
            "right": 0x27,
            "down": 0x28,
            "pagedown": 0x22,
            "end": 0x23,
            "insert": 0x2D,
            "delete": 0x2E,
        }

        key = None
        for token in hotkey_text.split("+"):
            if token in modifier_flags:
                modifiers |= modifier_flags[token]
            elif key is None:
                key = token
            else:
                raise ValueError(f"Hotkey has more than one non-modifier key: {hotkey_text}")

        if not key:
            raise ValueError(f"Hotkey has no key: {hotkey_text}")

        if key in key_names:
            virtual_key = key_names[key]
        elif len(key) >= 2 and key[0] == "f" and key[1:].isdigit():
            function_key = int(key[1:])
            if not 1 <= function_key <= 24:
                raise ValueError(f"Unsupported function key: {key}")
            virtual_key = 0x70 + function_key - 1
        elif len(key) == 1:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
            user32.VkKeyScanW.restype = ctypes.c_short
            key_scan = user32.VkKeyScanW(key)
            if key_scan == -1:
                raise ValueError(f"Unsupported Windows hotkey: {hotkey_text}")
            virtual_key = key_scan & 0xFF
            keyboard_modifiers = (key_scan >> 8) & 0xFF
            if keyboard_modifiers & 0x01:
                modifiers |= 0x0004
            if keyboard_modifiers & 0x02:
                modifiers |= 0x0002
            if keyboard_modifiers & 0x04:
                modifiers |= 0x0001
        else:
            raise ValueError(f"Unsupported Windows hotkey: {hotkey_text}")

        return modifiers, virtual_key

    def _register_windows_hotkeys(self, bindings):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        hwnd = wintypes.HWND(int(self.winId()))

        grouped_bindings = {}
        for hotkey_text, callback in bindings:
            try:
                signature = self._parse_windows_hotkey(hotkey_text)
            except ValueError:
                logging.exception("Invalid Windows hotkey: %s", hotkey_text)
                return False
            grouped_bindings.setdefault(signature, []).append(callback)

        self._clear_windows_hotkeys()
        registered_actions = {}
        for index, ((modifiers, virtual_key), callbacks) in enumerate(
            grouped_bindings.items(), start=1
        ):
            hotkey_id = 0x5200 + index
            if not user32.RegisterHotKey(
                hwnd, hotkey_id, modifiers, virtual_key
            ):
                for registered_id in registered_actions:
                    user32.UnregisterHotKey(hwnd, int(registered_id))
                logging.error(
                    "Failed to register Windows hotkey (modifiers=%s, vk=%s): error %s",
                    modifiers,
                    virtual_key,
                    ctypes.get_last_error(),
                )
                self._clear_windows_hotkeys()
                return False
            registered_actions[hotkey_id] = callbacks

        self._windows_hotkey_actions = registered_actions
        logging.info(
            "Registered %d Windows global hotkey(s)",
            len(registered_actions),
        )
        return True

    def _clear_registered_hotkeys(self):
        self._clear_windows_hotkeys()
        if self._hotkey_ids and not self._ensure_keyboard_module():
            self._hotkey_ids = {}
            self._hotkey_bindings = {}
            return
        for _, hotkey_id in list(self._hotkey_ids.items()):
            try:
                keyboard.remove_hotkey(hotkey_id)
            except Exception:
                pass
        self._hotkey_ids = {}
        self._hotkey_bindings = {}

    def _register_hotkey(self, key_name, hotkey_text, callback, fallback, force=False):
        previous_hotkey_id = self._hotkey_ids.get(key_name)
        previous_binding = self._hotkey_bindings.get(key_name)
        if (
            not force
            and previous_hotkey_id is not None
            and previous_binding == hotkey_text
        ):
            return True

        try:
            hotkey_id = keyboard.add_hotkey(hotkey_text, callback)
            registered_hotkey = hotkey_text
        except Exception as requested_error:
            if hotkey_text == fallback:
                logging.exception(
                    "Failed to register hotkey %s (%s)",
                    key_name,
                    hotkey_text,
                )
                return False
            logging.warning(
                "Failed to register hotkey %s (%s); trying fallback %s: %s",
                key_name,
                hotkey_text,
                fallback,
                requested_error,
            )
            try:
                hotkey_id = keyboard.add_hotkey(fallback, callback)
                registered_hotkey = fallback
            except Exception:
                logging.exception(
                    "Failed to register fallback hotkey %s (%s)",
                    key_name,
                    fallback,
                )
                return False

        self._hotkey_ids[key_name] = hotkey_id
        self._hotkey_bindings[key_name] = registered_hotkey
        self.settings[key_name] = registered_hotkey
        if previous_hotkey_id is not None:
            try:
                keyboard.remove_hotkey(previous_hotkey_id)
            except Exception:
                logging.exception(
                    "Failed to remove previous hotkey registration for %s",
                    key_name,
                )
        return True

    def _delayed_rebind_hotkeys(self):
        """Отложенная регистрация горячих клавиш для избежания фоновых окон при старте."""
        try:
            if not self.rebind_hotkeys():
                logging.error("One or more global hotkeys could not be registered")
        except Exception:
            logging.exception("Failed to register global hotkeys at startup")

    def _delayed_init_keyboard_module(self):
        """Инициализирует keyboard модуль после полной загрузки UI и фокуса главного окна."""
        try:
            # Убедиться что главное окно в фокусе и видимо
            if not self.isVisible():
                self.show()
            self.activateWindow()
            self.raise_()
            
            # Запустим в фоновом потоке чтобы не блокировать UI
            def _init_keyboard_in_thread():
                try:
                    # Небольшая дополнительная задержка в потоке
                    import time
                    time.sleep(0.5)
                    if self._ensure_keyboard_module():
                        self.rebind_hotkeys()
                except Exception:
                    pass

            init_thread = threading.Thread(target=_init_keyboard_in_thread, daemon=True)
            init_thread.start()
        except Exception:
            pass

    def rebind_hotkeys(self, force_refresh=False):
        def normalize_hotkey(hotkey_value, fallback):
            value = str(hotkey_value or "").strip().lower()
            value = value.replace(" ", "")
            value = "+".join(
                "backslash" if key == "\\" else key
                for key in value.split("+")
            )
            return value or fallback

        hk_show = normalize_hotkey(self.settings.get("hk_show", "f1"), "f1")
        hk_coords = normalize_hotkey(self.settings.get("hk_coords", "f2"), "f2")

        if sys.platform == "win32":
            return self._register_windows_hotkeys(
                [
                    (hk_show, self.signaler.toggle_sig.emit),
                    (hk_coords, self.signaler.calibrate_sig.emit),
                ]
            )

        if not self._ensure_keyboard_module():
            logging.error("Cannot register hotkeys: keyboard module unavailable")
            return False

        show_registered = self._register_hotkey(
            "hk_show",
            hk_show,
            self.signaler.toggle_sig.emit,
            "f1",
            force=force_refresh,
        )
        coords_registered = self._register_hotkey(
            "hk_coords",
            hk_coords,
            self.signaler.calibrate_sig.emit,
            "f2",
            force=force_refresh,
        )

        # F3 - ОТПРАВИТЬ - ОТКЛЮЧЕНО, теперь только через кнопку
        # keyboard.add_hotkey(
        #     self.settings.get("hk_send", "f3"), self.signaler.apply_sig.emit
        # )
        return show_registered and coords_registered

    def _keepalive_hotkeys(self):
        """Refresh hooks where needed and retry missing Windows registrations."""
        try:
            if sys.platform == "win32":
                if not self._windows_hotkey_actions:
                    self.rebind_hotkeys()
                return
            if not self.rebind_hotkeys(force_refresh=True):
                logging.error("Global hotkey refresh failed")
        except Exception:
            logging.exception("Failed to refresh global hotkeys")

    def handle_hotkey_apply(self):
        # Защита от повторного входа (если один и тот же клавишный сигнал пришёл дважды)
        if self.apply_running:
            return
        self.apply_running = True

        try:
            # Если окно свернуто, не реагируем
            if self.isMinimized() or not self.isVisible():
                return

            # ПРОВЕРЯЕМ ПОЗИЦИЮ КУРСОРА - данные отправляются только если курсор НАД окном
            if not self.is_cursor_over_window():
                return

            if hasattr(self, "tabs") and self.tabs.currentIndex() == 1:
                self.tab_cascade.run_automation()
            else:
                self.update_calc()
                self.send_volume_to_terminal()
        finally:
            self.apply_running = False

    def handle_hotkey_calibration(self):
        if hasattr(self, "tabs") and self.tabs.currentIndex() == 1:
            self.tab_cascade.handle_calibration_hotkey()
        else:
            self.capture_coords()

    def _cancel_active_calibration(self):
        if hasattr(self, "tab_cascade") and self.tab_cascade.is_apply_active():
            return False

        if hasattr(self, "tab_cascade") and self.tab_cascade.cancel_calibration():
            return True

        if getattr(self, "calc_calibration_active", False):
            self._reset_active_calc_calibration()
            self.calc_calibration_active = False
            hk_coords = self.settings.get("hk_coords", "f2").upper()
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_status.setText(t["calc_calib_reset"].format(hotkey=hk_coords))
            self.lbl_status.setStyleSheet(
                f"color: #FF9F0A; font-size: {self._scaled_pt(7)}pt;"
            )
            return True

        return False

    # Обработка нажатия Enter на клавиатуре (когда фокус в программе)
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F2:
            if hasattr(self, "tabs") and self.tabs.currentIndex() == 1:
                self.tab_cascade.handle_calibration_hotkey()
            else:
                self.capture_coords()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """Фильтр событий для обработки колесика мыши на lbl_cells_count"""
        if obj == self.lbl_cells_count and event.type() == event.Type.Wheel:
            delta = event.angleDelta().y()
            if delta > 0:
                self.increase_cells()
            elif delta < 0:
                self.decrease_cells()
            return True
        return super().eventFilter(obj, event)

    def send_volume_to_terminal(self):
        """Отправляет объемы ячеек в терминал"""
        if not self._ensure_pyautogui_module() or not self._ensure_keyboard_module():
            return

        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
        active_rows = sorted(self._get_active_rows_for_table())
        is_reversed = bool(
            self.settings.get(
                self._cells_reversed_setting_key(),
                False,
            )
        )
        if is_reversed:
            active_rows = list(reversed(active_rows))

        if not active_rows:
            return

        transfers = []
        for row in active_rows:
            vol_item = self.cells_table.item(row, 1)
            vol_to_send = (
                vol_item.text().replace(" ", "").replace(",", ".")
                if vol_item and vol_item.text()
                else "0"
            )
            transfers.append((row, vol_to_send))

        if not transfers:
            return

        target_batches = []
        skipped_glasses = []

        if self._uses_shared_preset_controls():
            selected_glasses = self._get_pf_selected_glasses()
            if not selected_glasses:
                return

            for glass in selected_glasses:
                points = self._get_pf_points_for_glass(glass)
                has_all_points = all(len(points) > point_index for point_index, _ in transfers)
                menu_ready = True
                if self._is_menu_terminal():
                    menu_ready = self._is_menu_glass_ready(glass)
                if self._is_surf_terminal():
                    menu_ready = self._get_surf_hover_point(glass) is not None

                if has_all_points and menu_ready:
                    target_batches.append((int(glass), points))
                else:
                    skipped_glasses.append(int(glass))

            if not target_batches:
                missing = ", ".join(self._pf_glass_label(g) for g in skipped_glasses)
                self.lbl_status.setText(
                    t.get(
                        "calc_status_missing_glasses",
                        "Не откалиброваны пресеты: {glasses}",
                    ).format(glasses=missing)
                )
                self.lbl_status.setStyleSheet(
                    f"color: #FF9F0A; font-size: {self._scaled_pt(7)}pt;"
                )
                return

            if skipped_glasses:
                skipped_text = ", ".join(self._pf_glass_label(g) for g in skipped_glasses)
                self._set_transient_status_then_neutral(
                    t.get(
                        "calc_status_skip_missing_glasses",
                        "Пропускаю не откалиброванные пресеты: {glasses}",
                    ).format(glasses=skipped_text),
                    self.lbl_status.text() if hasattr(self, "lbl_status") else "",
                    status_color="#FF9F0A",
                    delay_ms=4200,
                )
        else:
            points = self._get_active_calc_points()
            has_all_points = all(len(points) > point_index for point_index, _ in transfers)
            if not has_all_points:
                self.lbl_status.setText(t["calc_not_enough_points"])
                self.lbl_status.setStyleSheet(
                    f"color: #FF9F0A; font-size: {self._scaled_pt(7)}pt;"
                )
                return
            target_batches.append((None, points))

        # Order already follows the intended row direction

        old_clip = ""
        start_x, start_y = None, None
        try:
            old_clip = pyperclip.paste()
            # capture exact start position to restore later if needed
            try:
                start_pos = pyautogui.position()
                start_x, start_y = int(start_pos[0]), int(start_pos[1])
            except Exception:
                start_x, start_y = None, None

            if bool(self.settings.get("minimize_after_apply", True)):
                self.showMinimized()
                time.sleep(0.08)
            else:
                time.sleep(0.02)

            if self._is_menu_terminal():
                try:
                    pyautogui.MINIMUM_SLEEP = 0.0005
                    pyautogui.MINIMUM_DURATION = 0.005
                    pyautogui.PAUSE = 0.0
                except Exception:
                    pass

                menu_kind = self._menu_terminal_kind() or "tiger"
                is_tiger_trade = menu_kind == "tiger"
                open_menu_settle_delay = 0.06 if is_tiger_trade else 0.03
                post_paste_settle_delay = 0.025 if is_tiger_trade else 0.012
                between_cells_delay = 0.05 if is_tiger_trade else 0.025
                close_menu_delay = 0.06 if is_tiger_trade else 0.03

                requires_final_point = self._menu_terminal_requires_final_point()
                for batch_index, (glass, points) in enumerate(target_batches):
                    if len(target_batches) > 1 and glass is not None:
                        self.lbl_status.setText(
                            t.get(
                                "calc_status_applying_glass",
                                "Выставляю в {glass} ({idx}/{total})...",
                            ).format(
                                glass=self._pf_glass_label(glass),
                                idx=batch_index + 1,
                                total=len(target_batches),
                            )
                        )
                        self.lbl_status.setStyleSheet(
                            f"color: cyan; font-size: {self._scaled_pt(7)}pt;"
                        )
                        QApplication.processEvents()

                    t_open, t_close = self._get_menu_points_for_glass(glass)
                    if t_open is None or (requires_final_point and t_close is None):
                        need_key = f"calc_{menu_kind}_need_points"
                        self.lbl_status.setText(t.get(need_key, t["calc_not_enough_points"]))
                        self.lbl_status.setStyleSheet(
                            f"color: #FF9F0A; font-size: {self._scaled_pt(7)}pt;"
                        )
                        return

                    pyautogui.moveTo(t_open[0], t_open[1], duration=0.015)
                    pyautogui.click()
                    time.sleep(0.02 if is_tiger_trade else 0.012)
                    pyautogui.doubleClick(interval=0.03)
                    time.sleep(open_menu_settle_delay)

                    for transfer_index, (point_index, vol_to_send) in enumerate(transfers):
                        pyperclip.copy(vol_to_send)
                        time.sleep(0.015 if is_tiger_trade else 0.01)
                        pyautogui.moveTo(
                            points[point_index][0], points[point_index][1], duration=0.015
                        )
                        pyautogui.click()
                        time.sleep(0.02 if is_tiger_trade else 0.012)
                        pyautogui.doubleClick(interval=0.03)
                        time.sleep(0.02 if is_tiger_trade else 0.012)
                        keyboard.press_and_release("ctrl+a")
                        time.sleep(0.015 if is_tiger_trade else 0.01)
                        keyboard.press_and_release("backspace")
                        time.sleep(0.015 if is_tiger_trade else 0.01)
                        keyboard.press_and_release("ctrl+v")
                        time.sleep(post_paste_settle_delay)
                        if transfer_index < len(transfers) - 1:
                            time.sleep(between_cells_delay)
                        elif menu_kind == "vataga":
                            # Vataga closes the menu by Enter only after the last edited cell.
                            keyboard.press_and_release("enter")
                            time.sleep(close_menu_delay)

                    if requires_final_point:
                        pyautogui.moveTo(t_close[0], t_close[1], duration=0.015)
                        pyautogui.click()
                        time.sleep(close_menu_delay)

                    if batch_index < len(target_batches) - 1:
                        time.sleep(0.06 if is_tiger_trade else 0.04)
            else:
                try:
                    pyautogui.MINIMUM_SLEEP = 0.0005
                    pyautogui.MINIMUM_DURATION = 0.005
                    pyautogui.PAUSE = 0.0
                except Exception:
                    pass

                is_metascalp = self._is_metascalp_terminal()

                for batch_index, (glass, points) in enumerate(target_batches):
                    if (
                        (self._is_profit_forge_terminal() or self._is_metascalp_terminal())
                        and len(target_batches) > 1
                        and glass is not None
                    ):
                        self.lbl_status.setText(
                            t.get(
                                "calc_status_applying_glass",
                                "Выставляю в {glass} ({idx}/{total})...",
                            ).format(
                                glass=self._pf_glass_label(glass),
                                idx=batch_index + 1,
                                total=len(target_batches),
                            )
                        )
                        self.lbl_status.setStyleSheet(
                            f"color: cyan; font-size: {self._scaled_pt(7)}pt;"
                        )
                        QApplication.processEvents()

                    if is_metascalp:
                        # MetaScalp: first cell needs a short settle delay before editing starts.
                        time.sleep(0.06)

                    surf_hover_point = None
                    if self._is_surf_terminal():
                        surf_hover_point = self._get_surf_hover_point(glass)
                        if surf_hover_point is None:
                            self.lbl_status.setText(
                                t.get(
                                    "calc_surf_need_points",
                                    "⚠ SURF hover calibration point is missing",
                                )
                            )
                            self.lbl_status.setStyleSheet(
                                f"color: #FF9F0A; font-size: {self._scaled_pt(7)}pt;"
                            )
                            return

                    for transfer_index, (point_index, vol_to_send) in enumerate(transfers):
                        pyperclip.copy(vol_to_send)
                        if surf_hover_point is not None:
                            # SURF expands its compact preset strip on hover. Re-hover
                            # before each edit, then double-click the cell to edit it.
                            pyautogui.moveTo(
                                surf_hover_point[0],
                                surf_hover_point[1],
                                duration=0.015,
                            )
                            time.sleep(0.03)
                            pyautogui.moveTo(
                                points[point_index][0],
                                points[point_index][1],
                                duration=0.015,
                            )
                            pyautogui.click(clicks=2, interval=0.03)
                            keyboard.press_and_release("ctrl+v")
                            keyboard.press_and_release("enter")
                            time.sleep(0.025)
                            continue

                        time.sleep(0.01)
                        pyautogui.moveTo(
                            points[point_index][0],
                            points[point_index][1],
                            duration=0.015,
                        )
                        is_metascalp_first_calibrated = is_metascalp and point_index == 0
                        pyautogui.click()
                        if is_metascalp_first_calibrated:
                            # First captured MetaScalp cell: use live double click
                            # (two real clicks with pauses) for stable focus.
                            time.sleep(0.07)
                            pyautogui.click()
                            time.sleep(0.07)
                        elif is_metascalp:
                            time.sleep(0.012)
                        else:
                            time.sleep(0.012)
                        if not is_metascalp_first_calibrated:
                            pyautogui.doubleClick(interval=0.03)

                        if is_metascalp_first_calibrated:
                            time.sleep(0.03)
                        elif is_metascalp:
                            time.sleep(0.012)
                        else:
                            time.sleep(0.012)
                        keyboard.press_and_release("ctrl+a")
                        time.sleep(0.01)
                        keyboard.press_and_release("backspace")
                        time.sleep(0.01)
                        keyboard.press_and_release("ctrl+v")
                        time.sleep(0.012)
                        keyboard.press_and_release("enter")
                        time.sleep(0.025)

                    if batch_index < len(target_batches) - 1:
                        time.sleep(0.04)

            if self._uses_shared_preset_controls() and target_batches:
                applied_text = t.get(
                    "calc_status_done_glasses",
                    "✓ Выставлено в {count} пресет(а)",
                ).format(count=len(target_batches))
                self._set_transient_status_then_neutral(
                    applied_text,
                    t.get("calc_ready_to_apply", "Готово к выставлению"),
                    status_color="#38BE1D",
                    delay_ms=10000,
                )

                if bool(self.settings.get("pf_show_preview_frames", False)):
                    self._flash_pf_preview_frames([glass for glass, _ in target_batches if glass])
        except Exception as e:
            print(f"Error: {e}")
        finally:
            # restore original cursor position if captured
            if start_x is not None and start_y is not None:
                try:
                    pyautogui.moveTo(start_x, start_y)
                except Exception:
                    pass
            try:
                pyperclip.copy(old_clip)
            except Exception:
                pass
            # Окно остается свернутым - не разворачиваем автоматически

    def start_calibration_calc(self):
        """Начинает калибровку - очищает точки и показывает инструкции"""
        cells_count = self._get_terminal_cells_count()
        hk_coords = self.settings.get("hk_coords", "f2").upper()
        status_pt = self._scaled_pt(7)

        points = self._get_active_calc_points()
        menu_ready = False
        menu_kind = self._menu_terminal_kind()
        if self._is_surf_terminal():
            if len(points) >= cells_count and self._get_surf_hover_point() is not None:
                self.calc_calibration_active = False
                t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                ready_text = t.get(
                    "calc_surf_points_exists",
                    "✓ Points are already captured: {cells} cells",
                ).format(cells=cells_count)
                self._set_ready_status_with_neutral_timeout(ready_text)
                self.update_calibration_status()
                return

            self.calc_calibration_active = True
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            instruction = t.get(
                "calc_surf_calib_instruction",
                "Capture the collapsed selector area, then the five expanded cells using {hotkey}.",
            ).format(cells=cells_count, hotkey=hk_coords)
            self.lbl_status.setText(instruction)
            self.lbl_status.setStyleSheet(f"color: cyan; font-size: {status_pt}pt;")
            self.update_calibration_status()
            return

        if self._is_menu_terminal():
            menu_ready = self._is_menu_glass_ready(self._get_pf_active_glass())

        if self._is_menu_terminal():
            if menu_ready and len(points) >= cells_count:
                self.calc_calibration_active = False
                t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                exists_key = f"calc_{menu_kind}_points_exists"
                ready_text = t.get(exists_key, t["calc_calib_exists"]).format(cells=cells_count)
                self._set_ready_status_with_neutral_timeout(ready_text)
                self.update_calibration_status()
                return

            self.calc_calibration_active = True
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            instruction_key = f"calc_{menu_kind}_calib_instruction"
            instruction = t.get(
                instruction_key,
                "Hover the volume selector cells in the order book, choose the first one and press {hotkey}",
            ).format(cells=cells_count, hotkey=hk_coords)
            self.lbl_status.setText(instruction)
            self.lbl_status.setStyleSheet(
                f"color: cyan; font-size: {status_pt}pt;"
            )
            self.update_calibration_status()
            return

        if len(points) >= cells_count:
            self.calc_calibration_active = False
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            ready_text = t["calc_calib_exists"].format(cells=cells_count)
            self._set_ready_status_with_neutral_timeout(ready_text)
            self.update_calibration_status()
            return

        self.calc_calibration_active = True
        self.update_calibration_status()

    def capture_coords(self):
        """Захватывает координаты ячеек (ровно столько, сколько нужно)"""
        if not self._ensure_pyautogui_module():
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_status.setText(
                t.get(
                    "calc_capture_module_error",
                    "Ошибка калибровки: не удалось загрузить модуль управления мышью",
                )
            )
            self.lbl_status.setStyleSheet(
                f"color: #FF6B6B; font-size: {self._scaled_pt(7)}pt;"
            )
            return

        if not getattr(self, "calc_calibration_active", False):
            configured = self._get_terminal_cells_count()

            existing_points = self._get_active_calc_points()
            menu_ready = False
            if self._is_menu_terminal():
                menu_ready = self._is_menu_glass_ready(self._get_pf_active_glass())
            should_reset = len(existing_points) >= configured
            if self._is_surf_terminal():
                should_reset = (
                    should_reset and self._get_surf_hover_point() is not None
                )
            if self._is_menu_terminal():
                should_reset = should_reset and menu_ready

            if should_reset:
                self._reset_active_calc_calibration()
                self.calc_calibration_active = False
                hk_coords = self.settings.get("hk_coords", "f2").upper()
                t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                if self._is_menu_terminal():
                    menu_kind = self._menu_terminal_kind() or "tiger"
                    reset_key = f"calc_{menu_kind}_points_reset"
                    reset_text = t.get(reset_key, t["calc_calib_reset_short"]).format(hotkey=hk_coords)
                else:
                    reset_text = t["calc_calib_reset_short"].format(hotkey=hk_coords)
                self.lbl_status.setText(reset_text)
                self.lbl_status.setStyleSheet(f"color: #FF9F0A; font-size: {self._scaled_pt(7)}pt;")
                self._update_pf_multi_glass_ui()
                return

            self.start_calibration_calc()
            return

        cells_count = self._get_terminal_cells_count()

        try:
            x, y = pyautogui.position()
        except Exception:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            self.lbl_status.setText(
                t.get(
                    "calc_capture_position_error",
                    "Ошибка калибровки: не удалось получить позицию курсора",
                )
            )
            self.lbl_status.setStyleSheet(
                f"color: #FF6B6B; font-size: {self._scaled_pt(7)}pt;"
            )
            return

        if self._is_menu_terminal():
            requires_final_point = self._menu_terminal_requires_final_point()
            menu_open, menu_close = self._get_menu_points_for_glass(self._get_pf_active_glass())
            points = self._get_active_calc_points()

            if menu_open is None:
                self._set_menu_point_for_glass([x, y], is_close=False)
                self.save_settings()
                self.update_calibration_status()
                return

            if len(points) < cells_count:
                points.append([x, y])
                self._set_active_calc_points(points)
                self.save_settings()
                if len(points) >= cells_count and not requires_final_point:
                    self.calc_calibration_active = False
                    self._update_pf_multi_glass_ui()
                self.update_calibration_status()
                return

            if requires_final_point and menu_close is None:
                self._set_menu_point_for_glass([x, y], is_close=True)
                self.save_settings()
                self.calc_calibration_active = False
            elif not requires_final_point:
                self.calc_calibration_active = False

            self._update_pf_multi_glass_ui()
            self.update_calibration_status()
            return

        if self._is_surf_terminal() and self._get_surf_hover_point() is None:
            self._set_surf_hover_point([x, y])
            self.save_settings()
            if len(self._get_active_calc_points()) >= cells_count:
                self.calc_calibration_active = False
                self._update_pf_multi_glass_ui()
            self.update_calibration_status()
            return

        points = self._get_shared_active_calibration_points()

        # Если уже есть достаточно - не захватываем дальше
        if len(points) >= cells_count:
            self.calc_calibration_active = False
            self.update_calibration_status()
            return

        points.append([x, y])
        self._set_shared_active_calibration_points(points)
        self.save_settings()

        if len(points) >= cells_count:
            self.calc_calibration_active = False
            if self._is_profit_forge_terminal() and bool(
                self.settings.get("pf_show_preview_frames", False)
            ):
                QTimer.singleShot(
                    40,
                    lambda g=self._get_pf_active_glass(): self._flash_pf_preview_frames(
                        [g]
                    ),
                )
            self._update_pf_multi_glass_ui()

        self.update_calibration_status()

    def update_calibration_status(self):
        """Обновляет подсказку о калибровке при переключении вкладок"""
        # Обновляем, если мы на вкладке калькулятора или если вкладок вообще нет.
        if not hasattr(self, "tabs") or self.tabs.currentIndex() == 0:
            self._update_status_text()

    def _set_ready_status_with_neutral_timeout(self, text, ready_color="#38BE1D", delay_ms=5000):
        status_pt = self._scaled_pt(7)
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(f"color: {ready_color}; font-size: {status_pt}pt;")

        self._status_neutral_token += 1
        token = self._status_neutral_token

        def _neutralize():
            if token != self._status_neutral_token:
                return
            if getattr(self, "calc_calibration_active", False):
                return
            if not hasattr(self, "lbl_status"):
                return
            if self.lbl_status.text() != text:
                return
            self.lbl_status.setStyleSheet(f"color: #666; font-size: {self._scaled_pt(7)}pt;")

        QTimer.singleShot(int(delay_ms), _neutralize)

    def _set_transient_status_then_neutral(self, status_text, neutral_text, status_color="#FF9F0A", delay_ms=5000):
        status_pt = self._scaled_pt(7)
        self.lbl_status.setText(status_text)
        self.lbl_status.setStyleSheet(f"color: {status_color}; font-size: {status_pt}pt;")

        self._status_neutral_token += 1
        token = self._status_neutral_token

        def _neutralize():
            if token != self._status_neutral_token:
                return
            if getattr(self, "calc_calibration_active", False):
                return
            if not hasattr(self, "lbl_status"):
                return
            self.lbl_status.setText(neutral_text)
            self.lbl_status.setStyleSheet(f"color: #666; font-size: {self._scaled_pt(7)}pt;")

        QTimer.singleShot(int(delay_ms), _neutralize)

    def _update_status_text(self):
        """Внутренний метод для обновления текста статуса"""
        cells_count = self._get_terminal_cells_count()
        points_count = len(self._get_active_calc_points())
        hk_coords = self.settings.get("hk_coords", "f2").upper()
        status_pt = self._scaled_pt(7)
        pf_status_suffix = ""
        if self._uses_shared_preset_controls() and self._get_pf_glasses_count() > 1:
            pf_status_suffix = "  |  " + self._pf_glass_label(self._get_pf_active_glass())

        def _with_pf_suffix(text):
            if not pf_status_suffix:
                return text
            return f"{text}{pf_status_suffix}"

        if self._is_surf_terminal():
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            hover_point = self._get_surf_hover_point()
            if self.calc_calibration_active:
                if hover_point is None:
                    step_text = t.get(
                        "calc_surf_step_open",
                        "Hover over the collapsed volume selector and press {hotkey}",
                    ).format(hotkey=hk_coords)
                elif points_count < cells_count:
                    step_key = (
                        "calc_surf_step_cell_first"
                        if points_count == 0
                        else "calc_surf_step_cell_next"
                    )
                    step_text = t.get(
                        step_key,
                        "Hover over cell {num} and press {hotkey}",
                    ).format(num=points_count + 1, hotkey=hk_coords)
                else:
                    step_text = t.get(
                        "calc_surf_points_ready",
                        "✓ Points captured: {cells} cells",
                    ).format(cells=cells_count)
                self.lbl_status.setText(_with_pf_suffix(step_text))
                self.lbl_status.setStyleSheet(f"color: cyan; font-size: {status_pt}pt;")
            elif points_count >= cells_count and hover_point is not None:
                ready_text = t.get(
                    "calc_surf_points_ready",
                    "✓ Points captured: {cells} cells",
                ).format(cells=cells_count)
                self._set_ready_status_with_neutral_timeout(
                    _with_pf_suffix(ready_text)
                )
            else:
                need_text = t.get(
                    "calc_surf_need_points",
                    "⚠ SURF calibration points are missing",
                )
                self.lbl_status.setText(_with_pf_suffix(need_text))
                self.lbl_status.setStyleSheet(f"color: #666; font-size: {status_pt}pt;")
            return

        if self._is_menu_terminal():
            menu_kind = self._menu_terminal_kind() or "tiger"
            requires_final_point = self._menu_terminal_requires_final_point()
            menu_open, menu_close = self._get_menu_points_for_glass(self._get_pf_active_glass())
            has_open = menu_open is not None
            has_close = (not requires_final_point) or (menu_close is not None)

            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            if not self.calc_calibration_active and has_open and has_close and points_count >= cells_count:
                ready_key = f"calc_{menu_kind}_points_ready"
                ready_text = t.get(ready_key, t["calc_calib_ready"]).format(cells=cells_count)
                self._set_ready_status_with_neutral_timeout(ready_text)
                return

            if self.calc_calibration_active:
                if not has_open:
                    step_open_key = f"calc_{menu_kind}_step_open"
                    self.lbl_status.setText(
                        t.get(step_open_key, "Наведи на ячейки выбора объема в стакане, выбери 1 ячейку и нажми {hotkey}").format(
                            hotkey=hk_coords
                        )
                    )
                elif points_count < cells_count:
                    step_key = (
                        f"calc_{menu_kind}_step_cell_first"
                        if points_count == 0
                        else f"calc_{menu_kind}_step_cell_next"
                    )
                    self.lbl_status.setText(
                        t.get(step_key, "Теперь наведи на {num} ячейку и нажми {hotkey}").format(
                            num=points_count + 1,
                            hotkey=hk_coords,
                        )
                    )
                elif not has_close:
                    step_close_key = f"calc_{menu_kind}_step_close"
                    self.lbl_status.setText(
                        t.get(step_close_key, "Теперь наведи на крестик закрытия меню и нажми {hotkey}").format(
                            hotkey=hk_coords
                        )
                    )
                else:
                    ready_key = f"calc_{menu_kind}_points_ready"
                    self.lbl_status.setText(
                        t.get(ready_key, t["calc_calib_ready"]).format(cells=cells_count)
                    )
                self.lbl_status.setStyleSheet(f"color: cyan; font-size: {status_pt}pt;")
            else:
                need_key = f"calc_{menu_kind}_need_points"
                self.lbl_status.setText(
                    t.get(need_key, "⚠ Точки для выставления терминала не захвачены. Нажми горячую клавишу захвата")
                )
                self.lbl_status.setStyleSheet(f"color: #666; font-size: {status_pt}pt;")
            return

        if points_count == 0:
            if self.calc_calibration_active:
                t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
                self.lbl_status.setText(
                    t.get(
                        "calc_calib_step_first",
                        "Наведи на 1 ячейку объема и нажми {hotkey}",
                    ).format(hotkey=hk_coords)
                    + (pf_status_suffix if pf_status_suffix else "")
                )
                self.lbl_status.setStyleSheet(f"color: cyan; font-size: {status_pt}pt;")
            else:
                self.lbl_status.setText("")
                self.lbl_status.setStyleSheet(f"color: #666; font-size: {status_pt}pt;")
        elif points_count < cells_count:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            if self.calc_calibration_active:
                self.lbl_status.setText(
                    _with_pf_suffix(
                        t.get(
                        "calc_calib_step_next",
                        "Наведи на {num} ячейку объема и нажми {hotkey} ({points} из {cells})",
                        ).format(
                            num=points_count + 1,
                            hotkey=hk_coords,
                            points=points_count,
                            cells=cells_count,
                        )
                    )
                )
                self.lbl_status.setStyleSheet(f"color: cyan; font-size: {status_pt}pt;")
            else:
                self.lbl_status.setText(
                    _with_pf_suffix(
                        t["calc_calib_progress"].format(
                            points=points_count, cells=cells_count
                        )
                    )
                )
                self.lbl_status.setStyleSheet(f"color: #FF9F0A; font-size: {status_pt}pt;")
        else:
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            ready_text = _with_pf_suffix(t["calc_calib_ready"].format(cells=cells_count))
            self._set_ready_status_with_neutral_timeout(ready_text)

    def increase_cells(self):
        """Увеличивает количество ячеек"""
        if not self._is_metascalp_terminal():
            return
        current = int(self.lbl_cells_count.text())
        if current < 5:
            current += 1
            current = self._set_terminal_cells_count(current)
            self.lbl_cells_count.setText(str(current))
            self.on_cells_changed()
            self._apply_manual_min_order_defaults()
            self._sync_cells_count_controls(refresh_table=False)

    def decrease_cells(self):
        """Уменьшает количество ячеек"""
        if not self._is_metascalp_terminal():
            return
        current = int(self.lbl_cells_count.text())
        if current > 1:
            current -= 1
            current = self._set_terminal_cells_count(current)
            self.lbl_cells_count.setText(str(current))
            self.on_cells_changed()
            self._apply_manual_min_order_defaults()
            self._sync_cells_count_controls(refresh_table=False)

    def _apply_manual_min_order_defaults(self):
        if (
            not hasattr(self, "cb_distribution")
            or int(self.cb_distribution.currentIndex()) != 2
        ):
            return

        active_rows = self._get_active_rows_for_table()
        if not active_rows:
            return

        total_vol = float(self._get_active_table_total_volume() or 0.0)
        if total_vol <= 0:
            return

        try:
            min_order = float(self.inp_min_order.text().replace(",", ".") or 0)
        except Exception:
            min_order = 0.0

        if min_order <= 0:
            return

        min_percent = int(round((min_order / total_vol) * 100))
        min_percent = max(1, min(100, min_percent))

        try:
            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
        except Exception:
            pass

        for i in active_rows:
            # Skip the target row that has transferred volume - preserve it as-is
            if i == self.position_target_row_active:
                continue
            percent_item = self.cells_table.item(i, 2)
            if not percent_item:
                continue
            current_text = (percent_item.text() or "").strip()
            current_val = int(current_text) if current_text.isdigit() else 0
            if current_val <= 0:
                percent_item.setText(str(min_percent))

        self.cells_table.itemChanged.connect(self.on_table_item_changed)
        self.update_cell_volumes()
        self.save_cell_settings()

    def _apply_manual_active_row_flags(self):
        if (
            not hasattr(self, "cb_distribution")
            or int(self.cb_distribution.currentIndex()) != 2
            or not hasattr(self, "cells_table")
        ):
            return

        default_flags = QTableWidgetItem().flags()
        for i in range(5):
            for col in range(3):
                item = self.cells_table.item(i, col)
                if not item:
                    continue
                if col in (0, 1):
                    item.setFlags(default_flags & ~Qt.ItemFlag.ItemIsEditable)
                else:
                    item.setFlags(default_flags)

    def toggle_cells_order(self):
        """Переворачивает порядок ячеек и % от общего в активном режиме."""
        if not hasattr(self, "cells_table"):
            return

        pos_mode = bool(self.settings.get("pos_mode_enabled", False))
        reverse_key = "cells_reversed_pos" if pos_mode else "cells_reversed"

        cells_count = 5
        percentages = []
        for i in range(cells_count):
            item = self.cells_table.item(i, 2)
            if item and item.text():
                try:
                    percentages.append(int(item.text()))
                except Exception:
                    percentages.append(0)
            else:
                percentages.append(0)

        reversed_percentages = list(reversed(percentages))

        try:
            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
        except Exception:
            pass

        for i in range(cells_count):
            item = self.cells_table.item(i, 2)
            if item:
                item.setText(str(reversed_percentages[i]))

        try:
            self.cells_table.itemChanged.connect(self.on_table_item_changed)
        except Exception:
            pass

        self.settings[reverse_key] = not bool(self.settings.get(reverse_key, False))
        self.update_cells_labels()
        self._update_selected_rows_visuals()
        self.update_cell_volumes()
        self.save_cell_settings()

    def on_cells_changed(self):
        """Обновляет поля ячеек при изменении количества (таблица всегда 5 строк)"""
        cells_count = int(self.lbl_cells_count.text())

        # Отключаем сигнал на время обновления
        try:
            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
        except:
            pass

        # Очищаем таблицу
        self.cells_table.setRowCount(0)

        # Всегда создаем 5 строк
        for i in range(5):
            self.cells_table.insertRow(i)

            is_active = i < cells_count

            # Ячейка с названием (не редактируется, не выделяется)
            t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])
            label_item = QTableWidgetItem(t["calc_cell_label"].format(num=i + 1))
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            label_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cells_table.setItem(i, 0, label_item)

            # Ячейка с объемом (не редактируется, не выделяется, рассчитывается)
            volume_item = QTableWidgetItem("0")
            volume_item.setFlags(
                volume_item.flags()
                & ~Qt.ItemFlag.ItemIsEditable
                & ~Qt.ItemFlag.ItemIsSelectable
            )
            volume_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cells_table.setItem(i, 1, volume_item)

            # Ячейка с процентом (редактируется только для активных)
            percent_item = QTableWidgetItem("")
            percent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cells_table.setItem(i, 2, percent_item)

        # Обновляем подписи ячеек с учетом порядка
        self.update_cells_labels()

        # Обновляем высоту таблицы, чтобы всегда были видны 5 строк
        self.update_cells_table_height()
        self._sync_selected_rows_with_cells_count()

        # Переприменяем текущий тип распределения
        preset_index = self.cb_distribution.currentIndex()

        if preset_index != 2 and self.position_target_row_active is not None:
            self._set_position_target_row_mask(None)
        self._apply_preset_values(preset_index)

        # Загружаем сохраненные значения процентов только для режима "Вручную"
        if preset_index == 2:
            saved_multipliers = self._get_manual_distribution_values()

            # Use actual active rows (which may include target row beyond cells_count)
            active_rows = self._get_active_rows_for_table()
            for i in active_rows:
                # Skip loading saved value for target row if we have active transfer
                # - keep it at 100% to preserve transferred volume
                if i == self.position_target_row_active:
                    percent_item = self.cells_table.item(i, 2)
                    if percent_item:
                        percent_item.setText("100")
                    continue
                if i < len(saved_multipliers) and saved_multipliers[i] > 0:
                    percent_item = self.cells_table.item(i, 2)
                    if percent_item:
                        percent_item.setText(str(saved_multipliers[i]))
            self._apply_manual_active_row_flags()

        self._update_selected_rows_visuals()

        # Подключаем сигнал изменения
        self.cells_table.itemChanged.connect(self.on_table_item_changed)

        self.update_cell_volumes()
        self.save_cell_settings()
        self._update_status_text()

    def update_cells_labels(self):
        if not hasattr(self, "cells_table"):
            return

        cells_count = int(self.lbl_cells_count.text())
        pos_mode = bool(self.settings.get("pos_mode_enabled", False))
        is_reversed = bool(self.settings.get("cells_reversed_pos" if pos_mode else "cells_reversed", False))

        active_labels = list(range(1, cells_count + 1))
        if is_reversed:
            active_labels.reverse()

        t = TRANS.get(self.settings.get("lang", "ru"), TRANS["ru"])

        for i in range(5):
            label_item = self.cells_table.item(i, 0)
            if not label_item:
                continue

            if i < cells_count:
                label_item.setText(t["calc_cell_label"].format(num=active_labels[i]))
            else:
                label_item.setText(t["calc_cell_label"].format(num=i + 1))

        self._update_selected_rows_visuals()

    def update_cells_table_height(self):
        if not hasattr(self, "cells_table"):
            return

        # Всегда отключаем скроллбары для таблицы калькулятора:
        # горизонтальный скролл может появляться на некоторых масштабах и "съедать"
        # высоту последней строки, из-за чего визуально таблица заходит под кнопку.
        self.cells_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.cells_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Рассчитываем высоту строки по реальному sizeHint
        row_height = 0
        for i in range(self.cells_table.rowCount()):
            row_height = max(row_height, self.cells_table.sizeHintForRow(i))

        # Fallback, если sizeHint еще не готов
        if row_height <= 0:
            scale = self.settings.get("scale", self.base_scale)
            try:
                ratio = int(scale) / float(self.base_scale) if self.base_scale else 1.0
            except Exception:
                ratio = 1.0
            min_row_h = 16 if int(scale) < 100 else 20
            row_height = max(min_row_h, int(28 * ratio))

        # Фиксируем высоту строк, чтобы 5 строк всегда были видны
        for i in range(self.cells_table.rowCount()):
            self.cells_table.setRowHeight(i, row_height)

        header = self.cells_table.horizontalHeader()
        header_height = max(header.height(), header.sizeHint().height())

        # Берем фактическую длину вертикального хедера после установки высот строк.
        # Это надежнее, чем row_height * N на разных DPI/масштабах/шрифтах.
        rows_height = self.cells_table.verticalHeader().length()

        # Добавляем небольшой буфер, чтобы нижняя строка никогда не обрезалась.
        scale = self.settings.get("scale", self.base_scale)
        try:
            ratio = int(scale) / float(self.base_scale) if self.base_scale else 1.0
        except Exception:
            ratio = 1.0
        bottom_buffer = max(6, int(8 * ratio))

        table_height = (
            header_height
            + rows_height
            + (self.cells_table.frameWidth() * 2)
            + bottom_buffer
        )

        # Keep full table body visible even when style metrics are reported late.
        min_rows_height = row_height * max(1, int(self.cells_table.rowCount()))
        table_height = max(
            table_height,
            header_height + min_rows_height + (self.cells_table.frameWidth() * 2) + bottom_buffer,
        )

        self.cells_table.setFixedHeight(table_height)

        if self.isVisible():
            self._set_window_size_with_extra_height(grow_only=False)

    def on_table_item_clicked(self, item):
        """Обработчик клика по ячейке: toggle-мультивыбор в колонке 0, редактирование в колонке 2"""
        self._clear_ghost_focus()
        if not item:
            return

        if item.column() == 0:
            row = item.row()

            selected = set(getattr(self, "selected_transfer_rows", set()))
            if row in selected:
                selected.remove(row)
            else:
                selected.add(row)

            self.selected_transfer_rows = selected
            key = self._selected_rows_setting_key()
            self.settings[key] = sorted(selected)
            if not bool(self.settings.get("pos_mode_enabled", False)):
                self.settings["selected_cells"] = sorted(selected)

            if bool(self.settings.get("pos_mode_enabled", False)) and self.cb_distribution.currentIndex() == 2:
                self._capture_manual_distribution_snapshot_from_table()

            preset_index = self.cb_distribution.currentIndex()
            if preset_index != 2:
                try:
                    self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
                except Exception:
                    pass
                self._apply_preset_values(preset_index)
                self.cells_table.itemChanged.connect(self.on_table_item_changed)

            # In manual mode we must preserve the last user-entered values instead of
            # forcing the selected cell to 100% when rows are toggled on/off.
            if preset_index == 2:
                self._capture_manual_distribution_snapshot_from_table()
                self._restore_manual_distribution_for_active_rows(selected)
            elif bool(self.settings.get("pos_mode_enabled", False)):
                override = float(getattr(self, "table_volume_override", 0.0) or 0.0)
                if override <= 0:
                    override = float(self.settings.get("pos_table_volume_override", 0.0) or 0.0)
                    if override > 0:
                        self.table_volume_override = override
                delta = float(getattr(self, "pos_adjust_delta", 0.0) or 0.0)
                if (override > 0) or (delta > 0):
                    if len(selected) == 1:
                        target_row = next(iter(selected))
                        try:
                            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
                        except Exception:
                            pass
                        for i in range(self.cells_table.rowCount()):
                            p_item = self.cells_table.item(i, 2)
                            if not p_item:
                                continue
                            if i == target_row:
                                p_item.setText("100")
                            else:
                                p_item.setText("")
                        self.cells_table.itemChanged.connect(self.on_table_item_changed)

            self._update_selected_rows_visuals()
            self.update_cell_volumes()
            self.save_cell_settings()

            self.cells_table.clearSelection()
            self.cells_table.setCurrentItem(None)
        elif item.column() == 1:
            self.cells_table.clearSelection()
            self.cells_table.setCurrentItem(None)
        elif item.column() == 2:
            # Percent column: 1-click to edit, 2-click to select all
            now_ms = int(time.time() * 1000)
            last_ms = (item.data(Qt.ItemDataRole.UserRole + 1) or 0)
            click_count = (item.data(Qt.ItemDataRole.UserRole + 2) or 0)

            # Reset click_count if more than 350ms have passed since last click
            if now_ms - last_ms > 350 or last_ms == 0:
                click_count = 0

            # Reset click_count for all other items to avoid interference
            for row in range(self.cells_table.rowCount()):
                for col in range(self.cells_table.columnCount()):
                    other_item = self.cells_table.item(row, col)
                    if other_item is not item:
                        other_item.setData(Qt.ItemDataRole.UserRole + 2, 0)
                        other_item.setData(Qt.ItemDataRole.UserRole + 1, 0)

            click_count += 1
            item.setData(Qt.ItemDataRole.UserRole + 1, now_ms)
            item.setData(Qt.ItemDataRole.UserRole + 2, click_count)

            if click_count == 1:
                # First click: open editor with cursor at end, no selection
                self.cells_table.editItem(item)
                # Ensure no text is selected after editor opens
                def deselect_and_position():
                    from PyQt6.QtWidgets import QApplication
                    editor = QApplication.instance().focusWidget()
                    if isinstance(editor, QLineEdit):
                        editor.deselect()
                        editor.setCursorPosition(len(editor.text()))
                QTimer.singleShot(0, deselect_and_position)
            elif click_count == 2:
                # Second click: select all text
                from PyQt6.QtWidgets import QApplication
                editor = QApplication.instance().focusWidget()
                if not editor or not isinstance(editor, QLineEdit):
                    # If no editor yet, open and select with delay
                    self.cells_table.editItem(item)
                    def select_all_delayed():
                        ed = QApplication.instance().focusWidget()
                        if isinstance(ed, QLineEdit):
                            # Use setSelection() to explicitly select all text
                            ed.setSelection(0, len(ed.text()))
                    QTimer.singleShot(15, select_all_delayed)
                else:
                    # Already editing, select all text
                    editor.setSelection(0, len(editor.text()))


    def _persist_manual_percent_snapshot(self, values=None, pos_mode=None):
        """Immediately writes the current manual percentages to settings.

        Blank cells during row toggles or partial edits must preserve the last
        non-zero manual value instead of being rewritten to zero, otherwise a
        single clear operation wipes the entire manual distribution snapshot.
        """
        if pos_mode is None:
            pos_mode = bool(self.settings.get("pos_mode_enabled", False))

        previous_values = self._get_manual_distribution_values(pos_mode=pos_mode)

        if values is None:
            values = []
            for i in range(5):
                cell = self.cells_table.item(i, 2) if hasattr(self, "cells_table") else None
                text = (cell.text() if cell else "") or ""
                text = str(text).strip()
                if not text:
                    values.append(int(previous_values[i]) if i < len(previous_values) else 0)
                    continue
                try:
                    values.append(max(0, min(100, int(text))))
                except Exception:
                    values.append(int(previous_values[i]) if i < len(previous_values) else 0)

        values = [max(0, min(100, int(v))) for v in values[:5]] + [0] * max(0, 5 - len(values[:5]))
        manual_key = self._manual_distribution_setting_key(pos_mode)
        if bool(pos_mode):
            self.settings[manual_key] = list(values)
            self.settings["scalp_multipliers"] = list(values)
        else:
            self.settings["scalp_manual_multipliers"] = list(values)
            self.settings[manual_key] = list(values)
            self.settings["scalp_multipliers"] = list(values)
        self.settings[self._distribution_type_setting_key(pos_mode)] = int(
            self.cb_distribution.currentIndex() if hasattr(self, "cb_distribution") else 2
        )

    def on_table_item_changed(self, item):
        """Вызывается когда изменяется ячейка таблицы"""
        if item.column() == 2:  # Только для колонки с процентами
            if (
                hasattr(self, "cb_distribution")
                and int(self.cb_distribution.currentIndex()) != 2
            ):
                return

            text = item.text().strip()
            if text == "":
                self._capture_current_manual_distribution()
                self._persist_manual_percent_snapshot()
                self.update_cell_volumes()
                self.save_cell_settings()
                self._schedule_smooth_content_resize(force=True)
                return

            try:
                value = int(text)
            except ValueError:
                item.setText("")
                self._capture_current_manual_distribution()
                self._persist_manual_percent_snapshot()
                self.update_cell_volumes()
                self.save_cell_settings()
                self._schedule_smooth_content_resize(force=True)
                return

            value = max(0, min(100, value))
            normalized = str(value)
            if normalized != text:
                item.setText(normalized)

            self._capture_current_manual_distribution()
            self._persist_manual_percent_snapshot()
            self.update_cell_volumes()
            self.save_cell_settings()
            self._schedule_smooth_content_resize(force=True)

    def toggle_all_transfer_rows(self):
        if not hasattr(self, "cells_table"):
            return
        selected = set(getattr(self, "selected_transfer_rows", set()))
        if len(selected) >= 5:
            selected = set()
        else:
            selected = set(range(5))

        self.selected_transfer_rows = selected
        key = self._selected_rows_setting_key()
        self.settings[key] = sorted(selected)
        if not bool(self.settings.get("pos_mode_enabled", False)):
            self.settings["selected_cells"] = sorted(selected)

        preset_index = (
            int(self.cb_distribution.currentIndex())
            if hasattr(self, "cb_distribution")
            else 2
        )
        if preset_index == 2:
            self._capture_manual_distribution_snapshot_from_table()

        if preset_index != 2:
            try:
                self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
            except Exception:
                pass
            self._apply_preset_values(preset_index)
            self.cells_table.itemChanged.connect(self.on_table_item_changed)
        elif preset_index == 2:
            self._restore_manual_distribution_for_active_rows(selected)

        self._update_selected_rows_visuals()
        self.update_cell_volumes()
        self.save_cell_settings()

    def finalize_startup_layout(self):
        logging.debug("finalize_startup_layout START")
        self.update_cells_table_height()
        logging.debug("update_cells_table_height done")
        self._adapt_window_width_to_content()
        logging.debug("_adapt_window_width_to_content done")
        self._set_window_size_with_extra_height()
        logging.debug("_set_window_size_with_extra_height done")
        self._ensure_window_on_screen(margin=6, prefer_active=True)
        logging.debug("_ensure_window_on_screen done")
        if self._startup_window_size is None:
            self._startup_window_size = (int(self.width()), int(self.height()))
        if not self._resize_len_baseline:
            for name in (
                "inp_dep",
                "inp_risk",
                "inp_stop",
                "inp_pos_vol",
                "inp_pos_risk",
                "inp_pos_stop",
                "inp_pos_stop_now",
                "inp_min_order",
            ):
                widget = getattr(self, name, None)
                if widget:
                    self._resize_len_baseline[name] = len((widget.text() or "").strip())
            self._last_applied_resize_pressure = self._current_resize_pressure_chars()

    def _apply_preset_values(self, preset_index):
        """Применяет значения выбранного пресета"""
        active_rows = self._get_active_rows_for_table()
        reverse_key = self._cells_reversed_setting_key()
        if bool(self.settings.get(reverse_key, False)):
            active_rows = list(reversed(active_rows))
        cells_count = len(active_rows)

        if preset_index == 2:  # Вручную
            return

        if cells_count <= 0:
            return

        presets = {
            0: "equal",  # Равномерно
            1: "decreasing",  # Убывающая: 100, 75, 50, 25, 10
        }

        preset = presets.get(preset_index, "equal")
        values = []

        if preset == "equal":
            # Равномерное распределение
            equal_percent = int(100 / cells_count)
            remainder = 100 % cells_count
            for i in range(cells_count):
                value = equal_percent
                if i < remainder:
                    value += 1
                values.append(value)
        elif preset == "decreasing":
            values = [100, 75, 50, 25, 10][:cells_count]

        # Применяем значения
        for idx, row in enumerate(active_rows):
            item = self.cells_table.item(row, 2)
            if item:
                item.setText(str(values[idx]))

    def _get_manual_distribution_values(self, pos_mode=None):
        if pos_mode is None:
            pos_mode = bool(self.settings.get("pos_mode_enabled", False))
        key = self._manual_distribution_setting_key(pos_mode)
        saved = self.settings.get(key, None)
        if saved is None:
            saved = self.settings.get(
                "scalp_manual_multipliers",
                self.settings.get("scalp_multipliers", [100, 50, 25, 10, 0]),
            )
        if not isinstance(saved, list):
            saved = [100, 50, 25, 10, 0]
        return list(saved)[:5] + [0] * max(0, 5 - len(saved))

    def _capture_current_manual_distribution(self, pos_mode=None):
        if not hasattr(self, "cells_table"):
            return

        previous_values = self._get_manual_distribution_values(
            pos_mode=bool(self.settings.get("pos_mode_enabled", False))
            if pos_mode is None
            else pos_mode
        )

        manual_values = []
        for i in range(5):
            item = self.cells_table.item(i, 2)
            text = (item.text() if item else "") or ""
            text = str(text).strip()
            if not text or not text.isdigit():
                manual_values.append(int(previous_values[i]) if i < len(previous_values) else 0)
                continue
            manual_values.append(max(0, min(100, int(text))))

        if pos_mode is None:
            pos_mode = bool(self.settings.get("pos_mode_enabled", False))
        key = self._manual_distribution_setting_key(pos_mode)
        self.settings[key] = manual_values
        if bool(pos_mode):
            self.settings["scalp_multipliers"] = list(manual_values)
        else:
            self.settings["scalp_manual_multipliers"] = list(manual_values)
            self.settings["scalp_multipliers"] = list(manual_values)

    def _capture_manual_distribution_snapshot_from_table(self, pos_mode=None):
        """Сохраняет текущие проценты, но не затирает старые ручные значения пустыми ячейками."""
        if not hasattr(self, "cells_table"):
            return
        if pos_mode is None:
            pos_mode = bool(self.settings.get("pos_mode_enabled", False))

        previous_values = self._get_manual_distribution_values(pos_mode=pos_mode)
        manual_values = []
        for i in range(5):
            item = self.cells_table.item(i, 2)
            text = (item.text() if item else "") or ""
            text = str(text).strip()
            if not text:
                manual_values.append(int(previous_values[i]) if i < len(previous_values) else 0)
                continue
            try:
                val = int(text)
                manual_values.append(max(0, min(100, val)))
            except Exception:
                manual_values.append(int(previous_values[i]) if i < len(previous_values) else 0)
        self.settings[self._manual_distribution_setting_key(pos_mode)] = manual_values

    def _restore_manual_distribution(self):
        if not hasattr(self, "cells_table"):
            return

        saved = self._get_manual_distribution_values()
        # Keep stored manual values in their actual row order. The reverse button
        # should be the only place that flips the order visually.

        # Guard against stale zero snapshots from older runs. If the current manual
        # key is empty/zero but the generic manual key has real values, prefer the
        # real values when restoring the table.
        if not any(int(v) > 0 for v in saved):
            generic_saved = self.settings.get("scalp_manual_multipliers", saved)
            if isinstance(generic_saved, list) and any(int(v) > 0 for v in generic_saved):
                saved = list(generic_saved)

        active_rows = set(self._get_active_rows_for_table())
        for i in range(5):
            item = self.cells_table.item(i, 2)
            if not item:
                continue
            if i in active_rows:
                val = saved[i]
                item.setText(str(int(val) if str(val).isdigit() else 0))
            else:
                item.setText("")

        self._apply_manual_active_row_flags()

    def _restore_manual_distribution_for_active_rows(self, selected_rows=None):
        if not hasattr(self, "cells_table"):
            return
        if hasattr(self, "cb_distribution") and int(self.cb_distribution.currentIndex()) != 2:
            return

        pos_mode = bool(self.settings.get("pos_mode_enabled", False))

        if selected_rows is None:
            selected_rows = set(self._get_active_rows_for_table())
        else:
            selected_rows = {
                int(i)
                for i in selected_rows
                if isinstance(i, (int, str)) and 0 <= int(i) < 5
            }

        # Preserve the last valid percentage for each row before clearing inactive ones.
        # A row may be temporarily hidden while toggling, but its previous manual value
        # must remain in the snapshot so re-enabling it restores the original value
        # instead of empty/zero, while position mode keeps the special 100% fallback.
        previous_values = self._get_manual_distribution_values(pos_mode=pos_mode)
        manual_snapshot = []
        for i in range(5):
            item = self.cells_table.item(i, 2)
            text = (item.text() if item else "") or ""
            text = str(text).strip()
            if text:
                try:
                    manual_snapshot.append(max(0, min(100, int(text))))
                    continue
                except Exception:
                    pass
            manual_snapshot.append(int(previous_values[i]) if i < len(previous_values) else 0)
        self.settings[self._manual_distribution_setting_key(pos_mode)] = manual_snapshot

        saved = list(manual_snapshot)
        if not any(int(v) > 0 for v in saved):
            persisted = self._get_manual_distribution_values(pos_mode=pos_mode)
            if any(int(v) > 0 for v in persisted):
                saved = list(persisted)

        # Preserve the underlying row-based percentage snapshot. The reverse button
        # changes only the visible display order, not the stored per-row values.
        # If we reverse here again, toggling an individual cell flips the values a
        # second time even when the reverse command was not pressed.
        has_real_manual_value = any(int(v) > 0 for v in saved)
        try:
            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
        except Exception:
            pass
        try:
            for i in range(5):
                item = self.cells_table.item(i, 2)
                if not item:
                    continue
                if i in selected_rows:
                    val = 0
                    if i < len(saved):
                        try:
                            val = int(saved[i])
                        except Exception:
                            val = 0
                    if val > 0:
                        item.setText(str(val))
                    elif pos_mode and len(selected_rows) == 1 and min(selected_rows) == i and not has_real_manual_value:
                        item.setText("100")
                    else:
                        item.setText("")
                else:
                    item.setText("")
        finally:
            try:
                self.cells_table.itemChanged.connect(self.on_table_item_changed)
            except Exception:
                pass

    def _distribution_type_setting_key(self, pos_mode_enabled=None):
        if pos_mode_enabled is None:
            pos_mode_enabled = bool(self.settings.get("pos_mode_enabled", False))
        return (
            "scalp_distribution_type_pos"
            if bool(pos_mode_enabled)
            else "scalp_distribution_type"
        )

    def _cells_reversed_setting_key(self, pos_mode_enabled=None):
        if pos_mode_enabled is None:
            pos_mode_enabled = bool(self.settings.get("pos_mode_enabled", False))
        return "cells_reversed_pos" if bool(pos_mode_enabled) else "cells_reversed"

    def _manual_distribution_setting_key(self, pos_mode_enabled=None, pos_mode=None):
        if pos_mode is not None:
            pos_mode_enabled = pos_mode
        if pos_mode_enabled is None:
            pos_mode_enabled = bool(self.settings.get("pos_mode_enabled", False))
        return (
            "scalp_manual_multipliers_pos"
            if bool(pos_mode_enabled)
            else "scalp_manual_multipliers"
        )

    def _save_current_distribution_state(self, pos_mode_enabled):
        if not hasattr(self, "cb_distribution"):
            return
        preset_index = int(self.cb_distribution.currentIndex() or 0)
        self.settings[self._distribution_type_setting_key(pos_mode_enabled)] = preset_index
        if preset_index == 2:
            self._capture_current_manual_distribution(pos_mode=pos_mode_enabled)

    def _restore_distribution_state(self, enabled):
        if not hasattr(self, "cb_distribution"):
            return

        if enabled:
            preset_index = int(
                self.settings.get(
                    self._distribution_type_setting_key(enabled),
                    self.settings.get("scalp_distribution_type", 0),
                )
                or 0
            )
        else:
            preset_index = int(
                self.settings.get(self._distribution_type_setting_key(enabled), 0) or 0
            )
        if preset_index >= 3:
            preset_index = 0

        self.cb_distribution.blockSignals(True)
        self.cb_distribution.setCurrentIndex(preset_index)
        self.cb_distribution.blockSignals(False)

        try:
            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
        except Exception:
            pass

        if preset_index == 2:
            self._restore_manual_distribution()
        else:
            self._apply_preset_values(preset_index)

        self.cells_table.itemChanged.connect(self.on_table_item_changed)
        self._update_selected_rows_visuals()
        self.update_cell_volumes()
        if not bool(getattr(self, "_startup_restore_suppressed", False)):
            self.save_cell_settings()

    def _selected_rows_setting_key(self, pos_mode_enabled=None):
        if pos_mode_enabled is None:
            pos_mode_enabled = bool(self.settings.get("pos_mode_enabled", False))
        return "selected_cells_pos" if bool(pos_mode_enabled) else "selected_cells"

    def _save_selected_rows_state(self, pos_mode_enabled):
        if not hasattr(self, "selected_transfer_rows"):
            return
        key = self._selected_rows_setting_key(pos_mode_enabled)
        self.settings[key] = sorted(int(i) for i in list(self.selected_transfer_rows))

    def _restore_selected_rows_state(self, enabled):
        key = self._selected_rows_setting_key(enabled)
        raw = self.settings.get(key, None)
        if raw is None:
            raw = self.settings.get("selected_cells", [])
        try:
            selected = set(int(i) for i in (raw or []) if str(i).isdigit())
        except Exception:
            selected = set()
        self.selected_transfer_rows = selected
        try:
            self._update_selected_rows_visuals()
        except Exception:
            pass

    def apply_distribution_preset(self):
        """Применяет выбранную предустановку распределения"""
        preset_index = self.cb_distribution.currentIndex()
        prev_preset_index = int(
            self.settings.get(self._distribution_type_setting_key(), 0) or 0
        )

        if prev_preset_index == 2 and preset_index != 2:
            self._capture_current_manual_distribution()

        if preset_index != 2:
            self.table_volume_override = 0.0
            self.settings["pos_table_volume_override"] = 0.0

        if preset_index == 2 and hasattr(self, "lbl_cells_count"):
            # In manual mode, preserve the current cell count (don't force to 1)
            current_cells_count = int(self.lbl_cells_count.text())

        if preset_index != 2 and self.position_target_row_active is not None:
            self._set_position_target_row_mask(None)

        # Отключаем сигнал чтобы не вызывать сохранение много раз
        try:
            self.cells_table.itemChanged.disconnect(self.on_table_item_changed)
        except:
            pass

        # Применяем значения пресета
        if preset_index == 2:
            self._restore_manual_distribution()
        else:
            self._apply_preset_values(preset_index)

        # Включаем сигнал обратно
        self.cells_table.itemChanged.connect(self.on_table_item_changed)

        # Сохраняем выбранный тип и всё остальное
        self.settings[self._distribution_type_setting_key()] = preset_index
        self._update_selected_rows_visuals()
        self.update_cell_volumes()
        self.save_cell_settings()  # This calls save_settings() internally

    def _get_active_table_total_volume(self):
        override = float(getattr(self, "table_volume_override", 0.0) or 0.0)
        if override <= 0:
            override = float(self.settings.get("pos_table_volume_override", 0.0) or 0.0)
            if override > 0:
                self.table_volume_override = override
        if override > 0:
            return override

        if bool(self.settings.get("pos_mode_enabled", False)):
            delta = float(getattr(self, "pos_adjust_delta", 0.0) or 0.0)
            if delta > 0:
                return delta
        return float(getattr(self, "current_vol", 0.0) or 0.0)

    def update_cell_volumes(self):
        """Обновляет объемы в каждой ячейке на основе процентов и минимума"""
        active_rows = set(self._get_active_rows_for_table())
        total_vol = self._get_active_table_total_volume()
        p_vol = self._get_calc_volume_precision()
        preset_index = (
            int(self.cb_distribution.currentIndex())
            if hasattr(self, "cb_distribution")
            else 2
        )

        try:
            min_order = float(self.inp_min_order.text().replace(",", ".") or 6)
        except:
            min_order = 6

        self.cells_table.blockSignals(True)
        for i in range(5):
            volume_item = self.cells_table.item(i, 1)
            percent_item = self.cells_table.item(i, 2)

            if not volume_item:
                continue

            if i in active_rows and percent_item:
                try:
                    percent = float(percent_item.text() or 0)
                    raw_volume = (total_vol * percent) / 100.0
                    if preset_index == 0:  # Равномерно: не раздуваем сумму до min_order
                        volume = raw_volume
                    else:
                        volume = max(min_order, raw_volume)  # Не меньше минимума
                    volume_item.setText(
                        f"{volume:,.{p_vol}f}".replace(",", " ").replace(".", ",")
                    )
                except:
                    volume_item.setText("0")
            else:
                volume_item.setText("")
                if percent_item:
                    percent_item.setText("")

            # Сохраняем минимум в настройки
            self.settings["scalp_min_order"] = min_order
        self.cells_table.blockSignals(False)
        self._update_selected_rows_visuals()

    def on_min_order_changed(self):
        """Вызывается при нажатии Enter в поле минимального ордера"""
        self._apply_min_order_live()
        self.inp_min_order.deselect()
        self.inp_min_order.clearFocus()

    def on_min_order_live_changed(self):
        if hasattr(self, "_min_order_live_timer"):
            self._min_order_live_timer.start(20)
        else:
            self._apply_min_order_live()

    def _apply_min_order_live(self):
        self.update_cell_volumes()
        self._schedule_smooth_content_resize()
        self.save_cell_settings()

    def _commit_input(self):
        sender = self.sender()
        if isinstance(sender, QLineEdit):
            self._clear_ghost_focus()
            sender.deselect()
            sender.clearFocus()

    def _clear_ghost_focus(self, except_obj=None):
        """Очищает свойства фокуса (ghost focus больше не используется, оставлено для совместимости)"""
        self._ghost_input = None


    def save_cell_settings(self):
        """Сохраняет настройки ячеек"""
        if self.position_target_row_active is not None:
            cells_count = int(self._get_terminal_cells_count())
        else:
            cells_count = int(self.lbl_cells_count.text())
        multipliers = []
        is_manual_mode = hasattr(self, "cb_distribution") and int(self.cb_distribution.currentIndex()) == 2
        saved_manual = self._get_manual_distribution_values(
            pos_mode=bool(self.settings.get("pos_mode_enabled", False))
        )

        for i in range(5):
            item = self.cells_table.item(i, 2)
            if item:
                val = item.text().strip()
                if not val:
                    if is_manual_mode and i < len(saved_manual):
                        mult = int(saved_manual[i])
                    else:
                        mult = 0
                else:
                    try:
                        mult = int(val)
                    except Exception:
                        mult = int(saved_manual[i]) if is_manual_mode and i < len(saved_manual) else 0
                multipliers.append(max(0, min(100, mult)))

        try:
            min_order_text = self.inp_min_order.text().replace(",", ".")
            min_order = float(min_order_text) if min_order_text else 6
        except Exception:
            min_order = 6

        self._set_terminal_cells_count(cells_count)

        mode_is_pos = bool(self.settings.get("pos_mode_enabled", False))
        distribution_key = self._distribution_type_setting_key(mode_is_pos)
        current_dist_index = int(
            self.cb_distribution.currentIndex() if hasattr(self, "cb_distribution") else 2
        )

        self.settings[distribution_key] = current_dist_index
        self.settings["scalp_multipliers"] = list(multipliers)

        if not mode_is_pos:
            self.settings["scalp_distribution_type"] = current_dist_index

        # Preserve the last manual snapshot while a preset (equal/decreasing) is active.
        # Otherwise switching back to manual restores the preset values instead of the
        # last user-defined manual values.
        if is_manual_mode:
            manual_key = self._manual_distribution_setting_key(mode_is_pos)
            self.settings[manual_key] = list(multipliers)
            if not mode_is_pos:
                self.settings["scalp_manual_multipliers"] = list(multipliers)

        self.settings["scalp_min_order"] = min_order
        self.settings["cells_reversed"] = bool(self.settings.get("cells_reversed", False))
        self.settings["cells_reversed_pos"] = bool(
            self.settings.get("cells_reversed_pos", False)
        )
        self.save_settings()

    def is_cursor_over_window(self):
        """Проверяет находится ли курсор мыши над окном приложения"""
        cursor_pos = pyautogui.position()
        win_geom = self.geometry()

        return (
            win_geom.x() <= cursor_pos[0] <= win_geom.x() + win_geom.width()
            and win_geom.y() <= cursor_pos[1] <= win_geom.y() + win_geom.height()
        )

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.globalPosition().toPoint()
            self._clear_ghost_focus()

            # Разрешаем перетаскивание по свободным участкам окна
            widget = self.childAt(self.mapFromGlobal(pos))
            non_draggable_types = (
                QLineEdit,
                QPushButton,
                QComboBox,
                QCheckBox,
                QTableWidget,
                QSpinBox,
                QDoubleSpinBox,
            )

            if not widget or not isinstance(widget, non_draggable_types):
                self.old_pos = pos
            else:
                self.old_pos = None

    def mouseMoveEvent(self, e):
        if self.old_pos:
            delta = e.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.old_pos = None

    def eventFilter(self, obj, event):
        """Перехватывает события мыши на вкладках для перетаскивания"""
        pf_spin = getattr(self, "sb_pf_count", None)
        pf_line = None
        if pf_spin is not None:
            try:
                pf_line = pf_spin.lineEdit()
            except Exception:
                pf_line = None

        def _clear_pf_spin_input():
            try:
                line = pf_spin.lineEdit() if pf_spin is not None else None
            except Exception:
                line = None

            try:
                if line is not None:
                    line.deselect()
                    line.setSelection(0, 0)
                    line.setCursorPosition(len(line.text() or ""))
                    line.clearFocus()
            except Exception:
                pass

            try:
                if pf_spin is not None:
                    pf_spin.clearFocus()
            except Exception:
                pass

            try:
                fw = QApplication.focusWidget()
                if fw is line or fw is pf_spin:
                    if hasattr(self, "tabs") and self.tabs is not None:
                        self.tabs.setFocus(Qt.FocusReason.OtherFocusReason)
                    elif hasattr(self, "tab_calculator") and self.tab_calculator is not None:
                        self.tab_calculator.setFocus(Qt.FocusReason.OtherFocusReason)
                    else:
                        self.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

        if (
            obj is pf_line
            and event.type() == event.Type.KeyPress
            and event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            try:
                if pf_spin is not None:
                    pf_spin.interpretText()
            except Exception:
                pass

            # Do not consume: let Qt finish internal handling, then clear selection.
            QTimer.singleShot(0, _clear_pf_spin_input)
            QTimer.singleShot(20, _clear_pf_spin_input)
            QTimer.singleShot(80, _clear_pf_spin_input)
            return False

        if (
            obj is pf_line
            and event.type() == event.Type.KeyRelease
            and event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            _clear_pf_spin_input()
            QTimer.singleShot(0, _clear_pf_spin_input)
            QTimer.singleShot(30, _clear_pf_spin_input)
            QTimer.singleShot(120, _clear_pf_spin_input)
            return False

        if obj is pf_line and event.type() == event.Type.FocusOut:
            QTimer.singleShot(0, _clear_pf_spin_input)
            return False

        if isinstance(obj, QLineEdit):
            no_text_selection = bool(obj.property("no_text_selection"))

            if no_text_selection:
                if event.type() == event.Type.Wheel:
                    parent_widget = obj.parentWidget()
                    if isinstance(parent_widget, (QSpinBox, QDoubleSpinBox)):
                        return True

                if event.type() == event.Type.MouseButtonPress:
                    obj.setFocus()
                    QTimer.singleShot(0, obj.deselect)
                    return False

                if event.type() == event.Type.MouseButtonDblClick:
                    obj.setFocus()
                    QTimer.singleShot(0, obj.deselect)
                    return True

                if event.type() == event.Type.KeyPress:
                    if event.key() == Qt.Key.Key_A and (
                        event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    ):
                        obj.deselect()
                        return True

                    if event.key() in (
                        Qt.Key.Key_Escape,
                        Qt.Key.Key_Return,
                        Qt.Key.Key_Enter,
                    ):
                        parent_widget = obj.parentWidget()
                        if isinstance(parent_widget, (QSpinBox, QDoubleSpinBox)):
                            try:
                                parent_widget.interpretText()
                            except Exception:
                                pass
                        obj.deselect()
                        obj.clearFocus()
                        return True

                    QTimer.singleShot(0, obj.deselect)
                    return False

                if event.type() == event.Type.KeyRelease:
                    QTimer.singleShot(0, obj.deselect)
                    return False

            if event.type() == event.Type.Wheel:
                parent_widget = obj.parentWidget()
                if isinstance(parent_widget, (QSpinBox, QDoubleSpinBox)):
                    return True
            if event.type() == event.Type.MouseButtonPress:
                now_ms = int(time.time() * 1000)
                last_ms = obj.property("last_click_ms") or 0
                click_count = obj.property("click_count") or 0

                # Count clicks: if within 350ms, increment; otherwise reset to 1
                if now_ms - last_ms <= 350:
                    click_count += 1
                else:
                    click_count = 1

                obj.setProperty("last_click_ms", now_ms)
                obj.setProperty("click_count", click_count)

                if click_count == 1:
                    # First click: focus + cursor at end, NO select
                    obj.setFocus()
                    obj.deselect()
                    QTimer.singleShot(
                        0, lambda o=obj: o.setCursorPosition(len(o.text()))
                    )
                    return True
                elif click_count == 2:
                    # Second click: select all
                    obj.setFocus()
                    QTimer.singleShot(0, obj.selectAll)
                    return True
            elif event.type() == event.Type.MouseButtonDblClick:
                # Double-click: select all
                obj.setFocus()
                QTimer.singleShot(0, obj.selectAll)
                return True
            elif event.type() == event.Type.KeyPress:
                if event.key() in (
                    Qt.Key.Key_Escape,
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Enter,
                ):
                    parent_widget = obj.parentWidget()
                    spin_parent = (
                        parent_widget
                        if isinstance(parent_widget, (QSpinBox, QDoubleSpinBox))
                        else None
                    )
                    if spin_parent is None and hasattr(self, "sb_pf_count"):
                        try:
                            if self.sb_pf_count.lineEdit() is obj:
                                spin_parent = self.sb_pf_count
                        except Exception:
                            spin_parent = None

                    if spin_parent is not None:
                        try:
                            spin_parent.interpretText()
                        except Exception:
                            pass

                    def _clear_spin_selection():
                        try:
                            obj.deselect()
                        except Exception:
                            pass
                        try:
                            obj.clearFocus()
                        except Exception:
                            pass
                        try:
                            if spin_parent is not None:
                                line = spin_parent.lineEdit()
                                if line is not None:
                                    line.deselect()
                                spin_parent.clearFocus()
                        except Exception:
                            pass
                        try:
                            if hasattr(self, "tabs") and self.tabs is not None:
                                self.tabs.setFocus(Qt.FocusReason.OtherFocusReason)
                            elif hasattr(self, "tab_calculator") and self.tab_calculator is not None:
                                self.tab_calculator.setFocus(Qt.FocusReason.OtherFocusReason)
                        except Exception:
                            pass

                    _clear_spin_selection()
                    QTimer.singleShot(0, _clear_spin_selection)
                    QTimer.singleShot(15, _clear_spin_selection)
                    obj.setProperty("click_count", 0)
                    obj.setProperty("last_click_ms", 0)
                    return True
        if event.type() == event.Type.WindowDeactivate:
            self._clear_ghost_focus()
        if isinstance(obj, QComboBox):
            if event.type() == event.Type.KeyPress:
                if event.key() in (
                    Qt.Key.Key_Escape,
                    Qt.Key.Key_Return,
                    Qt.Key.Key_Enter,
                ):
                    obj.hidePopup()
                    obj.clearFocus()
                    return True
        if isinstance(obj, QSpinBox):
            if event.type() == event.Type.Wheel:
                return True

            if (
                obj is pf_spin
                and event.type() == event.Type.KeyRelease
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape)
            ):
                _clear_pf_spin_input()
                QTimer.singleShot(0, _clear_pf_spin_input)
                QTimer.singleShot(30, _clear_pf_spin_input)
                QTimer.singleShot(120, _clear_pf_spin_input)
                return False

            if (
                obj is pf_spin
                and event.type() == event.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape)
            ):
                try:
                    obj.interpretText()
                except Exception:
                    pass

                QTimer.singleShot(0, _clear_pf_spin_input)
                QTimer.singleShot(20, _clear_pf_spin_input)
                QTimer.singleShot(80, _clear_pf_spin_input)
                return False

            if event.type() == event.Type.KeyPress and event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Escape,
            ):
                try:
                    obj.interpretText()
                except Exception:
                    pass

                def _clear_spin_selection_spinbox():
                    try:
                        line = obj.lineEdit()
                        if line is not None:
                            line.deselect()
                            line.clearFocus()
                    except Exception:
                        pass
                    try:
                        obj.clearFocus()
                    except Exception:
                        pass
                    try:
                        if hasattr(self, "tabs") and self.tabs is not None:
                            self.tabs.setFocus(Qt.FocusReason.OtherFocusReason)
                        elif hasattr(self, "tab_calculator") and self.tab_calculator is not None:
                            self.tab_calculator.setFocus(Qt.FocusReason.OtherFocusReason)
                    except Exception:
                        pass

                _clear_spin_selection_spinbox()
                QTimer.singleShot(0, _clear_spin_selection_spinbox)
                QTimer.singleShot(15, _clear_spin_selection_spinbox)
                return True
        if (
            hasattr(self, "tab_calculator")
            and obj is self.tab_calculator
            and event.type() == event.Type.MouseButtonPress
        ):
            self._clear_ghost_focus()
            if event.button() == Qt.MouseButton.LeftButton:
                local_pos = event.position().toPoint()
                widget = obj.childAt(local_pos)
                non_draggable_types = (
                    QLineEdit,
                    QPushButton,
                    QComboBox,
                    QCheckBox,
                    QTableWidget,
                    QSpinBox,
                    QDoubleSpinBox,
                )
                if not widget or not isinstance(widget, non_draggable_types):
                    self.old_pos = event.globalPosition().toPoint()
                    return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        """Сохраняет позицию окна при закрытии"""
        self._clear_pf_preview_frames()
        self._ensure_window_on_screen(margin=6)
        self.settings["window_pos"] = [self.x(), self.y()]
        self.settings["window_size"] = [int(self.width()), int(self.height())]
        self.settings["window_size_scale"] = int(
            self.settings.get("scale", self.base_scale) or self.base_scale
        )
        self.settings["window_size_v2"] = True
        self.settings["pos_table_volume_override"] = float(
            getattr(self, "table_volume_override", 0.0) or 0.0
        )
        try:
            self.save_cell_settings()
        except Exception:
            self.save_settings()
        event.accept()

    def _on_app_about_to_quit(self):
        """Сохраняет настройки при завершении приложения"""
        try:
            try:
                self._clear_registered_hotkeys()
            except Exception:
                pass
            self._clear_pf_preview_frames()
            self._ensure_window_on_screen(margin=6)
            self.settings["window_pos"] = [self.x(), self.y()]
            self.settings["window_size"] = [int(self.width()), int(self.height())]
            self.settings["window_size_scale"] = int(
                self.settings.get("scale", self.base_scale) or self.base_scale
            )
            self.settings["window_size_v2"] = True
            self.settings["pos_table_volume_override"] = float(
                getattr(self, "table_volume_override", 0.0) or 0.0
            )
            try:
                self.save_cell_settings()
            except Exception:
                self.save_settings()
        except Exception:
            self.save_settings()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._startup_reveal_done:
            QTimer.singleShot(0, self._reveal_startup_window)

    def _reveal_startup_window(self):
        """Reveal the window by restoring opacity from 0 to 1"""
        logging.debug("_reveal_startup_window: Revealing window")
        try:
            self.setWindowOpacity(1.0)
            self._startup_reveal_done = True
            logging.debug("_reveal_startup_window: Window opacity set to 1.0")
        except Exception as e:
            logging.debug(f"_reveal_startup_window: Error - {e}")
            self._startup_reveal_done = True

    def _start_startup_window_suppression(self):
        if sys.platform != "win32":
            return
        self._startup_window_suppress_deadline = time.time() + 2.0
        if self._startup_window_suppress_timer is None:
            self._startup_window_suppress_timer = QTimer(self)
            self._startup_window_suppress_timer.timeout.connect(
                self._suppress_unexpected_startup_windows
            )
        self._startup_window_suppress_timer.start(25)

    def _suppress_unexpected_startup_windows(self):
        if sys.platform != "win32":
            if self._startup_window_suppress_timer is not None:
                self._startup_window_suppress_timer.stop()
            return

        if time.time() >= float(self._startup_window_suppress_deadline):
            if self._startup_window_suppress_timer is not None:
                self._startup_window_suppress_timer.stop()
            return

        try:
            user32 = ctypes.windll.user32
            current_pid = os.getpid()
            main_hwnd = int(self.winId()) if self.winId() else 0

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            pid_buf = ctypes.c_ulong(0)

            def _enum_proc(hwnd, lparam):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    if int(hwnd) == int(main_hwnd):
                        return True

                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
                    if int(pid_buf.value) != int(current_pid):
                        return True

                    # Hide only framed top-level windows that are not the main app window.
                    GWL_STYLE = -16
                    WS_CAPTION = 0x00C00000
                    style = int(user32.GetWindowLongW(hwnd, GWL_STYLE))
                    if style & WS_CAPTION:
                        user32.ShowWindow(hwnd, 0)  # SW_HIDE
                except Exception:
                    pass
                return True

            user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)
        except Exception:
            pass


if __name__ == "__main__":
    logging.debug("=== Application startup ===")
    _hide_console_window_on_windows()
    logging.debug("console hidden")
    existing_qt_rules = os.environ.get("QT_LOGGING_RULES", "")
    dpi_noise_rule = "qt.qpa.window.warning=false"
    if dpi_noise_rule not in existing_qt_rules:
        os.environ["QT_LOGGING_RULES"] = (
            f"{existing_qt_rules};{dpi_noise_rule}"
            if existing_qt_rules
            else dpi_noise_rule
        )

    # Защита от множественного запуска
    logging.debug("Creating shared memory")
    shared_memory = QSharedMemory("RiskVolume_single_instance_v1")
    if not shared_memory.create(1):
        logging.debug("Shared memory already exists - another instance running")
        # Пытаемся очистить "зависший" сегмент и выходим, если уже запущено
        if shared_memory.attach():
            shared_memory.detach()
        if not shared_memory.create(1):
            logging.debug("Exiting - another instance already running")
            sys.exit(0)
    _app_shared_memory_guard = shared_memory
    logging.debug("Shared memory created successfully")

    logging.debug("Creating QApplication")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    logging.debug("QApplication created, setting theme")
    _force_consistent_qt_theme(app)
    logging.debug("Theme set, creating RiskVolumeApp window")
    win = RiskVolumeApp()
    logging.debug("RiskVolumeApp window created")

    def _show_main_window():
        logging.debug("Showing main window")
        win.show()
        logging.debug("Main window shown")

    QTimer.singleShot(0, _show_main_window)
    logging.debug("Starting event loop")
    sys.exit(app.exec())
