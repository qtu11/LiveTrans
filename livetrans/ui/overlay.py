"""Cửa sổ phụ đề: không viền, nền đen bán trong suốt, luôn nổi, kéo thả được."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget

from ..audio_capture import SOURCE_LABELS

FONT_PT = {"small": 18, "medium": 24, "large": 32}
IDLE_FADE_MS = 8000
STATUS_MS = 4000
MAX_ENTRIES = 2


@dataclass
class _Entry:
    source: str
    seg_id: int
    lang: str
    text: str
    translation: str


def _label(color: str) -> QLabel:
    lb = QLabel()
    lb.setWordWrap(True)
    lb.setTextFormat(Qt.TextFormat.PlainText)
    lb.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    lb.setStyleSheet(f"color: {color}; background: transparent;")
    return lb


class Overlay(QWidget):
    menu_requested = Signal(QPoint)
    moved = Signal(int, int)  # x, bottom

    def __init__(
        self,
        font_size: str = "medium",
        width_ratio: float = 0.6,
        pos: list[int] | None = None,
        autohide: bool = False,
    ):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("LiveTrans")

        self._entries: deque[_Entry] = deque(maxlen=MAX_ENTRIES)
        self._partial: tuple[str, int, str, str] | None = None  # source, seg_id, text, bản dịch tạm
        self._status = ""
        self._show_source = False
        self._user_visible = True
        self._autohide = autohide
        self._drag_offset: QPoint | None = None
        self._hovered = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 14)
        layout.setSpacing(2)
        self._status_label = _label("#FFB547")  # hổ phách (đèn ON AIR)
        layout.addWidget(self._status_label)
        self._rows: list[tuple[QLabel, QLabel]] = []
        for i in range(MAX_ENTRIES):
            orig, trans = _label("#9DB8E0"), _label("#FFF1D6")  # câu gốc xanh lạnh, tiếng Việt kem sáng
            if i > 0:
                orig.setContentsMargins(0, 8, 0, 0)
            shadow = QGraphicsDropShadowEffect(trans)
            shadow.setBlurRadius(8)
            shadow.setOffset(1, 1)
            shadow.setColor(QColor(0, 0, 0, 230))
            trans.setGraphicsEffect(shadow)
            layout.addWidget(orig)
            layout.addWidget(trans)
            self._rows.append((orig, trans))
        self._partial_label = _label("#7F93B5")
        self._partial_label.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self._partial_label)
        self._partial_trans_label = _label("#D9C9A8")
        layout.addWidget(self._partial_trans_label)

        self._fade_timer = QTimer(self, singleShot=True, interval=IDLE_FADE_MS)
        self._fade_timer.timeout.connect(self._fade_out)
        self._status_timer = QTimer(self, singleShot=True, interval=STATUS_MS)
        self._status_timer.timeout.connect(self.clear_status)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._anim.finished.connect(self._on_fade_finished)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self._width = max(360, int(screen.width() * width_ratio))
        if pos:
            self._x, self._bottom = pos
        else:
            self._x = screen.x() + (screen.width() - self._width) // 2
            self._bottom = screen.y() + screen.height() - int(screen.height() * 0.08)
        self.setFixedWidth(self._width)
        self.set_font_size(font_size)

    # ------------------------------------------------------------------ API
    def show_final(self, source: str, seg_id: int, lang: str, text: str, translation: str) -> None:
        if self._partial and self._partial[0] == source and self._partial[1] <= seg_id:
            self._partial = None
        self._entries.append(_Entry(source, seg_id, lang, text, translation))
        self._render(new_content=True)

    def show_partial(self, source: str, seg_id: int, text: str, translation: str = "") -> None:
        if any(e.source == source and e.seg_id >= seg_id for e in self._entries):
            return  # đến muộn, đoạn này đã chốt
        if not translation and self._partial and self._partial[:2] == (source, seg_id) and self._partial[3]:
            translation = self._partial[3]  # giữ bản dịch tạm cũ cho tới khi có bản mới
        self._partial = (source, seg_id, text, translation)
        self._render(new_content=True)

    def drop_segment(self, source: str, seg_id: int) -> None:
        if self._partial and self._partial[0] == source and self._partial[1] == seg_id:
            self._partial = None
            self._render(new_content=False)

    def show_status(self, text: str, sticky: bool = False) -> None:
        self._status = text
        if sticky:
            self._status_timer.stop()
        else:
            self._status_timer.start()
        self._render(new_content=True)

    def clear_status(self) -> None:
        self._status_timer.stop()
        if self._status:
            self._status = ""
            self._render(new_content=False)

    def set_font_size(self, size: str) -> None:
        pt = FONT_PT.get(size, FONT_PT["medium"])
        small = max(11, round(pt * 0.58))
        trans_font = QFont("Segoe UI", pt)
        trans_font.setWeight(QFont.Weight.DemiBold)
        orig_font = QFont("Segoe UI", small)
        partial_font = QFont("Segoe UI", small + 1)
        partial_font.setItalic(True)
        partial_trans_font = QFont("Segoe UI", max(small + 2, round(pt * 0.8)))
        partial_trans_font.setItalic(True)
        for orig, trans in self._rows:
            orig.setFont(orig_font)
            trans.setFont(trans_font)
        self._partial_label.setFont(partial_font)
        self._partial_trans_label.setFont(partial_trans_font)
        self._status_label.setFont(QFont("Segoe UI", small))
        self._render(new_content=False)

    def set_source_labels(self, show: bool) -> None:
        self._show_source = show
        self._render(new_content=False)

    def set_autohide(self, autohide: bool) -> None:
        self._autohide = autohide
        if autohide:
            self._fade_timer.start()
        else:
            self._fade_timer.stop()
            self._anim.stop()
            self.setWindowOpacity(1.0)

    def clear(self) -> None:
        """Xoá phụ đề (khi tạm dừng dịch)."""
        self._entries.clear()
        self._partial = None
        self._render(new_content=False)

    def set_user_visible(self, visible: bool) -> None:
        self._user_visible = visible
        if not visible:
            self._anim.stop()
            self.hide()
        else:
            self.show_status("Phụ đề đang bật")

    def is_user_visible(self) -> bool:
        return self._user_visible

    def position(self) -> list[int]:
        return [self._x, self._bottom]

    # ------------------------------------------------------------- render
    def _tag(self, source: str, lang: str) -> str:
        tag = f"[{lang.upper()}]"
        if self._show_source:
            tag += f" [{SOURCE_LABELS.get(source, source)}]"
        return tag

    def _render(self, new_content: bool) -> None:
        self._status_label.setText(self._status)
        self._status_label.setVisible(bool(self._status))
        entries = list(self._entries)
        for i, (orig, trans) in enumerate(self._rows):
            if i >= len(entries):
                orig.hide()
                trans.hide()
                continue
            e = entries[i]
            tag = self._tag(e.source, e.lang)
            if e.lang == "vi":
                orig.setText(tag)
                trans.setText(e.text)
            elif e.translation:
                orig.setText(f"{tag} {e.text}")
                trans.setText(e.translation)
            else:  # ngôn ngữ chưa hỗ trợ dịch
                orig.setText(f"{tag} (chưa hỗ trợ dịch)")
                trans.setText(e.text)
            orig.show()
            trans.show()
        if self._partial:
            src, _, text, translation = self._partial
            prefix = f"[{SOURCE_LABELS.get(src, src)}] " if self._show_source else ""
            self._partial_label.setText(f"{prefix}{text} …")
            self._partial_label.show()
            if translation and translation != text:
                self._partial_trans_label.setText(f"{translation} …")
                self._partial_trans_label.show()
            else:
                self._partial_trans_label.hide()
        else:
            self._partial_label.hide()
            self._partial_trans_label.hide()

        has_content = bool(self._status or entries or self._partial)
        if not has_content or not self._user_visible:
            self.hide()
            return
        self._relayout()
        if new_content:
            self._anim.stop()
            self.setWindowOpacity(1.0)
            if self._autohide and not self._hovered:
                self._fade_timer.start()
        if not self.isVisible():
            self.show()

    def _relayout(self) -> None:
        layout = self.layout()
        layout.activate()
        h = layout.totalHeightForWidth(self._width) if layout.hasHeightForWidth() else layout.sizeHint().height()
        self.setGeometry(self._x, self._bottom - h, self._width, h)

    def _fade_out(self) -> None:
        if self._hovered or self._drag_offset is not None or not self.isVisible():
            return
        self._anim.stop()
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_fade_finished(self) -> None:
        if self.windowOpacity() <= 0.01:
            self._entries.clear()
            self._partial = None
            if not self._status_timer.isActive():
                self._status = ""
            self.hide()
            self.setWindowOpacity(1.0)

    # -------------------------------------------------------------- events
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(16, 20, 31, 225))  # xanh đêm, đủ đậm để không lẫn phụ đề có sẵn của video
        p.drawRoundedRect(self.rect(), 14, 14)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._fade_timer.stop()
        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
            self.setWindowOpacity(1.0)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        if self._autohide:
            self._fade_timer.start()

    def mousePressEvent(self, event) -> None:
        gp = event.globalPosition().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = gp - self.pos()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu_requested.emit(gp)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._x, self._bottom = self.x(), self.y() + self.height()
            self.moved.emit(self._x, self._bottom)
