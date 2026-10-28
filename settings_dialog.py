from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QSlider,
    QGridLayout,
    QComboBox,
    QWidget,
    QSpinBox,
    QAbstractSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QCheckBox,
    QFrame,
    QMessageBox,
    QScrollArea,
    QAbstractItemView,
    QListView,
)
from translations import TRANS  # Импортируем наш новый файл
from PyQt6.QtCore import (
    Qt,
    QPoint,
    QRegularExpression,
    QRect,
    QItemSelectionModel,
    QVariantAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import (
    QRegularExpressionValidator,
    QPainter,
    QPen,
    QColor,
    QFont,
    QIntValidator,
    QPixmap,
    QIcon,
)

import os

TERMINAL_LOGO_PATH = os.path.join(os.path.dirname(__file__), "Logo", "Logo.png")


class CustomCheckBox(QCheckBox):
    """Чекбокс с кастомной отрисовкой галочки"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFixedSize(20, 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Рисуем прямоугольник индикатора
        rect = QRect(1, 1, 18, 18)

        if self.isChecked():
            # Зеленый фон когда включено
            painter.fillRect(rect, QColor(0x38, 0xBE, 0x1D))
            painter.setPen(QPen(QColor(0x38, 0xBE, 0x1D), 1))
            painter.drawRoundedRect(rect, 3, 3)

            # Рисуем черную галочку
            painter.setPen(QPen(QColor(0, 0, 0), 2))
            # Координаты галочки
            painter.drawLine(5, 10, 8, 13)
            painter.drawLine(8, 13, 14, 6)
        else:
            # Серый фон когда выключено
            painter.fillRect(rect, QColor(0x2A, 0x2A, 0x2A))
            painter.setPen(QPen(QColor(0x44, 0x44, 0x44), 1))
            painter.drawRoundedRect(rect, 3, 3)


class HotkeyEdit(QLineEdit):
    def __init__(self, *args, placeholder_text=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self.setPlaceholderText(placeholder_text or "Нажми клавишу...")
        self.setStyleSheet(
            """
            QLineEdit { 
                background: #252525; 
                color: #38BE1D; 
                border: 1px solid #333; 
                padding: 4px; 
                border-radius: 4px; 
                font-weight: bold; 
            }
            QLineEdit:hover { border: 1px solid #38BE1D; background: #2a2a2a; }
            QLineEdit:focus { border: 1px solid #FF9F0A; background: #333; }
        """
        )

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.setText("esc")
            return

        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        mods = []
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            mods.append("ctrl")
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            mods.append("alt")
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            mods.append("shift")

        special_keys = {
            Qt.Key.Key_Return: "enter",
            Qt.Key.Key_Enter: "enter",
            Qt.Key.Key_Space: "space",
            Qt.Key.Key_Tab: "tab",
            Qt.Key.Key_Backspace: "backspace",
            Qt.Key.Key_Delete: "delete",
            Qt.Key.Key_Insert: "insert",
            Qt.Key.Key_Home: "home",
            Qt.Key.Key_End: "end",
            Qt.Key.Key_PageUp: "page up",
            Qt.Key.Key_PageDown: "page down",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
            Qt.Key.Key_F1: "f1",
            Qt.Key.Key_F2: "f2",
            Qt.Key.Key_F3: "f3",
            Qt.Key.Key_F4: "f4",
            Qt.Key.Key_F5: "f5",
            Qt.Key.Key_F6: "f6",
            Qt.Key.Key_F7: "f7",
            Qt.Key.Key_F8: "f8",
            Qt.Key.Key_F9: "f9",
            Qt.Key.Key_F10: "f10",
            Qt.Key.Key_F11: "f11",
            Qt.Key.Key_F12: "f12",
            Qt.Key.Key_Backslash: "backslash",
        }

        key_name = special_keys.get(key)
        if not key_name:
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                key_name = chr(ord("a") + (int(key) - int(Qt.Key.Key_A)))
            elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                key_name = str(int(key) - int(Qt.Key.Key_0))
            else:
                key_name = (event.text() or "").strip().lower()

        if key_name:
            self.setText("+".join(mods + [key_name]) if mods else key_name)


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class HoverHighlightListView(QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            sel = self.selectionModel()
            if sel is not None:
                sel.setCurrentIndex(
                    index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect,
                )
        super().mouseMoveEvent(event)


class AnimatedHoverButton(QPushButton):
    def __init__(self, text="", theme=None, parent=None):
        super().__init__(text, parent)
        self._theme = {
            "base_bg": "#2E2E2E",
            "hover_bg": "#3A3A3A",
            "pressed_bg": "#454545",
            "disabled_bg": "#1A1A1A",
            "base_border": "#545454",
            "hover_border": "#7A7A7A",
            "pressed_border": "#9A9A9A",
            "disabled_border": "#2A2A2A",
            "base_text": "#E8E8E8",
            "hover_text": "#FFFFFF",
            "pressed_text": "#FFFFFF",
            "disabled_text": "#666666",
            "radius": 6,
            "padding_v": 8,
            "padding_h": 12,
            "font_size": 9,
        }
        if isinstance(theme, dict):
            self._theme.update(theme)

        self._hover_progress = 0.0
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(170)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_anim_value)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_dynamic_style()

    def _blend(self, a, b, progress):
        ca = QColor(str(a))
        cb = QColor(str(b))
        r = int(ca.red() + (cb.red() - ca.red()) * progress)
        g = int(ca.green() + (cb.green() - ca.green()) * progress)
        bch = int(ca.blue() + (cb.blue() - ca.blue()) * progress)
        return QColor(r, g, bch).name()

    def _apply_dynamic_style(self):
        p = max(0.0, min(1.0, float(self._hover_progress)))

        if not self.isEnabled():
            bg = str(self._theme["disabled_bg"])
            border = str(self._theme["disabled_border"])
            text = str(self._theme["disabled_text"])
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            bg = self._blend(self._theme["base_bg"], self._theme["hover_bg"], p)
            border = self._blend(
                self._theme["base_border"], self._theme["hover_border"], p
            )
            text = self._blend(self._theme["base_text"], self._theme["hover_text"], p)
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(
            (
                f"QPushButton {{ background: {bg}; color: {text}; border: 1px solid {border}; "
                f"border-radius: {int(self._theme['radius'])}px; "
                f"padding: {int(self._theme['padding_v'])}px {int(self._theme['padding_h'])}px; "
                f"font-size: {int(self._theme['font_size'])}pt; "
                "font-weight: bold; }"
                f"QPushButton:pressed {{ background: {self._theme['pressed_bg']}; "
                f"border: 1px solid {self._theme['pressed_border']}; "
                f"color: {self._theme['pressed_text']}; }}"
                f"QPushButton:disabled {{ background: {self._theme['disabled_bg']}; "
                f"border: 1px solid {self._theme['disabled_border']}; "
                f"color: {self._theme['disabled_text']}; }}"
            )
        )

    def _animate_hover_to(self, target):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(float(target))
        self._hover_anim.start()

    def _on_hover_anim_value(self, value):
        self._hover_progress = float(value)
        self._apply_dynamic_style()

    def enterEvent(self, event):
        if self.isEnabled():
            self._animate_hover_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isEnabled():
            self._animate_hover_to(0.0)
        super().leaveEvent(event)

    def changeEvent(self, event):
        if event.type() == event.Type.EnabledChange:
            self._hover_anim.stop()
            self._hover_progress = 0.0
            self._apply_dynamic_style()
        super().changeEvent(event)


class SettingsDialog(QDialog):
    def _enable_combo_popup_hover_highlight(self, combo):
        view = HoverHighlightListView(combo)
        combo.setView(view)

    def show_about_dialog(self):
        from about_dialog import AboutDialog

        dlg = AboutDialog(self)
        dlg.exec()

    def show_donate_dialog(self):
        try:
            from donate_dialog import DonateDialog

            dlg = DonateDialog(self)
            dlg.exec()
        except ModuleNotFoundError as e:
            t = TRANS.get(self.parent_window.settings.get("lang", "ru"), TRANS["ru"])
            QMessageBox.warning(
                self,
                t["support_title"],
                t["support_qr_missing"],
            )
        except Exception as e:
            t = TRANS.get(self.parent_window.settings.get("lang", "ru"), TRANS["ru"])
            QMessageBox.warning(
                self,
                t["support_title"],
                t["support_open_failed"].format(error=e),
            )

    def _create_checkmark_icon(self):
        import os
        import tempfile

        path = os.path.join(tempfile.gettempdir(), "rv_checkmark.png")
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

        self._checkmark_path_css = path.replace("\\", "/")
        return path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        lang_code = parent.settings.get("lang", "ru")
        t = TRANS[lang_code]

        self.setStyleSheet(
            """
            QDialog { background: #1E1E1E; border: 2px solid #555; border-radius: 8px; }
            QLabel { color: #ccc; font-size: 10pt; font-weight: bold; }
            QLabel:disabled { color: #555; }
            QLabel#SectionHeader { color: #38BE1D; font-size: 9pt; font-weight: bold; margin-top: 5px; }
            QLabel#SectionHeader:disabled { color: #456345; }
            QLineEdit#FeeInput, QLineEdit#PrecInput { 
                background: #252525; color: #38BE1D; border: 1px solid #333; 
                padding: 4px; border-radius: 4px; font-weight: bold; 
            }
            QLineEdit#FeeInput:hover, QLineEdit#PrecInput:hover { border: 1px solid #38BE1D; }
            QLineEdit#FeeInput:disabled, QLineEdit#PrecInput:disabled {
                background: #1A1A1A; color: #666; border: 1px solid #2A2A2A;
            }
            QPushButton { 
                background: #38BE1D; color: black; border: none; 
                padding: 8px; border-radius: 4px; font-weight: bold; 
            }
            QPushButton:hover { background: #45e024; }
            QSlider::groove:horizontal { height: 6px; background: #333; border-radius: 3px; }
            QSlider::handle:horizontal { background: #38BE1D; width: 14px; margin: -5px 0; border-radius: 7px; }
            QCheckBox { color: #ccc; font-size: 10pt; font-weight: bold; }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: #38BE1D;
                border: 1px solid #38BE1D;
            }
            QFrame#Separator {
                background: #333;
                max-height: 1px;
            }
            QComboBox#ScaleCombo, QComboBox#LangCombo {
                background: #252525;
                color: #EAEAEA;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 4px 22px 4px 8px;
                min-height: 20px;
            }
            QComboBox#ScaleCombo:hover, QComboBox#LangCombo:hover {
                border: 1px solid #38BE1D;
            }
            QComboBox#ScaleCombo:disabled, QComboBox#LangCombo:disabled {
                background: #1A1A1A;
                color: #666;
                border: 1px solid #2A2A2A;
            }
            QComboBox#AutoDepCombo:hover {
                border: 1px solid #38BE1D;
            }
            QComboBox#ScaleCombo:focus, QComboBox#LangCombo:focus {
                border: 1px solid #333;
            }
            QComboBox#AutoDepCombo:focus {
                border: 1px solid #333;
            }
            QComboBox#ScaleCombo::drop-down, QComboBox#LangCombo::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox#AutoDepCombo::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox#ScaleCombo::down-arrow, QComboBox#LangCombo::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #B8B8B8;
                width: 0;
                height: 0;
                margin-right: 6px;
            }
            QComboBox#AutoDepCombo::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #B8B8B8;
                width: 0;
                height: 0;
                margin-right: 6px;
            }
            QComboBox#ScaleCombo QAbstractItemView, QComboBox#LangCombo QAbstractItemView {
                background: #252525;
                color: #EAEAEA;
                border: 1px solid #333;
                selection-background-color: #38BE1D;
                selection-color: black;
            }
            QComboBox#LangCombo QAbstractItemView::item:hover {
                background: #38BE1D;
                color: black;
            }
            QComboBox#LangCombo QAbstractItemView::item:selected {
                background: #38BE1D;
                color: black;
            }
            QComboBox#AutoDepCombo QAbstractItemView {
                background: #252525;
                color: #EAEAEA;
                border: 1px solid #333;
                selection-background-color: #38BE1D;
                selection-color: black;
            }
        """
        )

        self.setMinimumWidth(390)
        self.resize(400, 560)

        layout = QVBoxLayout(self)

        # Добавляем пустое место сверху (шапка окна)
        layout.addSpacing(32)

        # --- КНОПКИ ---
        extra_btns = QHBoxLayout()
        self.btn_about = QPushButton(t["about_btn"])
        self.btn_about.clicked.connect(self.show_about_dialog)
        self.btn_about.setAutoDefault(False)
        self.btn_about.setDefault(False)
        self.btn_donate = QPushButton(t["support_btn"])
        self.btn_donate.clicked.connect(self.show_donate_dialog)
        self.btn_donate.setAutoDefault(False)
        self.btn_donate.setDefault(False)
        # Темный стиль для этих двух кнопок
        dark_style = (
            "QPushButton {"
            "background: #2a2a2a;"
            "color: white;"
            "border-radius: 6px;"
            "border: 1px solid #3a3a3a;"
            "font-weight: bold;"
            "font-size: 11px;"
            "padding: 6px 12px;"
            "}"
            "QPushButton:hover {"
            "background: #3a3a3a;"
            "border: 1px solid #555;"
            "}"
        )
        self.btn_about.setStyleSheet(dark_style)
        self.btn_donate.setStyleSheet(dark_style)
        extra_btns.addWidget(self.btn_about)
        extra_btns.addWidget(self.btn_donate)
        layout.addLayout(extra_btns)

        # Масштаб и язык
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel(t["scale"]))
        self.cb_scale = QComboBox()
        self.cb_scale.setObjectName("ScaleCombo")
        # Direct scales: 60-120
        self.scale_display = [
            str(i) for i in range(60, 130, 10)
        ]  # [60, 70, 80, 90, 100, 110, 120]
        self.scale_actual = [
            i for i in range(60, 130, 10)
        ]  # [60, 70, 80, 90, 100, 110, 120]
        self.cb_scale.addItems(self.scale_display)
        current_scale = int(parent.settings.get("scale", 100))
        # Find display index from actual scale
        if current_scale in self.scale_actual:
            idx = self.scale_actual.index(current_scale)
        else:
            clamped_scale = max(self.scale_actual[0], min(self.scale_actual[-1], current_scale))
            idx = min(
                range(len(self.scale_actual)),
                key=lambda i: abs(self.scale_actual[i] - clamped_scale),
            )
        self.cb_scale.setCurrentIndex(idx)
        self.cb_scale.setFixedWidth(96)
        self.cb_scale.activated.connect(self.cb_scale.clearFocus)
        scale_row.addWidget(self.cb_scale)

        # Компактное меню языка
        scale_row.addSpacing(20)
        self.combo_lang = QComboBox()
        self.combo_lang.setObjectName("LangCombo")
        self.combo_lang.addItems(["Русский", "English"])
        self.combo_lang.setCurrentIndex(0 if lang_code == "ru" else 1)
        self.combo_lang.setFixedWidth(118)
        self.combo_lang.activated.connect(self.combo_lang.clearFocus)
        scale_row.addWidget(self.combo_lang)

        scale_row.addStretch()
        layout.addLayout(scale_row)
        # Определяем текущий язык
        lang_code = parent.settings.get("lang", "ru")
        t = TRANS[lang_code]

        grid = QGridLayout()

        # Поля ввода клавиш
        self.hk_show = HotkeyEdit(
            parent.settings.get("hk_show", "f1"), placeholder_text=t["hk_placeholder"]
        )
        self.hk_coords = HotkeyEdit(
            parent.settings.get("hk_coords", "f2"),
            placeholder_text=t["hk_placeholder"],
        )

        # Комиссия
        fee_total = float(parent.settings.get("fee_percent", 0.1))
        fee_taker = float(parent.settings.get("fee_taker", fee_total / 2))
        fee_maker = float(parent.settings.get("fee_maker", fee_total / 2))
        self.inp_fee_taker = QLineEdit(str(fee_taker))
        self.inp_fee_taker.setObjectName("FeeInput")
        self.inp_fee_maker = QLineEdit(str(fee_maker))
        self.inp_fee_maker.setObjectName("FeeInput")
        self.inp_fee_taker.textChanged.connect(self._preview_fee_change)
        self.inp_fee_maker.textChanged.connect(self._preview_fee_change)

        # Чекбокс для учета комиссии
        self.chk_use_fee = CustomCheckBox()
        use_fee = parent.settings.get("use_fee", True)
        self.chk_use_fee.setChecked(use_fee)
        self.chk_use_fee.stateChanged.connect(self.toggle_fee_fields)
        self.chk_use_fee.stateChanged.connect(self._preview_fee_change)

        # Метки для полей комиссии
        self.lbl_fee_maker = QLabel(t["fee_maker"])
        self.lbl_fee_taker = QLabel(t["fee_taker"])

        # Авто-депозит через API
        self.chk_auto_deposit = CustomCheckBox()
        self.chk_auto_deposit.setChecked(
            bool(parent.settings.get("auto_dep_enabled", False))
        )
        self.chk_auto_deposit.stateChanged.connect(self._toggle_auto_deposit_fields)

        self.cb_auto_dep_exchange = NoWheelComboBox()
        self.cb_auto_dep_exchange.setObjectName("LangCombo")
        self._auto_dep_exchange_values = [
            "binance",
            "bybit",
            "okx",
            "gate",
            "bitget",
            "mexc",
            "kucoin",
        ]
        self.cb_auto_dep_exchange.addItems(
            [
                "Binance",
                "Bybit",
                "OKX",
                "Gate",
                "Bitget",
                "MEXC",
                "KuCoin",
            ]
        )
        self._enable_combo_popup_hover_highlight(self.cb_auto_dep_exchange)
        if hasattr(parent, "get_auto_dep_credentials_plain"):
            self._auto_dep_credentials = parent.get_auto_dep_credentials_plain()
        else:
            self._auto_dep_credentials = self._normalize_auto_dep_credentials(
                parent.settings
            )
        saved_exchange = str(parent.settings.get("auto_dep_exchange", "binance"))
        if saved_exchange not in self._auto_dep_exchange_values:
            saved_exchange = "binance"
        try:
            self.cb_auto_dep_exchange.setCurrentIndex(
                self._auto_dep_exchange_values.index(saved_exchange)
            )
        except Exception:
            self.cb_auto_dep_exchange.setCurrentIndex(0)
        self._active_auto_dep_exchange = self._auto_dep_exchange_values[
            self.cb_auto_dep_exchange.currentIndex()
        ]
        self.cb_auto_dep_exchange.currentIndexChanged.connect(
            self._on_auto_dep_exchange_changed
        )

        self.cb_auto_dep_market = NoWheelComboBox()
        self.cb_auto_dep_market.setObjectName("LangCombo")
        self.cb_auto_dep_market.addItems(
            [t["auto_dep_market_futures"], t["auto_dep_market_spot"]]
        )
        self._enable_combo_popup_hover_highlight(self.cb_auto_dep_market)
        saved_market = str(parent.settings.get("auto_dep_market", "futures")).lower()
        self.cb_auto_dep_market.setCurrentIndex(1 if saved_market == "spot" else 0)

        self.inp_auto_dep_asset = QLineEdit(
            str(parent.settings.get("auto_dep_asset", "USDT"))
        )
        self.inp_auto_dep_asset.setObjectName("FeeInput")

        self.inp_auto_dep_api_key = QLineEdit("")
        self.inp_auto_dep_api_key.setObjectName("FeeInput")

        self.inp_auto_dep_api_secret = QLineEdit("")
        self.inp_auto_dep_api_secret.setObjectName("FeeInput")
        self.inp_auto_dep_api_secret.setEchoMode(QLineEdit.EchoMode.Password)

        self.inp_auto_dep_api_passphrase = QLineEdit("")
        self.inp_auto_dep_api_passphrase.setObjectName("FeeInput")
        self.inp_auto_dep_api_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self._load_auto_dep_credentials_for_exchange(self._active_auto_dep_exchange)

        self._auto_dep_connected = bool(parent.settings.get("auto_dep_connected", False))
        self._auto_dep_connected_exchange = str(
            parent.settings.get("auto_dep_connected_exchange", "") or ""
        ).strip().lower()
        self._auto_dep_connected_market = str(
            parent.settings.get("auto_dep_connected_market", "") or ""
        ).strip().lower()
        self._auto_dep_allow_unverified = bool(
            parent.settings.get("auto_dep_allow_unverified", False)
        )

        # Настройки точности
        self.prec_dep = QLineEdit(str(parent.settings.get("prec_dep", 2)))
        self.prec_risk = QLineEdit(str(parent.settings.get("prec_risk", 2)))
        self.prec_fee = QLineEdit(str(parent.settings.get("prec_fee", 3)))
        self.prec_lev = QLineEdit(str(parent.settings.get("prec_lev", 1)))  # ПЛЕЧО

        for inp in [
            self.prec_dep,
            self.prec_risk,
            self.prec_fee,
            self.prec_lev,
        ]:
            inp.setObjectName("PrecInput")
            inp.setFixedWidth(45)

        # --- НАЧАЛО ЗАМЕНЫ БЛОКА GRID ---
        row = 0

        # === ГОРЯЧИЕ КЛАВИШИ ===
        lbl_hotkeys = QLabel(t["section_hotkeys"])
        lbl_hotkeys.setObjectName("SectionHeader")
        grid.addWidget(lbl_hotkeys, row, 0, 1, 2)
        row += 1

        grid.addWidget(QLabel(t["hide"]), row, 0)
        grid.addWidget(self.hk_show, row, 1)
        row += 1
        grid.addWidget(QLabel(t["coords"]), row, 0)
        grid.addWidget(self.hk_coords, row, 1)
        row += 1

        self.chk_minimize_after_apply = QCheckBox(t["minimize_after_apply"])
        self.chk_minimize_after_apply.setObjectName("MinimizeAfterApply")
        self.chk_minimize_after_apply.setChecked(
            bool(parent.settings.get("minimize_after_apply", True))
        )
        self._create_checkmark_icon()
        self.chk_minimize_after_apply.setStyleSheet(
            "QCheckBox#MinimizeAfterApply { color: #aaa; font-size: 9pt; spacing: 5px; }"
            "QCheckBox#MinimizeAfterApply::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #555; background: #1A1A1A; }"
            f"QCheckBox#MinimizeAfterApply::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({self._checkmark_path_css}); }}"
        )
        grid.addWidget(self.chk_minimize_after_apply, row, 0, 1, 2)
        row += 1

        # Разделитель
        sep1 = QFrame()
        sep1.setObjectName("Separator")
        sep1.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep1, row, 0, 1, 2)
        row += 1
        grid.setRowMinimumHeight(row, 8)  # Отступ
        row += 1

        # === КОМИССИЯ ===
        lbl_fee = QLabel(t["section_fee"])
        lbl_fee.setObjectName("SectionHeader")
        grid.addWidget(lbl_fee, row, 0, 1, 2)
        row += 1

        grid.addWidget(QLabel(t["use_fee"]), row, 0)
        grid.addWidget(self.chk_use_fee, row, 1)
        row += 1
        grid.addWidget(self.lbl_fee_maker, row, 0)
        grid.addWidget(self.inp_fee_maker, row, 1)
        row += 1
        grid.addWidget(self.lbl_fee_taker, row, 0)
        grid.addWidget(self.inp_fee_taker, row, 1)
        row += 1

        # Разделитель
        sep_auto = QFrame()
        sep_auto.setObjectName("Separator")
        sep_auto.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep_auto, row, 0, 1, 2)
        row += 1
        grid.setRowMinimumHeight(row, 8)
        row += 1

        # === АВТО-ДЕПОЗИТ ===
        lbl_auto_dep = QLabel(t["section_auto_deposit"])
        lbl_auto_dep.setObjectName("SectionHeader")
        self.lbl_auto_dep_header = lbl_auto_dep
        grid.addWidget(lbl_auto_dep, row, 0, 1, 2)
        row += 1

        self.lbl_auto_dep_enabled = QLabel(t["auto_dep_enabled"])
        grid.addWidget(self.lbl_auto_dep_enabled, row, 0)
        grid.addWidget(self.chk_auto_deposit, row, 1)
        row += 1

        self.lbl_auto_dep_exchange = QLabel(t["auto_dep_exchange"])
        grid.addWidget(self.lbl_auto_dep_exchange, row, 0)
        grid.addWidget(self.cb_auto_dep_exchange, row, 1)
        row += 1

        self.lbl_auto_dep_market = QLabel(t["auto_dep_market"])
        grid.addWidget(self.lbl_auto_dep_market, row, 0)
        grid.addWidget(self.cb_auto_dep_market, row, 1)
        row += 1
        self._update_auto_dep_market_visibility()

        self.lbl_auto_dep_asset = QLabel(t["auto_dep_asset"])
        grid.addWidget(self.lbl_auto_dep_asset, row, 0)
        grid.addWidget(self.inp_auto_dep_asset, row, 1)
        row += 1

        self.lbl_auto_dep_api_key = QLabel(t["auto_dep_api_key"])
        grid.addWidget(self.lbl_auto_dep_api_key, row, 0)
        grid.addWidget(self.inp_auto_dep_api_key, row, 1)
        row += 1

        self.lbl_auto_dep_api_secret = QLabel(t["auto_dep_api_secret"])
        grid.addWidget(self.lbl_auto_dep_api_secret, row, 0)
        grid.addWidget(self.inp_auto_dep_api_secret, row, 1)
        row += 1

        self.lbl_auto_dep_api_passphrase = QLabel(t["auto_dep_api_passphrase"])
        grid.addWidget(self.lbl_auto_dep_api_passphrase, row, 0)
        grid.addWidget(self.inp_auto_dep_api_passphrase, row, 1)
        row += 1

        

        self.lbl_auto_dep_connect_state = QLabel("")
        self.lbl_auto_dep_connect_state.setStyleSheet(
            "color: #9C9C9C; font-size: 8pt; font-weight: normal;"
        )
        self.btn_auto_dep_connect = AnimatedHoverButton(
            t.get("auto_dep_connect_btn", "Connect").capitalize(),
            theme={
                "base_bg": "#232A23",
                "hover_bg": "#2D382D",
                "pressed_bg": "#3A4A3A",
                "disabled_bg": "#1A1A1A",
                "base_border": "#3D5A3D",
                "hover_border": "#52A552",
                "pressed_border": "#6BCD6B",
                "disabled_border": "#2A2A2A",
                "base_text": "#C7E1C7",
                "hover_text": "#FFFFFF",
                "pressed_text": "#FFFFFF",
                "disabled_text": "#666666",
                "radius": 5,
                "padding_v": 4,
                "padding_h": 8,
                "font_size": 8,
            },
        )
        self.btn_auto_dep_connect.setFixedWidth(102)
        self.btn_auto_dep_connect.setFixedHeight(26)
        self.btn_auto_dep_connect.clicked.connect(self._on_auto_dep_connect_clicked)

        connect_row = QHBoxLayout()
        connect_row.setContentsMargins(0, 0, 0, 0)
        connect_row.setSpacing(8)
        connect_row.addWidget(self.lbl_auto_dep_connect_state)
        connect_row.addStretch()
        connect_row.addWidget(self.btn_auto_dep_connect)
        

        connect_container = QWidget()
        connect_container.setStyleSheet("background: transparent;")
        connect_container.setLayout(connect_row)
        self.auto_dep_connect_container = connect_container
        grid.addWidget(connect_container, row, 0, 1, 2)
        row += 1

        self._auto_dep_panel_widgets = [
            self.lbl_auto_dep_header,
            self.lbl_auto_dep_enabled,
            self.lbl_auto_dep_exchange,
            self.lbl_auto_dep_market,
            self.lbl_auto_dep_asset,
            self.lbl_auto_dep_api_key,
            self.lbl_auto_dep_api_secret,
            self.inp_auto_dep_api_passphrase,
            self.lbl_auto_dep_connect_state,
            self.cb_auto_dep_exchange,
            self.cb_auto_dep_market,
            self.inp_auto_dep_asset,
            self.inp_auto_dep_api_key,
            self.inp_auto_dep_api_secret,
            self.inp_auto_dep_api_passphrase,
            self.btn_auto_dep_connect,
            self.auto_dep_connect_container,
        ]

        # Разделитель
        sep2 = QFrame()
        sep2.setObjectName("Separator")
        sep2.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep2, row, 0, 1, 2)
        row += 1
        grid.setRowMinimumHeight(row, 8)  # Отступ
        row += 1

        # === ТОЧНОСТЬ ОТОБРАЖЕНИЯ ===
        lbl_prec = QLabel(t["section_precision"])
        lbl_prec.setObjectName("SectionHeader")
        grid.addWidget(lbl_prec, row, 0, 1, 2)
        row += 1

        grid.addWidget(QLabel(t["prec_dep"]), row, 0)
        grid.addWidget(self.prec_dep, row, 1)
        row += 1
        grid.addWidget(QLabel(t["prec_risk"]), row, 0)
        grid.addWidget(self.prec_risk, row, 1)
        row += 1
        grid.addWidget(QLabel(t["prec_fee"]), row, 0)
        grid.addWidget(self.prec_fee, row, 1)
        row += 1
        grid.addWidget(QLabel(t["prec_lev"]), row, 0)
        grid.addWidget(self.prec_lev, row, 1)
        row += 1

        # Разделитель
        sep_terminal = QFrame()
        sep_terminal.setObjectName("Separator")
        sep_terminal.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep_terminal, row, 0, 1, 2)
        row += 1
        grid.setRowMinimumHeight(row, 8)
        row += 1

        # === ТЕРМИНАЛ АВТОВЫСТАВЛЕНИЯ ===
        lbl_terminal = QLabel(t.get("section_terminal", "ТЕРМИНАЛ АВТОВЫСТАВЛЕНИЯ"))
        lbl_terminal.setObjectName("SectionHeader")
        grid.addWidget(lbl_terminal, row, 0, 1, 2)
        row += 1

        grid.addWidget(
            QLabel(t.get("auto_apply_terminal", "Терминал автовыставления:")),
            row,
            0,
        )

        self.cb_apply_terminal = NoWheelComboBox()
        self.cb_apply_terminal.setObjectName("LangCombo")
        self._apply_terminal_values = ["profit_forge", "metascalp", "tigertrade", "surf", "vataga"]
        self.cb_apply_terminal.addItem(t.get("terminal_profit_forge", "Profit Forge"))
        self.cb_apply_terminal.addItem(t.get("terminal_metascalp", "MetaScalp"))
        self.cb_apply_terminal.addItem(t.get("terminal_tigertrade", "TigerTrade"))
        self.cb_apply_terminal.addItem(t.get("terminal_surf", "SURF"))
        self.cb_apply_terminal.addItem(t.get("terminal_vataga", "Vataga"))
        self._enable_combo_popup_hover_highlight(self.cb_apply_terminal)

        saved_terminal = str(
            parent.settings.get("auto_apply_terminal", "profit_forge") or "profit_forge"
        ).strip().lower()
        try:
            self.cb_apply_terminal.setCurrentIndex(
                self._apply_terminal_values.index(saved_terminal)
            )
        except Exception:
            self.cb_apply_terminal.setCurrentIndex(0)

        grid.addWidget(self.cb_apply_terminal, row, 1)
        # --- КОНЕЦ ЗАМЕНЫ БЛОКА GRID ---

        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        grid_container.setLayout(grid)

        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        grid_scroll.setWidget(grid_container)
        grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        grid_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: #1A1A1A; width: 8px; border: none; }"
            "QScrollBar::handle:vertical { background: #3A3A3A; min-height: 24px; border-radius: 4px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #1A1A1A; }"
        )
        layout.addWidget(grid_scroll, 1)

        # --- КНОПКИ ---
        btns = QHBoxLayout()
        save_btn = QPushButton(t["save"])
        save_btn.clicked.connect(self.save_and_close)
        close_btn = AnimatedHoverButton(
            t["cancel"],
            theme={
                "base_bg": "#2A2A2A",
                "hover_bg": "#343434",
                "pressed_bg": "#454545",
                "base_border": "#666666",
                "hover_border": "#38BE1D",
                "pressed_border": "#52DA35",
                "base_text": "#E2E2E2",
                "hover_text": "#FFFFFF",
                "pressed_text": "#FFFFFF",
            },
        )
        close_btn.clicked.connect(self.close)
        btns.addWidget(close_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

        # Применяем начальное состояние полей комиссии
        self.toggle_fee_fields()
        self._toggle_auto_deposit_fields()

        self.inp_auto_dep_api_key.textChanged.connect(self._mark_auto_dep_connection_dirty)
        self.inp_auto_dep_api_secret.textChanged.connect(
            self._mark_auto_dep_connection_dirty
        )
        self.inp_auto_dep_api_passphrase.textChanged.connect(
            self._mark_auto_dep_connection_dirty
        )
        self.cb_auto_dep_market.currentIndexChanged.connect(
            self._on_auto_dep_market_changed
        )
        self._refresh_auto_dep_connect_state_label()

        # Верхняя большая кнопка закрытия (правый верхний угол). Не добавляем в layout.
        self.top_close_btn = QPushButton("✕", self)
        self.top_close_btn.setObjectName("TopCloseBtn")
        self.top_close_btn.setFixedSize(40, 30)
        self.top_close_btn.clicked.connect(self.close)
        self.top_close_btn.setStyleSheet(
            "QPushButton#TopCloseBtn { background: transparent; color: white; border: none; font-weight: bold; font-size: 18px; }"
            "QPushButton#TopCloseBtn:hover { color: #ff3333; }"
        )
        self.top_close_btn.raise_()

        self.top_min_btn = QPushButton("_", self)
        self.top_min_btn.setObjectName("TopMinBtn")
        self.top_min_btn.setFixedSize(40, 30)
        self.top_min_btn.clicked.connect(self._minimize_program)
        self.top_min_btn.setStyleSheet(
            "QPushButton#TopMinBtn { background: transparent; color: white; border: none; font-weight: bold; font-size: 16px; }"
            "QPushButton#TopMinBtn:hover { color: #38BE1D; }"
        )
        self.top_min_btn.raise_()

        self._install_enter_accept_handlers()
        self._center_on_parent_window()

    def _center_on_parent_window(self):
        parent = self.parent_window
        if parent is None:
            return

        parent_geom = parent.frameGeometry()
        x = parent_geom.x() + (parent_geom.width() - self.width()) // 2
        y = parent_geom.y() + (parent_geom.height() - self.height()) // 2
        self.move(max(0, x), max(0, y))

    def _install_enter_accept_handlers(self):
        for widget in self.findChildren(QLineEdit):
            if isinstance(widget, HotkeyEdit):
                continue
            widget.installEventFilter(self)
        for widget in self.findChildren(QAbstractSpinBox):
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Escape,
        ):
            if isinstance(obj, (QLineEdit, QAbstractSpinBox)) and not isinstance(
                obj, HotkeyEdit
            ):
                if isinstance(obj, QAbstractSpinBox):
                    obj.interpretText()
                if isinstance(obj, QLineEdit):
                    obj.deselect()
                obj.clearFocus()
                return True
        return super().eventFilter(obj, event)

    def toggle_fee_fields(self):
        """Показать/скрыть поля комиссии в зависимости от чекбокса"""
        is_checked = self.chk_use_fee.isChecked()
        self.lbl_fee_maker.setVisible(is_checked)
        self.inp_fee_maker.setVisible(is_checked)
        self.lbl_fee_taker.setVisible(is_checked)
        self.inp_fee_taker.setVisible(is_checked)

    def _toggle_auto_deposit_fields(self, *_):
        is_checked = self.chk_auto_deposit.isChecked()
        for widget in getattr(self, "_auto_dep_panel_widgets", []):
            widget.setEnabled(is_checked)
        self._refresh_auto_dep_connect_state_label()

    def _dialog_lang_code(self):
        if hasattr(self, "combo_lang"):
            return "ru" if self.combo_lang.currentIndex() == 0 else "en"
        return self.parent_window.settings.get("lang", "ru")

    def _dialog_t(self):
        return TRANS.get(self._dialog_lang_code(), TRANS["ru"])

    def _current_auto_dep_exchange(self):
        return self._auto_dep_exchange_values[self.cb_auto_dep_exchange.currentIndex()]

    def _current_auto_dep_market(self):
        if self._current_auto_dep_exchange() == "bybit":
            return "futures"
        return "spot" if self.cb_auto_dep_market.currentIndex() == 1 else "futures"

    def _is_auto_dep_connected_for_current_selection(self):
        return (
            self._auto_dep_connected
            and self._auto_dep_connected_exchange == self._current_auto_dep_exchange()
            and self._auto_dep_connected_market == self._current_auto_dep_market()
        )

    def _refresh_auto_dep_connect_state_label(self, message=None, is_error=False):
        t = self._dialog_t()
        if not self.chk_auto_deposit.isChecked():
            text = t.get("auto_dep_connect_status_off", "Connection disabled")
            style = "color: #7A7A7A; font-size: 8pt; font-weight: normal;"
        elif self._is_auto_dep_connected_for_current_selection() and self._auto_dep_allow_unverified:
            text = t.get(
                "auto_dep_connect_status_unverified",
                "Connected (permission check skipped)",
            )
            style = "color: #D6A542; font-size: 8pt; font-weight: normal;"
        elif self._is_auto_dep_connected_for_current_selection():
            text = t.get("auto_dep_connect_status_connected", "Connected")
            style = "color: #38BE1D; font-size: 8pt; font-weight: normal;"
        else:
            text = message or t.get(
                "auto_dep_connect_status_pending", "Not connected"
            )
            color = "#FF6B6B" if is_error else "#D6A542"
            style = f"color: {color}; font-size: 8pt; font-weight: normal;"

        self.lbl_auto_dep_connect_state.setText(text)
        self.lbl_auto_dep_connect_state.setStyleSheet(style)

    def _mark_auto_dep_connection_dirty(self, *_):
        self._auto_dep_connected = False
        self._auto_dep_allow_unverified = False
        self._refresh_auto_dep_connect_state_label()

    def _push_auto_dep_state_to_parent(self, force_sync=False):
        if self.parent_window is None:
            return

        self._store_current_auto_dep_credentials()

        selected_exchange = self._current_auto_dep_exchange()
        selected_market = self._current_auto_dep_market()
        connected_flag = bool(
            self.chk_auto_deposit.isChecked()
            and self._is_auto_dep_connected_for_current_selection()
        )

        if hasattr(self.parent_window, "set_auto_dep_credentials_plain"):
            self.parent_window.set_auto_dep_credentials_plain(self._auto_dep_credentials)

        self.parent_window.settings.update(
            {
                "auto_dep_enabled": self.chk_auto_deposit.isChecked(),
                "auto_dep_exchange": selected_exchange,
                "auto_dep_market": selected_market,
                "auto_dep_asset": (self.inp_auto_dep_asset.text() or "USDT").strip().upper(),
                "auto_dep_connected": connected_flag,
                "auto_dep_connected_exchange": selected_exchange if connected_flag else "",
                "auto_dep_connected_market": selected_market if connected_flag else "",
                "auto_dep_allow_unverified": bool(
                    connected_flag and self._auto_dep_allow_unverified
                ),
            }
        )

        if force_sync and hasattr(self.parent_window, "_apply_auto_deposit_sync"):
            self.parent_window._apply_auto_deposit_sync(force_now=True)

    def _try_auto_dep_connect(self, interactive=True, allow_broker_prompt=True):
        t = self._dialog_t()

        if not self.chk_auto_deposit.isChecked():
            self._refresh_auto_dep_connect_state_label()
            return False

        self._store_current_auto_dep_credentials()
        selected_exchange = self._current_auto_dep_exchange()
        selected_market = self._current_auto_dep_market()
        selected_creds = self._auto_dep_credentials.get(selected_exchange, {})

        api_key = str(selected_creds.get("api_key", "") or "").strip()
        api_secret = str(selected_creds.get("api_secret", "") or "").strip()
        api_passphrase = str(selected_creds.get("api_passphrase", "") or "").strip()

        if not api_key or not api_secret:
            self._auto_dep_connected = False
            self._auto_dep_allow_unverified = False
            self._refresh_auto_dep_connect_state_label(
                t.get("auto_dep_connect_status_pending", "Not connected"),
                is_error=False,
            )
            if interactive:
                QMessageBox.warning(
                    self,
                    "API",
                    t.get(
                        "auto_dep_connect_missing_keys",
                        "Enter API Key and API Secret first.",
                    ),
                )
            return False

        ok = True
        reason = ""
        if hasattr(self.parent_window, "validate_auto_dep_credentials_read_only"):
            ok, reason = self.parent_window.validate_auto_dep_credentials_read_only(
                selected_exchange,
                api_key,
                api_secret,
                selected_market,
                api_passphrase,
                use_cache=False,
            )

        if not ok:
            allow_unverified = False
            if selected_exchange in ("binance",) and allow_broker_prompt:
                msg = t.get(
                    "auto_dep_connect_broker_prompt",
                    "Could not verify permissions via Binance API. If you use broker keys, continue with unverified connection?",
                )
                if interactive:
                    reply = QMessageBox.question(
                        self,
                        "API",
                        f"{reason}\n\n{msg}",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    allow_unverified = reply == QMessageBox.StandardButton.Yes

            if not allow_unverified:
                self._auto_dep_connected = False
                self._auto_dep_allow_unverified = False
                self._refresh_auto_dep_connect_state_label(
                    str(reason or ""),
                    is_error=True,
                )
                if interactive:
                    QMessageBox.warning(
                        self,
                        "API",
                        str(
                            reason
                            or t.get("auto_dep_connect_failed", "Connection failed.")
                        ),
                    )
                return False

            self._auto_dep_connected = True
            self._auto_dep_connected_exchange = selected_exchange
            self._auto_dep_connected_market = selected_market
            self._auto_dep_allow_unverified = True
            self._refresh_auto_dep_connect_state_label()
            if interactive:
                QMessageBox.information(
                    self,
                    "API",
                    t.get(
                        "auto_dep_connect_unverified_ok",
                        "Connected in broker mode. Permissions were not verified.",
                    ),
                )
            return True

        self._auto_dep_connected = True
        self._auto_dep_connected_exchange = selected_exchange
        self._auto_dep_connected_market = selected_market
        self._auto_dep_allow_unverified = False
        self._refresh_auto_dep_connect_state_label()
        if interactive:
            QMessageBox.information(
                self,
                "API",
                t.get("auto_dep_connect_ok", "Connected successfully."),
            )
        return True

    def _auto_dep_reconnect_for_selection(self):
        self._mark_auto_dep_connection_dirty()
        if not self.chk_auto_deposit.isChecked():
            self._push_auto_dep_state_to_parent(force_sync=True)
            return

        self._try_auto_dep_connect(interactive=False, allow_broker_prompt=False)
        self._push_auto_dep_state_to_parent(force_sync=True)

    def _on_auto_dep_connect_clicked(self):
        self._try_auto_dep_connect(interactive=True, allow_broker_prompt=True)
        self._push_auto_dep_state_to_parent(force_sync=True)

    def _normalize_auto_dep_credentials(self, settings):
        raw = settings.get("auto_dep_credentials", {})
        if not isinstance(raw, dict):
            raw = {}

        result = {}
        for exchange_id in self._auto_dep_exchange_values:
            source = raw.get(exchange_id, {})
            if not isinstance(source, dict):
                source = {}
            result[exchange_id] = {
                "api_key": str(source.get("api_key", "") or ""),
                "api_secret": str(source.get("api_secret", "") or ""),
                "api_passphrase": str(source.get("api_passphrase", "") or ""),
            }

        # Миграция старых общих ключей в Binance.
        if not any(result["binance"].values()):
            result["binance"] = {
                "api_key": str(settings.get("auto_dep_api_key", "") or ""),
                "api_secret": str(settings.get("auto_dep_api_secret", "") or ""),
                "api_passphrase": str(
                    settings.get("auto_dep_api_passphrase", "") or ""
                ),
            }

        return result

    def _store_current_auto_dep_credentials(self):
        exchange_id = self._active_auto_dep_exchange
        self._auto_dep_credentials[exchange_id] = {
            "api_key": self.inp_auto_dep_api_key.text().strip(),
            "api_secret": self.inp_auto_dep_api_secret.text().strip(),
            "api_passphrase": self.inp_auto_dep_api_passphrase.text().strip(),
        }

    def _load_auto_dep_credentials_for_exchange(self, exchange_id):
        creds = self._auto_dep_credentials.get(exchange_id, {})
        self.inp_auto_dep_api_key.setText(str(creds.get("api_key", "") or ""))
        self.inp_auto_dep_api_secret.setText(str(creds.get("api_secret", "") or ""))
        self.inp_auto_dep_api_passphrase.setText(
            str(creds.get("api_passphrase", "") or "")
        )

    def _on_auto_dep_exchange_changed(self, *_):
        self._store_current_auto_dep_credentials()
        new_exchange = self._auto_dep_exchange_values[
            self.cb_auto_dep_exchange.currentIndex()
        ]
        self._active_auto_dep_exchange = new_exchange
        self._load_auto_dep_credentials_for_exchange(new_exchange)
        self._update_auto_dep_market_visibility()
        self._auto_dep_reconnect_for_selection()

    def _update_auto_dep_market_visibility(self):
        is_bybit = self._current_auto_dep_exchange() == "bybit"
        self.lbl_auto_dep_market.setVisible(not is_bybit)
        self.cb_auto_dep_market.setVisible(not is_bybit)

    def _on_auto_dep_market_changed(self, *_):
        self._auto_dep_reconnect_for_selection()

    

    def _preview_fee_change(self):
        if not self.parent_window:
            return

        try:
            fee_taker = float(self.inp_fee_taker.text().replace(",", ".") or 0)
        except Exception:
            fee_taker = 0.0
        try:
            fee_maker = float(self.inp_fee_maker.text().replace(",", ".") or 0)
        except Exception:
            fee_maker = 0.0

        self.parent_window.settings["use_fee"] = self.chk_use_fee.isChecked()
        self.parent_window.settings["fee_taker"] = fee_taker
        self.parent_window.settings["fee_maker"] = fee_maker
        self.parent_window.settings["fee_percent"] = fee_taker + fee_maker
        self.parent_window.schedule_update_calc()

    def _clamp_prec_vol_input(self, value):
        if not value:
            return

        try:
            num = int(value)
        except ValueError:
            self.prec_vol.setText("0")
            return

        if num > 6:
            self.prec_vol.setText("6")

    def _safe_int(self, text, default, min_val=None, max_val=None):
        try:
            num = int(text)
        except ValueError:
            num = default

        if min_val is not None:
            num = max(min_val, num)
        if max_val is not None:
            num = min(max_val, num)
        return num

    def save_and_close(self):
        self._store_current_auto_dep_credentials()
        new_scale = self.scale_actual[self.cb_scale.currentIndex()]
        prev_scale = None
        scale_changed = False
        if self.parent_window is not None:
            try:
                prev_scale = int(
                    self.parent_window.settings.get(
                        "scale",
                        getattr(self.parent_window, "base_scale", 100),
                    )
                )
                scale_changed = int(new_scale) != int(prev_scale)
            except Exception:
                scale_changed = False

        parent_size = None
        if self.parent_window is not None:
            try:
                parent_size = (int(self.parent_window.width()), int(self.parent_window.height()))
                if (
                    not scale_changed
                    and hasattr(self.parent_window, "_freeze_window_size_temporarily")
                ):
                    self.parent_window._freeze_window_size_temporarily(
                        parent_size[0], parent_size[1], duration_ms=850
                    )
            except Exception:
                parent_size = None

        selected_market_is_spot = self.cb_auto_dep_market.currentIndex() == 1
        preserve_calc_state = (
            self.chk_auto_deposit.isChecked() and selected_market_is_spot
        )

        preserved_dist_index = None
        preserved_manual_texts = None
        if preserve_calc_state and self.parent_window:
            if hasattr(self.parent_window, "cb_distribution"):
                try:
                    preserved_dist_index = int(
                        self.parent_window.cb_distribution.currentIndex()
                    )
                except Exception:
                    preserved_dist_index = None
            if hasattr(self.parent_window, "cells_table"):
                preserved_manual_texts = []
                for i in range(5):
                    item = self.parent_window.cells_table.item(i, 2)
                    preserved_manual_texts.append((item.text() if item else "") or "")

        try:
            fee_taker = float(self.inp_fee_taker.text().replace(",", "."))
        except:
            fee_taker = 0.05
        try:
            fee_maker = float(self.inp_fee_maker.text().replace(",", "."))
        except:
            fee_maker = 0.05
        fee_val = fee_taker + fee_maker

        prec_dep = self._safe_int(self.prec_dep.text() or "", 2, 0, 6)
        prec_risk = self._safe_int(self.prec_risk.text() or "", 2, 0, 6)
        prec_fee = self._safe_int(self.prec_fee.text() or "", 3, 0, 6)
        prec_lev = self._safe_int(self.prec_lev.text() or "", 1, 0, 6)

        self.prec_dep.setText(str(prec_dep))
        self.prec_risk.setText(str(prec_risk))
        self.prec_fee.setText(str(prec_fee))
        self.prec_lev.setText(str(prec_lev))
        selected_exchange = self._auto_dep_exchange_values[
            self.cb_auto_dep_exchange.currentIndex()
        ]
        selected_creds = self._auto_dep_credentials.get(selected_exchange, {})
        selected_market = "spot" if self.cb_auto_dep_market.currentIndex() == 1 else "futures"
        is_connected = (
            self._auto_dep_connected
            and self._auto_dep_connected_exchange == selected_exchange
            and self._auto_dep_connected_market == selected_market
        )

        connected_flag = bool(self.chk_auto_deposit.isChecked() and is_connected)
        allow_unverified_flag = bool(connected_flag and self._auto_dep_allow_unverified)

        if hasattr(self.parent_window, "set_auto_dep_credentials_plain"):
            self.parent_window.set_auto_dep_credentials_plain(self._auto_dep_credentials)

        self.parent_window.settings.update(
            {
                "scale": new_scale,
                "hk_show": self.hk_show.text(),
                "hk_coords": self.hk_coords.text(),
                "minimize_after_apply": self.chk_minimize_after_apply.isChecked(),
                "use_fee": self.chk_use_fee.isChecked(),
                "fee_taker": fee_taker,
                "fee_maker": fee_maker,
                "fee_percent": fee_val,
                "auto_dep_enabled": self.chk_auto_deposit.isChecked(),
                "auto_dep_exchange": selected_exchange,
                "auto_dep_market": (
                    "spot" if self.cb_auto_dep_market.currentIndex() == 1 else "futures"
                ),
                "auto_dep_asset": (self.inp_auto_dep_asset.text() or "USDT").strip().upper(),
                "auto_dep_connected": connected_flag,
                "auto_dep_connected_exchange": selected_exchange if connected_flag else "",
                "auto_dep_connected_market": selected_market if connected_flag else "",
                "auto_dep_allow_unverified": allow_unverified_flag,
                "auto_dep_api_key": "",
                "auto_dep_api_secret": "",
                "auto_dep_api_passphrase": "",
                "auto_apply_terminal": self._apply_terminal_values[
                    self.cb_apply_terminal.currentIndex()
                ],
                "prec_dep": prec_dep,
                "prec_risk": prec_risk,
                "prec_fee": prec_fee,
                "prec_lev": prec_lev,
                "prec_min_order": 0,
                "lang": "ru" if self.combo_lang.currentIndex() == 0 else "en",
            }
        )
        self.parent_window.save_settings()
        self.parent_window.refresh_labels()
        self.parent_window.apply_styles()
        if hasattr(self.parent_window, "_apply_terminal_mode"):
            self.parent_window._apply_terminal_mode()
        self.parent_window.rebind_hotkeys()
        if hasattr(self.parent_window, "_apply_auto_deposit_sync"):
            self.parent_window._apply_auto_deposit_sync(force_now=True)
        if hasattr(self.parent_window, "refresh_quick_deposit_controls"):
            self.parent_window.refresh_quick_deposit_controls()
        self.parent_window.update_calc()

        if preserve_calc_state and self.parent_window:
            if (
                preserved_dist_index is not None
                and hasattr(self.parent_window, "cb_distribution")
            ):
                safe_index = max(0, min(2, int(preserved_dist_index)))
                self.parent_window.cb_distribution.blockSignals(True)
                self.parent_window.cb_distribution.setCurrentIndex(safe_index)
                self.parent_window.cb_distribution.blockSignals(False)
                self.parent_window.settings["scalp_distribution_type"] = safe_index

            if (
                preserved_manual_texts is not None
                and preserved_dist_index == 2
                and hasattr(self.parent_window, "cells_table")
                and hasattr(self.parent_window, "on_table_item_changed")
            ):
                try:
                    self.parent_window.cells_table.itemChanged.disconnect(
                        self.parent_window.on_table_item_changed
                    )
                except Exception:
                    pass

                for i, text in enumerate(preserved_manual_texts):
                    item = self.parent_window.cells_table.item(i, 2)
                    if item:
                        item.setText(text)

                self.parent_window.cells_table.itemChanged.connect(
                    self.parent_window.on_table_item_changed
                )

                self.parent_window._capture_current_manual_distribution()
                self.parent_window.update_cell_volumes()
                self.parent_window.save_cell_settings()

        if self.parent_window is not None and parent_size is not None:
            try:
                if (
                    not scale_changed
                    and hasattr(self.parent_window, "_freeze_window_size_temporarily")
                ):
                    self.parent_window._freeze_window_size_temporarily(
                        parent_size[0], parent_size[1], duration_ms=850
                    )
            except Exception:
                pass

        if self.parent_window is not None and scale_changed:
            try:
                if hasattr(self.parent_window, "_lock_dynamic_resize"):
                    self.parent_window._lock_dynamic_resize = False
                if hasattr(self.parent_window, "_adapt_window_width_to_content"):
                    self.parent_window._adapt_window_width_to_content(
                        grow_only=False,
                        smooth=False,
                    )
                if hasattr(self.parent_window, "_set_window_size_with_extra_height"):
                    self.parent_window._set_window_size_with_extra_height(
                        grow_only=False,
                        smooth=False,
                    )
                if hasattr(self.parent_window, "_ensure_window_on_screen"):
                    self.parent_window._ensure_window_on_screen(margin=6, prefer_active=True)
            except Exception:
                pass

        if self.parent_window is not None:
            try:
                self.parent_window.activateWindow()
                self.parent_window.raise_()
                self.parent_window.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

        self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "old_pos"):
            delta = QPoint(event.globalPosition().toPoint() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Позиционируем кнопку в правом верхнем углу (в шапке окна)
        try:
            if hasattr(self, "top_close_btn"):
                x = self.width() - self.top_close_btn.width() - 8
                y = 6
                self.top_close_btn.move(x, y)
            if hasattr(self, "top_min_btn"):
                x = self.width() - self.top_close_btn.width() - self.top_min_btn.width() - 10
                y = 6
                self.top_min_btn.move(x, y)
        except Exception:
            pass

    def _minimize_program(self):
        if self.parent_window is not None:
            self.parent_window.showMinimized()
        self.showMinimized()
