from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QWidget,
)
from PyQt6.QtCore import Qt, QUrl, QSettings
from PyQt6.QtGui import QDesktopServices, QFont
import config


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Переводы
        self.translations = {
            "RU": {
                "title": "О программе",
                "version": f"Версия {config.APP_VERSION}",
                "description": "Это калькулятор для расчёта объёма входа в сделку в зависимости от желаемого процентного стоп-лосса. Помогает быстро рассчитать размер позиции с возможностью автоматического переноса полученных значений в ячейки объёмов в стакан терминала.",
                "developer": "Разработчик:",
                "youtube_btn": "🔗 Smart Link",
            },
            "EN": {
                "title": "About",
                "version": f"Version {config.APP_VERSION}",
                "description": "This is a calculator for position entry size based on the desired stop-loss percentage. It helps you quickly calculate position size with the ability to automatically transfer the values into terminal order-book volume cells.",
                "developer": "Developer:",
                "youtube_btn": "🔗 Smart Link",
            },
        }

        # --- Получаем масштаб интерфейса из parent.settings, если есть ---
        scale = None
        settings_obj = None

        # Пытаемся получить объект settings
        if parent is not None:
            if hasattr(parent, "settings"):
                settings_obj = parent.settings
            elif hasattr(parent, "parent_window") and hasattr(
                parent.parent_window, "settings"
            ):
                # Если parent - это SettingsDialog, берем settings из parent_window
                settings_obj = parent.parent_window.settings

        if settings_obj and settings_obj.get("scale"):
            scale = settings_obj.get("scale")
        if not scale:
            qset = QSettings("MyTradeTools", "TF-Alerter")
            scale = qset.value("interface_scale_text", "100%")
        try:
            value = int(str(scale).replace("%", ""))
            value = max(100, value)
            factor = value / 100.0
        except Exception:
            factor = 1.0

        def s(px):
            return max(1, int(px * factor))

        lang_code = "ru"
        if settings_obj:
            lang_code = settings_obj.get("lang", "ru")
        self.current_lang = "EN" if lang_code == "en" else "RU"
        self.t = self.translations[self.current_lang]
        self.setWindowTitle(self.t["title"])

        # Размер окна зависит от масштаба интерфейса
        base_w, base_h = 420, 480
        self.setFixedSize(s(base_w), s(base_h))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Главный контейнер
        main_container = QFrame(self)
        main_container.setStyleSheet(
            f"""
            QFrame {{
                background-color: {config.COLORS['background']};
                border: 2px solid {config.COLORS['border']};
                border-radius: 10px;
            }}
        """
        )
        main_container.setGeometry(0, 0, s(420), s(480))

        layout = QVBoxLayout(main_container)
        layout.setContentsMargins(s(25), s(15), s(25), s(20))
        layout.setSpacing(s(8))

        # Заголовок с кнопкой закрытия
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(s(28), s(28))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {config.COLORS['text']};
                border: none;
                font-size: {s(16)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: transparent;
                color: #ff4d4d;
            }}
        """
        )
        header_layout.addWidget(close_btn)
        layout.addLayout(header_layout)

        # Заголовок с логотипом
        title_layout = QHBoxLayout()
        title_layout.setSpacing(s(10))
        title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_label = QLabel()
        from PyQt6.QtGui import QPixmap

        logo_pix = QPixmap(config.LOGO_PATH).scaled(
            s(40),
            s(40),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        logo_label.setPixmap(logo_pix)
        logo_label.setStyleSheet("background: transparent; border: none;")
        title_layout.addWidget(logo_label)

        title = QLabel("RiskVolume")
        title.setStyleSheet(
            f"""
            color: #38BE1D;
            font-size: {s(22)}px;
            font-weight: bold;
            font-style: italic;
            border: none;
        """
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)

        layout.addLayout(title_layout)

        # Версия
        version = QLabel(self.t["version"])
        version.setStyleSheet(
            f"color: {config.COLORS['text']}; font-size: {s(11)}px; border: none;"
        )
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        # небольшое разделение между версией и описанием
        layout.addSpacing(4)

        # Краткое описание программы
        description = QLabel(self.t["description"])
        description.setStyleSheet(
            f"""
            color: {config.COLORS['text']};
            font-size: {s(12)}px;
            border: none;
            background: transparent;
        """
        )
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        layout.addWidget(description)

        # убираем лишние отступы перед блоком разработчика
        # (ранее использовался отрицательный отступ)

        # Разработчик (в контейнере с нулевыми отступами, чтобы убрать пустое пространство)
        dev_container = QWidget()
        dev_container.setStyleSheet("background: transparent;")
        dev_layout = QHBoxLayout(dev_container)
        dev_layout.setContentsMargins(0, 0, 0, 0)
        dev_layout.setSpacing(s(8))
        dev_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dev_label = QLabel(self.t["developer"])
        dev_label.setStyleSheet(
            f"color: #888; font-size: {s(11)}px; border: none; background: transparent;"
        )
        dev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_layout.addWidget(dev_label)

        dev_name = QLabel(config.AUTHOR_NAME)
        dev_name.setStyleSheet(
            f"""
            color: {config.COLORS['text']};
            font-size: {s(14)}px;
            font-weight: bold;
            border: none;
            background: transparent;
        """
        )
        dev_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_layout.addWidget(dev_name)

        layout.addWidget(dev_container)

        layout.addSpacing(6)

        # Кнопка YouTube
        youtube_btn = QPushButton(self.t["youtube_btn"])
        youtube_btn.setFixedHeight(s(38))
        youtube_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        youtube_btn.clicked.connect(self.open_smart_link)
        youtube_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #1565C0;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px;
                font-size: {s(13)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #0D47A1;
            }}
        """
        )
        layout.addWidget(youtube_btn)

        # Для перетаскивания
        self.old_pos = None

    def open_smart_link(self):
        """Открывает smart-link в браузере"""
        main_window = None
        parent = self.parent()
        if parent is not None:
            if hasattr(parent, "parent_window") and parent.parent_window is not None:
                main_window = parent.parent_window
            else:
                main_window = parent

        if main_window is not None and hasattr(main_window, "showMinimized"):
            try:
                main_window.showMinimized()
            except Exception:
                pass

        self.close()
        QDesktopServices.openUrl(QUrl("https://linktr.ee/intronaft"))

    def mousePressEvent(self, event):
        """Начало перетаскивания окна"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        """Перетаскивание окна"""
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        """Окончание перетаскивания"""
        self.old_pos = None
