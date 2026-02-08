import logging
import math
import time
from collections import deque
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QTextDocument
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

from . import config

if TYPE_CHECKING:
    from .subtitle_window import SubtitleWindow

logger = logging.getLogger(__name__)


class SubtitleDisplayWidget(QLabel):
    def __init__(
        self, main_window_parent: "SubtitleWindow", parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self._main_window_parent = main_window_parent
        self._segments: list[config.WordSegment] = []
        self._pending_words: deque[tuple[str, int]] = deque()
        self._last_update_time = time.time()
        self._current_batch_id = 0

        self._font_size = config.DEFAULT_FONT_SIZE
        self._max_batches = config.DEFAULT_MAX_BATCHES
        self._bg_opacity = config.DEFAULT_BG_OPACITY

        self.setStyleSheet("color: white; background: transparent;")
        self.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        self.setWordWrap(True)
        self.setContentsMargins(0, 0, 0, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setOffset(2, 2)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)

        self._update_font()

        self._word_timer = QTimer(self)
        self._word_timer.timeout.connect(self._process_next_word)
        self._word_timer.start(100)

    def update_settings(self, font_size: int, max_batches: int, bg_opacity: int):
        self._font_size = font_size
        self._max_batches = max_batches
        self._bg_opacity = bg_opacity
        self._update_font()
        self._update_display()

    def _update_font(self):
        self.setFont(QFont(config.FONT_FAMILY, self._font_size, QFont.Weight.Bold))

    def clear_text(self):
        self._segments.clear()
        self._pending_words.clear()
        self.setText("")
        self._main_window_parent.reposition_subtitle_display()

    def receive_new_text(self, new_text: str):
        current_time = time.time()
        if current_time - self._last_update_time > config.TEXT_TIMEOUT_SECONDS:
            self._segments.clear()
            self._pending_words.clear()
            self._current_batch_id = 0

        self._current_batch_id += 1
        for word in new_text.split():
            self._pending_words.append((word, self._current_batch_id))
        self._last_update_time = current_time

    def _process_next_word(self):
        if not self._pending_words:
            return
        word, b_id = self._pending_words.popleft()
        self._segments.append({"text": word, "batch_id": b_id})
        self._update_display()

    def reposition_label(self, window_width: int, window_height: int):
        margin_side = 15
        margin_bottom = 20
        available_width = window_width - (margin_side * 2)

        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(self.font())
        doc.setTextWidth(float(available_width))
        doc.setHtml(self.text())

        h = math.ceil(doc.size().height()) + 15

        self.setFixedSize(available_width, h)

        new_y = window_height - h - margin_bottom
        self.move(margin_side, new_y)

    def _update_display(self):
        unique_batches = sorted(
            list(set(s["batch_id"] for s in self._segments)), reverse=True
        )
        kept_batches = unique_batches[: self._max_batches]

        if kept_batches:
            oldest = kept_batches[-1]
            while self._segments and self._segments[0]["batch_id"] < oldest:
                self._segments.pop(0)

        if not self._segments:
            self.setText("")
            self._main_window_parent.reposition_subtitle_display()
            return

        newest_id = unique_batches[0]
        grouped = []
        cur_group, cur_id = [], -1
        for s in self._segments:
            if s["batch_id"] != cur_id:
                if cur_group:
                    grouped.append((cur_id, cur_group))
                cur_group, cur_id = [s["text"]], s["batch_id"]
            else:
                cur_group.append(s["text"])
        if cur_group:
            grouped.append((cur_id, cur_group))

        batch_age_map = {b_id: i for i, b_id in enumerate(unique_batches)}
        html_lines = []
        for b_id, words in grouped:
            age = batch_age_map.get(b_id, 0)
            color = config.TEXT_GRADIENT[min(age, len(config.TEXT_GRADIENT) - 1)]
            weight = "800" if b_id == newest_id else "normal"
            scaled_size = int(self._font_size * (0.9**age))
            prefix = (
                '<span style="color: #FFAB40;">➤</span> ' if b_id == newest_id else ""
            )

            html_lines.append(
                f'<div style="margin: 0; margin-bottom: 2px; font-size: {scaled_size}pt;">'
                f'{prefix}<span style="color: {color}; font-weight: {weight};">{" ".join(words)}</span>'
                f"</div>"
            )

        self.setText("".join(html_lines))
        self._main_window_parent.reposition_subtitle_display()
