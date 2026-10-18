"""Widget tuỳ biến cho giao diện cabin phiên dịch."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme


def label(text: str = "", obj: str | None = None, f: QFont | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    if f is not None:
        lb.setFont(f)
    lb.setWordWrap(wrap)
    return lb


def eyebrow(text: str) -> QLabel:
    lb = label(text, "muted", theme.eyebrow_font())
    return lb


def glyph(char: str, px: int = 18, color: str = theme.MUTED) -> QLabel:
    lb = QLabel(char)
    lb.setFont(theme.icon_font(px))
    lb.setStyleSheet(f"color: {color}; background: transparent;")
    lb.setFixedWidth(px + 6)
    return lb


def card(obj: str = "card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(obj)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    return frame, layout


def keycap(text: str) -> QLabel:
    return label(text, "keycap")


class Combo(QComboBox):
    """QComboBox có mũi tên (stylesheet tối giản ẩn mũi tên mặc định)."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setFont(theme.icon_font(10))
        p.setPen(QColor(theme.MUTED))
        p.drawText(QRectF(self.width() - 28, 0, 20, self.height()), Qt.AlignmentFlag.AlignCenter,
                   theme.G_CHEVRON_DOWN)


class ToggleSwitch(QAbstractButton):
    """Công tắc gạt; tương thích QCheckBox (``toggled``, ``isChecked``, ``setChecked``)."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140 if theme.animations_enabled() else 0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def _set_pos(self, v) -> None:
        self._pos = float(v)
        self.update()

    def nextCheckState(self) -> None:  # người dùng bấm → có hoạt ảnh
        super().nextCheckState()
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if self.isChecked() else 0.0)
        self._anim.start()

    def checkStateSet(self) -> None:  # setChecked() từ code → nhảy thẳng
        super().checkStateSet()
        self._anim.stop()
        self._set_pos(1.0 if self.isChecked() else 0.0)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, 42, 22)
        on, off = QColor(theme.AMBER), QColor(theme.LINE)
        track = QColor(
            round(off.red() + (on.red() - off.red()) * self._pos),
            round(off.green() + (on.green() - off.green()) * self._pos),
            round(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        if not self.isEnabled():
            track.setAlpha(90)
        p.setPen(QPen(QColor(theme.AMBER_HOVER), 1.5) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, 11, 11)
        knob_x = r.left() + 3 + (r.width() - 22) * self._pos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1C1405") if self._pos > 0.5 else QColor(theme.TEXT))
        p.drawEllipse(QRectF(knob_x, r.top() + 3, 16, 16))


class TallyLamp(QWidget):
    """Đèn ON AIR: hổ phách "thở" khi đang nghe, hổ phách mờ khi chuẩn bị, xám khi dừng, đỏ khi lỗi."""

    COLORS = {"live": theme.AMBER, "loading": theme.AMBER, "off": "#4A5368", "error": theme.RED}

    def __init__(self, size: int = 30, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.state = "off"
        self._glow = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(1800)
        self._anim.setStartValue(0.35)
        self._anim.setKeyValueAt(0.5, 1.0)
        self._anim.setEndValue(0.35)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.valueChanged.connect(self._on_glow)

    def _on_glow(self, v) -> None:
        self._glow = float(v)
        self.update()

    def set_state(self, state: str) -> None:
        self.state = state
        self._anim.stop()
        if state == "live" and theme.animations_enabled():
            self._anim.start()
        else:
            self._glow = {"live": 0.8, "loading": 0.35, "error": 0.6}.get(state, 0.0)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        color = QColor(self.COLORS.get(self.state, theme.MUTED))
        if self._glow > 0:
            g = QRadialGradient(c, self.width() / 2)
            halo = QColor(color)
            halo.setAlphaF(0.45 * self._glow)
            g.setColorAt(0.0, halo)
            halo.setAlphaF(0.0)
            g.setColorAt(1.0, halo)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, self.width() / 2, self.height() / 2)
        core = self.width() * 0.22
        if self.state == "loading":
            color.setAlphaF(0.6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(c, core, core)


class Segmented(QFrame):
    """Nhóm nút chọn một trong nhiều (giống công tắc chọn kênh)."""

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], current: str | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("segbar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in items:
            b = QPushButton(text)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self._group.addButton(b)
            self._buttons[key] = b
            layout.addWidget(b)
        self.set_current(current)

    def set_current(self, key: str | None) -> None:
        self._group.setExclusive(False)
        for k, b in self._buttons.items():
            b.setChecked(k == key)
        self._group.setExclusive(True)

    def current(self) -> str | None:
        return next((k for k, b in self._buttons.items() if b.isChecked()), None)


class ChannelTile(QPushButton):
    """Ô chọn nguồn âm thanh: icon + tên + mô tả ngắn."""

    def __init__(self, glyph_char: str, title: str, caption: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setMinimumHeight(78)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        self._icon = glyph(glyph_char, 20)
        t = label(title, f=theme.font("body", 10.5, QFont.Weight.DemiBold))
        c = label(caption, "muted", theme.font("body", 8.5), wrap=True)
        for w in (self._icon, t, c):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(w)
        self.toggled.connect(self._restyle)

    def _restyle(self, checked: bool) -> None:
        self._icon.setStyleSheet(f"color: {theme.AMBER if checked else theme.MUTED}; background: transparent;")


class SettingRow(QWidget):
    """Một dòng cài đặt: tiêu đề + mô tả bên trái, điều khiển bên phải."""

    def __init__(self, title: str, caption: str, control: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(title, f=theme.font("body", 10)))
        if caption:
            text.addWidget(label(caption, "muted", theme.font("body", 8.5), wrap=True))
        layout.addLayout(text, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
