"""Ô "Gõ tiếng Việt → English" (tab trong cửa sổ chính): tự dịch khi ngừng gõ, Enter để copy."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from . import theme
from .widgets import ToggleSwitch, keycap, label

from ..text_translate import TextTranslateService

DEBOUNCE_MS = 600


class _InputEdit(QPlainTextEdit):
    submitted = Signal()
    escaped = Signal()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            e.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            return
        if e.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(e)


class ComposeWidget(QWidget):
    copied = Signal(str, bool)  # bản tiếng Anh, có ẩn cửa sổ sau khi copy không
    escaped = Signal()
    hide_after_copy_changed = Signal(bool)

    def __init__(self, service: TextTranslateService, hide_after_copy: bool, hotkey: str):
        super().__init__()
        self._service = service
        self._latest_id = 0
        self._translated_for: str | None = None
        self._copy_pending = False

        self.input = _InputEdit()
        self.input.setFont(theme.font("body", 12.5))
        self.input.setStyleSheet(f"color: {theme.TARGET};")
        self.input.setPlaceholderText("Gõ tiếng Việt ở đây…")
        self.output = QPlainTextEdit()
        self.output.setFont(theme.font("body", 12.5))
        self.output.setStyleSheet(f"color: {theme.SOURCE};")
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Bản tiếng Anh hiện ở đây")
        self.status = label("", "muted", theme.font("body", 9))
        self.chk_hide = ToggleSwitch(hide_after_copy)
        self.chk_hide.toggled.connect(self.hide_after_copy_changed)
        btn_copy = QPushButton("  Copy bản tiếng Anh")
        btn_copy.setObjectName("primary")
        btn_copy.setIcon(theme.glyph_icon(theme.G_COPY, "#1C1405", 14))
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self.submit)

        in_header = QHBoxLayout()
        in_header.addWidget(label("VI", "chipTarget"))
        in_header.addWidget(label("Tiếng Việt", f=theme.font("body", 10, QFont.Weight.DemiBold)))
        in_header.addStretch()
        out_header = QHBoxLayout()
        out_header.addWidget(label("EN", "chipSource"))
        out_header.addWidget(label("English", f=theme.font("body", 10, QFont.Weight.DemiBold)))
        out_header.addStretch()
        out_header.addWidget(self.status)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(self.chk_hide)
        bottom.addWidget(label("Copy xong thì xoá chữ và ẩn cửa sổ"))
        bottom.addStretch()
        bottom.addWidget(btn_copy)

        hints = QHBoxLayout()
        hints.setSpacing(6)
        for key, what in ((hotkey, "mở nhanh"), ("Enter", "copy"), ("Shift+Enter", "xuống dòng"), ("Esc", "ẩn")):
            hints.addWidget(keycap(key))
            hints.addWidget(label(what, "muted", theme.font("body", 8.5)))
            hints.addSpacing(10)
        hints.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(in_header)
        layout.addWidget(self.input, 1)
        layout.addSpacing(6)
        layout.addLayout(out_header)
        layout.addWidget(self.output, 1)
        layout.addSpacing(4)
        layout.addLayout(bottom)
        layout.addLayout(hints)

        self._timer = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._timer.timeout.connect(self._request)
        self.input.textChanged.connect(self._on_text_changed)
        self.input.submitted.connect(self.submit)
        self.input.escaped.connect(self.escaped)
        service.finished.connect(self._on_finished)
        service.failed.connect(self._on_failed)

    # ------------------------------------------------------------------ API
    def focus_input(self) -> None:
        self.input.setFocus()

    def current_text(self) -> str:
        return self.input.toPlainText().strip()

    def submit(self) -> None:
        text = self.current_text()
        if not text:
            return
        if text == self._translated_for:
            self._copy()
        else:
            self._copy_pending = True
            self._timer.stop()
            self._request()

    # ------------------------------------------------------------ internals
    def _on_text_changed(self) -> None:
        if self.current_text() != self._translated_for:
            self.status.setText("…")
        self._timer.start()

    def _request(self) -> None:
        text = self.current_text()
        if not text:
            self.output.clear()
            self._translated_for = ""
            self.status.clear()
            return
        if text == self._translated_for:
            return
        self._latest_id = self._service.request(text)
        self.status.setText("Đang dịch…")

    def _on_finished(self, req_id: int, src: str, out: str) -> None:
        if req_id != self._latest_id:
            return
        self.output.setPlainText(out)
        self._translated_for = src
        self.status.setText("✓")
        if self._copy_pending and src == self.current_text():
            self._copy_pending = False
            self._copy()

    def _on_failed(self, req_id: int, message: str) -> None:
        if req_id == self._latest_id:
            self._copy_pending = False
            self.status.setText(message)

    def _copy(self) -> None:
        english = self.output.toPlainText().strip()
        if not english:
            return
        QGuiApplication.clipboard().setText(english)
        hide = self.chk_hide.isChecked()
        if hide:
            self.input.clear()
            self.output.clear()
            self._translated_for = None
            self.status.clear()
        else:
            self.status.setText("Đã copy ✓  (Ctrl+V để dán)")
        self.copied.emit(english, hide)
