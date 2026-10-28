from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSpacerItem,
    QSizePolicy,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QSpinBox,
    QFrame,
    QAbstractSpinBox,
    QTableWidget,
    QAbstractItemView,
    QStyledItemDelegate,
    QCheckBox,
    QWidget,
)
from PyQt6.QtCore import Qt, QRegularExpression, QTimer
from PyQt6.QtGui import QRegularExpressionValidator
from translations import TRANS


class PercentItemDelegate(QStyledItemDelegate):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setFrame(False)
            editor.setFont(option.font)
            editor.setContentsMargins(0, 0, 0, 0)
            editor.setStyleSheet("padding: 0px; margin: 0px;")
            editor.setValidator(
                QRegularExpressionValidator(QRegularExpression(r"[0-9]*"), editor)
            )

            model = index.model()
            row = index.row()
            col = index.column()

            def _push_live_value(text, m=model, r=row, c=col):
                idx = m.index(r, c)
                if not idx.isValid():
                    return
                current = str(m.data(idx, Qt.ItemDataRole.EditRole) or "")
                if current != text:
                    m.setData(idx, text, Qt.ItemDataRole.EditRole)

            editor.textChanged.connect(_push_live_value)
            # Place cursor at end without selecting (1-click behavior)
            QTimer.singleShot(0, lambda e=editor: (e.deselect(), e.setCursorPosition(len(e.text()))))
        return editor

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


