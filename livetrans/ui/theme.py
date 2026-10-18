"""Giao diện "cabin phiên dịch": nền xanh đêm, đèn ON AIR hổ phách, mã màu hai ngôn ngữ.

Ngôn ngữ nguồn (nước ngoài) luôn màu xanh lạnh ``SOURCE``; tiếng Việt luôn màu kem ấm ``TARGET``.
"""

from __future__ import annotations

import ctypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

# ----------------------------------------------------------------- màu
BG = "#10141F"  # nền phòng thu
SIDEBAR = "#0B0E17"
SURFACE = "#181D2B"  # thẻ
RAISED = "#222940"  # mục đang chọn
FIELD = "#121727"  # ô nhập
LINE = "#2B3349"
TEXT = "#E9EDF6"
MUTED = "#8D96AD"
AMBER = "#FFB547"  # đèn ON AIR — điểm nhấn duy nhất
AMBER_HOVER = "#FFC877"
RED = "#F0565B"
SOURCE = "#8FB4E8"  # câu gốc tiếng nước ngoài
TARGET = "#FFE3B3"  # tiếng Việt

# ----------------------------------------------------------------- chữ
DISPLAY = "Bahnschrift"
BODY = "Segoe UI Variable Text"
BODY_DISPLAY = "Segoe UI Variable Display"
MONO = "Cascadia Mono"
ICONS = "Segoe Fluent Icons"
ICONS_FALLBACK = "Segoe MDL2 Assets"  # Windows 10

# Mã glyph Segoe Fluent Icons / MDL2
G_LIVE = ""  # loa
G_MIC = ""
G_BOTH = ""  # đồng bộ hai chiều
G_KEYBOARD = ""
G_HISTORY = ""
G_SETTINGS = ""
G_PLAY = ""
G_STOP = ""
G_VOLUME = ""
G_COPY = ""
G_DELETE = ""
G_HIDE = ""  # thu nhỏ
G_POWER = ""
G_FOLDER = ""
G_CHEVRON_DOWN = ""


