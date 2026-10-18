"""Model, chế độ chất lượng và tải model vào thư mục ``models/``."""

from __future__ import annotations

import ctypes
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .paths import APP_DIR, MODELS_DIR

log = logging.getLogger(__name__)

WHISPER_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
NLLB_FILES = ["config.json", "model.bin", "sentencepiece.bpe.model", "shared_vocabulary.txt"]
_WHISPER_SIZES_MB = {"tiny": 75, "base": 145, "small": 480, "medium": 1500, "large-v3": 3100}


@dataclass(frozen=True)
class MtModel:
    key: str
    repo: str
    folder: str
    mb: int


MT_MODELS = {
    "nllb-600M": MtModel("nllb-600M", "JustFrederik/nllb-200-distilled-600M-ct2-int8", "nllb-200-distilled-600M-ct2-int8", 620),
    "nllb-1.3B": MtModel("nllb-1.3B", "JustFrederik/nllb-200-distilled-1.3B-ct2-int8", "nllb-200-distilled-1.3B-ct2-int8", 1320),
}


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    whisper: str  # model cho câu chốt
    preview: str  # model cho câu xem trước
    mt: str  # khoá trong MT_MODELS


PROFILES = {
    "fast": Profile("fast", "Nhanh (máy yếu)", "base", "base", "nllb-600M"),
    "balanced": Profile("balanced", "Cân bằng", "small", "base", "nllb-600M"),
    "accurate": Profile("accurate", "Chính xác nhất", "small", "base", "nllb-1.3B"),
}
INSTALL_PROFILE_PATH = APP_DIR / "install_profile.json"  # bộ cài ghi lựa chọn của người dùng vào đây


# ------------------------------------------------------------------ phần cứng
def total_ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(stat)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return 8.0
    return stat.ullTotalPhys / 1024**3


def recommend_profile(cpu_count: int, ram_gb: float) -> str:
    """Cùng quy tắc với trang chọn chất lượng trong bộ cài (packaging/LiveTrans.iss)."""
    if cpu_count >= 6 and ram_gb >= 7.5:
        return "accurate"
    if cpu_count >= 4 and ram_gb >= 5.5:
        return "balanced"
    return "fast"


def auto_threads(cpu_count: int | None = None) -> int:
    """~70% số luồng: thêm luồng gần như không nhanh hơn (đo trên i5-9400F: 4 luồng 2,3 s, 6 luồng 2,2 s)
    nhưng tranh CPU với trình duyệt đang phát video."""
    n = cpu_count or os.cpu_count() or 4
    return max(2, min(8, round(n * 0.7)))


def resolve_profile(quality: str) -> Profile:
    if quality in PROFILES:
        return PROFILES[quality]
    try:
        chosen = json.loads(INSTALL_PROFILE_PATH.read_text(encoding="utf-8")).get("quality")
        if chosen in PROFILES:
            return PROFILES[chosen]
    except (OSError, ValueError):
        pass
    return PROFILES[recommend_profile(os.cpu_count() or 4, total_ram_gb())]


# --------------------------------------------------------------------- vị trí
def whisper_repo(size: str) -> str:
    if "/" in size:
        return size
    if size == "large-v3-turbo":
        return "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    return f"Systran/faster-whisper-{size}"


def whisper_dir(size: str) -> Path:
    return MODELS_DIR / ("whisper-" + size.replace("/", "--"))


def mt_dir(key: str) -> Path:
    return MODELS_DIR / MT_MODELS[key].folder


def nllb_dir() -> Path:
    """Model dịch mặc định (600M) — dùng cho test và self-test."""
    return mt_dir("nllb-600M")


def whisper_complete(wdir: Path) -> bool:
    """Đủ file để nạp (bộ cài có thể bị dừng giữa chừng → chỉ có một phần)."""
    return all((wdir / f).exists() for f in ("config.json", "model.bin", "tokenizer.json")) and any(
        wdir.glob("vocabulary.*")
    )


def mt_complete(key: str) -> bool:
    return all((mt_dir(key) / f).exists() for f in NLLB_FILES)


def profile_present(profile: Profile) -> bool:
    return (
        whisper_complete(whisper_dir(profile.whisper))
        and whisper_complete(whisper_dir(profile.preview))
        and mt_complete(profile.mt)
    )


def models_present(size: str) -> bool:
    return whisper_complete(whisper_dir(size)) and mt_complete("nllb-600M")


# ----------------------------------------------------------------------- tải
def _download(repo: str, target: Path, patterns: list[str]) -> None:
    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo, local_dir=str(target), allow_patterns=patterns)


def ensure_whisper(size: str, progress: Callable[[str], None] = lambda s: None) -> Path:
    wdir = whisper_dir(size)
    if not whisper_complete(wdir):
        mb = _WHISPER_SIZES_MB.get(size)
        size_txt = f" (~{mb} MB)" if mb else ""
        progress(f"Đang tải model Whisper {size}{size_txt}…")
        log.info("downloading %s -> %s", whisper_repo(size), wdir)
        _download(whisper_repo(size), wdir, WHISPER_FILES)
    return wdir


def ensure_mt(key: str, progress: Callable[[str], None] = lambda s: None) -> Path:
    spec = MT_MODELS[key]
    if not mt_complete(key):
        progress(f"Đang tải model dịch {key} (~{spec.mb} MB)…")
        log.info("downloading %s -> %s", spec.repo, mt_dir(key))
        _download(spec.repo, mt_dir(key), NLLB_FILES)
    return mt_dir(key)


def ensure_profile(profile: Profile, progress: Callable[[str], None] = lambda s: None) -> tuple[Path, Path, Path]:
    """(Whisper câu chốt, Whisper xem trước, model dịch) — tải nếu thiếu."""
    return (
        ensure_whisper(profile.whisper, progress),
        ensure_whisper(profile.preview, progress),
        ensure_mt(profile.mt, progress),
    )


def ensure_models(whisper_size: str, progress: Callable[[str], None] = lambda s: None) -> tuple[Path, Path]:
    """(Whisper, NLLB 600M) — dùng cho test."""
    return ensure_whisper(whisper_size, progress), ensure_mt("nllb-600M", progress)
