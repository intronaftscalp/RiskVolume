# cascade_tab.py
import logging
import time
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QGridLayout,
    QFrame,
    QAbstractSpinBox,
    QSizePolicy,
    QCheckBox,
    QStyledItemDelegate,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRegularExpression
from PyQt6.QtGui import (
    QRegularExpressionValidator,
    QCursor,
    QPixmap,
    QPainter,
    QColor,
    QPen,
    QIcon,
)
from translations import TRANS


class CascadeTableItemDelegate(QStyledItemDelegate):
    """Делегат для редактирования ячеек таблицы каскадов с центрированным текстом"""
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setFrame(False)
            editor.setFont(option.font)
            editor.setContentsMargins(0, 0, 0, 0)
            editor.setStyleSheet("padding: 0px; margin: 0px;")
            # Add validator for digits only
            editor.setValidator(
                QRegularExpressionValidator(QRegularExpression(r"[0-9]*[.,]?[0-9]*"), editor)
            )
            # Immediately place cursor at end without selecting
            editor.deselect()
            editor.setCursorPosition(len(editor.text()))
        return editor

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class CascadeWorker(QThread):
    """Поток для выполнения кликов"""

    finished = pyqtSignal()
    cancelled = pyqtSignal()  # Сигнал об остановке по ESC
    failed = pyqtSignal(str)

    def __init__(self, settings, orders_data, main_window, prev_count=None):
        super().__init__()
        self.settings = settings
        self.orders = orders_data
        self.main_window = main_window
        self.prev_count = prev_count
        self._cancelled = False
        self._failed = False

    def run(self):
        try:
            self._run_automation()
        except Exception as exc:
            self._failed = True
            logging.exception("Cascade automation failed")
            self.failed.emit(str(exc))
        finally:
            if not self._cancelled and not self._failed:
                self.finished.emit()

    def _run_automation(self):
        import pyautogui
        import keyboard
        import pyperclip

        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0
        pyautogui.MINIMUM_DURATION = 0.0
        pyautogui.MINIMUM_SLEEP = 0.0

        vol_prec = int(self.settings.get("prec_dep", 2))
        if vol_prec < 0:
            vol_prec = 0
        if vol_prec > 6:
            vol_prec = 6

        # Достаем координаты
        c_gear = self.settings.get("cas_p_gear")  # Шестеренка
        c_book = self.settings.get("cas_p_book")  # Пункт меню Книга заявок
        c_scrollbar = self.settings.get("cas_p_scrollbar")  # Ползунок скроллбара
        c_vol1 = self.settings.get("cas_p_vol1")
        c_dist1 = self.settings.get("cas_p_dist1")
        c_vol2 = self.settings.get("cas_p_vol2")
        c_combo = self.settings.get("cas_p_combo_vol") or c_vol1
        c_plus = self.settings.get("cas_p_btn_add") or self.settings.get("cas_p_plus")
        c_del = self.settings.get("cas_p_btn_del") or self.settings.get("cas_p_x")
        c_close = self.settings.get("cas_p_close_x")

        # Отладка - выводим координаты
        logging.debug(
            "[CASCADE] Points: gear=%s book=%s scrollbar=%s "
            "vol1=%s dist1=%s vol2=%s combo=%s plus=%s delete=%s close=%s; orders=%s",
            c_gear,
            c_book,
            c_scrollbar,
            c_vol1,
            c_dist1,
            c_vol2,
            c_combo,
            c_plus,
            c_del,
            c_close,
            len(self.orders),
        )

        # Если не все точки заданы - стоп
        if not (
            c_gear
            and c_book
            and c_vol1
            and c_dist1
            and c_vol2
            and c_plus
            and c_del
        ):
            logging.error("[CASCADE] Не заданы обязательные точки калибровки")
            raise RuntimeError("Не заданы обязательные точки калибровки")

        row_height = c_vol2[1] - c_vol1[1]
        base_y = c_vol1[1]

        # Tuned timings: speed up non-critical actions, keep slider-related timings safe
        delay_click = 0.03
        delay_short = 0.03
        # Keep long delay to allow settings window / UI to render before interacting with sliders
        delay_long = 0.18
        drag_duration = 0.05
        # Restore speed multipliers to original safe values to avoid too-small sleeps
        speed_mul = 0.6
        min_sleep = 0.01
        # Restore safer delete delay to ensure UI processes deletion clicks
        delete_delay = 0.12

        def sleep_fast(sec):
            time.sleep(max(min_sleep, sec * speed_mul))

        # Регистрируем ESC для остановки
        def on_esc():
            self._cancelled = True
            self.cancelled.emit()

        def check_cancel():
            if self._cancelled:
                return True
            try:
                if keyboard.is_pressed("esc"):
                    self._cancelled = True
                    self.cancelled.emit()
                    return True
            except Exception:
                pass
            return False

        esc_hotkey_id = None
        try:
            esc_hotkey_id = keyboard.add_hotkey("esc", on_esc)
        except Exception:
            esc_hotkey_id = None

        try:
            # 1. Открываем настройки (Шестеренка)
            if check_cancel():
                return
            pyautogui.moveTo(c_gear[0], c_gear[1])
            pyautogui.click()
            sleep_fast(delay_long)

            def _win_quick_drag(x1, y1, x2, y2, hold=0.02, press_delay=0.01):
                import ctypes, time

                user32 = ctypes.windll.user32
                user32.SetCursorPos(int(x1), int(y1))
                user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
                time.sleep(press_delay)
                user32.SetCursorPos(int(x2), int(y2))
                time.sleep(hold)
                user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP

            # 2. Выбираем пункт "Книга заявок"
            if check_cancel():
                return
            pyautogui.moveTo(c_book[0], c_book[1])
            pyautogui.click()
            sleep_fast(delay_long)

            # 3. Быстро перетаскиваем правый ползунок вниз
            if check_cancel():
                return
            if c_scrollbar:
                scrollbar_x = c_scrollbar[0]
                scrollbar_y_start = c_scrollbar[1]
                try:
                    _win_quick_drag(
                        scrollbar_x,
                        scrollbar_y_start,
                        scrollbar_x,
                        scrollbar_y_start + 1200,
                        hold=0.04,
                        press_delay=0.01,
                    )
                except Exception:
                    pyautogui.moveTo(scrollbar_x, scrollbar_y_start, duration=0)
                    pyautogui.mouseDown(button="left")
                    pyautogui.moveTo(
                        scrollbar_x, scrollbar_y_start + 1200, duration=0.05
                    )
                    pyautogui.mouseUp(button="left")
                time.sleep(0.06)

                # === Speed-up non-slider actions ===
                # Sliders already moved; now make subsequent actions faster (smaller sleeps/durations)
                try:
                    pyautogui.MINIMUM_SLEEP = 0.0005
                    pyautogui.MINIMUM_DURATION = 0.0005
                    pyautogui.PAUSE = 0.0
                except Exception:
                    pass
                # Reduce multiplier used by sleep_fast to make sleeps shorter
                speed_mul = 0.35
                min_sleep = 0.001

            # 4. Очистка (удаляем старые строки каскада)
            if check_cancel():
                return
            prev_count = (
                self.prev_count if self.prev_count is not None else len(self.orders)
            )
            base_count = max(int(prev_count), len(self.orders), 1)
            base_count = min(20, base_count)
            del_clicks = max(0, base_count - 1)
            if del_clicks > 0:
                base_y = c_vol2[1]
            logging.debug(
                "[CASCADE] Removing previous rows at %s; clicks=%s",
                c_del,
                del_clicks,
            )
            pyautogui.moveTo(c_del[0], c_del[1])
            for i in range(del_clicks):
                if check_cancel():
                    return
                logging.debug("[CASCADE] Delete click %s/%s", i + 1, del_clicks)
                pyautogui.click()
                sleep_fast(delete_delay)

            # 5. Создаем нужное количество строк
            if check_cancel():
                return
            logging.debug(
                "[CASCADE] Filling order rows; row height=%s", row_height
            )
            plus_count = 0
            for i, order in enumerate(self.orders):
                if check_cancel():
                    return
                # После прокрутки новая строка ВСЕГДА оказывается на позиции base_y
                cur_y = base_y
                logging.debug(
                    "[CASCADE] Order %s: volume=%s distance=%s%% y=%s",
                    i + 1,
                    order["vol"],
                    order["dist"],
                    cur_y,
                )

                if i > 0:
                    if check_cancel():
                        return
                    pyautogui.moveTo(c_plus[0], c_plus[1])
                    pyautogui.click()
                    sleep_fast(delay_long)
                    # ВСЕГДА 2 раза вниз для прокрутки
                    logging.debug("[CASCADE] Moving down twice in volume selector")
                    if check_cancel():
                        return
                    for _ds in range(2):
                        pyautogui.press("down")
                        sleep_fast(0.05)
                    sleep_fast(0.15)

                # --- Комбобокс объема: 6 раз вниз + Enter ---
                pyautogui.moveTo(c_combo[0], cur_y)
                pyautogui.click()
                sleep_fast(0.2)
                for _ in range(6):
                    if check_cancel():
                        return
                    pyautogui.press("down")
                    sleep_fast(0.04)
                pyautogui.press("enter")
                sleep_fast(0.12)

                # --- Объём ---
                vol_str = str(order["vol"]).replace(",", ".")
                logging.debug(
                    "[CASCADE] Entering volume %s at (%s, %s)",
                    vol_str,
                    c_vol1[0],
                    cur_y,
                )
                pyperclip.copy(vol_str)
                # Slightly longer pause to ensure clipboard is set before moving/clicking
                sleep_fast(0.12)
                pyautogui.moveTo(c_vol1[0], cur_y)
                pyautogui.click()
                sleep_fast(0.08)
                if check_cancel():
                    return
                pyautogui.click(clicks=2)
                sleep_fast(0.03)
                keyboard.press_and_release("ctrl+a")
                sleep_fast(0.035)
                if check_cancel():
                    return
                keyboard.press_and_release("backspace")
                sleep_fast(0.035)
                keyboard.press_and_release("ctrl+v")
                # ensure paste completed before hitting Enter
                sleep_fast(0.12)
                if check_cancel():
                    return
                keyboard.press_and_release("enter")
                sleep_fast(0.03)

                # --- Дистанция ---
                dist_str = str(order["dist"]).replace(",", ".")
                pyperclip.copy(dist_str)
                sleep_fast(0.03)
                pyautogui.moveTo(c_dist1[0], cur_y)
                pyautogui.click()
                sleep_fast(0.08)
                if check_cancel():
                    return
                pyautogui.click(clicks=2)
                sleep_fast(0.03)
                keyboard.press_and_release("ctrl+a")
                sleep_fast(0.03)
                if check_cancel():
                    return
                keyboard.press_and_release("backspace")
                sleep_fast(0.03)
                keyboard.press_and_release("ctrl+v")
                sleep_fast(0.05)
                if check_cancel():
                    return
                keyboard.press_and_release("enter")

                sleep_fast(delay_short)

            # 6. Закрываем настройки
            if not self._cancelled:
                sleep_fast(0.03)
                if c_close:
                    pyautogui.moveTo(c_close[0], c_close[1])
                    pyautogui.click()
                else:
                    pyautogui.press("esc")
        finally:
            try:
                pyautogui.mouseUp(button="left")
            except Exception:
                pass
            # Убираем хоткей ESC
            try:
                if esc_hotkey_id is not None:
                    keyboard.remove_hotkey(esc_hotkey_id)
            except:
                pass


class CascadeTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.calib_active = False
        self.calib_step = 0
        self.apply_active = False
        self.init_ui()

    def _t(self, key, **kwargs):
        t = TRANS.get(self.main.settings.get("lang", "ru"), TRANS["ru"])
        text = t.get(key, "")
        return text.format(**kwargs) if kwargs else text

    def _create_checkmark_icon(self):
        """Create a small black checkmark PNG and return its path."""
        import os, tempfile

        path = os.path.join(tempfile.gettempdir(), "rv_checkmark.png")
        if not os.path.exists(path):
            pix = QPixmap(12, 12)
            pix.fill(QColor(0, 0, 0, 0))  # transparent
            p = QPainter(pix)
            pen = QPen(QColor(0, 0, 0))
            pen.setWidth(2)
            p.setPen(pen)
            # Draw a checkmark: short leg then long leg
            p.drawLine(2, 6, 5, 9)
            p.drawLine(5, 9, 10, 3)
            p.end()
            pix.save(path, "PNG")
        # Store path with forward slashes for CSS
        self._checkmark_path_css = path.replace("\\", "/")
        return path

    def _wrap_spinbox(self, spinbox):
        wrap = QFrame()
        wrap.setObjectName("SpinWrap")
        wrap_layout = QHBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(0)

        left_btn = QPushButton("-")
        right_btn = QPushButton("+")
        left_btn.setObjectName("SpinStepBtn")
        right_btn.setObjectName("SpinStepBtn")

        # Helper function to step without selecting text
        def step_without_select(func):
            def wrapper():
                # For QSpinBox/QDoubleSpinBox, get lineEdit and deselect it
                if hasattr(spinbox, 'lineEdit'):
                    line_edit = spinbox.lineEdit()
                    if line_edit:
                        line_edit.deselect()
                func()
                if hasattr(spinbox, 'lineEdit'):
                    line_edit = spinbox.lineEdit()
                    if line_edit:
                        line_edit.deselect()
            return wrapper

        left_btn.clicked.connect(step_without_select(spinbox.stepDown))
        right_btn.clicked.connect(step_without_select(spinbox.stepUp))

        wrap_layout.addWidget(left_btn)
        wrap_layout.addWidget(spinbox)
        wrap_layout.addWidget(right_btn)

        # Сохраняем ссылки для масштабирования
        if spinbox is getattr(self, "sb_count", None):
            self.sb_count_left, self.sb_count_right = left_btn, right_btn
        elif spinbox is getattr(self, "sb_min", None):
            self.sb_min_left, self.sb_min_right = left_btn, right_btn
        elif spinbox is getattr(self, "sb_dist", None):
            self.sb_dist_left, self.sb_dist_right = left_btn, right_btn
        elif spinbox is getattr(self, "sb_range_width", None):
            self.sb_range_left, self.sb_range_right = left_btn, right_btn
        elif spinbox is getattr(self, "sb_manual_k", None):
            self.sb_manual_k_left, self.sb_manual_k_right = left_btn, right_btn

        return wrap

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        t = TRANS.get(self.main.settings.get("lang", "ru"), TRANS["ru"])

        # --- Стили для этого окна ---
        self.setStyleSheet(
            """
            QGroupBox { 
                border: 1px solid #333; 
                border-radius: 6px; 
                margin-top: 6px; 
                font-weight: bold; 
                color: #ccc;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QLabel { color: #aaa; font-size: 9pt; }
            /* Стиль кнопок процентов (Исправлено) */
            QPushButton.percBtn {
                background-color: #252525;
                color: #888;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }
            QPushButton.percBtn:checked {
                background-color: #38BE1D; /* Ярко-зеленый */
                color: black;             /* Черный текст - читается отлично */
                border: 1px solid #38BE1D;
            }
            QPushButton.percBtn[dimmed="true"] {
                background-color: #1b1b1b;
                color: #555;
                border: 1px solid #2a2a2a;
            }
            QPushButton.percBtn:hover { border: 1px solid #555; }
            
            QComboBox {
                background: #1A1A1A; color: white; border: 1px solid #333; padding: 2px;
                min-width: 60px; /* Чтобы текст не резался */
            }
            QFrame#SpinWrap {
                background: #1A1A1A;
                border: 1px solid #333;
                border-radius: 4px;
            }
            QFrame#SpinWrap:disabled {
                background: #0F0F0F;
                border: 1px solid #222;
            }
            QSpinBox#spinInner, QDoubleSpinBox#spinInner {
                background: transparent; color: white; border: none; padding: 2px;
                selection-background-color: rgba(90, 205, 80, 150);
                selection-color: white;
            }
            QSpinBox#spinInner:disabled, QDoubleSpinBox#spinInner:disabled {
                color: #555;
            }
            QLineEdit {
                background: #1A1A1A;
                color: white;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 2px;
                selection-background-color: rgba(90, 205, 80, 150);
                selection-color: white;
            }
            QLineEdit:focus {
                border: 1px solid #FFFFFF;
            }
            QLineEdit:disabled {
                background: #0F0F0F;
                color: #555;
                border: 1px solid #222;
            }
            QPushButton#SpinStepBtn {
                background: #2a2a2a;
                color: #cfcfcf;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 0px;
                font-weight: bold;
                font-size: 9pt;
            }
            QPushButton#SpinStepBtn:hover {
                background: #3a3a3a;
            }
            QPushButton#SpinStepBtn:disabled {
                background: #1a1a1a;
                color: #555;
                border: 1px solid #222;
            }
        """
        )

        # --- БЛОК 1: Объем ---
        self.gb_vol = QGroupBox(t["casc_block1"])
        l_vol = QVBoxLayout()

        num_validator = QRegularExpressionValidator(
            QRegularExpression(r"[0-9]*[.,]?[0-9]*")
        )

        h_perc = QHBoxLayout()
        self.group_btns = []
        for text in ["25%", "50%", "75%", "100%"]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setProperty("class", "percBtn")  # Для CSS
            btn.setObjectName("percBtn")  # Для Qt
            btn.clicked.connect(self.on_perc_click)
            self.group_btns.append(btn)
            h_perc.addWidget(btn)

        self.group_btns[3].setChecked(True)  # 100% по умолчанию

        self.btn_use_custom_percent = QPushButton(t["casc_custom_percent"])
        self.btn_use_custom_percent.setCheckable(True)
        self.btn_use_custom_percent.setProperty("class", "percBtn")
        self.btn_use_custom_percent.setObjectName("percBtn")
        self.btn_use_custom_percent.setChecked(
            bool(self.main.settings.get("cas_use_custom_percent", False))
        )
        self.btn_use_custom_percent.toggled.connect(self.on_custom_percent_toggled)
        h_perc.addWidget(self.btn_use_custom_percent)

        custom_percent = float(self.main.settings.get("cas_custom_percent", 100.0))
        self.inp_custom_percent = QLineEdit(
            str(int(custom_percent))
            if custom_percent == int(custom_percent)
            else str(custom_percent).replace(".", ",")
        )
        self.inp_custom_percent.setValidator(num_validator)
        self.inp_custom_percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inp_custom_percent.setEnabled(self.btn_use_custom_percent.isChecked())
        self.inp_custom_percent.textChanged.connect(self.on_custom_percent_text_changed)
        self.inp_custom_percent.returnPressed.connect(self.save_custom_percent_setting)
        self.inp_custom_percent.installEventFilter(self.main)
        h_perc.addWidget(self.inp_custom_percent)

        if self.btn_use_custom_percent.isChecked():
            for btn in self.group_btns:
                btn.setChecked(False)

        h_source = QHBoxLayout()
        self.btn_use_custom_vol = QPushButton(t["casc_custom_volume"])
        self.btn_use_custom_vol.setCheckable(True)
        self.btn_use_custom_vol.setProperty("class", "percBtn")
        self.btn_use_custom_vol.setObjectName("percBtn")
        self.btn_use_custom_vol.setChecked(
            bool(self.main.settings.get("cas_use_custom_vol", False))
        )
        self.btn_use_custom_vol.toggled.connect(self.on_volume_source_changed)

        custom_total = float(self.main.settings.get("cas_custom_total_vol", 0.01))
        self.inp_custom_total = QLineEdit(
            str(int(custom_total))
            if custom_total == int(custom_total)
            else str(custom_total).replace(".", ",")
        )
        self.inp_custom_total.setValidator(num_validator)
        self.inp_custom_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inp_custom_total.textChanged.connect(self.on_custom_vol_text_changed)
        self.inp_custom_total.returnPressed.connect(self.save_custom_vol_setting)
        self.inp_custom_total.installEventFilter(self.main)

        h_source.addWidget(self.btn_use_custom_vol)
        h_source.addWidget(self.inp_custom_total, 1)

        self.set_custom_vol_enabled(self.btn_use_custom_vol.isChecked())

        self.lbl_total_vol = QLabel(t["casc_total"].format(total="0"))
        self.lbl_total_vol.setStyleSheet(
            "color: #FF9F0A; font-weight: bold; font-size: 11pt; margin-top: 5px;"
        )
        self.lbl_total_vol.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_total_vol_hint = QLabel("0")
        self.lbl_total_vol_hint.setStyleSheet("color: #666; font-size: 8pt;")
        self.lbl_total_vol_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_custom_total_hint = QLabel("")
        self.lbl_custom_total_hint.setStyleSheet(
            "color: #666; font-size: 8pt; margin-top: 2px;"
        )
        self.lbl_custom_total_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_custom_total_hint_value(self._parse_custom_total_value(self.inp_custom_total.text()))
        self.lbl_custom_total_hint.setVisible(self.btn_use_custom_vol.isChecked())

        l_vol.addLayout(h_perc)
        l_vol.addLayout(h_source)
        l_vol.addWidget(self.lbl_custom_total_hint)
        l_vol.addWidget(self.lbl_total_vol)
        l_vol.addWidget(self.lbl_total_vol_hint)
        self.gb_vol.setLayout(l_vol)
        layout.addWidget(self.gb_vol)

        # --- БЛОК 2: Настройки (Сетка исправлена) ---
        self.gb_set = QGroupBox(t["casc_block2"])
        self.grid_settings = QGridLayout()
        self.grid_settings.setHorizontalSpacing(12)  # Отступ между колонками
        self.grid_settings.setVerticalSpacing(8)

        # Используем QLabel с wordWrap, чтобы текст переносился если что
        self.lbl_count_title = QLabel(t["casc_count"])
        self.grid_settings.addWidget(self.lbl_count_title, 0, 0)
        self.sb_count = QSpinBox()
        self.sb_count.setRange(2, 20)
        saved_count = int(self.main.settings.get("last_cascade_count", 5) or 5)
        self.sb_count.setValue(max(2, min(20, saved_count)))
        self._last_max_possible = 50  # Отслеживаем предыдущий максимум
        self._last_type_index = -1  # Отслеживаем смену типа
        self._skip_initial_autoset = True
        self.sb_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.sb_count.setObjectName("spinInner")
        self.sb_count_wrap = self._wrap_spinbox(self.sb_count)
        self.grid_settings.addWidget(self.sb_count_wrap, 0, 1)

        self.lbl_min_order_title = QLabel(t["casc_min_order"])
        self.grid_settings.addWidget(self.lbl_min_order_title, 0, 2)
        self.sb_min = QDoubleSpinBox()
        self.sb_min.setRange(1, 1000)
        min_order_prec = int(self.main.settings.get("prec_min_order", 2))
        if min_order_prec < 0:
            min_order_prec = 0
        if min_order_prec > 6:
            min_order_prec = 6
        self.sb_min.setDecimals(min_order_prec)
        self.sb_min.setSingleStep(1 if min_order_prec == 0 else 10 ** (-min_order_prec))
        self.sb_min.setValue(float(self.main.settings.get("scalp_min_order", 6)))
        self.sb_min.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.sb_min.setObjectName("spinInner")
        self.sb_min_wrap = self._wrap_spinbox(self.sb_min)
        self.grid_settings.addWidget(self.sb_min_wrap, 0, 3)

        # Подсказка под Кол-во (новая строка 1)
        self.lbl_count_hint = QLabel(t["casc_max_cells"].format(max="?"))
        self.lbl_count_hint.setStyleSheet("color: #40E0D0; font-size: 8pt;")
        self.lbl_count_hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.grid_settings.addWidget(self.lbl_count_hint, 1, 0, 1, 2)

        self.lbl_type_title = QLabel(t["casc_type"])
        self.grid_settings.addWidget(self.lbl_type_title, 1, 2)
        self.cb_type = QComboBox()
        # Сократим названия, чтобы влазили
        self.cb_type.addItems(
            [
                t["casc_type_uniform"],
                t["casc_type_matr_12"],
                t["casc_type_matr_15"],
                t["casc_type_manual"],
            ]
        )
        saved_type = int(self.main.settings.get("cas_type_index", 0) or 0)
        if saved_type < 0:
            saved_type = 0
        if saved_type == 4:
            saved_type = 3
        elif saved_type >= 3:
            saved_type = 2
        if saved_type > 3:
            saved_type = 3
        self.cb_type.setCurrentIndex(saved_type)
        self.cb_type.setMinimumWidth(70)  # Более компактная ширина
        self.grid_settings.addWidget(self.cb_type, 1, 3)

        self.lbl_manual_k = QLabel(t["casc_manual_k"])
        self.grid_settings.addWidget(self.lbl_manual_k, 2, 2)
        self.sb_manual_k = QDoubleSpinBox()
        self.sb_manual_k.setRange(1.00, 1000.0)
        self.sb_manual_k.setDecimals(2)
        self.sb_manual_k.setSingleStep(0.1)
        self.sb_manual_k.setKeyboardTracking(False)
        self.sb_manual_k.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.sb_manual_k.setValue(
            float(self.main.settings.get("cas_manual_k", 2.0) or 2.0)
        )
        self.sb_manual_k.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.sb_manual_k.setObjectName("spinInner")
        self.sb_manual_k.lineEdit().setReadOnly(False)
        self.sb_manual_k.lineEdit().setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.sb_manual_k_wrap = self._wrap_spinbox(self.sb_manual_k)
        self.grid_settings.addWidget(self.sb_manual_k_wrap, 2, 3)

        self.lbl_step_title = QLabel(t["casc_step"])
        self.grid_settings.addWidget(self.lbl_step_title, 3, 2)
        self.sb_dist = QDoubleSpinBox()
        self.sb_dist.setRange(0.001, 10.0)
        self.sb_dist.setDecimals(2)
        saved_dist = float(self.main.settings.get("cas_dist_step", 0.1) or 0.1)
        saved_dist = max(
            self.sb_dist.minimum(), min(self.sb_dist.maximum(), saved_dist)
        )
        self.sb_dist.setValue(saved_dist)
        self.sb_dist.setSingleStep(0.01)
        self.sb_dist.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.sb_dist.setObjectName("spinInner")
        self.sb_dist_wrap = self._wrap_spinbox(self.sb_dist)
        self.grid_settings.addWidget(self.sb_dist_wrap, 3, 3)

        self.chk_range_mode = QCheckBox(t["casc_range"])
        self.chk_range_mode.setChecked(
            bool(self.main.settings.get("cas_range_mode", False))
        )
        # Generate a black checkmark on green background icon for the checkbox
        self._create_checkmark_icon()
        self.chk_range_mode.setStyleSheet(
            "QCheckBox { color: #aaa; font-size: 9pt; spacing: 5px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #444; background: #2A2A2A; }"
            f"QCheckBox::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({self._checkmark_path_css}); }}"
        )
        self.grid_settings.addWidget(self.chk_range_mode, 3, 0)
        self.sb_range_width = QDoubleSpinBox()
        self.sb_range_width.setRange(0.0, 100.0)
        self.sb_range_width.setDecimals(2)
        self.sb_range_width.setSingleStep(0.1)
        self.sb_range_width.setValue(
            float(self.main.settings.get("cas_range_width", 0.0) or 0.0)
        )
        self.sb_range_width.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.sb_range_width.setObjectName("spinInner")
        self.sb_range_wrap = self._wrap_spinbox(self.sb_range_width)
        self.grid_settings.addWidget(self.sb_range_wrap, 3, 1)

        # Используем тот же eventFilter, что и в калькуляторе (из main.py)
        self.sb_count.lineEdit().installEventFilter(self.main)
        self.sb_min.lineEdit().installEventFilter(self.main)
        self.sb_dist.lineEdit().installEventFilter(self.main)
        self.sb_range_width.lineEdit().installEventFilter(self.main)
        self.inp_custom_total.installEventFilter(self.main)

        # События
        self.sb_count.valueChanged.connect(self.on_count_changed)
        self.sb_min.valueChanged.connect(self.recalc_table)
        self.cb_type.currentIndexChanged.connect(self.on_type_changed)
        self.sb_dist.valueChanged.connect(self.on_dist_changed)
        self.sb_range_width.valueChanged.connect(self.on_range_width_changed)
        self.sb_manual_k.valueChanged.connect(self.recalc_table)
        self.chk_range_mode.toggled.connect(self.on_range_mode_toggled)

        # Применяем начальное состояние enable/disable для шага и диапазона
        self._apply_range_mode_state(self.chk_range_mode.isChecked())

        # Реал-тайм обновление при вводе текста в спинбоксы
        # Подключаемся к встроенному QLineEdit для обновления при каждом символе
        self.sb_min.lineEdit().textChanged.connect(self.on_min_text_changed)
        self.sb_dist.lineEdit().textChanged.connect(self.on_dist_text_changed)
        self.sb_range_width.lineEdit().textChanged.connect(self.on_range_text_changed)
        self.sb_manual_k.lineEdit().textChanged.connect(self.on_manual_k_text_changed)

        # Обновляем подсказку когда меняется процент
        self.group_btns[0].clicked.connect(self.recalc_table)
        self.group_btns[1].clicked.connect(self.recalc_table)
        self.group_btns[2].clicked.connect(self.recalc_table)
        self.group_btns[3].clicked.connect(self.recalc_table)

        self.gb_set.setLayout(self.grid_settings)
        layout.addWidget(self.gb_set)

        # --- БЛОК 3: Таблица (Исправлено обрезание) ---
        self.table = QTableWidget()
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(
            [t["casc_table_vol"], t["casc_table_dist"]]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        # Увеличиваем высоту строк, чтобы шрифт не резался
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setRowCount(0)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.table.setMinimumHeight(120)
        # Базовый стиль таблицы (точные размеры выставятся в apply_scale)
        self.table.setStyleSheet(
            "QTableWidget { background: #141414; color: #D0D0D0; alternate-background-color: #141414; gridline-color: #191919; }"
            "QTableWidget::item { background: #141414; color: #D0D0D0; font-size: 6pt; padding: 0px 2px; }"
            "QTableWidget::item:focus { outline: none; border: none; background: #141414; }"
            "QLineEdit { background: #141414 !important; color: white; border: 1px solid #191919 !important; border-radius: 2px; padding: 0px; font-size: 6pt; selection-background-color: rgba(90, 205, 80, 150); selection-color: white; }"
            "QHeaderView { background: #141414; }"
            "QHeaderView::section:horizontal { background: #1A1A1A; color: #A0A0A0; border: 1px solid #1F1F1F; font-size: 8pt; padding: 2px; }"
            "QHeaderView::section:vertical { background: #141414; color: #707070; border: 1px solid #1F1F1F; font-size: 8pt; padding: 2px; }"
            "QTableCornerButton::section { background: #141414; border: 1px solid #1F1F1F; }"
            "QTableWidget QScrollBar:vertical { background: #111111; width: 14px; margin: 0px; border: 1px solid #232323; }"
            "QTableWidget QScrollBar::handle:vertical { background: #3A3A3A; min-height: 24px; border-radius: 4px; border: 1px solid #4A4A4A; }"
            "QTableWidget QScrollBar::add-page:vertical, QTableWidget QScrollBar::sub-page:vertical { background: #111111; }"
            "QTableWidget QScrollBar::add-line:vertical, QTableWidget QScrollBar::sub-line:vertical { background: #1A1A1A; height: 14px; border: 1px solid #1F1F1F; }"
            "QTableWidget QScrollBar:horizontal { background: #111111; height: 14px; margin: 0px; border: 1px solid #232323; }"
            "QTableWidget QScrollBar::handle:horizontal { background: #3A3A3A; min-width: 24px; border-radius: 4px; border: 1px solid #4A4A4A; }"
            "QTableWidget QScrollBar::add-page:horizontal, QTableWidget QScrollBar::sub-page:horizontal { background: #111111; }"
            "QTableWidget QScrollBar::add-line:horizontal, QTableWidget QScrollBar::sub-line:horizontal { background: #1A1A1A; width: 14px; border: 1px solid #1F1F1F; }"
            "selection-background-color: #38BE1D; selection-color: black;"
        )
        # Set delegate for both columns
        self.table.setItemDelegateForColumn(0, CascadeTableItemDelegate(self.table))
        self.table.setItemDelegateForColumn(1, CascadeTableItemDelegate(self.table))
        
        # Use NoEditTriggers to manage editing manually via click handlers
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        self.table.cellChanged.connect(self._on_table_cell_changed)
        self.table.itemClicked.connect(self._on_cascade_table_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_cascade_table_item_double_clicked)
        layout.addWidget(self.table, 1)

        # --- БЛОК 4: Кнопка выставления ---
        self.btn_apply = QPushButton(t["casc_apply"])
        self.btn_apply.setStyleSheet(
            "background: #38BE1D; color: black; font-weight: bold; padding: 8px; font-size: 10pt;"
        )
        # Save click position on press so we can restore cursor exactly where user clicked
        self.btn_apply.pressed.connect(self._store_apply_click_pos)
        self.btn_apply.clicked.connect(self.run_automation)
        layout.addWidget(self.btn_apply)

        # Статус (с переносом текста)
        self.lbl_status = QLabel(t["casc_status_need"])
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)  # <-- ВАЖНО: Текст будет переноситься
        self.lbl_status.setStyleSheet(
            "color: #666; font-size: 7pt; margin-bottom: 5px;"
        )
        layout.addWidget(self.lbl_status)

        # Применяем масштабирование под текущий размер интерфейса
        self.apply_scale()
        self.on_type_changed(self.cb_type.currentIndex())
        self._refresh_calibration_status()
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)

    def refresh_labels(self):
        t = TRANS.get(self.main.settings.get("lang", "ru"), TRANS["ru"])
        self.gb_vol.setTitle(t["casc_block1"])
        self.gb_set.setTitle(t["casc_block2"])
        self.btn_use_custom_percent.setText(t["casc_custom_percent"])
        self.btn_use_custom_vol.setText(t["casc_custom_volume"])
        self._set_custom_total_hint_value(
            self._parse_custom_total_value(self.inp_custom_total.text())
        )
        self.lbl_count_title.setText(t["casc_count"])
        self.lbl_min_order_title.setText(t["casc_min_order"])
        self.lbl_type_title.setText(t["casc_type"])
        self.lbl_manual_k.setText(t["casc_manual_k"])
        self.lbl_step_title.setText(t["casc_step"])
        self.chk_range_mode.setText(t["casc_range"])
        current_idx = self.cb_type.currentIndex()
        self.cb_type.blockSignals(True)
        self.cb_type.clear()
        self.cb_type.addItems(
            [
                t["casc_type_uniform"],
                t["casc_type_matr_12"],
                t["casc_type_matr_15"],
                t["casc_type_manual"],
            ]
        )
        self.cb_type.setCurrentIndex(max(0, min(current_idx, 3)))
        self.cb_type.blockSignals(False)
        self.table.setHorizontalHeaderLabels(
            [t["casc_table_vol"], t["casc_table_dist"]]
        )
        self.btn_apply.setText(t["casc_apply"])
        self.recalc_table()
        self._refresh_calibration_status()

    def _clear_input_focus(self):
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, QLineEdit):
            focus_widget.deselect()
            focus_widget.clearFocus()
        elif isinstance(focus_widget, QAbstractSpinBox):
            focus_widget.clearFocus()
        if hasattr(self.main, "_clear_ghost_focus"):
            self.main._clear_ghost_focus()

    def _clear_table_focus(self):
        if not hasattr(self, "table"):
            return
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.setCurrentItem(None)
        self.table.clearFocus()

    def _on_focus_changed(self, _old, now):
        if not hasattr(self, "table"):
            return
        if now is None:
            self._clear_table_focus()
            return
        if now is self.table or now is self.table.viewport() or self.table.isAncestorOf(now):
            return
        self._clear_table_focus()

    def _store_apply_click_pos(self):
        """Сохраняет глобальную позицию курсора в момент нажатия кнопки ВЫСТАВИТЬ."""
        try:
            self._btn_apply_click_pos = QCursor.pos()
        except Exception:
            self._btn_apply_click_pos = None

    def mousePressEvent(self, event):
        clicked = self.childAt(event.position().toPoint())
        if not clicked or not (clicked is self.table or self.table.isAncestorOf(clicked)):
            self._clear_table_focus()
        if not isinstance(clicked, (QLineEdit, QAbstractSpinBox)):
            self._clear_input_focus()
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        # No special handling needed - let QAbstractItemView manage the editor
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.calib_active:
                self.cancel_calibration()
                event.accept()
                return
            self._clear_table_focus()
            self._clear_input_focus()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._clear_table_focus()
            self._clear_input_focus()
            event.accept()
            return
        super().keyPressEvent(event)

    def apply_scale(self):
        """
        Подгоняет размеры элементов под текущий масштаб интерфейса (settings['scale']),
        чтобы на вкладке каскадов ничего не вылезало за рамки и текст не резался.
        """
        scale = self.main.settings.get("scale", 100)
        base_scale = getattr(self.main, "base_scale", 130)
        ratio = scale / float(base_scale)
        sc = scale / 100.0

        # Uniform spacing scaling with current UI scale.
        base_h_spacing = 12
        base_v_spacing = 8
        h_spacing = max(4, int(base_h_spacing * ratio))
        v_spacing = max(3, int(base_v_spacing * ratio))
        self.grid_settings.setHorizontalSpacing(h_spacing)
        self.grid_settings.setVerticalSpacing(v_spacing)

        # Кнопка типов: компактная ширина и синхронно с "Кол-во"
        compact_w = max(60, int(70 * sc))
        self.cb_type.setMinimumWidth(compact_w)
        self.cb_type.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.sb_count_wrap.setFixedWidth(compact_w)
        self.sb_min_wrap.setFixedWidth(compact_w)
        self.sb_dist_wrap.setFixedWidth(compact_w)
        self.sb_range_wrap.setFixedWidth(compact_w)
        self.sb_manual_k_wrap.setFixedWidth(compact_w)

        btn_w = max(10, int(11 * sc))
        btn_h = max(9, int(9 * sc))
        input_w = max(26, compact_w - (btn_w * 2) - 6)
        field_h = max(14, int(14 * sc))

        # At scale 100 these controls were too short and clipped digits.
        # Keep other scales unchanged.
        if int(scale) == 100:
            field_h = max(field_h, 22)
            btn_h = max(btn_h, 18)
            btn_w = max(btn_w, 12)
            input_w = max(26, compact_w - (btn_w * 2) - 6)

        for spin, left_btn, right_btn in (
            (self.sb_count, self.sb_count_left, self.sb_count_right),
            (self.sb_min, self.sb_min_left, self.sb_min_right),
            (self.sb_dist, self.sb_dist_left, self.sb_dist_right),
            (self.sb_range_width, self.sb_range_left, self.sb_range_right),
            (self.sb_manual_k, self.sb_manual_k_left, self.sb_manual_k_right),
        ):
            spin.setFixedWidth(input_w)
            spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
            spin.setFixedHeight(field_h)
            left_btn.setFixedSize(btn_w, btn_h)
            right_btn.setFixedSize(btn_w, btn_h)
        self.sb_count_wrap.setFixedHeight(field_h)
        self.sb_min_wrap.setFixedHeight(field_h)
        self.sb_dist_wrap.setFixedHeight(field_h)
        self.sb_range_wrap.setFixedHeight(field_h)
        self.sb_manual_k_wrap.setFixedHeight(field_h)

        # Top custom value fields need a bit more vertical room than compact spin wrappers,
        # otherwise digits can look clipped on some DPI/font combinations.
        custom_line_h = max(field_h + 4, 26)
        if hasattr(self, "inp_custom_total"):
            self.inp_custom_total.setFixedHeight(custom_line_h)
            self.inp_custom_total.setMinimumWidth(max(80, int(90 * sc)))
        if hasattr(self, "inp_custom_percent"):
            self.inp_custom_percent.setFixedHeight(custom_line_h)
            self.inp_custom_percent.setMinimumWidth(max(80, int(90 * sc)))
        if hasattr(self, "inp_max_limit"):
            self.inp_max_limit.setFixedHeight(field_h)
            self.inp_max_limit.setFixedWidth(max(52, int(60 * sc)))
        if hasattr(self, "btn_max_limit"):
            self.btn_max_limit.setFixedHeight(field_h)
            self.btn_max_limit.setFixedWidth(max(46, int(52 * sc)))

        # Итоговый объем каскада
        self.lbl_total_vol.setStyleSheet(
            "color: #FF9F0A; font-weight: bold; font-size: 11pt; margin-top: 5px;"
        )

        # Таблица ордеров
        self.table.verticalHeader().setDefaultSectionSize(int(14 * sc))
        self.table.setMinimumHeight(int(80 * sc))
        item_font = max(6, int(6 * ratio))
        header_font = max(6, int(8 * ratio))
        self.table.setStyleSheet(
            "QTableWidget { background: #141414; color: #D0D0D0; alternate-background-color: #141414; gridline-color: #2A2A2A; }"
            f"QTableWidget::item {{ background: #141414; color: #D0D0D0; font-size: {item_font}pt; padding: 0px 1px; margin: 0px; }}"
            "QTableWidget::item:focus { outline: none; border: none; }"
            "QHeaderView { background: #141414; }"
            f"QHeaderView::section:horizontal {{ background: #1A1A1A; color: #A0A0A0; border: 1px solid #2A2A2A; font-size: {header_font}pt; padding: 1px; }}"
            f"QHeaderView::section:vertical {{ background: #141414; color: #707070; border: 1px solid #2A2A2A; font-size: {header_font}pt; padding: 1px; }}"
            "QTableCornerButton::section { background: #141414; border: 1px solid #2A2A2A; }"
            "QTableWidget QScrollBar:vertical { background: #111111; width: 14px; margin: 0px; border: 1px solid #232323; }"
            "QTableWidget QScrollBar::handle:vertical { background: #3A3A3A; min-height: 24px; border-radius: 4px; border: 1px solid #4A4A4A; }"
            "QTableWidget QScrollBar::add-page:vertical, QTableWidget QScrollBar::sub-page:vertical { background: #111111; }"
            "QTableWidget QScrollBar::add-line:vertical, QTableWidget QScrollBar::sub-line:vertical { background: #1A1A1A; height: 14px; border: 1px solid #2A2A2A; }"
            "QTableWidget QScrollBar:horizontal { background: #111111; height: 14px; margin: 0px; border: 1px solid #232323; }"
            "QTableWidget QScrollBar::handle:horizontal { background: #3A3A3A; min-width: 24px; border-radius: 4px; border: 1px solid #4A4A4A; }"
            "QTableWidget QScrollBar::add-page:horizontal, QTableWidget QScrollBar::sub-page:horizontal { background: #111111; }"
            "QTableWidget QScrollBar::add-line:horizontal, QTableWidget QScrollBar::sub-line:horizontal { background: #1A1A1A; width: 14px; border: 1px solid #2A2A2A; }"
            "selection-background-color: #38BE1D; selection-color: black;"
        )

        # Строка статуса внизу
        self.lbl_status.setStyleSheet(
            "color: #666; font-size: 7pt; margin-bottom: 5px;"
        )

    def apply_min_order_precision(self, decimals):
        if decimals < 0:
            decimals = 0
        if decimals > 6:
            decimals = 6

        self.sb_min.blockSignals(True)
        self.sb_min.setDecimals(decimals)
        self.sb_min.setSingleStep(1 if decimals == 0 else 10 ** (-decimals))
        self.sb_min.setValue(round(self.sb_min.value(), decimals))
        self.sb_min.blockSignals(False)
        self.recalc_table()

    def on_perc_click(self):
        sender = self.sender()
        for btn in self.group_btns:
            btn.setChecked(False)
        sender.setChecked(True)
        if getattr(self, "btn_use_custom_percent", None):
            self.btn_use_custom_percent.setChecked(False)
            self.inp_custom_percent.setEnabled(False)
            self.main.settings["cas_use_custom_percent"] = False
            self.main.save_settings()
        self.recalc_table()
        self._clear_main_deposit_selection()

    def on_custom_percent_toggled(self, checked):
        if checked:
            for btn in self.group_btns:
                btn.setChecked(False)
        else:
            if not any(btn.isChecked() for btn in self.group_btns):
                self.group_btns[3].setChecked(True)
        self.inp_custom_percent.setEnabled(bool(checked))
        self.main.settings["cas_use_custom_percent"] = bool(checked)
        self.save_custom_percent_setting()
        self.recalc_table()
        self._clear_main_deposit_selection()

    def on_custom_percent_text_changed(self, text):
        if not self.btn_use_custom_percent.isChecked():
            return
        value = self._parse_custom_percent_value(text)
        self.main.settings["cas_custom_percent"] = float(value)
        self.main.save_settings()
        self.recalc_table()

    def save_custom_percent_setting(self):
        value = self._parse_custom_percent_value(self.inp_custom_percent.text())
        self.main.settings["cas_custom_percent"] = float(value)
        self.main.save_settings()

    def get_percent(self):
        if (
            getattr(self, "btn_use_custom_percent", None)
            and self.btn_use_custom_percent.isChecked()
        ):
            value = self._parse_custom_percent_value(self.inp_custom_percent.text())
            return max(0.0, min(100.0, value)) / 100.0
        for btn in self.group_btns:
            if btn.isChecked():
                return float(btn.text().replace("%", "")) / 100.0
        return 1.0

    def _parse_custom_percent_value(self, text):
        try:
            value = float((text or "").replace(" ", "").replace(",", ".") or 0)
        except Exception:
            value = 0.0
        return max(0.0, min(100.0, value))

    def set_custom_vol_enabled(self, enabled):
        self.inp_custom_total.setEnabled(enabled)
        if hasattr(self, "lbl_custom_total_hint"):
            self.lbl_custom_total_hint.setVisible(bool(enabled))
        if hasattr(self, "btn_use_custom_vol"):
            self.btn_use_custom_vol.setProperty("dimmed", not enabled)
            self.btn_use_custom_vol.style().polish(self.btn_use_custom_vol)
            self.btn_use_custom_vol.update()

    def on_volume_source_changed(self, checked):
        self.set_custom_vol_enabled(checked)
        self.main.settings["cas_use_custom_vol"] = bool(checked)
        self.main.save_settings()
        self.recalc_table()
        self._clear_main_deposit_selection()

    def on_custom_vol_text_changed(self, text):
        if not self.btn_use_custom_vol.isChecked():
            return
        value = self._parse_custom_total_value(text)
        self.main.settings["cas_custom_total_vol"] = float(value)
        self.main.save_settings()
        self._set_custom_total_hint_value(value)
        self.recalc_table()

    def save_custom_vol_setting(self):
        value = self._parse_custom_total_value(self.inp_custom_total.text())
        self.main.settings["cas_custom_total_vol"] = float(value)
        self.main.save_settings()
        self._set_custom_total_hint_value(value)

    def _set_custom_total_hint_value(self, value):
        if not hasattr(self, "lbl_custom_total_hint"):
            return
        hint_value = self.main.format_hint_no_decimals(value)
        self.lbl_custom_total_hint.setText(hint_value)

    def _parse_custom_total_value(self, text):
        try:
            value = float((text or "").replace(" ", "").replace(",", ".") or 0)
        except Exception:
            value = 0.0
        return max(0.01, value)

    def on_min_text_changed(self, text):
        """Реал-тайм обновление при изменении текста в 'Мин. ордер'"""
        try:
            float(text)  # Проверяем, что это валидное число
            self.recalc_table()
        except ValueError:
            pass  # Ждем, пока пользователь доведет ввод до валидного числа

    def on_dist_text_changed(self, text):
        """Реал-тайм обновление при изменении текста в 'Шаг'"""
        try:
            float(text)  # Проверяем, что это валидное число
            self.recalc_table()
        except ValueError:
            pass  # Ждем, пока пользователь доведет ввод до валидного числа

    def on_count_changed(self, value):
        self.main.settings["last_cascade_count"] = int(value)
        self.main.save_settings()
        self.recalc_table()

    def on_dist_changed(self, value):
        self.main.settings["cas_dist_step"] = float(value)
        self.main.save_settings()
        self.recalc_table()

    def on_range_text_changed(self, text):
        try:
            float(text)
            self.on_range_width_changed(self.sb_range_width.value())
        except ValueError:
            pass

    def on_manual_k_text_changed(self, text):
        try:
            float(text)
            self.recalc_table()
        except ValueError:
            pass

    def on_type_changed(self, index):
        is_manual = index == 3
        self.sb_manual_k_wrap.setEnabled(is_manual)
        self.sb_manual_k_wrap.setVisible(is_manual)
        self.lbl_manual_k.setVisible(is_manual)
        self.main.settings["cas_type_index"] = int(index)
        self.main.settings["cas_manual_k"] = float(self.sb_manual_k.value())
        self.main.save_settings()
        self.recalc_table()

    def _on_cascade_table_item_clicked(self, item):
        """1-click: open editor and put cursor to the right without selecting text"""
        if not item:
            return

        self.table.editItem(item)

        def deselect_and_position():
            from PyQt6.QtWidgets import QApplication
            editor = QApplication.instance().focusWidget()
            if isinstance(editor, QLineEdit):
                editor.deselect()
                editor.setCursorPosition(len(editor.text()))

        QTimer.singleShot(0, deselect_and_position)


    def _on_cascade_table_item_double_clicked(self, item):
        """2-click: select all text inside active editor"""
        if not item:
            return

        def select_all_delayed():
            from PyQt6.QtWidgets import QApplication
            editor = QApplication.instance().focusWidget()
            if isinstance(editor, QLineEdit):
                editor.setSelection(0, len(editor.text()))

        QTimer.singleShot(0, select_all_delayed)

    def _on_table_cell_changed(self, row, column):
        # Do not auto-change cascade type when user edits distance values
        # User should be able to enter values without type changing
        pass

    def on_range_mode_toggled(self, checked):
        """Переключение режима: ширина диапазона vs шаг."""
        self.main.settings["cas_range_mode"] = bool(checked)
        self.main.save_settings()
        self._apply_range_mode_state(checked)
        self.recalc_table()

    def _apply_range_mode_state(self, range_mode_on):
        """Включает/выключает контролы в зависимости от режима."""
        # Range mode ON: range width enabled, step disabled
        self.sb_range_width.setEnabled(range_mode_on)
        self.sb_range_wrap.setEnabled(range_mode_on)
        if hasattr(self, "sb_range_left"):
            self.sb_range_left.setEnabled(range_mode_on)
            self.sb_range_right.setEnabled(range_mode_on)

        # Range mode OFF: step enabled, range width disabled
        self.sb_dist.setEnabled(not range_mode_on)
        self.sb_dist_wrap.setEnabled(not range_mode_on)
        self.lbl_step_title.setEnabled(not range_mode_on)
        if hasattr(self, "sb_dist_left"):
            self.sb_dist_left.setEnabled(not range_mode_on)
            self.sb_dist_right.setEnabled(not range_mode_on)

        # Обновляем стили для затемнения
        disabled_style = "color: #444; font-size: 9pt;"
        enabled_style = "color: #aaa; font-size: 9pt;"
        self.lbl_step_title.setStyleSheet(
            disabled_style if range_mode_on else enabled_style
        )
        # Затемняем чекбокс когда он выключен (range_mode_on = False)
        self.chk_range_mode.setStyleSheet(
            "QCheckBox { color: #aaa; font-size: 9pt; spacing: 5px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #555; background: #1A1A1A; }"
            f"QCheckBox::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({self._checkmark_path_css}); }}"
            if range_mode_on
            else "QCheckBox { color: #444; font-size: 9pt; spacing: 5px; }"
            "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #333; background: #0F0F0F; }"
            f"QCheckBox::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({self._checkmark_path_css}); }}"
        )

    def on_range_width_changed(self, value):
        self.main.settings["cas_range_width"] = float(value)
        self.main.save_settings()
        self.recalc_table()

    def get_base_volume(self):
        if (
            getattr(self, "btn_use_custom_vol", None)
            and self.btn_use_custom_vol.isChecked()
        ):
            return self._parse_custom_total_value(self.inp_custom_total.text())
        return getattr(self.main, "current_vol", 0)

    def calculate_max_possible(self, total_vol, min_size, mult):
        if mult == 1.0:
            max_possible = int(total_vol / min_size)
        else:
            max_possible = 1
            while max_possible <= 20:
                geo_sum = min_size * (mult**max_possible - 1) / (mult - 1)
                if geo_sum > total_vol:
                    break
                max_possible += 1
            max_possible = max(1, max_possible - 1)
        return max(1, max_possible)

    def auto_configure_by_range(self):
        range_width = self.sb_range_width.value()
        if range_width <= 0:
            return

        if self.cb_type.currentIndex() == 0:
            self.cb_type.blockSignals(True)
            self.cb_type.setCurrentIndex(1)
            self.cb_type.blockSignals(False)

        mult = self.get_multiplier()
        min_size = self.sb_min.value()
        total_vol = self.get_base_volume() * self.get_percent()
        if total_vol <= 0:
            return

        max_possible = self.calculate_max_possible(total_vol, min_size, mult)
        max_possible = min(20, max_possible)
        min_step = self.sb_dist.minimum()
        if min_step <= 0:
            return
        max_count_by_range = int(range_width / min_step) + 1
        desired_count = min(max_possible, max_count_by_range)
        desired_count = max(2, desired_count)

        desired_dist = range_width / (desired_count - 1)
        desired_dist = max(
            self.sb_dist.minimum(), min(self.sb_dist.maximum(), desired_dist)
        )

        self.sb_count.blockSignals(True)
        self.sb_dist.blockSignals(True)
        self._last_type_index = self.cb_type.currentIndex()
        self.sb_count.setValue(desired_count)
        self.sb_dist.setValue(desired_dist)
        self.sb_count.blockSignals(False)
        self.sb_dist.blockSignals(False)

        self.recalc_table()

    def get_multiplier(self):
        idx = self.cb_type.currentIndex()
        if idx == 0:
            return 1.0
        if idx == 1:
            return 1.2
        if idx == 2:
            return 1.5
        if idx == 3:
            self.main.settings["cas_manual_k"] = float(self.sb_manual_k.value())
            return float(self.sb_manual_k.value())
        return 1.0

    def _last_order_share(self, multiplier, count):
        if count <= 1:
            return 1.0
        if abs(multiplier - 1.0) < 1e-9:
            return 1.0 / count

        # Численно устойчивая формула без больших степеней:
        # share_last = (m-1) / (m - m^{-(n-1)})
        try:
            inv_pow = multiplier ** (-(count - 1))
        except OverflowError:
            inv_pow = 0.0

        denominator = multiplier - inv_pow
        if abs(denominator) < 1e-12:
            return 1.0 / count
        return (multiplier - 1.0) / denominator

    def _effective_multiplier_with_cap(self, target_multiplier, count, cap_share=0.40):
        if count <= 1 or target_multiplier <= 1.0:
            return (
                max(1.0, target_multiplier),
                False,
                False,
                self._last_order_share(max(1.0, target_multiplier), count),
            )

        current_share = self._last_order_share(target_multiplier, count)
        if current_share <= cap_share:
            return target_multiplier, False, False, current_share

        min_share = self._last_order_share(1.0, count)
        if min_share > cap_share:
            return 1.0, True, True, min_share

        low = 1.0
        high = target_multiplier
        for _ in range(32):
            mid = (low + high) / 2.0
            mid_share = self._last_order_share(mid, count)
            if mid_share > cap_share:
                high = mid
            else:
                low = mid

        effective = max(1.0, low)
        return effective, True, False, self._last_order_share(effective, count)

    def recalc_table(self):
        base_vol = self.get_base_volume()
        total_vol = base_vol * self.get_percent()

        p_dep = int(self.main.settings.get("prec_dep", 2))
        if p_dep < 0:
            p_dep = 0
        if p_dep > 6:
            p_dep = 6

        p_vol = int(self.main.settings.get("prec_dep", 2))
        if p_vol < 0:
            p_vol = 0
        if p_vol > 6:
            p_vol = 6

        self.lbl_total_vol.setText(
            self._t("casc_total", total=f"{total_vol:.{p_dep}f}")
        )
        if hasattr(self, "lbl_total_vol_hint"):
            self.lbl_total_vol_hint.setText(
                self.main.format_hint_no_decimals(total_vol)
            )
        if hasattr(self, "lbl_custom_total_hint"):
            base_hint_val = self._parse_custom_total_value(self.inp_custom_total.text())
            self._set_custom_total_hint_value(base_hint_val)

        count = self.sb_count.value()
        min_size = self.sb_min.value()
        dist_step = self.sb_dist.value()
        range_width = float(self.sb_range_width.value() or 0.0)
        mult = self.get_multiplier()

        if total_vol <= 0:
            self.table.setRowCount(0)
            self.calculated_orders = []
            return

        # Проверяем: изменился ли тип
        current_type_index = self.cb_type.currentIndex()
        type_changed = current_type_index != self._last_type_index

        # Проверяем: был ли count на максимуме перед изменением типа
        user_was_at_max = count == self._last_max_possible

        # Вычисляем максимально возможное количество ячеек
        max_possible = self.calculate_max_possible(total_vol, min_size, mult)
        max_possible = min(20, max_possible)

        # Устанавливаем максимум для SpinBox
        self.sb_count.blockSignals(True)
        self.sb_count.setMaximum(max_possible)

        skip_autoset = bool(getattr(self, "_skip_initial_autoset", False))
        if skip_autoset:
            self._skip_initial_autoset = False

        # Если тип изменился или пользователь был на максимуме, ставим новый максимум
        if (type_changed or user_was_at_max) and not skip_autoset:
            self.sb_count.setValue(max_possible)
        elif count > max_possible:
            # Если count > max_possible, принудительно ограничиваем
            self.sb_count.setValue(max_possible)

        self.sb_count.blockSignals(False)

        count = self.sb_count.value()

        # Авто-лимит риска: последний ордер не должен быть слишком большим
        if current_type_index == 4:
            capped_by_risk = False
            cap_impossible = False
        else:
            effective_mult, capped_by_risk, cap_impossible, _ = (
                self._effective_multiplier_with_cap(mult, count, cap_share=0.40)
            )
            mult = effective_mult

        # Запоминаем текущий максимум и тип для следующего вызова
        self._last_max_possible = max_possible
        self._last_type_index = current_type_index

        # === РАВНОМЕРНОЕ РАСПРЕДЕЛЕНИЕ ===
        if mult == 1.0:
            # Используем введенное кол-во, делим поровну
            vol_per_cell = total_vol / count
            final_volumes = [vol_per_cell for _ in range(count)]

            # Подсказка для равномерного
            hint_text = self._t("casc_max_cells", max=max_possible)
            self.lbl_count_hint.setText(hint_text)
            if count > max_possible:
                self.lbl_count_hint.setStyleSheet(
                    "color: #40E0D0; font-size: 8pt; font-weight: bold;"
                )
            elif cap_impossible:
                self.lbl_count_hint.setStyleSheet(
                    "color: #40E0D0; font-size: 8pt; font-weight: bold;"
                )
            else:
                self.lbl_count_hint.setStyleSheet("color: #40E0D0; font-size: 8pt;")

        else:
            # === МАТРЕШКА/АГРЕССИВНО (экспоненциальное распределение) ===
            # Геометрическая прогрессия с масштабированием
            # volume[i] = scale * min_size * mult^i
            # где scale подбирается так, чтобы сумма = total_vol

            # Вычисляем сумму идеальной геометрической прогрессии
            # S = min_size * (mult^count - 1) / (mult - 1)
            geo_sum = min_size * (mult**count - 1) / (mult - 1)

            # Вычисляем коэффициент масштабирования
            scale = total_vol / geo_sum if geo_sum > 0 else 1.0

            # Генерируем масштабированный ряд
            final_volumes = [scale * min_size * (mult**i) for i in range(count)]

            # Подсказка для матрешки с максимумом
            hint_text = self._t("casc_max_cells", max=max_possible)
            self.lbl_count_hint.setText(hint_text)
            if count > max_possible:
                self.lbl_count_hint.setStyleSheet(
                    "color: #40E0D0; font-size: 8pt; font-weight: bold;"
                )
            elif cap_impossible:
                self.lbl_count_hint.setStyleSheet(
                    "color: #40E0D0; font-size: 8pt; font-weight: bold;"
                )
            else:
                self.lbl_count_hint.setStyleSheet("color: #40E0D0; font-size: 8pt;")

        # Заполнение таблицы
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(final_volumes))
            self.calculated_orders = []

            dist_prec = max(2, int(self.sb_dist.decimals()))
            for i, vol in enumerate(final_volumes):
                if self.chk_range_mode.isChecked():
                    if count > 1 and range_width > 0:
                        dist = range_width * (i / (count - 1))
                        if i == count - 1:
                            dist = range_width
                    else:
                        dist = 0.0
                else:
                    dist = i * dist_step
                vol_item = QTableWidgetItem(f"{vol:.{p_vol}f}")
                vol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                vol_item.setBackground(QColor("#141414"))
                vol_item.setForeground(QColor("#D0D0D0"))

                # Подсвечиваем если < min_size
                if vol < min_size:
                    vol_item.setForeground(Qt.GlobalColor.red)

                self.table.setItem(i, 0, vol_item)

                dist_item = QTableWidgetItem(f"{dist:.{dist_prec}f}")
                dist_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                dist_item.setBackground(QColor("#141414"))
                dist_item.setForeground(QColor("#D0D0D0"))
                self.table.setItem(i, 1, dist_item)
                self.calculated_orders.append(
                    {"vol": round(vol, p_vol), "dist": round(dist, 2)}
                )
        finally:
            self.table.blockSignals(False)

    def start_calibration(self):
        # Сбрасываем старые точки калибровки перед началом новой
        for key in [
            "cas_p_gear",
            "cas_p_book",
            "cas_p_scrollbar",
            "cas_p_vol1",
            "cas_p_dist1",
            "cas_p_vol2",
            "cas_p_dist2",
            "cas_p_btn_add",
            "cas_p_btn_del",
            "cas_p_combo_vol",
            "cas_p_close_x",
        ]:
            self.main.settings[key] = None
        self.main.save_settings()

        # Получаем горячую клавишу для захвата координат из настроек
        self.calib_hotkey = self.main.settings.get("hk_coords", "f2").lower()
        hotkey_display = self.calib_hotkey.upper().replace("+", " + ")

        self.lbl_status.setText(self._t("casc_step_1", hotkey=hotkey_display))
        self.lbl_status.setStyleSheet("color: cyan;")
        self.calib_active = True
        self.calib_step = 1

    def handle_calibration_hotkey(self):
        if not self.calib_active:
            self.start_calibration()
            return
        self.next_calib_step()

    def cancel_calibration(self):
        if not self.calib_active:
            return False

        self.main.settings["cas_p_gear"] = None
        self.main.settings["cas_p_book"] = None
        self.main.settings["cas_p_scrollbar"] = None
        self.main.settings["cas_p_vol1"] = None
        self.main.settings["cas_p_dist1"] = None
        self.main.settings["cas_p_vol2"] = None
        self.main.settings["cas_p_dist2"] = None
        self.main.settings["cas_p_btn_add"] = None
        self.main.settings["cas_p_btn_del"] = None
        self.main.settings["cas_p_combo_vol"] = None
        self.main.settings["cas_p_close_x"] = None
        self.main.save_settings()

        self.calib_active = False
        self.calib_step = 0
        hotkey_display = (
            self.main.settings.get("hk_coords", "f2").upper().replace("+", " + ")
        )
        self.lbl_status.setText(self._t("casc_calib_reset", hotkey=hotkey_display))
        self.lbl_status.setStyleSheet("color: #FF9F0A;")
        return True

    def next_calib_step(self):
        import pyautogui

        x, y = pyautogui.position()
        hotkey_display = self.calib_hotkey.upper().replace("+", " + ")

        if self.calib_step == 1:
            self.main.settings["cas_p_gear"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_2", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 2:
            self.main.settings["cas_p_book"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_3", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 3:
            self.main.settings["cas_p_scrollbar"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_4", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 4:
            self.main.settings["cas_p_vol1"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_5", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 5:
            self.main.settings["cas_p_dist1"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_6", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 6:
            self.main.settings["cas_p_vol2"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_7", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 7:
            self.main.settings["cas_p_dist2"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_8", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 8:
            self.main.settings["cas_p_btn_add"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_9", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 9:
            self.main.settings["cas_p_btn_del"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_10", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 10:
            self.main.settings["cas_p_combo_vol"] = [x, y]
            self.lbl_status.setText(self._t("casc_step_11", hotkey=hotkey_display))
            self.lbl_status.setStyleSheet("color: cyan;")

        elif self.calib_step == 11:
            self.main.settings["cas_p_close_x"] = [x, y]
            self.lbl_status.setText(self._t("casc_calib_done"))
            self.lbl_status.setStyleSheet("color: #38BE1D;")
            self.main.save_settings()
            self.calib_active = False
            self.calib_step = 0
            QTimer.singleShot(20000, self._set_ready_status)
            return

        self.calib_step += 1

    def run_automation(self):
        self._clear_main_deposit_selection()

        if not hasattr(self, "calculated_orders") or not self.calculated_orders:
            self.recalc_table()

        required_points = (
            self.main.settings.get("cas_p_gear"),
            self.main.settings.get("cas_p_book"),
            self.main.settings.get("cas_p_vol1"),
            self.main.settings.get("cas_p_dist1"),
            self.main.settings.get("cas_p_vol2"),
            self.main.settings.get("cas_p_btn_add")
            or self.main.settings.get("cas_p_plus"),
            self.main.settings.get("cas_p_btn_del")
            or self.main.settings.get("cas_p_x"),
        )
        if not all(required_points):
            self.lbl_status.setText(self._t("casc_status_need"))
            self.lbl_status.setStyleSheet("color: #666;")
            return

        # Сохраняем позицию кнопки ВЫСТАВИТЬ на экране.
        # Prefer the actual cursor position where the user pressed the button (stored on pressed()),
        # otherwise fall back to button center.
        try:
            pos = getattr(self, "_btn_apply_click_pos", None)
            if pos:
                # QCursor.pos() returns a QPoint (global coords)
                self._btn_apply_global_pos = pos
            else:
                btn_center = self.btn_apply.rect().center()
                self._btn_apply_global_pos = self.btn_apply.mapToGlobal(btn_center)
        except Exception:
            self._btn_apply_global_pos = None

        self.lbl_status.setText(self._t("casc_status_applying"))
        self.lbl_status.setStyleSheet("color: #FF9F0A;")
        self.apply_active = True

        # Save exact mouse position (screen coords) like calculator does, then minimize
        try:
            import pyautogui as _pyag

            start_pos = _pyag.position()
            # store tuple for later exact restoration
            self._btn_apply_start_pos = (int(start_pos[0]), int(start_pos[1]))
        except Exception:
            self._btn_apply_start_pos = None

        import time as _t

        if bool(self.main.settings.get("minimize_after_apply", True)):
            self.main.showMinimized()
            _t.sleep(0.15)
        else:
            _t.sleep(0.03)

        orders_for_apply = []
        for row in range(self.table.rowCount()):
            vol_item = self.table.item(row, 0)
            dist_item = self.table.item(row, 1)
            vol_text = vol_item.text().strip() if vol_item and vol_item.text() else "0"
            dist_text = (
                dist_item.text().strip() if dist_item and dist_item.text() else "0"
            )
            orders_for_apply.append({"vol": vol_text, "dist": dist_text})

        prev_count = self.main.settings.get("cas_last_applied_count")
        if prev_count is None:
            prev_count = len(orders_for_apply)
        self._last_apply_count = len(orders_for_apply)
        self.worker = CascadeWorker(
            self.main.settings, orders_for_apply, self.main, prev_count
        )
        self.worker.finished.connect(self._on_cascade_finished)
        self.worker.cancelled.connect(self._on_cascade_cancelled)
        self.worker.failed.connect(self._on_cascade_failed)
        self.worker.start()

    def _restore_cursor_after_apply(self):
        """Перемещаем курсор на позицию кнопки ВЫСТАВИТЬ (окно НЕ разворачиваем)"""
        # Prefer the exact screen coords captured via pyautogui.position()
        start_pos = getattr(self, "_btn_apply_start_pos", None)
        if start_pos:
            try:
                import pyautogui

                pyautogui.moveTo(start_pos[0], start_pos[1])
                return
            except Exception:
                pass

        # Fallback to stored global QPoint from pressed() if available
        pos = getattr(self, "_btn_apply_global_pos", None)
        if not pos:
            return
        try:
            import pyautogui

            pyautogui.moveTo(pos.x(), pos.y())
        except Exception:
            pass

    def _clear_main_deposit_selection(self):
        try:
            if hasattr(self.main, "_clear_ghost_focus"):
                self.main._clear_ghost_focus()
            fw = QApplication.focusWidget()
            if fw is not None:
                fw.clearFocus()
            if hasattr(self.main, "inp_dep") and self.main.inp_dep is not None:
                self.main.inp_dep.deselect()
                self.main.inp_dep.clearFocus()
            if hasattr(self.main, "tabs") and self.main.tabs is not None:
                self.main.tabs.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass

    def _on_cascade_finished(self):
        self.lbl_status.setText(self._t("casc_status_done"))
        self.lbl_status.setStyleSheet("color: #38BE1D; font-size: 7pt;")
        try:
            self.main.settings["cas_last_applied_count"] = int(
                getattr(self, "_last_apply_count", 1)
            )
            self.main.save_settings()
        except Exception:
            pass
        self.apply_active = False
        self._restore_cursor_after_apply()
        self._clear_main_deposit_selection()
        QTimer.singleShot(5000, self._set_ready_status)

    def _on_cascade_cancelled(self):
        self.lbl_status.setText(self._t("casc_status_cancel"))
        self.lbl_status.setStyleSheet("color: #FF9F0A; font-size: 7pt;")
        self._cancel_status_until = time.time() + 7.0
        self.apply_active = False
        self._restore_cursor_after_apply()
        self._clear_main_deposit_selection()
        QTimer.singleShot(7000, self._set_ready_status)

    def _on_cascade_failed(self, error):
        self.lbl_status.setText(self._t("casc_status_error", error=error))
        self.lbl_status.setStyleSheet("color: #FF453A; font-size: 7pt;")
        self.apply_active = False
        self._restore_cursor_after_apply()
        self._clear_main_deposit_selection()

    def is_apply_active(self):
        return bool(getattr(self, "apply_active", False))

    def _cascade_points_count(self):
        required = [
            "cas_p_gear",
            "cas_p_book",
            "cas_p_scrollbar",
            "cas_p_vol1",
            "cas_p_dist1",
            "cas_p_vol2",
            "cas_p_dist2",
            "cas_p_close_x",
        ]
        count = sum(1 for key in required if self.main.settings.get(key))
        if self.main.settings.get("cas_p_btn_add") or self.main.settings.get(
            "cas_p_plus"
        ):
            count += 1
        if self.main.settings.get("cas_p_btn_del") or self.main.settings.get("cas_p_x"):
            count += 1
        if self.main.settings.get("cas_p_combo_vol") or self.main.settings.get(
            "cas_p_vol1"
        ):
            count += 1
        return count

    def _set_ready_status(self):
        if self.calib_active or self.apply_active:
            return
        if time.time() < float(getattr(self, "_cancel_status_until", 0.0) or 0.0):
            return
        cells_count = self._cascade_points_count()
        self.lbl_status.setText(self._t("casc_status_ready", count=cells_count))
        self.lbl_status.setStyleSheet("color: #38BE1D; font-size: 7pt;")

    def _refresh_calibration_status(self):
        if self.calib_active or self.apply_active:
            return
        if time.time() < float(getattr(self, "_cancel_status_until", 0.0) or 0.0):
            return
        points_count = self._cascade_points_count()
        if points_count >= 11:
            self._set_ready_status()
            return
        if points_count > 0:
            self.lbl_status.setText(self._t("casc_status_partial", count=points_count))
            self.lbl_status.setStyleSheet("color: #FF9F0A; font-size: 7pt;")
            return
        self.lbl_status.setText(self._t("casc_status_need"))
        self.lbl_status.setStyleSheet(
            "color: #666; font-size: 7pt; margin-bottom: 5px;"
        )
