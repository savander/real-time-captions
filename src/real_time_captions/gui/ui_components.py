from typing import Optional

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QEnterEvent, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QPushButton

from . import config


class ToastLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background-color: rgba(0, 0, 0, 200); color: white; border-radius: 8px; padding: 6px 12px; font-size: 14px; font-weight: bold;"
        )
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, duration: int = 1500):
        self.setText(text)
        self.adjustSize()

        parent = self.parentWidget()

        if parent is not None:
            parent_rect = parent.rect()
            self.move(
                parent_rect.center().x() - self.width() // 2,
                parent_rect.center().y() - self.height() // 2,
            )

        self.show()
        self.raise_()
        self._timer.start(duration)


class BaseModernButton(QPushButton):
    def __init__(self, hover_color: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(config.BUTTON_SIZE, config.BUTTON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_hovered = False
        self._hover_color = QColor(hover_color)
        self._base_color = QColor(255, 255, 255, 40)

    def enterEvent(self, event: Optional[QEnterEvent]):
        self._is_hovered = True
        self.update()
        if event:
            super().enterEvent(event)

    def leaveEvent(self, a0: Optional[QEvent]):
        self._is_hovered = False
        self.update()
        if a0:
            super().leaveEvent(a0)

    def paintEvent(self, a0):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(
            QBrush(self._hover_color if self._is_hovered else self._base_color)
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect())
        painter.setPen(
            QPen(QColor("white"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        self.draw_icon(painter)

    def draw_icon(self, painter: QPainter):
        pass


class CloseButton(BaseModernButton):
    def __init__(self, parent=None):
        super().__init__(config.CLOSE_BUTTON_HOVER_COLOR, parent)

    def draw_icon(self, painter: QPainter):
        c, o = self.rect().center(), 5
        painter.drawLine(c.x() - o, c.y() - o, c.x() + o, c.y() + o)
        painter.drawLine(c.x() + o, c.y() - o, c.x() - o, c.y() + o)


class ClearButton(BaseModernButton):
    def __init__(self, parent=None):
        super().__init__(config.CLEAR_BUTTON_HOVER_COLOR, parent)

    def draw_icon(self, painter: QPainter):
        cx, cy = self.width() // 2, self.height() // 2
        painter.setPen(QPen(QColor("white"), 1.5))
        painter.drawLine(cx - 5, cy - 4, cx + 5, cy - 4)
        painter.drawRect(cx - 4, cy - 4, 8, 9)
