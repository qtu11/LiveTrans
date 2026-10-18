"""Đọc to bản dịch tiếng Việt bằng Piper (offline, CPU).

Chỉ dùng giọng ``vi_VN-vais1000-medium``: các giọng Piper tiếng Việt cũ (0.2.0) không có ký hiệu thanh điệu
dạng số mà espeak-ng hiện tại sinh ra → đọc mất dấu.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from .paths import MODELS_DIR

log = logging.getLogger(__name__)

VOICE_REPO = "rhasspy/piper-voices"
VOICE_KEY = "vi_VN-vais1000-medium"
VOICE_DIR = "vi/vi_VN/vais1000/medium"
VOICE_FILES = [f"{VOICE_DIR}/{VOICE_KEY}.onnx", f"{VOICE_DIR}/{VOICE_KEY}.onnx.json"]
VOICE_MB = 61

# length_scale của Piper: < 1 là đọc nhanh hơn
SPEEDS = {"slow": 1.15, "normal": 1.0, "fast": 0.85, "faster": 0.72}
MAX_PENDING = 2  # đọc không kịp → bỏ câu cũ để luôn bám theo câu mới nhất
_CHUNK_S = 0.05


def voice_path() -> Path:
    return MODELS_DIR / "piper" / VOICE_DIR / f"{VOICE_KEY}.onnx"


def voice_present() -> bool:
    p = voice_path()
    return p.exists() and p.with_suffix(".onnx.json").exists()


def ensure_voice(progress: Callable[[str], None] = lambda s: None) -> Path:
    if not voice_present():
        from huggingface_hub import snapshot_download

        progress(f"Đang tải giọng đọc tiếng Việt (~{VOICE_MB} MB)…")
        log.info("downloading %s/%s", VOICE_REPO, VOICE_DIR)
        snapshot_download(repo_id=VOICE_REPO, local_dir=str(MODELS_DIR / "piper"), allow_patterns=VOICE_FILES)
    return voice_path()


class _PiperEngine:
    """Tổng hợp → int16 mono; phát qua PortAudio dùng chung với phần bắt âm thanh."""

    def __init__(self) -> None:
        from piper import PiperVoice

        self.voice = PiperVoice.load(str(ensure_voice()))
        self.sample_rate = self.voice.config.sample_rate

    def synthesize(self, text: str, length_scale: float) -> np.ndarray:
        from piper import SynthesisConfig

        chunks = list(self.voice.synthesize(text, syn_config=SynthesisConfig(length_scale=length_scale)))
        if not chunks:
            return np.empty(0, dtype=np.int16)
        return np.concatenate([c.audio_int16_array for c in chunks])

    def play(self, audio: np.ndarray, should_stop: Callable[[], bool]) -> None:
        from .audio_capture import close_stream, open_output_stream

        stream = open_output_stream(self.sample_rate)
        try:
            step = int(self.sample_rate * _CHUNK_S)
            for i in range(0, len(audio), step):
                if should_stop():
                    break
                stream.write(audio[i : i + step].tobytes())
        finally:
            close_stream(stream)


class Speaker(QObject):
    """Hàng đợi đọc chạy trên thread riêng. ``state_changed``: loading / ready / speaking / error."""

    state_changed = Signal(str, str)  # trạng thái, chi tiết

    def __init__(self, speed: str = "fast", volume: float = 0.9, engine_factory=_PiperEngine):
        super().__init__()
        self.speed = speed
        self.volume = volume
        self._engine_factory = engine_factory
        self._engine = None
        self._queue: deque[str] = deque()
        self._cond = threading.Condition()
        self._interrupt = False
        self._closed = False
        self._thread: threading.Thread | None = None
        self.speaking = False

    def start(self) -> None:
        """Nạp giọng (tải nếu thiếu) trên thread nền; gọi nhiều lần không sao."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="tts", daemon=True)
            self._thread.start()

    def say(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.start()
        with self._cond:
            self._queue.append(text)
            while len(self._queue) > MAX_PENDING:
                dropped = self._queue.popleft()
                log.info("đọc không kịp, bỏ câu: %s", dropped[:60])
            self._cond.notify()

    def stop_speaking(self) -> None:
        with self._cond:
            self._queue.clear()
            self._interrupt = True
            self._cond.notify()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._interrupt = True
            self._cond.notify()
        if self._thread is not None:
            self._thread.join(timeout=3)

    # ------------------------------------------------------------ thread
    def _run(self) -> None:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # WASAPI/MME cần COM trên thread phát
        self.state_changed.emit("loading", "Đang nạp giọng đọc…")
        try:
            self._engine = self._engine_factory()
        except Exception as e:
            log.exception("không nạp được giọng đọc")
            self.state_changed.emit("error", f"Lỗi giọng đọc: {e}")
            self._thread = None
            return
        self.state_changed.emit("ready", "Giọng đọc sẵn sàng")
        while True:
            with self._cond:
                while not self._queue and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                text = self._queue.popleft()
                self._interrupt = False
            try:
                audio = self._engine.synthesize(text, SPEEDS.get(self.speed, 1.0))
                if self.volume != 1.0:
                    audio = np.clip(audio.astype(np.float32) * self.volume, -32768, 32767).astype(np.int16)
                self.speaking = True
                self.state_changed.emit("speaking", text)
                self._engine.play(audio, lambda: self._interrupt)
            except Exception as e:
                log.exception("lỗi khi đọc")
                self.state_changed.emit("error", f"Lỗi khi đọc: {e}")
            finally:
                self.speaking = False
            with self._cond:
                idle = not self._queue
            if idle:
                self.state_changed.emit("ready", "")
