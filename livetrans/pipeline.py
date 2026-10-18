"""Điều phối: nguồn âm thanh → VAD → Segmenter → WorkQueue → worker (Whisper + NLLB) → Qt signal."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

import numpy as np
from PySide6.QtCore import QObject, Signal

from .audio_capture import SOURCE_LABELS, AudioSource, shutdown_portaudio
from .config import Config, VadConfig
from .segmenter import Event, Final, Segmenter
from .vad import FRAME, SileroVAD
from .work_queue import WorkQueue

log = logging.getLogger(__name__)

MODE_SOURCES = {"loopback": ["loopback"], "mic": ["mic"], "both": ["loopback", "mic"]}
MODE_LABELS = {"loopback": "Loa", "mic": "Micro", "both": "Loa + Micro"}
SLOW_FINAL_S = 5.0  # trung vị thời gian xử lý câu chốt vượt mức này → gợi ý hạ chất lượng


class SourceChannel:
    """Một nguồn âm thanh với VAD + Segmenter riêng."""

    def __init__(
        self,
        kind: str,
        vad_cfg: VadConfig,
        emit: Callable[[Event], None],
        on_status: Callable[[str], None],
        exclude_self: bool = False,
    ):
        self.kind = kind
        self._emit = emit
        self._lock = threading.Lock()
        self._vad = SileroVAD()
        self._seg = Segmenter(kind, vad_cfg)
        self._buf = np.empty(0, dtype=np.float32)
        self._source = AudioSource(kind, self._on_audio, on_status, exclude_self=exclude_self)

    def start(self) -> None:
        with self._lock:
            self._vad.reset()
            self._seg.reset()
            self._buf = np.empty(0, dtype=np.float32)
        self._source.start()

    def stop(self) -> None:
        self._source.stop()
        with self._lock:
            self._seg.reset()

    def tick(self) -> None:
        with self._lock:
            events = self._seg.tick(time.monotonic())
        for ev in events:
            self._emit(ev)

    def _on_audio(self, samples: np.ndarray) -> None:
        events: list[Event] = []
        with self._lock:
            buf = np.concatenate([self._buf, samples]) if self._buf.size else samples
            n = len(buf) // FRAME
            now = time.monotonic()
            for i in range(n):
                frame = buf[i * FRAME : (i + 1) * FRAME]
                events += self._seg.feed(frame, self._vad.prob(frame), now)
            self._buf = buf[n * FRAME :].copy()
        for ev in events:
            self._emit(ev)


class Pipeline(QObject):
    status_changed = Signal(str, bool)  # (text, sticky)
    running_changed = Signal(bool)
    final_ready = Signal(str, int, str, str, str)  # source, seg_id, lang, text, translation
    partial_ready = Signal(str, int, str, str)  # source, seg_id, text, bản dịch tạm ("" nếu chưa có)
    segment_dropped = Signal(str, int)
    models_failed = Signal(str)
    device_error = Signal(str)
    slow_warning = Signal(str)
    final_timing = Signal(float)  # giây xử lý (nhận dạng + dịch) cho mỗi câu chốt

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.queue = WorkQueue()
        self.running = False
        self._channels: dict[str, SourceChannel] = {}
        self._channels_lock = threading.Lock()
        self._asr = None
        self._translator = None
        self.profile = None
        self._final_times: deque[float] = deque(maxlen=7)
        self._slow_warned = False
        self._ready = threading.Event()
        self._retry = threading.Event()
        self._reload = threading.Event()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._ticker: threading.Thread | None = None

    # ------------------------------------------------------------------ API
    def start_engine(self) -> None:
        self._worker = threading.Thread(target=self._worker_loop, name="worker", daemon=True)
        self._worker.start()
        self._ticker = threading.Thread(target=self._tick_loop, name="ticker", daemon=True)
        self._ticker.start()

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    @property
    def translator(self):
        """Translator đã nạp (dùng chung cho ô gõ Việt → Anh) hoặc ``None``."""
        return self._translator if self.ready else None

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._start_sources()
        log.info("bắt đầu nghe: %s", self.cfg.source_mode)
        self.running_changed.emit(True)
        if self.ready:
            self.status_changed.emit(self.listening_text(), False)

    def pause(self) -> None:
        if not self.running:
            return
        self.running = False
        self._stop_sources()
        self.queue.clear()
        log.info("tạm dừng")
        self.running_changed.emit(False)
        self.status_changed.emit("Tạm dừng", False)

    def toggle(self) -> None:
        self.pause() if self.running else self.start()

    def set_source_mode(self, mode: str) -> None:
        self.cfg.source_mode = mode
        log.info("đổi nguồn: %s", mode)
        if self.running:
            self._stop_sources()
            self.queue.clear(partials_only=True)
            self._start_sources()
            if self.ready:
                self.status_changed.emit(self.listening_text(), False)

    def restart_sources(self) -> None:
        """Áp dụng tham số cắt câu mới (cfg.vad) — Segmenter tính số khung lúc khởi tạo."""
        if self.running:
            self._stop_sources()
            self.queue.clear(partials_only=True)
            self._start_sources()

    def set_source_language(self, lang: str) -> None:
        self.cfg.source_language = lang
        asr = self._asr
        if asr is not None:
            asr.forced_language = None if lang == "auto" else lang
        log.info("ngôn ngữ nguồn: %s", lang)

    def retry_models(self) -> None:
        self._retry.set()

    def shutdown(self) -> None:
        self.running = False
        self._stop_sources()
        self._stop.set()
        self._retry.set()
        self.queue.close()
        for t in (self._worker, self._ticker):
            if t is not None:
                t.join(timeout=3)
        shutdown_portaudio()

    def listening_text(self) -> str:
        quality = f" · {self.profile.label}" if self.profile else ""
        return f"Đang nghe: {MODE_LABELS[self.cfg.source_mode]}{quality}"

    # ------------------------------------------------------------- sources
    def _start_sources(self) -> None:
        with self._channels_lock:
            for kind in MODE_SOURCES[self.cfg.source_mode]:
                # Đang bật giọng đọc → nguồn Loa bỏ qua tiếng của chính LiveTrans
                ch = SourceChannel(kind, self.cfg.vad, self._on_event, self._on_device_status,
                                   exclude_self=self.cfg.tts_enabled)
                self._channels[kind] = ch
                ch.start()

    def _stop_sources(self) -> None:
        with self._channels_lock:
            channels = list(self._channels.values())
            self._channels.clear()
        for ch in channels:
            ch.stop()

    def _on_event(self, ev: Event) -> None:
        if self.running and self.ready:
            self.queue.put(ev)

    def _on_device_status(self, text: str) -> None:
        self.device_error.emit(text)

    def _tick_loop(self) -> None:
        while not self._stop.wait(0.1):
            with self._channels_lock:
                channels = list(self._channels.values())
            for ch in channels:
                try:
                    ch.tick()
                except Exception:
                    log.exception("tick")

    # -------------------------------------------------------------- worker
    def _load_models(self) -> bool:
        from .asr import Transcriber
        from .models import auto_threads, ensure_profile, resolve_profile
        from .translator import Translator

        progress = lambda text: self.status_changed.emit(text, True)  # noqa: E731
        try:
            profile = resolve_profile(self.cfg.quality)
            threads = self.cfg.cpu_threads or auto_threads()
            wdir, pdir, mdir = ensure_profile(profile, progress)
            progress(f"Đang nạp model ({profile.label})…")
            forced = None if self.cfg.source_language == "auto" else self.cfg.source_language
            asr = Transcriber(wdir, threads, forced_language=forced, preview_dir=pdir)
            asr.load()
            tr = Translator(mdir, threads)
            tr.load()
            # Lần chạy đầu của CTranslate2 chậm hơn hẳn → làm nóng trước.
            silence = np.zeros(16000, dtype=np.float32)
            asr.transcribe(silence, "final", "_warmup")
            asr.transcribe(silence, "partial", "_warmup")
            tr.translate("Hello.", "en")
        except Exception as e:
            log.exception("không tải/nạp được model")
            self.models_failed.emit(str(e))
            self.status_changed.emit(f"Lỗi tải model: {e}", True)
            return False
        self._asr, self._translator, self.profile = asr, tr, profile
        self._final_times.clear()
        self._slow_warned = False
        self._ready.set()
        log.info(
            "model sẵn sàng: %s (whisper=%s, preview=%s, dịch=%s, %d luồng)",
            profile.key, profile.whisper, profile.preview, profile.mt, threads,
        )
        self.status_changed.emit(self.listening_text() if self.running else "Tạm dừng", False)
        return True

    def reload_models(self) -> None:
        """Nạp lại model (đổi chất lượng). Chạy trên worker thread, không chặn UI."""
        self._reload.set()
        self._retry.set()

    def _worker_loop(self) -> None:
        need_load = True
        while not self._stop.is_set():
            if need_load or self._reload.is_set():
                self._reload.clear()
                self._retry.clear()
                self._ready.clear()
                self.queue.clear()
                self._asr = self._translator = None  # giải phóng model cũ trước khi nạp model mới
                need_load = not self._load_models()
                if need_load:
                    self._retry.wait()
                continue
            ev = self.queue.get(timeout=0.5)
            if ev is None or not self.ready:
                continue
            try:
                self._process(ev)
            except Exception:
                log.exception("lỗi khi xử lý đoạn %s#%d", ev.source, ev.seg_id)
                if isinstance(ev, Final):
                    self.segment_dropped.emit(ev.source, ev.seg_id)

    def _process(self, ev: Event) -> None:
        t0 = time.perf_counter()
        dur = len(ev.audio) / 16000
        if isinstance(ev, Final):
            res = self._asr.transcribe(ev.audio, "final", ev.source)
            if res is None:
                self.segment_dropped.emit(ev.source, ev.seg_id)
                return
            t1 = time.perf_counter()
            vi = self._translator.translate(res.text, res.lang)
            t2 = time.perf_counter()
            self.final_ready.emit(ev.source, ev.seg_id, res.lang, res.text, vi or "")
            log.info(
                "[%s#%d %s %.1fs] asr %.2fs, dịch %.2fs | %s => %s",
                SOURCE_LABELS.get(ev.source, ev.source), ev.seg_id, res.lang, dur, t1 - t0, t2 - t1, res.text, vi,
            )
            self.final_timing.emit(t2 - t0)
            self._check_speed(t2 - t0)
        else:
            if not self.running:
                return
            res = self._asr.transcribe(ev.audio, "partial", ev.source)
            if res is None:
                return
            self.partial_ready.emit(ev.source, ev.seg_id, res.text, "")
            # Dịch tạm câu đang nói — bỏ qua nếu đã có câu chốt đang chờ (ưu tiên độ trễ câu chốt).
            if self.cfg.translate_preview and self.queue.pending_finals() == 0:
                vi = self._translator.translate(res.text, res.lang, beam_size=1)
                if vi and self.queue.pending_finals() == 0:
                    self.partial_ready.emit(ev.source, ev.seg_id, res.text, vi)
            log.debug("partial %s#%d %.1fs: %.2fs", ev.source, ev.seg_id, dur, time.perf_counter() - t0)

    def _check_speed(self, seconds: float) -> None:
        """Gợi ý hạ chất lượng nếu máy xử lý không kịp (một lần cho mỗi lần nạp model)."""
        self._final_times.append(seconds)
        if self._slow_warned or self.profile is None or self.profile.key == "fast":
            return
        times = sorted(self._final_times)
        slow = len(times) >= 5 and times[len(times) // 2] > SLOW_FINAL_S
        if slow or self.queue.pending_finals() >= 3:
            self._slow_warned = True
            log.warning("máy xử lý chậm: %s", [round(t, 1) for t in self._final_times])
            self.slow_warning.emit(
                f"Máy xử lý chậm (~{times[len(times) // 2]:.1f} giây/câu). Chọn chất lượng thấp hơn trong menu "
                "khay (Chất lượng dịch) để phụ đề nhanh hơn."
            )
