from typing import Optional

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QMainWindow


class WindowFlasher:
    def __init__(
        self,
        target_window: QMainWindow,
        flash_duration_ms: int = 3000,
        flicker_interval_ms: int = 300,
    ):
        self._target_window = target_window
        self._flash_duration_ms = flash_duration_ms
        self._flicker_interval_ms = flicker_interval_ms

        self._is_flashing = False
        self._flash_timer: Optional[QTimer] = None
        self._flicker_timer: Optional[QTimer] = None

    def start_flicker_effect(self):
        self._is_flashing = True
        self._flash_timer = QTimer(self._target_window)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._stop_flicker_effect)
        self._flash_timer.start(self._flash_duration_ms)

        self._flicker_timer = QTimer(self._target_window)
        self._flicker_timer.timeout.connect(self._toggle_flicker)
        self._flicker_timer.start(self._flicker_interval_ms)
        self._target_window.update()

    def _toggle_flicker(self):
        self._is_flashing = not self._is_flashing
        self._target_window.update()

    def _stop_flicker_effect(self):
        if self._flicker_timer:
            self._flicker_timer.stop()
            self._flicker_timer = None
        self._is_flashing = False
        self._target_window.update()

    def is_flashing(self) -> bool:
        return self._is_flashing

    def draw_background(self, painter: QPainter, rect: QRectF, bg_opacity: int):
        if self._is_flashing:
            painter.setBrush(QColor(255, 255, 0, 255))
        else:
            painter.setBrush(QColor(0, 0, 0, bg_opacity))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 10, 10)
