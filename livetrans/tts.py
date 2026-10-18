"""Đọc to bản dịch tiếng Việt.

Hai loại giọng:
- ``piper``: Piper offline (``vi_VN-vais1000-medium``) — các giọng Piper tiếng Việt cũ (0.2.0) thiếu ký hiệu thanh
  điệu dạng số mà espeak-ng hiện tại sinh ra → đọc mất dấu, nên chỉ dùng giọng này.
- ``vi-VN-HoaiMyNeural`` / ``vi-VN-NamMinhNeural``: giọng neural của Microsoft qua dịch vụ "Đọc to" của Edge
  (online, gửi câu đã dịch dạng chữ). Lỗi/mất mạng → câu đó đọc bằng Piper.

Hai thread: một thread tổng hợp (lấy sẵn câu kế tiếp trong lúc đang đọc), một thread phát.
"""

from __future__ import annotations

import asyncio
import ctypes
import io
import logging
import threading
import time
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

PIPER = "piper"
EDGE_VOICES = {"vi-VN-HoaiMyNeural": "HoaiMy (nữ)", "vi-VN-NamMinhNeural": "NamMinh (nam)"}
VOICES = (PIPER, *EDGE_VOICES)

# Tốc độ đọc: length_scale của Piper (< 1 là nhanh hơn) và rate của Edge
SPEEDS = {"slow": 1.15, "normal": 1.0, "fast": 0.85, "faster": 0.72, "rush": 0.64}
EDGE_RATES = {"slow": "-10%", "normal": "+0%", "fast": "+15%", "faster": "+30%", "rush": "+45%"}
_SPEED_ORDER = ["slow", "normal", "fast", "faster", "rush"]


def boosted(speed: str) -> str:
    """Tốc độ cao hơn một bậc — dùng khi đang có câu chờ đọc, để bám kịp người nói thay vì bỏ câu."""
    i = _SPEED_ORDER.index(speed) if speed in _SPEED_ORDER else 2
    return _SPEED_ORDER[min(i + 1, len(_SPEED_ORDER) - 1)]
EDGE_RATE = 24000
EDGE_TIMEOUT_S = 6
# Dịch vụ miễn phí của Edge đôi khi đóng kết nối mà không trả âm thanh (~2,6 s mỗi lần lỗi). Sau một lần lỗi,
# đọc bằng Piper trong khoảng này rồi mới thử lại giọng online, để không bị trễ thêm ở từng câu.
ONLINE_COOLDOWN_S = 45.0
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


# ---------------------------------------------------------------- engines
class PiperEngine:
    online = False

    def __init__(self) -> None:
        from piper import PiperVoice

        self.voice = PiperVoice.load(str(ensure_voice()))
        self.sample_rate = self.voice.config.sample_rate

    def synthesize(self, text: str, speed: str) -> tuple[np.ndarray, int]:
        from piper import SynthesisConfig

        cfg = SynthesisConfig(length_scale=SPEEDS.get(speed, 1.0))
        chunks = list(self.voice.synthesize(text, syn_config=cfg))
        audio = np.concatenate([c.audio_int16_array for c in chunks]) if chunks else np.empty(0, np.int16)
        return audio, self.sample_rate


class EdgeEngine:
    online = True

    def __init__(self, voice: str) -> None:
        import edge_tts  # noqa: F401  (báo lỗi sớm nếu thiếu thư viện)

        self.voice = voice

    async def _fetch(self, text: str, rate: str) -> bytes:
        import edge_tts

        buf = io.BytesIO()
        comm = edge_tts.Communicate(text, self.voice, rate=rate, connect_timeout=EDGE_TIMEOUT_S,
                                    receive_timeout=EDGE_TIMEOUT_S)
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    def synthesize(self, text: str, speed: str) -> tuple[np.ndarray, int]:
        mp3 = asyncio.run(asyncio.wait_for(self._fetch(text, EDGE_RATES.get(speed, "+0%")), EDGE_TIMEOUT_S * 2))
        return decode_mp3(mp3), EDGE_RATE


def decode_mp3(data: bytes) -> np.ndarray:
    import av

    out = []
    resampler = av.AudioResampler(format="s16", layout="mono", rate=EDGE_RATE)
    with av.open(io.BytesIO(data)) as container:
        for frame in container.decode(audio=0):
            for f in resampler.resample(frame):
                out.append(f.to_ndarray().reshape(-1))
    for f in resampler.resample(None):
        out.append(f.to_ndarray().reshape(-1))
    return np.concatenate(out).astype(np.int16) if out else np.empty(0, np.int16)


def make_engine(voice: str):
    return EdgeEngine(voice) if voice in EDGE_VOICES else PiperEngine()


def play_audio(audio: np.ndarray, rate: int, should_stop: Callable[[], bool]) -> None:
    from .audio_capture import close_stream, open_output_stream

    stream = open_output_stream(rate)
    try:
        step = int(rate * _CHUNK_S)
        for i in range(0, len(audio), step):
            if should_stop():
                break
            stream.write(audio[i : i + step].tobytes())
    finally:
        close_stream(stream)


