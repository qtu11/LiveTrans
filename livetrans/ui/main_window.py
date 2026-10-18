"""Cửa sổ chính kiểu "cabin phiên dịch": thanh bên + các trang Trực tiếp / Gõ Việt → Anh / Lịch sử / Cài đặt."""

from __future__ import annotations

import ctypes
import html
import time
from collections import deque

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .compose import ComposeWidget
from .widgets import (
    ChannelTile,
    Combo,
    Segmented,
    SettingRow,
    TallyLamp,
    ToggleSwitch,
    card,
    eyebrow,
    glyph,
    keycap,
    label,
)
from ..config import Config, speed_of

SOURCES = [
    ("loopback", theme.G_LIVE, "Loa máy tính", "Video, phim, họp online"),
    ("mic", theme.G_MIC, "Micro", "Người nói trước máy"),
    ("both", theme.G_BOTH, "Cả hai", "Loa và micro cùng lúc"),
]
QUALITIES = [
    ("auto", "Tự động theo máy", "Theo lựa chọn lúc cài đặt, hoặc theo CPU/RAM của máy."),
    ("accurate", "Chính xác nhất", "Whisper small + NLLB 1.3B — dịch sát nghĩa nhất. Cần CPU từ 6 luồng."),
    ("balanced", "Cân bằng", "Whisper small + NLLB 600M — nhanh hơn ~0,5 giây mỗi câu."),
    ("fast", "Nhanh", "Whisper base + NLLB 600M — cho máy yếu; nhận dạng tiếng Nhật/Trung/Hàn kém hơn."),
]
SPEEDS = [("fast", "Nhanh · câu ≤ 5 giây"), ("standard", "Chuẩn · câu ≤ 8 giây")]
TTS_SPEEDS = [("slow", "Chậm"), ("normal", "Vừa"), ("fast", "Nhanh"), ("faster", "Rất nhanh")]
TTS_VOICES = [
    ("piper", "Piper · offline"),
    ("vi-VN-HoaiMyNeural", "HoaiMy · nữ · online"),
    ("vi-VN-NamMinhNeural", "NamMinh · nam · online"),
]
FONT_SIZES = [("small", "Nhỏ"), ("medium", "Vừa"), ("large", "Lớn")]
LANGUAGES = [
    ("auto", "Tự nhận diện"), ("en", "English"), ("ja", "日本語"), ("zh", "中文"), ("ko", "한국어"),
    ("fr", "Français"), ("de", "Deutsch"), ("es", "Español"), ("ru", "Русский"), ("th", "ไทย"),
    ("id", "Bahasa Indonesia"),
]
PAGES = [
    ("live", theme.G_LIVE, "Trực tiếp"),
    ("compose", theme.G_KEYBOARD, "Gõ Việt → Anh"),
    ("history", theme.G_HISTORY, "Lịch sử"),
    ("settings", theme.G_SETTINGS, "Cài đặt"),
]
HISTORY_MAX = 300


def _combo(items, current: str) -> QComboBox:
    box = Combo()
    for item in items:
        box.addItem(item[1], item[0])
    box.setCurrentIndex(max(0, box.findData(current)))
    return box


def _select(box: QComboBox, key: str) -> None:
    idx = box.findData(key)
    if idx >= 0 and idx != box.currentIndex():
        box.blockSignals(True)
        box.setCurrentIndex(idx)
        box.blockSignals(False)


def _page_header(title: str, caption: str) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(2)
    layout.addWidget(label(title, f=theme.font("display", 19, QFont.Weight.DemiBold)))
    layout.addWidget(label(caption, "muted", wrap=True))
    return layout


