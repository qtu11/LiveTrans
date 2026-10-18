"""Bắt âm thanh loa (WASAPI loopback) hoặc micro, trả về float32 mono 16 kHz."""

from __future__ import annotations

import ctypes
import logging
import queue
import threading
import time
from collections.abc import Callable
from fractions import Fraction

import numpy as np

log = logging.getLogger(__name__)

TARGET_RATE = 16000
SOURCE_LABELS = {"loopback": "Loa", "mic": "Micro"}

# Loopback WASAPI không gửi dữ liệu khi không có âm thanh phát ra. Sau khoảng lặng này ta mở lại
# stream để bám theo thiết bị loa mặc định mới (cắm tai nghe, đổi loa…).
_LOOPBACK_REOPEN_AFTER_S = 3.0
_RETRY_DELAY_S = 2.0
_COINIT_APARTMENTTHREADED = 0x2
_COINIT_MULTITHREADED = 0x0

# PortAudio không an toàn khi khởi tạo/giải phóng song song từ nhiều thread → dùng chung một instance,
# mọi lệnh gọi PortAudio (trừ callback) đều đi qua _pa_lock.
_pa_lock = threading.RLock()
_pa = None
_open_streams = 0


def _portaudio(refresh: bool):
    """Instance PyAudio dùng chung. ``refresh`` khởi tạo lại (để thấy thiết bị mới/thiết bị mặc định mới)
    — chỉ khi không còn stream nào đang mở. Gọi khi đang giữ ``_pa_lock``."""
    global _pa
    import pyaudiowpatch as pyaudio

    if _pa is not None and refresh and _open_streams == 0:
        _pa.terminate()
        _pa = None
    if _pa is None:
        _pa = pyaudio.PyAudio()
    return _pa


def shutdown_portaudio() -> None:
    global _pa
    with _pa_lock:
        if _pa is not None and _open_streams == 0:
            _pa.terminate()
            _pa = None