# ---------------------------------------------------------------- speaker
class Speaker(QObject):
    """``state_changed``: loading / ready / speaking / fallback / error."""

    state_changed = Signal(str, str)  # trạng thái, chi tiết

    def __init__(self, voice: str = PIPER, speed: str = "fast", volume: float = 0.9,
                 engine_factory=make_engine, player=play_audio, clock=time.monotonic):
        super().__init__()
        self._clock = clock
        self._online_blocked_until = 0.0
        self.voice = voice if voice in VOICES else PIPER
        self.speed = speed
        self.volume = volume
        self._engine_factory = engine_factory
        self._player = player
        self._engines: dict[str, object] = {}
        self._texts: deque[str] = deque()
        self._ready: deque[tuple[str, np.ndarray, int]] = deque()
        self._cond = threading.Condition()
        self._interrupt = False
        self._generation = 0  # tăng khi stop_speaking → bỏ âm thanh tổng hợp dở
        self._closed = False
        self._threads: list[threading.Thread] = []
        self.speaking = False

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        """Khởi động thread và nạp sẵn giọng hiện tại; gọi nhiều lần không sao."""
        if self._threads:
            return
        self._threads = [
            threading.Thread(target=self._synth_loop, name="tts-synth", daemon=True),
            threading.Thread(target=self._play_loop, name="tts-play", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def set_voice(self, voice: str) -> None:
        if voice in VOICES:
            self.voice = voice
            self.start()
            with self._cond:
                self._cond.notify_all()  # thread tổng hợp nạp giọng mới

    def say(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.start()
        with self._cond:
            self._texts.append(text)
            while len(self._texts) > MAX_PENDING:
                log.info("đọc không kịp, bỏ câu: %s", self._texts.popleft()[:60])
            self._cond.notify_all()

    def stop_speaking(self) -> None:
        with self._cond:
            self._texts.clear()
            self._ready.clear()
            self._generation += 1
            self._interrupt = True
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._interrupt = True
            self._cond.notify_all()
        for t in self._threads:
            t.join(timeout=3)

    # ------------------------------------------------------------ threads
    def _engine(self, voice: str):
        if voice not in self._engines:
            self.state_changed.emit("loading", "Đang nạp giọng đọc…")
            self._engines[voice] = self._engine_factory(voice)
            self.state_changed.emit("ready", "")
        return self._engines[voice]

    def _synthesize(self, text: str, speed: str) -> tuple[np.ndarray, int]:
        voice = self.voice
        if voice != PIPER and self._clock() < self._online_blocked_until:
            voice = PIPER  # giọng online vừa lỗi → tạm dùng giọng offline
        try:
            return self._engine(voice).synthesize(text, speed)
        except Exception as e:
            if voice == PIPER:
                raise
            log.warning("giọng online lỗi (%s: %s) → giọng offline %.0f giây", type(e).__name__, e, ONLINE_COOLDOWN_S)
            self._online_blocked_until = self._clock() + ONLINE_COOLDOWN_S
            self.state_changed.emit("fallback", "Giọng online không phản hồi — tạm đọc bằng giọng offline")
            return self._engine(PIPER).synthesize(text, speed)

    def _synth_loop(self) -> None:
        try:
            self._engine(self.voice)  # nạp sẵn
        except Exception as e:
            log.exception("không nạp được giọng đọc")
            self.state_changed.emit("error", f"Lỗi giọng đọc: {e}")
        while True:
            with self._cond:
                while not self._texts and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                text = self._texts.popleft()
                generation = self._generation
                behind = bool(self._texts) or bool(self._ready) or self.speaking
            speed = boosted(self.speed) if behind else self.speed
            try:
                audio, rate = self._synthesize(text, speed)
            except Exception as e:
                log.exception("lỗi khi tổng hợp giọng")
                self.state_changed.emit("error", f"Lỗi giọng đọc: {e}")
                continue
            with self._cond:
                if generation != self._generation or self._closed:
                    continue  # đã bấm dừng trong lúc tổng hợp
                self._ready.append((text, audio, rate))
                while len(self._ready) > MAX_PENDING:
                    log.info("đọc không kịp, bỏ câu đã tổng hợp: %s", self._ready.popleft()[0][:60])
                self._cond.notify_all()

    def _play_loop(self) -> None:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # WASAPI/MME cần COM trên thread phát
        while True:
            with self._cond:
                while not self._ready and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                text, audio, rate = self._ready.popleft()
                self._interrupt = False
            if self.volume != 1.0:
                audio = np.clip(audio.astype(np.float32) * self.volume, -32768, 32767).astype(np.int16)
            self.speaking = True
            self.state_changed.emit("speaking", text)
            try:
                self._player(audio, rate, lambda: self._interrupt)
            except Exception as e:
                log.exception("lỗi khi phát giọng đọc")
                self.state_changed.emit("error", f"Lỗi khi đọc: {e}")
            finally:
                self.speaking = False
            with self._cond:
                idle = not self._ready and not self._texts
            if idle:
                self.state_changed.emit("ready", "")
