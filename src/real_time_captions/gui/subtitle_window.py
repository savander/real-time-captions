import json
import logging
import sys
from typing import Optional

from PyQt6.QtCore import QEvent, QPoint, QRectF, Qt
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QEnterEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QSizeGrip, QWidget

from . import config
from .subtitle_display_widget import SubtitleDisplayWidget
from .ui_components import ClearButton, CloseButton, ToastLabel
from .window_flasher import WindowFlasher
from .worker import WorkerThread

logger = logging.getLogger(__name__)


class SubtitleWindow(QMainWindow):
    def __init__(
        self,
        language: Optional[str],
        model_size_override: Optional[str] = None,
        force_cpu: bool = False,
        max_cpu_ram_gb: Optional[int] = None,
    ):
        super().__init__()
        self._drag_start_position: Optional[QPoint] = None
        self._is_hovered = False
        self._font_size = config.DEFAULT_FONT_SIZE
        self._max_batches = config.DEFAULT_MAX_BATCHES
        self._bg_opacity = config.DEFAULT_BG_OPACITY

        self._model_size_override = model_size_override
        self._force_cpu = force_cpu
        self._max_cpu_ram_gb = max_cpu_ram_gb

        self._window_flasher = WindowFlasher(
            self, flash_duration_ms=3000, flicker_interval_ms=300
        )

        self._init_ui()
        self._load_window_state()

        initial_message = "Initializing program..."
        self._status_label.setText(initial_message)
        self._status_label.adjustSize()
        self._status_label.move(
            (self.width() - self._status_label.width()) // 2,
            (self.height() - self._status_label.height()) // 2,
        )
        self._status_label.show()

        self._start_worker(language)

        self._window_flasher.start_flicker_effect()

    def _init_ui(self):
        self.setWindowTitle("Auto Captions Overlay")
        self.resize(*config.DEFAULT_SIZE)
        self.setMinimumSize(300, 80)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._container = QWidget()
        self.setCentralWidget(self._container)

        self._subtitle_display = SubtitleDisplayWidget(self, self._container)

        self._size_grip = QSizeGrip(self)
        self._size_grip.setFixedSize(20, 20)
        self._size_grip.hide()

        self._close_btn = CloseButton(self)
        self._close_btn.clicked.connect(self.close)
        self._close_btn.hide()

        self._clear_btn = ClearButton(self)
        self._clear_btn.clicked.connect(self._clear_text)
        self._clear_btn.hide()

        self._status_label = QLabel(self._container)
        self._default_status_stylesheet = "color: #90A4AE; background: transparent; font-weight: bold; font-size: 18px;"
        self._status_label.setStyleSheet(self._default_status_stylesheet)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.hide()

        self._toast = ToastLabel(self)

    def _start_worker(self, language: Optional[str]):
        cmd = [sys.executable, "-m", config.MODULE_NAME, "--worker"]
        if language:
            cmd.extend(["--language", language])
        if self._model_size_override:
            cmd.extend(["--model-size", self._model_size_override])
        if self._force_cpu:
            cmd.append("--cpu")
        if self._max_cpu_ram_gb is not None:
            cmd.extend(["--max-cpu-ram-gb", str(self._max_cpu_ram_gb)])
        self._worker = WorkerThread(cmd)
        self._worker.text_received.connect(self._on_text_received)
        self._worker.status_received.connect(self._on_status_received)
        self._worker.error_received.connect(self._on_error_received)
        self._worker.log_received.connect(self._on_log_received)
        self._worker.start()

    def _load_window_state(self):
        if not config.CONFIG_FILE.exists():
            return
        try:
            with open(config.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("x") is not None:
                    self.move(data["x"], data["y"])
                if data.get("w") is not None:
                    self.resize(data["w"], data["h"])
                self._font_size = data.get("font_size", self._font_size)
                self._max_batches = data.get("max_batches", self._max_batches)
                self._bg_opacity = data.get("bg_opacity", self._bg_opacity)

            self._subtitle_display.update_settings(
                self._font_size, self._max_batches, self._bg_opacity
            )
        except Exception as e:
            logger.warning(f"Error loading state: {e}")

    def _save_window_state(self):
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "x": self.pos().x(),
            "y": self.pos().y(),
            "w": self.width(),
            "h": self.height(),
            "font_size": self._font_size,
            "max_batches": self._max_batches,
            "bg_opacity": self._bg_opacity,
        }
        with open(config.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _clear_text(self):
        self._subtitle_display.clear_text()
        self._toast.show_message("Cleared")

    def paintEvent(self, a0: Optional[QEvent]):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._window_flasher.draw_background(
            painter, QRectF(self.rect()), self._bg_opacity
        )

        if self._is_hovered:
            pen = QPen(QColor(255, 255, 255, 60))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)

    def enterEvent(self, event: Optional[QEnterEvent]):
        self._is_hovered = True
        self._close_btn.show()
        self._clear_btn.show()
        self._size_grip.show()
        self.update()

    def leaveEvent(self, a0: Optional[QEvent]):
        self._is_hovered = False
        self._close_btn.hide()
        self._clear_btn.hide()
        self._size_grip.hide()
        self.update()

    def resizeEvent(self, a0: Optional[QResizeEvent]):
        super().resizeEvent(a0)
        self._close_btn.move(self.width() - 35, 10)
        self._clear_btn.move(self.width() - 70, 10)
        self._size_grip.move(self.width() - 20, self.height() - 20)
        self.reposition_subtitle_display()

    def wheelEvent(self, a0: Optional[QWheelEvent]):
        if a0 is None:
            return
        delta = a0.angleDelta().y()
        modifiers = QApplication.keyboardModifiers()

        if modifiers == Qt.KeyboardModifier.ControlModifier:
            self._bg_opacity = max(
                1, min(self._bg_opacity + (15 if delta > 0 else -15), 255)
            )
            self._toast.show_message(f"Bg: {int((self._bg_opacity / 255) * 100)}%")
        elif modifiers == Qt.KeyboardModifier.ShiftModifier:
            self._max_batches = max(
                1, min(self._max_batches + (1 if delta > 0 else -1), 10)
            )
            self._toast.show_message(f"Segments: {self._max_batches}")
        else:
            self._font_size = max(
                10, min(self._font_size + (2 if delta > 0 else -2), 100)
            )
            self._toast.show_message(f"Size: {self._font_size}px")

        self._subtitle_display.update_settings(
            self._font_size, self._max_batches, self._bg_opacity
        )
        self.update()
        a0.accept()

    def mousePressEvent(self, a0: Optional[QMouseEvent]):
        if (
            a0
            and a0.button() == Qt.MouseButton.LeftButton
            and not self._size_grip.underMouse()
        ):
            self._drag_start_position = a0.globalPosition().toPoint()

    def mouseMoveEvent(self, a0: Optional[QMouseEvent]):
        if a0 and self._drag_start_position is not None:
            delta = a0.globalPosition().toPoint() - self._drag_start_position
            self.move(self.pos() + delta)
            self._drag_start_position = a0.globalPosition().toPoint()

    def mouseReleaseEvent(self, a0: Optional[QMouseEvent]):
        self._drag_start_position = None

    def closeEvent(self, a0: Optional[QCloseEvent]):
        self._save_window_state()
        self._worker.stop()
        if a0:
            a0.accept()

    def _on_status_received(self, msg: str):
        if (
            not self._subtitle_display._segments
            and not self._subtitle_display._pending_words
        ):
            self._status_label.setText(msg)
            self._status_label.adjustSize()
            self._status_label.move(
                (self.width() - self._status_label.width()) // 2,
                (self.height() - self._status_label.height()) // 2,
            )
            self._status_label.show()
        else:
            self._status_label.hide()

    def _on_error_received(self, msg: str):
        self._status_label.hide()
        self._subtitle_display.setText(
            f'<span style="color: #FF5252;">Error: {msg}</span>'
        )
        self.reposition_subtitle_display()

    def _on_text_received(self, new_text: str):
        self._status_label.hide()
        self._subtitle_display.receive_new_text(new_text)

    def _on_log_received(self, log_data: dict):
        level_name = log_data.get("level", "INFO").upper()
        log_message = log_data.get("message", "No message provided.")
        log_name = log_data.get("name", "worker")
        level_int = getattr(logging, level_name, logging.INFO)
        logger.log(level_int, f"Worker [{log_name}]: {log_message}")

    def reposition_subtitle_display(self):
        self._subtitle_display.reposition_label(self.width(), self.height())