def init_calculator_tab(app):
    main_layout = QVBoxLayout(app.tab_calculator)
    main_layout.setContentsMargins(4, 4, 4, 4)
    main_layout.setSpacing(4)
    app.calc_layout = main_layout

    v_reg = QRegularExpressionValidator(QRegularExpression(r"[0-9]*[.,]?[0-9]*"))

    t = TRANS.get(app.settings.get("lang", "ru"), TRANS["ru"])

    # --- ДЕПОЗИТ (ВВЕРХУ НА ВСЮ ШИРИНУ) ---
    app.lbl_dep_title = QLabel(t["dep"])
    app.lbl_dep_title.setStyleSheet("color: #888; font-size: 8pt; font-weight: bold;")
    main_layout.addWidget(app.lbl_dep_title)

    # Депозит без форматирования при загрузке
    dep_val = app.settings.get("deposit", 1000)
    app.inp_dep = QLineEdit(
        str(int(dep_val) if dep_val == int(dep_val) else dep_val).replace(".", ",")
    )
    app.inp_dep.setValidator(v_reg)
    app.inp_dep.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_dep.setFixedHeight(24)
    app.inp_dep.textChanged.connect(app.schedule_update_calc)
    app.inp_dep.returnPressed.connect(app._commit_input)
    app.inp_dep.installEventFilter(app)

    dep_row = QHBoxLayout()
    dep_row.setSpacing(4)
    dep_row.addWidget(app.inp_dep, 1)

    app.cb_quick_dep_exchange = QComboBox()
    app.cb_quick_dep_exchange.setObjectName("QuickDepositSelector")
    app.cb_quick_dep_exchange.setFixedSize(92, 24)
    app.cb_quick_dep_exchange.setStyleSheet(
        "QComboBox#QuickDepositSelector { padding: 0px 2px; }"
        "QComboBox#QuickDepositSelector:focus { border: 1px solid #333; outline: none; }"
        "QComboBox#QuickDepositSelector::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 0px; border: none; background: transparent; }"
        "QComboBox#QuickDepositSelector::down-arrow { image: none; width: 0px; height: 0px; border: none; background: transparent; }"
    )
    app.cb_quick_dep_exchange.setToolTip("Быстрый выбор биржи для автодепозита")
    app.cb_quick_dep_exchange.currentIndexChanged.connect(
        app.on_quick_deposit_source_changed
    )
    dep_row.addWidget(app.cb_quick_dep_exchange, 0)

    app.cb_quick_dep_market = QComboBox()
    app.cb_quick_dep_market.setObjectName("QuickDepositSelector")
    app.cb_quick_dep_market.setFixedSize(112, 24)
    app.cb_quick_dep_market.setStyleSheet(
        "QComboBox#QuickDepositSelector { padding: 0px 2px; }"
        "QComboBox#QuickDepositSelector:focus { border: 1px solid #333; outline: none; }"
        "QComboBox#QuickDepositSelector::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 0px; border: none; background: transparent; }"
        "QComboBox#QuickDepositSelector::down-arrow { image: none; width: 0px; height: 0px; border: none; background: transparent; }"
    )
    app.cb_quick_dep_market.addItems(
        ["Фьюч.(кросс)", t.get("auto_dep_market_spot", "Спот")]
    )
    for index in range(app.cb_quick_dep_market.count()):
        app.cb_quick_dep_market.setItemData(
            index, Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole
        )
    app.cb_quick_dep_market.currentIndexChanged.connect(
        app.on_quick_deposit_source_changed
    )
    dep_row.addWidget(app.cb_quick_dep_market, 0)

    app.btn_dep_refresh = QPushButton(t.get("dep_refresh", "↻"))
    app.btn_dep_refresh.setFixedSize(24, 24)
    app.btn_dep_refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    app.btn_dep_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
    app.btn_dep_refresh.setToolTip(
        t.get("dep_refresh_tip", "Обновить депозит с биржи")
    )
    app.btn_dep_refresh.setVisible(bool(app.settings.get("auto_dep_enabled", False)))
    app.btn_dep_refresh.clicked.connect(app.manual_refresh_deposit)
    app.btn_dep_refresh.setStyleSheet(
        "QPushButton { background: #1F1F1F; color: #8CB4FF; border: 1px solid #2D2D2D; border-radius: 4px; font-weight: bold; }"
        "QPushButton:hover { background: #2A2A2A; border: 1px solid #3E6FB8; }"
        "QPushButton:pressed { background: #183A6D; }"
    )
    dep_row.addWidget(app.btn_dep_refresh, 0)

    app.lbl_dep_api_status = QLabel(t.get("dep_api_status_off", "API: выкл"))
    app.lbl_dep_api_status.setStyleSheet("color: #666; font-size: 8pt;")
    app.lbl_dep_api_status.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_dep_api_status.setMinimumWidth(74)
    dep_row.addWidget(app.lbl_dep_api_status, 0)

    main_layout.addLayout(dep_row)
    app.refresh_quick_deposit_controls()

    app.lbl_hint = QLabel("0")
    app.lbl_hint.setStyleSheet("color: #666; font-size: 8pt;")
    app.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
    main_layout.addWidget(app.lbl_hint)

    # --- РИСК И СТОП В ОДНОЙ СТРОКЕ ---
    risk_stop_row = QHBoxLayout()
    risk_stop_row.setSpacing(6)

    # Риск
    risk_col = QVBoxLayout()
    risk_col.setSpacing(1)
    app.lbl_risk_title = QLabel(t["risk"])
    app.lbl_risk_title.setStyleSheet("color: #888; font-size: 8pt; font-weight: bold;")
    risk_col.addWidget(app.lbl_risk_title)
    app.inp_risk = QLineEdit(str(app.settings.get("risk", 1)))
    app.inp_risk.setValidator(v_reg)
    app.inp_risk.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_risk.setFixedHeight(24)
    app.inp_risk.textChanged.connect(app.schedule_update_calc)
    app.inp_risk.returnPressed.connect(app._commit_input)
    app.inp_risk.installEventFilter(app)
    risk_col.addWidget(app.inp_risk)
    risk_stop_row.addLayout(risk_col)

    # Стоп
    stop_col = QVBoxLayout()
    stop_col.setSpacing(1)
    app.lbl_stop_title = QLabel(t["stop"])
    app.lbl_stop_title.setStyleSheet("color: #888; font-size: 8pt; font-weight: bold;")
    stop_col.addWidget(app.lbl_stop_title)
    app.inp_stop = QLineEdit(str(app.settings.get("stop", 1)))
    app.inp_stop.setValidator(v_reg)
    app.inp_stop.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_stop.setFixedHeight(24)
    app.inp_stop.textChanged.connect(app.schedule_update_calc)
    app.inp_stop.returnPressed.connect(app._commit_input)
    app.inp_stop.installEventFilter(app)
    stop_col.addWidget(app.inp_stop)
    risk_stop_row.addLayout(stop_col)

    main_layout.addLayout(risk_stop_row)

    # --- ИНФОРМАЦИЯ (Риск сделки, Комиссия, Плечо) ---
    app.lbl_info = QLabel("")
    app.lbl_info.setStyleSheet("color: #888; font-size: 9pt; line-height: 1.2;")
    app.lbl_info.setWordWrap(False)
    app.lbl_info.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_info.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    main_layout.addWidget(app.lbl_info)

    app.lbl_risk_warning = QLabel("")
    app.lbl_risk_warning.setStyleSheet("color: #FF6B6B; font-size: 7pt;")
    app.lbl_risk_warning.setWordWrap(True)
    app.lbl_risk_warning.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_risk_warning.setVisible(False)
    main_layout.addWidget(app.lbl_risk_warning)

    # --- ОБЪЁМ (ПОСЛЕ ИНФОРМАЦИИ) ---
    app.lbl_vol_title = QLabel(str(t["vol"]).upper())
    app.lbl_vol_title.setStyleSheet(
        "color: #FF9F0A; font-size: 9pt; font-weight: 700; margin-top: 2px;"
    )
    main_layout.addWidget(app.lbl_vol_title)

    app.lbl_vol = QLabel("0")
    app.lbl_vol.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.lbl_vol.setStyleSheet(
        "color: #FF9F0A; font-size: 11pt; font-weight: bold; border: 1px solid #333; "
        "border-radius: 4px; padding: 4px; background: #1A1A1A;"
    )
    app.lbl_vol.setFixedHeight(36)
    main_layout.addWidget(app.lbl_vol)

    app.chk_pos_mode = QCheckBox(t["calc_pos_mode"])
    app.chk_pos_mode.setObjectName("PosModeToggle")
    app.chk_pos_mode.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    app.chk_pos_mode.setChecked(bool(app.settings.get("pos_mode_enabled", False)))
    app.chk_pos_mode.toggled.connect(app.on_position_mode_toggled)
    app.chk_pos_mode.setStyleSheet(
        "QCheckBox { font-size: 9pt; spacing: 5px; margin: 0px; padding: 0px; }"
        "QCheckBox:checked { color: #AAA; }"
        "QCheckBox:unchecked { color: #666; }"
        "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; margin: auto; }"
        f"QCheckBox::indicator:checked {{ background: #38BE1D; border: 1px solid #38BE1D; image: url({app._posmode_checkmark_path_css}); }}"
        "QCheckBox::indicator:unchecked { background: #2A2A2A; border: 1px solid #444; image: none; }"
    )
    main_layout.addWidget(app.chk_pos_mode)

    # --- ДОБОР / СОКРАЩЕНИЕ ПО ТЕКУЩЕЙ ПОЗИЦИИ ---
    pos_row = QHBoxLayout()
    pos_row.setSpacing(6)

    pos_vol_col = QVBoxLayout()
    pos_vol_col.setSpacing(1)
    app.lbl_pos_vol_title = QLabel(t["calc_in_position"])
    app.lbl_pos_vol_title.setStyleSheet("font-size: 8pt;")
    pos_vol_col.addWidget(app.lbl_pos_vol_title)

    app.inp_pos_vol = QLineEdit(str(app.settings.get("pos_current_vol", "0")))
    app.inp_pos_vol.setValidator(v_reg)
    app.inp_pos_vol.setFixedHeight(22)
    app.inp_pos_vol.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_pos_vol.setStyleSheet(
        "font-size: 8pt; padding: 1px; selection-background-color: rgba(90, 205, 80, 150); selection-color: white;"
    )
    app.inp_pos_vol.returnPressed.connect(app._commit_input)
    app.inp_pos_vol.installEventFilter(app)
    app.inp_pos_vol.textChanged.connect(app.update_position_adjustment_info)
    pos_vol_col.addWidget(app.inp_pos_vol)

    pos_risk_col = QVBoxLayout()
    pos_risk_col.setSpacing(1)
    app.lbl_pos_risk_title = QLabel(t["calc_risk_percent"])
    app.lbl_pos_risk_title.setStyleSheet("font-size: 8pt;")
    pos_risk_col.addWidget(app.lbl_pos_risk_title)

    app.inp_pos_risk = QLineEdit(str(app.settings.get("pos_risk", "1")))
    app.inp_pos_risk.setValidator(v_reg)
    app.inp_pos_risk.setFixedHeight(22)
    app.inp_pos_risk.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_pos_risk.setStyleSheet(
        "font-size: 8pt; padding: 1px; selection-background-color: rgba(90, 205, 80, 150); selection-color: white;"
    )
    app.inp_pos_risk.returnPressed.connect(app._commit_input)
    app.inp_pos_risk.installEventFilter(app)
    app.inp_pos_risk.textChanged.connect(app.update_position_adjustment_info)
    pos_risk_col.addWidget(app.inp_pos_risk)

    pos_stop_col = QVBoxLayout()
    pos_stop_col.setSpacing(1)
    app.lbl_pos_stop_title = QLabel(t["calc_stop_percent_entry"])
    app.lbl_pos_stop_title.setStyleSheet("font-size: 8pt;")
    pos_stop_col.addWidget(app.lbl_pos_stop_title)

    app.inp_pos_stop = QLineEdit(str(app.settings.get("pos_stop", "0")))
    app.inp_pos_stop.setValidator(v_reg)
    app.inp_pos_stop.setFixedHeight(22)
    app.inp_pos_stop.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_pos_stop.setStyleSheet(
        "font-size: 8pt; padding: 1px; selection-background-color: rgba(90, 205, 80, 150); selection-color: white;"
    )
    app.inp_pos_stop.returnPressed.connect(app._commit_input)
    app.inp_pos_stop.installEventFilter(app)
    app.inp_pos_stop.textChanged.connect(app.update_position_adjustment_info)
    pos_stop_col.addWidget(app.inp_pos_stop)

    pos_stop_now_col = QVBoxLayout()
    pos_stop_now_col.setSpacing(1)
    app.lbl_pos_stop_now_title = QLabel(t["calc_stop_percent_now"])
    app.lbl_pos_stop_now_title.setStyleSheet("font-size: 8pt;")
    pos_stop_now_col.addWidget(app.lbl_pos_stop_now_title)

    app.inp_pos_stop_now = QLineEdit(str(app.settings.get("pos_stop_now", app.settings.get("pos_stop", "0"))))
    app.inp_pos_stop_now.setValidator(v_reg)
    app.inp_pos_stop_now.setFixedHeight(22)
    app.inp_pos_stop_now.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_pos_stop_now.setStyleSheet(
        "font-size: 8pt; padding: 1px; selection-background-color: rgba(90, 205, 80, 150); selection-color: white;"
    )
    app.inp_pos_stop_now.returnPressed.connect(app._commit_input)
    app.inp_pos_stop_now.installEventFilter(app)
    app.inp_pos_stop_now.textChanged.connect(app.update_position_adjustment_info)
    pos_stop_now_col.addWidget(app.inp_pos_stop_now)

    pos_row.addLayout(pos_vol_col, 1)
    pos_row.addLayout(pos_risk_col, 1)
    pos_row.addLayout(pos_stop_col, 1)
    pos_row.addLayout(pos_stop_now_col, 1)
    main_layout.addLayout(pos_row)

    pos_hints_layout = QVBoxLayout()
    pos_hints_layout.setSpacing(2)
    pos_hints_row = QGridLayout()
    pos_hints_row.setHorizontalSpacing(4)
    pos_hints_row.setVerticalSpacing(0)
    pos_hints_row.setColumnStretch(0, 0)
    pos_hints_row.setColumnStretch(1, 0)
    pos_hints_row.setColumnStretch(2, 1)

    app.lbl_pos_vol_hint = QLabel("0")
    app.lbl_pos_vol_hint.setStyleSheet("color: #666; font-size: 8pt;")
    app.lbl_pos_vol_hint.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_pos_vol_hint.setSizePolicy(
        QSizePolicy.Policy.Maximum,
        QSizePolicy.Policy.Fixed,
    )
    pos_hints_row.addWidget(app.lbl_pos_vol_hint, 0, 0)

    app.lbl_pos_risk_cash = QLabel(t["pos_risk_cash_na"])
    app.lbl_pos_risk_cash.setStyleSheet(
        "color: #888; font-size: 8pt; padding-left: 0px; padding-right: 8px;"
    )
    app.lbl_pos_risk_cash.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_pos_risk_cash.setWordWrap(False)
    app.lbl_pos_risk_cash.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Fixed,
    )
    pos_hints_row.addWidget(app.lbl_pos_risk_cash, 0, 1)

    app.lbl_pos_action_chip = QLabel("")
    app.lbl_pos_action_chip.setStyleSheet(
        "font-size: 8pt; border: 1px solid #666; border-radius: 3px; padding: 0px 4px;"
    )
    app.lbl_pos_action_chip.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_pos_action_chip.setSizePolicy(
        QSizePolicy.Policy.Maximum,
        QSizePolicy.Policy.Fixed,
    )
    app.lbl_pos_action_chip.setVisible(False)
    pos_hints_row.addItem(
        QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        ),
        0,
        2,
    )

    app.lbl_pos_adjust = QLabel(t["calc_recommendation"])
    app.lbl_pos_adjust.setStyleSheet("color: #888; font-size: 8pt;")
    app.lbl_pos_adjust.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_pos_adjust.setWordWrap(False)
    app.lbl_pos_adjust.setMinimumHeight(16)
    app.lbl_pos_adjust.setSizePolicy(
        QSizePolicy.Policy.Maximum,
        QSizePolicy.Policy.Fixed,
    )

    app.lbl_pos_warning = QLabel("")
    app.lbl_pos_warning.setStyleSheet("color: #FF6B6B; font-size: 7pt;")
    app.lbl_pos_warning.setWordWrap(True)
    app.lbl_pos_warning.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_pos_warning.setVisible(False)

    app.lbl_pos_stop_delta = QLabel("")
    app.lbl_pos_stop_delta.setStyleSheet("color: #777; font-size: 7pt;")
    app.lbl_pos_stop_delta.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    app.lbl_pos_stop_delta.setVisible(False)

    pos_adjust_row = QHBoxLayout()
    pos_adjust_row.setContentsMargins(0, 0, 0, 0)
    pos_adjust_row.setSpacing(8)
    pos_adjust_row.addWidget(app.lbl_pos_adjust, 0)
    pos_adjust_row.addWidget(
        app.lbl_pos_action_chip,
        0,
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    pos_adjust_row.addStretch(1)

    pos_hints_layout.addLayout(pos_hints_row)
    pos_hints_layout.addLayout(pos_adjust_row)
    pos_hints_layout.addWidget(app.lbl_pos_stop_delta)
    pos_hints_layout.addWidget(app.lbl_pos_warning)

    main_layout.addLayout(pos_hints_layout)

    # --- НАСТРОЙКА ЯЧЕЕК ---
    cells_header = QHBoxLayout()

    # Кнопка переворота таблицы
    app.btn_reverse_cells = QPushButton("⇅")
    app.btn_reverse_cells.setStyleSheet("color: #8E8E8E;")
    app.btn_reverse_cells.setFixedSize(34, 25)
    app.btn_reverse_cells.setToolTip(t["calc_reverse_cells"])
    app.btn_reverse_cells.clicked.connect(app.toggle_cells_order)
    cells_header.addWidget(app.btn_reverse_cells)

    app.btn_toggle_all_cells = QPushButton(t["calc_toggle_all_btn"])
    app.btn_toggle_all_cells.setFixedSize(34, 25)
    app.btn_toggle_all_cells.setToolTip(t["calc_toggle_all"])
    app.btn_toggle_all_cells.setStyleSheet("color: #8E8E8E;")
    app.btn_toggle_all_cells.clicked.connect(app.toggle_all_transfer_rows)
    cells_header.addWidget(app.btn_toggle_all_cells)

    app.lbl_cells_count_title = QLabel(t.get("calc_cells_count", "Ячеек:"))
    app.lbl_cells_count_title.setStyleSheet("font-size: 8pt;")
    app.lbl_cells_count_title.setVisible(False)
    cells_header.addWidget(app.lbl_cells_count_title)

    app.btn_cells_minus = QPushButton("-")
    app.btn_cells_minus.setFixedSize(26, 25)
    app.btn_cells_minus.setStyleSheet("color: #8E8E8E;")
    app.btn_cells_minus.clicked.connect(app.decrease_cells)
    app.btn_cells_minus.setVisible(False)
    cells_header.addWidget(app.btn_cells_minus)

    app.lbl_cells_count = QLabel("5")
    app.lbl_cells_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.lbl_cells_count.setFixedWidth(22)
    app.lbl_cells_count.setVisible(False)
    cells_header.addWidget(app.lbl_cells_count)

    app.btn_cells_plus = QPushButton("+")
    app.btn_cells_plus.setFixedSize(26, 25)
    app.btn_cells_plus.setStyleSheet("color: #8E8E8E;")
    app.btn_cells_plus.clicked.connect(app.increase_cells)
    app.btn_cells_plus.setVisible(False)
    cells_header.addWidget(app.btn_cells_plus)

    # Минимальный ордер
    app.lbl_min_order_title = QLabel(t["calc_min_order"])
    app.lbl_min_order_title.setStyleSheet("font-size: 8pt;")
    cells_header.addWidget(app.lbl_min_order_title)
    try:
        min_order_val = int(float(app.settings.get("scalp_min_order")))
    except:
        min_order_val = 6
    app.inp_min_order = QLineEdit(str(min_order_val))
    app.inp_min_order.setValidator(
        QRegularExpressionValidator(QRegularExpression(r"[0-9]*"))
    )
    app.inp_min_order.setFixedWidth(50)
    app.inp_min_order.setFixedHeight(22)
    app.inp_min_order.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.inp_min_order.setStyleSheet(
        "font-size: 8pt; padding: 2px; selection-background-color: rgba(90, 205, 80, 150); selection-color: white;"
    )
    app.inp_min_order.textChanged.connect(app.on_min_order_live_changed)
    app.inp_min_order.returnPressed.connect(app.on_min_order_changed)
    app.inp_min_order.installEventFilter(app)
    cells_header.addWidget(app.inp_min_order)

    # Тип распределения (слева, в той же строке)
    app.lbl_calc_type_title = QLabel(t["calc_type"])
    app.lbl_calc_type_title.setStyleSheet("font-size: 8pt;")
    cells_header.addWidget(app.lbl_calc_type_title)
    app.cb_distribution = QComboBox()
    app.cb_distribution.addItems(
        [
            t["calc_dist_uniform"],
            t["calc_dist_desc"],
            t["calc_dist_manual"],
        ]
    )
    saved_type = app.settings.get("scalp_distribution_type", 0)
    if saved_type >= 3:
        saved_type = 0  # Защита от устаревших значений
    app.cb_distribution.setCurrentIndex(saved_type)
    app.cb_distribution.currentIndexChanged.connect(app.apply_distribution_preset)
    app.cb_distribution.setStyleSheet(
        """
        QComboBox { background: #1A1A1A; color: white; border: 1px solid #333; padding: 3px; border-radius: 4px; font-size: 8pt; }
        """
    )
    app.cb_distribution.installEventFilter(app)
    cells_header.addWidget(app.cb_distribution)
    cells_header.addStretch()
    main_layout.addLayout(cells_header)

    # Таблица на всю ширину (3 колонки, всегда 5 строк)
    app.cells_table = QTableWidget()
    app.cells_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Remove focus border
    app.cells_table.setColumnCount(3)
    app.cells_table.setHorizontalHeaderLabels(
        [
            t["calc_table_cells"],
            t["calc_table_volumes"],
            t["calc_table_percent"],
        ]
    )
    app.cells_table.verticalHeader().setVisible(False)
    app.cells_table.horizontalHeader().setStretchLastSection(True)
    # Only allow editing via programmatic editItem(), not direct double-click
    app.cells_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    app.cells_table.setStyleSheet(
        """
        QTableWidget { 
            background: #1A1A1A; 
            gridline-color: #191919; 
            color: white; 
            border: 1px solid #191919;
            border-radius: 4px;
            show-decoration-selected: 0;
        }
        QHeaderView::section { 
            background: #252525; 
            color: #888; 
            border: 1px solid #1F1F1F;
            padding: 4px;
            font-size: 8pt;
        }
        QTableWidget::item {
            padding: 5px;
            border: none;
            color: white;
            background: #1A1A1A;
            outline: none;
            font-size: 6pt;
        }
        QTableWidget::item:focus {
            border: none;
            outline: none;
            background: #1A1A1A;
        }
        QTableWidget::item:selected {
            background: #1A1A1A;
            border: none;
        }
        QTableWidget::item:disabled {
            color: #777;
            background: #000000;
        }
        QLineEdit {
            background: #1A1A1A !important;
            color: white;
            border: 1px solid #191919 !important;
            border-radius: 2px;
            padding: 1px;
            font-size: 6pt;
            margin: 0px;
            selection-background-color: rgba(90, 205, 80, 150);
            selection-color: white;
        }
        """
    )
    app.cells_table.setItemDelegateForColumn(2, PercentItemDelegate(app, app.cells_table))
    # Устанавливаем пропорции колонок (30%, 35%, 35%)
    app.cells_table.horizontalHeader().setSectionResizeMode(
        0, app.cells_table.horizontalHeader().ResizeMode.Stretch
    )
    app.cells_table.horizontalHeader().setSectionResizeMode(
        1, app.cells_table.horizontalHeader().ResizeMode.Stretch
    )
    app.cells_table.horizontalHeader().setSectionResizeMode(
        2, app.cells_table.horizontalHeader().ResizeMode.Stretch
    )
    # Обработчик для предотвращения выделения колонок 0 и 1
    app.cells_table.itemClicked.connect(app.on_table_item_clicked)
    main_layout.addWidget(app.cells_table)

    # Guard gap between table and action buttons: prevents visual collisions at high scales.
    app.w_cells_bottom_guard = QWidget()
    app.w_cells_bottom_guard.setObjectName("CellsBottomGuard")
    app.w_cells_bottom_guard.setFixedHeight(2)
    app.w_cells_bottom_guard.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )
    main_layout.addWidget(app.w_cells_bottom_guard)

    # --- КНОПКА ВЫСТАВИТЬ ---
    apply_row = QHBoxLayout()
    apply_row.setContentsMargins(0, 0, 0, 0)
    apply_row.setSpacing(6)

    app.btn_submit = QPushButton(t["calc_apply"])
    app.btn_submit.setStyleSheet(
        "background: #38BE1D; color: black; font-weight: bold; padding: 6px 16px 6px 24px;"
    )
    app.btn_submit.clicked.connect(app.send_volume_to_terminal)
    apply_row.addWidget(app.btn_submit, 1)

    app.btn_pf_preview = QPushButton(t.get("calc_preview_btn", "ПРЕВЬЮ"))
    app.btn_pf_preview.setToolTip(t.get("calc_show_frames", "Показать рамку"))
    app.btn_pf_preview.clicked.connect(app._on_pf_preview_clicked)
    apply_row.addWidget(app.btn_pf_preview, 0)

    main_layout.addLayout(apply_row)

    app.pf_controls_widget = QWidget()
    pf_controls_layout = QVBoxLayout(app.pf_controls_widget)
    pf_controls_layout.setContentsMargins(0, 0, 0, 0)
    pf_controls_layout.setSpacing(2)

    pf_controls_top_row = QHBoxLayout()
    pf_controls_top_row.setContentsMargins(0, 0, 0, 0)
    pf_controls_top_row.setSpacing(6)

    app.lbl_pf_glasses_title = QLabel(t.get("calc_glasses_count", "Пресетов объёмов:"))
    pf_controls_top_row.addWidget(app.lbl_pf_glasses_title)

    app.sb_pf_count = QSpinBox()
    app.sb_pf_count.setRange(1, 12)
    app.sb_pf_count.setValue(int(app.settings.get("pf_glasses_count", 1) or 1))
    app.sb_pf_count.setKeyboardTracking(False)
    app.sb_pf_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    app.sb_pf_count.setObjectName("pfSpinInner")
    app.sb_pf_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.sb_pf_count.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    if app.sb_pf_count.lineEdit() is not None:
        pf_line = app.sb_pf_count.lineEdit()
        pf_line.installEventFilter(app)
        pf_line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pf_line.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        pf_line.setProperty("no_text_selection", True)

        def _clear_pf_line_selection(line=pf_line):
            if line.hasSelectedText():
                line.deselect()

        pf_line.selectionChanged.connect(_clear_pf_line_selection)

    app.sb_pf_count_wrap = QFrame()
    app.sb_pf_count_wrap.setObjectName("PfSpinWrap")
    sb_wrap_layout = QHBoxLayout(app.sb_pf_count_wrap)
    sb_wrap_layout.setContentsMargins(0, 0, 0, 0)
    sb_wrap_layout.setSpacing(0)

    app.btn_pf_count_dec = QPushButton("-")
    app.btn_pf_count_inc = QPushButton("+")
    app.btn_pf_count_dec.setObjectName("PfSpinStepBtn")
    app.btn_pf_count_inc.setObjectName("PfSpinStepBtn")

    def _step_without_select(step_func, spin=app.sb_pf_count):
        if hasattr(spin, "lineEdit") and spin.lineEdit() is not None:
            spin.lineEdit().deselect()
        step_func()
        if hasattr(spin, "lineEdit") and spin.lineEdit() is not None:
            spin.lineEdit().deselect()

    app.btn_pf_count_dec.clicked.connect(
        lambda: _step_without_select(app.sb_pf_count.stepDown)
    )
    app.btn_pf_count_inc.clicked.connect(
        lambda: _step_without_select(app.sb_pf_count.stepUp)
    )

    sb_wrap_layout.addWidget(app.btn_pf_count_dec)
    sb_wrap_layout.addWidget(app.sb_pf_count)
    sb_wrap_layout.addWidget(app.btn_pf_count_inc)

    app.sb_pf_count.valueChanged.connect(app._on_pf_glasses_count_changed)
    pf_controls_top_row.addWidget(app.sb_pf_count_wrap)

    app.lbl_pf_calib_glass_title = QLabel(
        t.get("calc_calib_glass", "Калибровать пресет:")
    )
    pf_controls_top_row.addWidget(app.lbl_pf_calib_glass_title)

    app.cb_pf_calib_glass = QComboBox()
    app.cb_pf_calib_glass.installEventFilter(app)
    app.cb_pf_calib_glass.currentIndexChanged.connect(app._on_pf_calibration_glass_changed)
    pf_controls_top_row.addWidget(app.cb_pf_calib_glass)

    pf_controls_top_row.addStretch(1)

    app.chk_pf_show_frames = QCheckBox(t.get("calc_show_frames", "Показать рамку"))
    app.chk_pf_show_frames.setChecked(bool(app.settings.get("pf_show_preview_frames", False)))
    app.chk_pf_show_frames.toggled.connect(app._on_pf_preview_toggle_changed)
    pf_controls_top_row.addWidget(app.chk_pf_show_frames)

    pf_controls_layout.addLayout(pf_controls_top_row)

    pf_targets_row = QHBoxLayout()
    pf_targets_row.setContentsMargins(0, 0, 0, 0)
    pf_targets_row.setSpacing(6)

    app.lbl_pf_targets_title = QLabel(t.get("calc_targets", "Выставить в:"))
    pf_targets_row.addWidget(app.lbl_pf_targets_title)

    app.btn_pf_targets_toggle_all = QPushButton(
        t.get("calc_targets_toggle_all_btn", t.get("calc_toggle_all_btn", "Все"))
    )
    app.btn_pf_targets_toggle_all.setFixedSize(34, 25)
    app.btn_pf_targets_toggle_all.setToolTip(
        t.get("calc_targets_toggle_all", "Вкл/выкл все пресеты")
    )
    app.btn_pf_targets_toggle_all.setStyleSheet("color: #8E8E8E;")
    app.btn_pf_targets_toggle_all.clicked.connect(app._toggle_all_pf_target_glasses)
    pf_targets_row.addWidget(app.btn_pf_targets_toggle_all)

    app.pf_targets_widget = QWidget()
    app.pf_targets_widget.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Minimum,
    )
    app.pf_targets_widget.setMinimumHeight(22)
    app.pf_targets_layout = QGridLayout(app.pf_targets_widget)
    app.pf_targets_layout.setContentsMargins(0, 0, 0, 0)
    app.pf_targets_layout.setHorizontalSpacing(4)
    app.pf_targets_layout.setVerticalSpacing(2)
    pf_targets_row.addWidget(
        app.pf_targets_widget,
        1,
        Qt.AlignmentFlag.AlignVCenter,
    )

    pf_controls_layout.addLayout(pf_targets_row)

    pf_controls_bottom_row = QHBoxLayout()
    pf_controls_bottom_row.setContentsMargins(0, 0, 0, 0)
    pf_controls_bottom_row.setSpacing(6)
    pf_controls_bottom_row.addStretch(1)
    app.lbl_pf_targets_summary = QLabel("")
    app.lbl_pf_targets_summary.setAlignment(
        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
    )
    pf_controls_bottom_row.addWidget(app.lbl_pf_targets_summary)
    pf_controls_bottom_row.addStretch(1)
    pf_controls_layout.addLayout(pf_controls_bottom_row)

    main_layout.addWidget(app.pf_controls_widget)

    # --- СТАТУС (ВНИЗУ) ---
    app.lbl_status = QLabel("")
    app.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app.lbl_status.setWordWrap(True)
    app.lbl_status.setStyleSheet("color: #666; font-size: 8pt;")
    main_layout.addWidget(app.lbl_status)

    # Создаём поля ячеек (всегда 5 строк)
    app.on_position_mode_toggled(
        app.chk_pos_mode.isChecked(), is_startup=True
    )  # Restore mode state without overriding distribution
    app.on_cells_changed()
    app.update_calibration_status()
    app.update_position_adjustment_info()
    app.lbl_status.setText("")
    QTimer.singleShot(
        0,
        lambda: (
            app.inp_dep.clearFocus(),
            app.tab_calculator.setFocus(Qt.FocusReason.OtherFocusReason),
        ),
    )
    # Вызываем один раз при инициализации для показа статуса
    QTimer.singleShot(100, app._update_status_text)