def open_output_stream(rate: int, channels: int = 1):
    """Luồng phát int16 trên thiết bị ra mặc định (dùng cho giọng đọc). Đóng bằng ``close_stream``."""
    global _open_streams
    import pyaudiowpatch as pyaudio

    with _pa_lock:
        stream = _portaudio(refresh=False).open(
            format=pyaudio.paInt16, channels=channels, rate=rate, output=True, frames_per_buffer=max(1, rate // 20)
        )
        _open_streams += 1
        return stream


def close_stream(stream) -> None:
    global _open_streams
    with _pa_lock:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass
        _open_streams -= 1


def to_mono(data: bytes, channels: int) -> np.ndarray:
    samples = np.frombuffer(data, dtype=np.float32)
    if channels <= 1:
        return samples
    return samples.reshape(-1, channels).mean(axis=1, dtype=np.float32)


class Resampler:
    """Chuyển float32 mono từ ``rate_in`` sang 16 kHz theo luồng (PyAV / libswresample)."""

    def __init__(self, rate_in: int):
        self.rate_in = rate_in
        self._pts = 0
        self._r = None
        if rate_in != TARGET_RATE:
            import av

            self._r = av.AudioResampler(format="flt", layout="mono", rate=TARGET_RATE)

    def process(self, mono: np.ndarray) -> np.ndarray:
        if self._r is None:
            return mono
        import av

        frame = av.AudioFrame.from_ndarray(
            np.ascontiguousarray(mono, dtype=np.float32).reshape(1, -1), format="flt", layout="mono"
        )
        frame.sample_rate = self.rate_in
        frame.time_base = Fraction(1, self.rate_in)
        frame.pts = self._pts
        self._pts += len(mono)
        out = self._r.resample(frame)
        if not out:
            return np.empty(0, dtype=np.float32)
        return np.concatenate([f.to_ndarray().reshape(-1) for f in out]).astype(np.float32, copy=False)


class AudioSource:
    def __init__(
        self,
        kind: str,
        on_audio: Callable[[np.ndarray], None],
        on_status: Callable[[str], None] = lambda s: None,
        exclude_self: bool = False,
    ):
        if kind not in SOURCE_LABELS:
            raise ValueError(kind)
        self.kind = kind
        self.label = SOURCE_LABELS[kind]
        self.on_audio = on_audio
        self.on_status = on_status
        # Loa: bỏ tiếng của chính LiveTrans (giọng đọc) bằng process loopback, nếu Windows hỗ trợ
        self.exclude_self = exclude_self and kind == "loopback"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"audio-{self.kind}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    # ------------------------------------------------------------------
    def _find_device(self, pa) -> dict:
        import pyaudiowpatch as pyaudio

        if self.kind == "loopback":
            return pa.get_default_wasapi_loopback()
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        index = wasapi["defaultInputDevice"]
        if index is None or index < 0:
            raise OSError("không có micro")
        return pa.get_device_info_by_index(index)

    def _run(self) -> None:
        # WASAPI cần COM trên chính thread mở stream (PortAudio chỉ khởi tạo COM ở thread gọi Pa_Initialize).
        # Process loopback kích hoạt bất đồng bộ → dùng MTA; PortAudio chấp nhận cả hai.
        ole32 = ctypes.windll.ole32
        mode = _COINIT_MULTITHREADED if self.exclude_self else _COINIT_APARTMENTTHREADED
        com_ok = ole32.CoInitializeEx(None, mode) in (0, 1)  # S_OK / S_FALSE
        try:
            if not (self.exclude_self and self._process_loopback_loop()):
                self._capture_loop()
        finally:
            if com_ok:
                ole32.CoUninitialize()

    def _process_loopback_loop(self) -> bool:
        """Bắt loa trừ tiếng của LiveTrans. Trả về False nếu Windows không hỗ trợ (→ dùng loopback thường)."""
        from .process_loopback import ProcessLoopbackCapture

        cap = ProcessLoopbackCapture()
        try:
            cap.start()
        except OSError as e:
            log.warning("process loopback không dùng được (%s) → dùng loopback thường", e)
            cap.stop()
            return False
        log.info("%s: bắt âm thanh hệ thống trừ tiếng của LiveTrans (process loopback)", self.label)
        try:
            while not self._stop.is_set():
                data = cap.read()
                if data.size:
                    self.on_audio(data)
                else:
                    self._stop.wait(0.02)
        except OSError as e:
            log.warning("process loopback lỗi (%s) → dùng loopback thường", e)
            return False
        finally:
            cap.stop()
        return True

    def _capture_loop(self) -> None:
        global _open_streams
        import pyaudiowpatch as pyaudio

        failed = False
        last_device = None
        while not self._stop.is_set():
            stream = None
            try:
                chunks: queue.Queue[bytes] = queue.Queue(maxsize=1000)

                def callback(in_data, frame_count, time_info, status):
                    try:
                        chunks.put_nowait(in_data)
                    except queue.Full:
                        pass
                    return (None, pyaudio.paContinue)

                with _pa_lock:
                    pa = _portaudio(refresh=True)
                    dev = self._find_device(pa)
                    rate = int(dev["defaultSampleRate"])
                    channels = max(1, int(dev["maxInputChannels"]))
                    stream = pa.open(
                        format=pyaudio.paFloat32,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=dev["index"],
                        frames_per_buffer=max(1, rate // 50),
                        stream_callback=callback,
                    )
                    _open_streams += 1
                if dev["name"] != last_device:
                    log.info("%s: %s (%d Hz, %d kênh)", self.label, dev["name"], rate, channels)
                    last_device = dev["name"]
                if failed:
                    self.on_status(f"{self.label}: đã kết nối lại ({dev['name']})")
                    failed = False

                resampler = Resampler(rate)
                last_sound = time.monotonic()
                while not self._stop.is_set():
                    try:
                        data = chunks.get(timeout=0.2)
                    except queue.Empty:
                        with _pa_lock:
                            active = stream.is_active()
                        if not active:
                            raise OSError("stream đã dừng")
                        if (
                            self.kind == "loopback"
                            and _open_streams == 1  # chỉ khởi tạo lại PortAudio được khi không còn stream khác
                            and time.monotonic() - last_sound > _LOOPBACK_REOPEN_AFTER_S
                        ):
                            break  # mở lại để bám thiết bị loa mặc định
                        continue
                    mono = to_mono(data, channels)
                    if mono.size and float(np.abs(mono).max()) > 1e-5:
                        last_sound = time.monotonic()
                    out = resampler.process(mono)
                    if out.size:
                        self.on_audio(out)
            except Exception as e:  # thiết bị lỗi / bị rút / không có
                log.warning("%s: lỗi thiết bị: %s", self.label, e)
                if not failed:
                    self.on_status(f"{self.label}: lỗi thiết bị ({e}). Đang thử lại…")
                    failed = True
                self._stop.wait(_RETRY_DELAY_S)
            finally:
                if stream is not None:
                    with _pa_lock:
                        try:
                            stream.stop_stream()
                            stream.close()
                        except Exception:
                            pass
                        _open_streams -= 1


if __name__ == "__main__":
    import sys

    kind = sys.argv[1] if len(sys.argv) > 1 else "loopback"
    logging.basicConfig(level=logging.INFO)
    received = []
    src = AudioSource(kind, received.append, print)
    src.start()
    for _ in range(5):
        time.sleep(1)
        audio = np.concatenate(received) if received else np.zeros(1, np.float32)
        received.clear()
        print(f"{len(audio) / TARGET_RATE:.2f}s @16k, RMS={float(np.sqrt(np.mean(audio**2))):.4f}")
    src.stop()