def font(role: str, size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    family = {"display": DISPLAY, "body": BODY, "headline": BODY_DISPLAY, "mono": MONO}[role]
    f = QFont(family)
    f.setPointSizeF(size)
    f.setWeight(weight)
    if role == "display":
        f.setStretch(QFont.Stretch.SemiCondensed)
    return f


def eyebrow_font() -> QFont:
    # Không viết hoa toàn bộ: chữ hoa tiếng Việt có dấu chồng (Ấ, Ừ, Ể…) bị cắt mất dấu ở cỡ nhỏ.
    f = font("display", 9.5, QFont.Weight.DemiBold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
    return f


def icon_font(px: int) -> QFont:
    f = QFont(ICONS)
    f.setFamilies([ICONS, ICONS_FALLBACK])
    f.setPixelSize(px)
    return f


def glyph_icon(glyph: str, color: str, px: int = 18) -> QIcon:
    icon = QIcon()
    for scale in (1, 2):
        pm = QPixmap(px * scale, px * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(icon_font(px * scale))
        p.setPen(QColor(color))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    return icon


def animations_enabled() -> bool:
    """Tôn trọng tuỳ chọn "Hiệu ứng hoạt ảnh" của Windows (giảm chuyển động)."""
    SPI_GETCLIENTAREAANIMATION = 0x1042
    value = ctypes.c_int(1)
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0):
        return bool(value.value)
    return True


STYLESHEET = f"""
QWidget#root, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px 6px; }}

QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {LINE}; }}
QPushButton#nav {{
    text-align: left; padding: 9px 12px; border: none; border-radius: 8px;
    color: {MUTED}; font-size: 10.5pt; background: transparent;
}}
QPushButton#nav:hover {{ background: {SURFACE}; color: {TEXT}; }}
QPushButton#nav:checked {{ background: {RAISED}; color: {TEXT}; }}
QPushButton#nav:focus {{ border: 1px solid #4A5678; }}
QPushButton#navQuiet {{
    text-align: left; padding: 7px 12px; border: none; border-radius: 8px;
    color: {MUTED}; font-size: 9.5pt; background: transparent;
}}
QPushButton#navQuiet:hover {{ background: {SURFACE}; color: {TEXT}; }}
QPushButton#navDanger {{
    text-align: left; padding: 7px 12px; border: none; border-radius: 8px;
    color: {MUTED}; font-size: 9.5pt; background: transparent;
}}
QPushButton#navDanger:hover {{ background: #2A1A22; color: {RED}; }}

QFrame#card {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px; }}
QFrame#monitor {{
    border: 1px solid {LINE}; border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1B2133, stop:1 #141927);
}}
QLabel#muted {{ color: {MUTED}; }}
QLabel#source {{ color: {SOURCE}; }}
QLabel#target {{ color: {TARGET}; }}
QLabel#chipSource {{
    background: rgba(143, 180, 232, 0.14); color: {SOURCE}; border-radius: 6px; padding: 2px 7px;
    font-family: "{MONO}"; font-size: 8.5pt;
}}
QLabel#chipTarget {{
    background: rgba(255, 227, 179, 0.12); color: {TARGET}; border-radius: 6px; padding: 2px 7px;
    font-family: "{MONO}"; font-size: 8.5pt;
}}
QLabel#chipAmber {{
    background: rgba(255, 181, 71, 0.14); color: {AMBER}; border-radius: 6px; padding: 2px 8px; font-size: 9pt;
}}
QLabel#keycap {{
    background: {RAISED}; border: 1px solid {LINE}; border-bottom: 2px solid #39425E; border-radius: 5px;
    padding: 1px 6px; font-family: "{MONO}"; font-size: 8.5pt; color: {TEXT};
}}

QPushButton#primary {{
    background: {AMBER}; color: #1C1405; border: none; border-radius: 10px; padding: 10px 20px;
    font-weight: 600; font-size: 11pt;
}}
QPushButton#primary:hover {{ background: {AMBER_HOVER}; }}
QPushButton#primary:focus {{ border: 2px solid #FFE0A8; }}
QPushButton#danger {{
    background: transparent; color: {RED}; border: 1.5px solid {RED}; border-radius: 10px; padding: 10px 20px;
    font-weight: 600; font-size: 11pt;
}}
QPushButton#danger:hover {{ background: rgba(240, 86, 91, 0.12); }}
QPushButton#ghost {{
    background: transparent; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 12px; color: {TEXT};
}}
QPushButton#ghost:hover {{ border-color: #4A5678; background: {SURFACE}; }}
QPushButton#ghost:focus {{ border-color: {AMBER}; }}

QFrame#segbar {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 9px; }}
QPushButton#segment {{
    background: transparent; border: none; border-radius: 7px; padding: 5px 12px; color: {MUTED};
}}
QPushButton#segment:hover {{ color: {TEXT}; }}
QPushButton#segment:checked {{ background: {RAISED}; color: {TEXT}; }}
QPushButton#segment:focus {{ border: 1px solid #4A5678; }}

QPushButton#tile {{
    background: {FIELD}; border: 1px solid {LINE}; border-radius: 12px; text-align: left;
}}
QPushButton#tile:hover {{ border-color: #4A5678; }}
QPushButton#tile:checked {{ border: 1.5px solid {AMBER}; background: #1E1E22; }}
QPushButton#tile:focus {{ border-color: {AMBER_HOVER}; }}

QComboBox {{
    background: {FIELD}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 10px; min-height: 20px;
}}
QComboBox:hover {{ border-color: #4A5678; }}
QComboBox:focus {{ border-color: {AMBER}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {LINE}; selection-background-color: #34405F; outline: none; padding: 4px;
}}

QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {AMBER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:focus {{ background: {AMBER_HOVER}; }}

QPlainTextEdit, QTextBrowser {{
    background: {FIELD}; border: 1px solid {LINE}; border-radius: 12px; padding: 10px;
    selection-background-color: #3A4466;
}}
QPlainTextEdit:focus {{ border-color: #4A5678; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: #2E3650; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3D4868; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
"""
