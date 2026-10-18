"""Icon khay hệ thống + menu (dùng chung cho chuột phải trên overlay)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..config import HotkeyConfig
from .icon import make_icon

SOURCES = [("loopback", "Loa hệ thống"), ("mic", "Micro"), ("both", "Cả hai")]
FONT_SIZES = [("small", "Nhỏ"), ("medium", "Vừa"), ("large", "Lớn")]
QUALITIES = [
    ("auto", "Tự động theo máy"),
    ("accurate", "Chính xác nhất (Whisper small + NLLB 1.3B)"),
    ("balanced", "Cân bằng (Whisper small + NLLB 600M)"),
    ("fast", "Nhanh — máy yếu (Whisper base + NLLB 600M)"),
]


class Tray(QObject):
    open_requested = Signal()
    toggle_requested = Signal()
    source_selected = Signal(str)
    overlay_toggle_requested = Signal()
    font_size_selected = Signal(str)
    quality_selected = Signal(str)
    tts_toggled = Signal(bool)
    compose_requested = Signal()
    retry_requested = Signal()
    quit_requested = Signal()

    def __init__(self, source_mode: str, font_size: str, quality: str, hotkeys: HotkeyConfig):
        super().__init__()
        self._hk = hotkeys
        self._icons = {True: make_icon(True), False: make_icon(False)}
        self.icon = QSystemTrayIcon(self._icons[False])
        self.menu = QMenu()

        act_open = self.menu.addAction("Mở cửa sổ LiveTrans")
        font = act_open.font()
        font.setBold(True)
        act_open.setFont(font)
        act_open.triggered.connect(self.open_requested)
        self.menu.addSeparator()

        self.act_toggle = self.menu.addAction("")
        self.act_toggle.triggered.connect(self.toggle_requested)

        src_menu = self.menu.addMenu(f"Nguồn âm thanh\t{hotkeys.source}")
        self._src_actions = self._radio_group(src_menu, SOURCES, source_mode, self.source_selected)

        self.act_overlay = self.menu.addAction("")
        self.act_overlay.triggered.connect(self.overlay_toggle_requested)

        self.act_tts = self.menu.addAction(f"Đọc to bản dịch\t{hotkeys.speak}")
        self.act_tts.setCheckable(True)
        self.act_tts.toggled.connect(self.tts_toggled)

        font_menu = self.menu.addMenu("Cỡ chữ")
        self._font_actions = self._radio_group(font_menu, FONT_SIZES, font_size, self.font_size_selected)

        quality_menu = self.menu.addMenu("Chất lượng dịch")
        self._quality_actions = self._radio_group(quality_menu, QUALITIES, quality, self.quality_selected)

        self.menu.addSeparator()
        act_compose = self.menu.addAction(f"Gõ tiếng Việt → English…\t{hotkeys.compose}")
        act_compose.triggered.connect(self.compose_requested)

        self.act_retry = self.menu.addAction("Thử lại tải model")
        self.act_retry.triggered.connect(self.retry_requested)
        self.act_retry.setVisible(False)

        self.menu.addSeparator()
        self.menu.addAction("Thoát").triggered.connect(self.quit_requested)

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self.set_running(False)
        self.set_overlay_visible(True)
        self.set_status("Đang khởi động…")

    def _radio_group(self, menu: QMenu, items, current: str, signal) -> dict[str, QAction]:
        group = QActionGroup(menu)
        group.setExclusive(True)
        actions = {}
        for key, text in items:
            act = menu.addAction(text)
            act.setCheckable(True)
            act.setChecked(key == current)
            act.triggered.connect(lambda checked=False, k=key: signal.emit(k))
            group.addAction(act)
            actions[key] = act
        return actions

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_requested.emit()

    # ------------------------------------------------------------------ API
    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def set_running(self, running: bool) -> None:
        self.icon.setIcon(self._icons[running])
        label = "Tạm dừng dịch" if running else "Bắt đầu dịch"
        self.act_toggle.setText(f"{label}\t{self._hk.toggle}")

    def set_status(self, text: str) -> None:
        self.icon.setToolTip(f"LiveTrans — {text}")

    def set_source(self, mode: str) -> None:
        if mode in self._src_actions:
            self._src_actions[mode].setChecked(True)

    def set_font_size(self, size: str) -> None:
        if size in self._font_actions:
            self._font_actions[size].setChecked(True)

    def set_tts_enabled(self, enabled: bool) -> None:
        self.act_tts.blockSignals(True)
        self.act_tts.setChecked(enabled)
        self.act_tts.blockSignals(False)

    def set_quality(self, quality: str) -> None:
        if quality in self._quality_actions:
            self._quality_actions[quality].setChecked(True)

    def set_overlay_visible(self, visible: bool) -> None:
        label = "Ẩn phụ đề" if visible else "Hiện phụ đề"
        self.act_overlay.setText(f"{label}\t{self._hk.overlay}")

    def set_retry_visible(self, visible: bool) -> None:
        self.act_retry.setVisible(visible)

    def notify(self, title: str, message: str) -> None:
        self.icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
