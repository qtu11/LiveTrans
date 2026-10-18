"""Đọc / ghi config.json. Khoá thiếu hoặc sai kiểu → dùng giá trị mặc định."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SOURCE_MODES = ("loopback", "mic", "both")
FONT_SIZES = ("small", "medium", "large")
QUALITIES = ("auto", "fast", "balanced", "accurate")
TTS_SPEEDS = ("slow", "normal", "fast", "faster")
TTS_VOICES = ("piper", "vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural")  # khớp tts.VOICES

_CHOICES = {
    "source_mode": SOURCE_MODES, "font_size": FONT_SIZES, "quality": QUALITIES, "tts_speed": TTS_SPEEDS,
    "tts_voice": TTS_VOICES,
}


CONFIG_VERSION = 2  # v2: cắt câu ngắn hơn (preset "fast"), phụ đề không tự ẩn


@dataclass
class VadConfig:
    start_threshold: float = 0.5
    end_threshold: float = 0.35
    min_silence_ms: int = 450
    min_speech_ms: int = 250
    max_segment_s: float = 5.0
    pre_roll_ms: int = 200
    partial_interval_s: float = 1.5


# Tốc độ phụ đề: "fast" = câu ngắn, hiện sớm; "standard" = câu dài, đủ ngữ cảnh hơn.
SPEED_PRESETS = {
    "fast": {"min_silence_ms": 450, "max_segment_s": 5.0, "partial_interval_s": 1.5},
    "standard": {"min_silence_ms": 600, "max_segment_s": 8.0, "partial_interval_s": 2.0},
}


def speed_of(vad: VadConfig) -> str | None:
    for name, preset in SPEED_PRESETS.items():
        if all(getattr(vad, k) == v for k, v in preset.items()):
            return name
    return None


def apply_speed(vad: VadConfig, name: str) -> None:
    for k, v in SPEED_PRESETS[name].items():
        setattr(vad, k, v)


@dataclass
class HotkeyConfig:
    toggle: str = "Ctrl+Alt+T"
    overlay: str = "Ctrl+Alt+H"
    source: str = "Ctrl+Alt+M"
    compose: str = "Ctrl+Alt+V"
    speak: str = "Ctrl+Alt+R"


@dataclass
class Config:
    config_version: int = CONFIG_VERSION
    source_mode: str = "loopback"
    quality: str = "auto"  # auto = theo lựa chọn khi cài / theo cấu hình máy (xem models.PROFILES)
    cpu_threads: int = 0  # 0 = tự động (số luồng CPU - 1)
    translate_preview: bool = True  # dịch tạm câu đang nói
    source_language: str = "auto"
    font_size: str = "medium"
    overlay_pos: list[int] | None = None
    overlay_width_ratio: float = 0.6
    overlay_visible: bool = True
    overlay_autohide: bool = False  # True = mờ dần khi im lặng 8 giây
    compose_hide_after_copy: bool = True
    tts_enabled: bool = False  # đọc to bản dịch tiếng Việt
    tts_voice: str = "piper"  # piper (offline) / giọng Microsoft online (TTS_VOICES)
    tts_speed: str = "fast"  # slow / normal / fast / faster (tts.SPEEDS)
    tts_volume: float = 0.9
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    vad: VadConfig = field(default_factory=VadConfig)


def _merge(target, data: dict, prefix: str = "") -> None:
    """Ghi các giá trị hợp lệ từ ``data`` vào dataclass ``target`` (tại chỗ)."""
    for f in fields(target):
        if f.name not in data:
            continue
        name = prefix + f.name
        value = data[f.name]
        current = getattr(target, f.name)
        if is_dataclass(current):
            if isinstance(value, dict):
                _merge(current, value, name + ".")
            else:
                log.warning("config: %s phải là object, bỏ qua", name)
            continue
        if f.name == "overlay_pos":
            if value is None or (
                isinstance(value, list)
                and len(value) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
            ):
                setattr(target, f.name, value)
            else:
                log.warning("config: %s không hợp lệ, bỏ qua", name)
            continue
        expected = type(current)
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if type(value) is not expected:
            log.warning("config: %s sai kiểu (%r), dùng mặc định", name, value)
            continue
        if f.name in _CHOICES and value not in _CHOICES[f.name]:
            log.warning("config: %s=%r không hợp lệ, dùng mặc định", name, value)
            continue
        setattr(target, f.name, value)


def load_config(path: Path) -> Config:
    cfg = Config()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError) as e:
        log.warning("config: không đọc được %s (%s), dùng mặc định", path, e)
        return cfg
    if isinstance(data, dict):
        if not isinstance(data.get("config_version"), int) or data["config_version"] < 2:
            # v1 lưu sẵn tham số cắt câu cũ (8 s) và chế độ tự ẩn → dùng mặc định mới
            data = {k: v for k, v in data.items() if k not in ("vad", "config_version", "cpu_threads")}
        _merge(cfg, data)
        cfg.config_version = CONFIG_VERSION
    return cfg


def save_config(cfg: Config, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
