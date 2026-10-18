from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def make_pixmap(size: int, active: bool) -> QPixmap:
    """Chữ "VI" trên nền tròn (xanh = đang nghe, xám = tạm dừng)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2e7d32") if active else QColor("#757575"))
    margin = max(1, size // 32)
    p.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    font = QFont("Segoe UI")
    font.setPixelSize(max(6, round(size * 0.44)))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "VI")
    p.end()
    return pm


def make_icon(active: bool) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64):
        icon.addPixmap(make_pixmap(size, active))
    return icon