def _scroll(page: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidget(page)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    return area


class MainWindow(QWidget):
    toggle_requested = Signal()
    source_selected = Signal(str)
    quality_selected = Signal(str)
    speed_selected = Signal(str)
    overlay_visible_changed = Signal(bool)
    overlay_autohide_changed = Signal(bool)
    preview_changed = Signal(bool)
    font_size_selected = Signal(str)
    source_language_selected = Signal(str)
    autostart_changed = Signal(bool)
    tts_toggled = Signal(bool)
    tts_voice_selected = Signal(str)
    tts_speed_selected = Signal(str)
    tts_volume_changed = Signal(float)
    tts_test_requested = Signal()
    open_logs_requested = Signal()
    hidden_to_tray = Signal()
    quit_requested = Signal()

    def __init__(self, cfg: Config, compose: ComposeWidget, version: str,
                 autostart_supported: bool, autostart_enabled: bool):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(f"LiveTrans {version} — Phiên dịch thời gian thực")
        self.setFont(theme.font("body", 10))
        self.setStyleSheet(theme.STYLESHEET)
        self.resize(900, 760)
        self.setMinimumSize(780, 560)
        self.compose = compose
        self._timings: deque[float] = deque(maxlen=5)
        self._running = False
        self._timing_text = ""

        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {
            "live": _scroll(self._build_live(cfg)),
            "compose": self._build_compose(compose),
            "history": self._build_history(),
            "settings": _scroll(self._build_settings(cfg, autostart_supported, autostart_enabled)),
        }
        for w in self._pages.values():
            self.stack.addWidget(w)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar(version))
        root.addWidget(self.stack, 1)
        self.show_page("live")
        self.set_running(False)

    # ------------------------------------------------------------ sidebar
    def _build_sidebar(self, version: str) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(208)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        brand = QHBoxLayout()
        self.brand_lamp = TallyLamp(26)
        brand.addWidget(self.brand_lamp)
        name = QVBoxLayout()
        name.setSpacing(0)
        name.addWidget(label("LiveTrans", f=theme.font("display", 15, QFont.Weight.DemiBold)))
        name.addWidget(label("phiên dịch tại chỗ", "muted", theme.font("body", 8.5)))
        brand.addLayout(name, 1)
        layout.addLayout(brand)
        layout.addSpacing(18)

        self._nav = QButtonGroup(self)
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, g, text in PAGES:
            b = QPushButton(f"  {text}")
            b.setObjectName("nav")
            b.setIcon(theme.glyph_icon(g, theme.MUTED, 16))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # viền focus chỉ khi dùng bàn phím
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self._nav.addButton(b)
            self._nav_buttons[key] = b
            layout.addWidget(b)
        layout.addStretch()

        hide = QPushButton("  Ẩn xuống khay")
        hide.setObjectName("navQuiet")
        hide.setIcon(theme.glyph_icon(theme.G_HIDE, theme.MUTED, 14))
        hide.clicked.connect(self.hide_to_tray)
        quit_btn = QPushButton("  Thoát LiveTrans")
        quit_btn.setObjectName("navDanger")
        quit_btn.setIcon(theme.glyph_icon(theme.G_POWER, theme.MUTED, 14))
        quit_btn.clicked.connect(self.quit_requested)
        layout.addWidget(hide)
        layout.addWidget(quit_btn)
        layout.addSpacing(6)
        layout.addWidget(label(f"v{version} · chạy offline", "muted", theme.font("mono", 8)))
        return bar

    # --------------------------------------------------------------- live
    def _build_live(self, cfg: Config) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # Đầu trang: đèn ON AIR + trạng thái + nút bật/tắt
        head = QHBoxLayout()
        head.setSpacing(12)
        self.lamp = TallyLamp(38)
        head.addWidget(self.lamp, 0, Qt.AlignmentFlag.AlignTop)
        status = QVBoxLayout()
        status.setSpacing(0)
        self.status_title = label("Đang khởi động", f=theme.font("display", 22, QFont.Weight.DemiBold))
        self.status_meta = label("", "muted", theme.font("body", 9.5), wrap=True)
        status.addWidget(self.status_title)
        status.addWidget(self.status_meta)
        head.addLayout(status, 1)
        self.btn_toggle = QPushButton()
        self.btn_toggle.setMinimumSize(172, 46)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle_requested)
        head.addWidget(self.btn_toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(head)

        # Màn hình cabin: câu gốc (xanh lạnh) + bản dịch (kem ấm)
        monitor, mon = card("monitor")
        mon.setContentsMargins(22, 18, 22, 20)
        top = QHBoxLayout()
        self.monitor_eyebrow = eyebrow("Câu gần nhất")
        top.addWidget(self.monitor_eyebrow)
        top.addStretch()
        self.monitor_time = label("", "muted", theme.font("mono", 8.5))
        top.addWidget(self.monitor_time)
        mon.addLayout(top)
        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        self.monitor_lang = label("", "chipSource")
        self.monitor_lang.hide()
        self.monitor_source = label("Bản dịch hiện ở đây ngay khi có người nói.", "muted",
                                    theme.font("body", 11), wrap=True)
        src_row.addWidget(self.monitor_lang, 0, Qt.AlignmentFlag.AlignTop)
        src_row.addWidget(self.monitor_source, 1)
        mon.addLayout(src_row)
        self.monitor_target = label("", "target", theme.font("headline", 18, QFont.Weight.DemiBold), wrap=True)
        self.monitor_target.hide()
        mon.addWidget(self.monitor_target)
        layout.addWidget(monitor)

        # Kênh âm thanh
        layout.addWidget(eyebrow("Nghe từ"))
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self._src_group = QButtonGroup(self)
        self._src_tiles: dict[str, ChannelTile] = {}
        for key, g, title, caption in SOURCES:
            t = ChannelTile(g, title, caption)
            t.setChecked(key == cfg.source_mode)
            t._restyle(key == cfg.source_mode)
            t.clicked.connect(lambda _=False, k=key: self.source_selected.emit(k))
            self._src_group.addButton(t)
            self._src_tiles[key] = t
            tiles.addWidget(t)
        layout.addLayout(tiles)

        # Chất lượng + tốc độ phụ đề
        qcard, q = card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        grid.addWidget(eyebrow("Chất lượng dịch"), 0, 0)
        grid.addWidget(eyebrow("Tốc độ phụ đề"), 0, 1)
        self.quality_box = _combo(QUALITIES, cfg.quality)
        self.quality_box.currentIndexChanged.connect(self._on_quality_index)
        grid.addWidget(self.quality_box, 1, 0)
        self.speed_seg = Segmented(SPEEDS, speed_of(cfg.vad))
        self.speed_seg.changed.connect(self.speed_selected)
        grid.addWidget(self.speed_seg, 1, 1)
        self.quality_desc = label("", "muted", theme.font("body", 8.5), wrap=True)
        grid.addWidget(self.quality_desc, 2, 0)
        speed_desc = label("Nhanh: phụ đề hiện sớm. Chuẩn: câu dài hơn, đủ ngữ cảnh hơn.", "muted",
                           theme.font("body", 8.5), wrap=True)
        grid.addWidget(speed_desc, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        q.addLayout(grid)
        self._update_quality_desc()
        layout.addWidget(qcard)

        layout.addWidget(self._build_voice(cfg))
        layout.addStretch()
        return page

    def _build_voice(self, cfg: Config) -> QFrame:
        vcard, v = card()
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(glyph(theme.G_VOLUME, 20, theme.TARGET))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("Đọc to bản dịch tiếng Việt", f=theme.font("body", 10.5, QFont.Weight.DemiBold)))
        titles.addWidget(label("Lồng tiếng các câu nói tiếng nước ngoài sau khi dịch.", "muted",
                               theme.font("body", 8.5), wrap=True))
        head.addLayout(titles, 1)
        self.tts_state = label("", "chipAmber")
        self.tts_state.hide()
        head.addWidget(self.tts_state, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(keycap(cfg.hotkeys.speak), 0, Qt.AlignmentFlag.AlignVCenter)
        self.tts_switch = ToggleSwitch(cfg.tts_enabled)
        self.tts_switch.toggled.connect(self.tts_toggled)
        head.addWidget(self.tts_switch)
        v.addLayout(head)

        voices = QHBoxLayout()
        voices.setSpacing(10)
        voices.addWidget(label("Giọng", "muted"))
        self.tts_voice_seg = Segmented(TTS_VOICES, cfg.tts_voice)
        self.tts_voice_seg.changed.connect(self.tts_voice_selected)
        voices.addWidget(self.tts_voice_seg)
        voices.addStretch()
        v.addLayout(voices)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(label("Tốc độ đọc", "muted"))
        self.tts_speed_seg = Segmented(TTS_SPEEDS, cfg.tts_speed)
        self.tts_speed_seg.changed.connect(self.tts_speed_selected)
        row.addWidget(self.tts_speed_seg)
        row.addSpacing(10)
        row.addWidget(label("Âm lượng", "muted"))
        self.tts_volume = QSlider(Qt.Orientation.Horizontal)
        self.tts_volume.setRange(0, 100)
        self.tts_volume.setValue(round(cfg.tts_volume * 100))
        self.tts_volume.valueChanged.connect(lambda val: self.tts_volume_changed.emit(val / 100))
        row.addWidget(self.tts_volume, 1)
        test = QPushButton("  Nghe thử")
        test.setObjectName("ghost")
        test.setIcon(theme.glyph_icon(theme.G_PLAY, theme.TEXT, 13))
        test.clicked.connect(self.tts_test_requested)
        row.addWidget(test)
        v.addLayout(row)
        v.addWidget(label(
            "Giọng online (Microsoft) tự nhiên hơn nhưng cần Internet và gửi câu đã dịch (dạng chữ) tới Microsoft; "
            "khi không phản hồi, LiveTrans tạm đọc bằng giọng offline. Nguồn Loa tự bỏ qua giọng đọc của LiveTrans; "
            "dùng Micro thì nên đeo tai nghe.",
            "muted", theme.font("body", 8.5), wrap=True))
        return vcard

    # ------------------------------------------------------------ compose
    def _build_compose(self, compose: ComposeWidget) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)
        layout.addLayout(_page_header(
            "Gõ tiếng Việt → English",
            "Gõ tiếng Việt, bản tiếng Anh tự hiện khi bạn ngừng gõ. Nhấn Enter để copy rồi dán vào khung chat.",
        ))
        layout.addWidget(compose, 1)
        return page

    # ------------------------------------------------------------ history
    def _build_history(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)
        head = QHBoxLayout()
        head.addLayout(_page_header("Lịch sử", "Các câu đã dịch trong phiên này (tối đa 300 câu gần nhất)."), 1)
        btn_copy = QPushButton("  Copy tất cả")
        btn_copy.setObjectName("ghost")
        btn_copy.setIcon(theme.glyph_icon(theme.G_COPY, theme.TEXT, 13))
        btn_clear = QPushButton("  Xoá lịch sử")
        btn_clear.setObjectName("ghost")
        btn_clear.setIcon(theme.glyph_icon(theme.G_DELETE, theme.TEXT, 13))
        head.addWidget(btn_copy, 0, Qt.AlignmentFlag.AlignBottom)
        head.addWidget(btn_clear, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(head)
        self.history = QTextBrowser()
        self.history.setOpenLinks(False)
        self.history.document().setMaximumBlockCount(HISTORY_MAX)
        self.history.setPlaceholderText("Chưa có câu nào. Bấm Bắt đầu dịch ở trang Trực tiếp.")
        btn_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.history.toPlainText()))
        btn_clear.clicked.connect(self.history.clear)
        layout.addWidget(self.history, 1)
        return page

    # ----------------------------------------------------------- settings
    def _build_settings(self, cfg: Config, autostart_supported: bool, autostart_enabled: bool) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("Cài đặt", "Thay đổi được áp dụng ngay."))

        sub, s = card()
        s.addWidget(eyebrow("Phụ đề trên màn hình"))
        self.sw_overlay = ToggleSwitch(cfg.overlay_visible)
        self.sw_overlay.toggled.connect(self.overlay_visible_changed)
        s.addWidget(SettingRow("Hiện phụ đề", f"Phím tắt {cfg.hotkeys.overlay}. Kéo thanh phụ đề để đổi vị trí.",
                               self.sw_overlay))
        self.sw_preview = ToggleSwitch(cfg.translate_preview)
        self.sw_preview.toggled.connect(self.preview_changed)
        s.addWidget(SettingRow("Bản dịch tạm khi đang nói", "Dòng chữ nghiêng, cập nhật khoảng 1,5 giây một lần.",
                               self.sw_preview))
        self.sw_autohide = ToggleSwitch(cfg.overlay_autohide)
        self.sw_autohide.toggled.connect(self.overlay_autohide_changed)
        s.addWidget(SettingRow("Tự ẩn khi không ai nói", "Phụ đề mờ dần sau 8 giây im lặng.", self.sw_autohide))
        self.font_seg = Segmented(FONT_SIZES, cfg.font_size)
        self.font_seg.changed.connect(self.font_size_selected)
        s.addWidget(SettingRow("Cỡ chữ phụ đề", "", self.font_seg))
        layout.addWidget(sub)

        rec, r = card()
        r.addWidget(eyebrow("Nhận dạng giọng nói"))
        self.lang_box = _combo(LANGUAGES, cfg.source_language)
        self.lang_box.setMinimumWidth(180)
        self.lang_box.currentIndexChanged.connect(
            lambda _: self.source_language_selected.emit(self.lang_box.currentData())
        )
        r.addWidget(SettingRow("Ngôn ngữ người nói",
                               "Chọn đúng ngôn ngữ giúp nhận dạng chính xác và nhanh hơn một chút.", self.lang_box))
        layout.addWidget(rec)

        sysc, y = card()
        y.addWidget(eyebrow("Hệ thống"))
        self.sw_autostart = ToggleSwitch(autostart_enabled)
        self.sw_autostart.setEnabled(autostart_supported)
        self.sw_autostart.toggled.connect(self.autostart_changed)
        y.addWidget(SettingRow(
            "Tự chạy khi khởi động Windows",
            "LiveTrans chạy nền, không mở cửa sổ." if autostart_supported else "Chỉ có ở bản cài đặt.",
            self.sw_autostart,
        ))
        logs = QPushButton("  Mở thư mục log")
        logs.setObjectName("ghost")
        logs.setIcon(theme.glyph_icon(theme.G_FOLDER, theme.TEXT, 13))
        logs.clicked.connect(self.open_logs_requested)
        y.addWidget(SettingRow("Log", "Dùng khi cần báo lỗi.", logs))
        layout.addWidget(sysc)

        keys, k = card()
        k.addWidget(eyebrow("Phím tắt"))
        hk = cfg.hotkeys
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for i, (combo, what) in enumerate([
            (hk.toggle, "Bắt đầu / dừng dịch"), (hk.overlay, "Ẩn / hiện phụ đề"), (hk.source, "Đổi nguồn âm thanh"),
            (hk.compose, "Mở ô gõ Việt → Anh"), (hk.speak, "Bật / tắt giọng đọc"),
        ]):
            grid.addWidget(keycap(combo), i, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(label(what), i, 1)
        grid.setColumnStretch(1, 1)
        k.addLayout(grid)
        layout.addWidget(keys)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------ API
    def show_page(self, key: str) -> None:
        self.stack.setCurrentWidget(self._pages[key])
        for k, b in self._nav_buttons.items():
            b.setChecked(k == key)
            b.setIcon(theme.glyph_icon(dict((p[0], p[1]) for p in PAGES)[k],
                                       theme.AMBER if k == key else theme.MUTED, 16))

    def current_page(self) -> str:
        return next(k for k, w in self._pages.items() if w is self.stack.currentWidget())

    def bring_to_front(self, page: str | None = None) -> None:
        if page:
            self.show_page(page)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        if page == "compose":
            self.compose.focus_input()

    def hide_to_tray(self) -> None:
        self.hide()
        self.hidden_to_tray.emit()

    def set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self.btn_toggle.setText("  Dừng dịch")
            self.btn_toggle.setObjectName("danger")
            self.btn_toggle.setIcon(theme.glyph_icon(theme.G_STOP, theme.RED, 14))
        else:
            self.btn_toggle.setText("  Bắt đầu dịch")
            self.btn_toggle.setObjectName("primary")
            self.btn_toggle.setIcon(theme.glyph_icon(theme.G_PLAY, "#1C1405", 14))
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)

    def set_status(self, text: str) -> None:
        if text.startswith("Đang nghe"):
            title, meta, state = "Đang nghe", text.partition(":")[2].strip(), "live"
        elif text.startswith("Tạm dừng"):
            title, meta, state = "Đã dừng", "Bấm Bắt đầu dịch hoặc nhấn phím tắt để nghe tiếp.", "off"
        elif text.startswith("Lỗi") or "lỗi" in text:
            title, meta, state = "Có lỗi", text, "error"
        elif text.startswith("Đang"):
            title, meta, state = "Đang chuẩn bị", text, "loading"
        else:
            title, meta, state = text, "", "off"
        self.status_title.setText(title)
        self._status_meta = meta
        self._render_meta()
        self.lamp.set_state(state)
        self.brand_lamp.set_state(state)

    def _render_meta(self) -> None:
        parts = [p for p in (getattr(self, "_status_meta", ""), self._timing_text) if p]
        self.status_meta.setText("  ·  ".join(parts))

    def add_timing(self, seconds: float) -> None:
        self._timings.append(seconds)
        avg = sum(self._timings) / len(self._timings)
        self._timing_text = f"{avg:.1f} giây/câu".replace(".", ",")
        if avg > 4.0:
            self._timing_text += " — hơi chậm, thử chất lượng Cân bằng"
        self._render_meta()

    def show_warning(self, text: str) -> None:
        self._timing_text = text
        self._render_meta()

    def show_partial(self, source: str, seg_id: int, text: str, translation: str) -> None:
        self.monitor_eyebrow.setText("Đang nói…")
        self.monitor_time.setText("")
        self.monitor_lang.hide()
        self.monitor_source.setObjectName("source")
        self.monitor_source.setText(f"{text} …")
        self._repolish(self.monitor_source)
        if translation and translation != text:
            self.monitor_target.setText(f"{translation} …")
            self.monitor_target.show()

    def add_history(self, source: str, lang: str, text: str, translation: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        # màn hình cabin
        self.monitor_eyebrow.setText(f"Câu gần nhất · {source}")
        self.monitor_time.setText(stamp)
        self.monitor_lang.setText(lang.upper())
        self.monitor_lang.setObjectName("chipTarget" if lang == "vi" else "chipSource")
        self._repolish(self.monitor_lang)
        self.monitor_lang.show()
        self.monitor_source.setObjectName("target" if lang == "vi" else "source")
        self.monitor_source.setText(text)
        self._repolish(self.monitor_source)
        shown = translation if translation and translation != text else ""
        self.monitor_target.setText(shown)
        self.monitor_target.setVisible(bool(shown))
        # trang lịch sử
        meta = f"{stamp} · {lang.upper()} · {html.escape(source)}"
        src_color = theme.TARGET if lang == "vi" else theme.SOURCE
        block = (
            f'<p style="margin:0 0 12px 0;">'
            f'<span style="font-family:\'{theme.MONO}\'; font-size:8pt; color:{theme.MUTED};">{meta}</span><br>'
            f'<span style="color:{src_color};">{html.escape(text)}</span>'
        )
        if shown:
            block += f'<br><span style="color:{theme.TARGET}; font-size:11.5pt;">{html.escape(shown)}</span>'
        self.history.append(block + "</p>")

    def set_source(self, mode: str) -> None:
        tile = self._src_tiles.get(mode)
        if tile and not tile.isChecked():
            tile.setChecked(True)
        for k, t in self._src_tiles.items():
            t._restyle(k == mode)

    def set_quality(self, quality: str) -> None:
        _select(self.quality_box, quality)
        self._update_quality_desc()

    def set_font_size(self, size: str) -> None:
        self.font_seg.set_current(size)

    def set_overlay_visible(self, visible: bool) -> None:
        self.sw_overlay.blockSignals(True)
        self.sw_overlay.setChecked(visible)
        self.sw_overlay.blockSignals(False)

    def set_tts_enabled(self, enabled: bool) -> None:
        self.tts_switch.blockSignals(True)
        self.tts_switch.setChecked(enabled)
        self.tts_switch.blockSignals(False)

    def set_tts_state(self, text: str) -> None:
        self.tts_state.setText(text)
        self.tts_state.setVisible(bool(text))

    # ------------------------------------------------------------ internals
    @staticmethod
    def _repolish(w: QWidget) -> None:
        w.style().unpolish(w)
        w.style().polish(w)

    def _on_quality_index(self, _index: int) -> None:
        self._update_quality_desc()
        self.quality_selected.emit(self.quality_box.currentData())

    def _update_quality_desc(self) -> None:
        key = self.quality_box.currentData()
        self.quality_desc.setText(next((d for k, _, d in QUALITIES if k == key), ""))

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide_to_tray()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_to_tray()
        else:
            super().keyPressEvent(event)
