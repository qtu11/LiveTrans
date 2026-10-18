"""Phím tắt toàn cục bằng Win32 RegisterHotKey (không cần quyền admin)."""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

_MODS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
_KEYS = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "pause": 0x13, "insert": 0x2D,
    "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """``"Ctrl+Alt+T"`` → (modifiers | MOD_NOREPEAT, virtual-key)."""
    parts = [p.strip().lower() for p in spec.split("+")]
    if len(parts) < 2 or any(not p for p in parts):
        raise ValueError(f"phím tắt không hợp lệ: {spec!r}")
    *mods, key = parts
    flags = MOD_NOREPEAT
    for m in mods:
        if m not in _MODS:
            raise ValueError(f"phím bổ trợ không hợp lệ: {m!r} trong {spec!r}")
        flags |= _MODS[m]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in _KEYS:
        vk = _KEYS[key]
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    else:
        raise ValueError(f"phím không hợp lệ: {key!r} trong {spec!r}")
    return flags, vk


class GlobalHotkeys(QObject):
    triggered = Signal(str)

    def __init__(self, bindings: dict[str, str]):
        super().__init__()
        self.bindings = bindings
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._failed: list[str] = []

    def start(self) -> list[str]:
        """Đăng ký phím; trả về tên các phím không đăng ký được."""
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(2)
        return list(self._failed)

    def stop(self) -> None:
        if self._thread is not None and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        names: dict[int, str] = {}
        self._failed = []
        for i, (name, spec) in enumerate(self.bindings.items(), start=1):
            try:
                mods, vk = parse_hotkey(spec)
            except ValueError as e:
                log.warning("%s", e)
                self._failed.append(f"{name} ({spec})")
                continue
            if user32.RegisterHotKey(None, i, mods, vk):
                names[i] = name
            else:
                log.warning("không đăng ký được phím %s (%s), lỗi %d", spec, name, ctypes.get_last_error())
                self._failed.append(f"{name} ({spec})")
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in names:
                self.triggered.emit(names[msg.wParam])
        for i in names:
            user32.UnregisterHotKey(None, i)
