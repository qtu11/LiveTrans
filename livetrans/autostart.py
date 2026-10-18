"""Khởi động cùng Windows qua khoá HKCU\\...\\Run (bộ cài dùng cùng khoá/giá trị)."""

from __future__ import annotations

import sys
import winreg

from .paths import FROZEN

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LiveTrans"


def supported() -> bool:
    """Chỉ bản cài đặt (exe) mới có đường dẫn cố định để tự chạy."""
    return FROZEN


def command() -> str:
    return f'"{sys.executable}" --minimized'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
