"""Đường dẫn ứng dụng.

- Chạy từ mã nguồn: mọi thứ nằm trong thư mục dự án.
- Bản cài đặt (PyInstaller, ``sys.frozen``): model nằm cạnh ``LiveTrans.exe`` (bộ cài tải về đó);
  config và log nằm ở ``%LOCALAPPDATA%\\LiveTrans`` để giữ lại khi nâng cấp.
- ``LIVETRANS_MODELS`` ghi đè thư mục model.
"""

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "LiveTrans"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = APP_DIR

MODELS_DIR = Path(os.environ.get("LIVETRANS_MODELS") or APP_DIR / "models")
LOGS_DIR = DATA_DIR / "logs"
CONFIG_PATH = DATA_DIR / "config.json"
