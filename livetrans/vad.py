"""Silero VAD (ONNX đi kèm faster-whisper) chạy streaming từng khung 512 mẫu, có trạng thái."""

from __future__ import annotations

import os
import threading

import numpy as np

# Import ngay ở main thread: import song song từ nhiều thread (worker + audio) gây _DeadlockError.
import onnxruntime
from faster_whisper.utils import get_assets_path

FRAME = 512
CONTEXT = 64

_session = None
_session_lock = threading.Lock()


def _get_session():
    global _session
    with _session_lock:
        if _session is None:
            opts = onnxruntime.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            opts.enable_cpu_mem_arena = False
            opts.log_severity_level = 4
            _session = onnxruntime.InferenceSession(
                os.path.join(get_assets_path(), "silero_vad_v6.onnx"),
                providers=["CPUExecutionProvider"],
                sess_options=opts,
            )
        return _session


class SileroVAD:
    def __init__(self) -> None:
        self._session = _get_session()
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)

    def prob(self, frame: np.ndarray) -> float:
        frame = np.asarray(frame, dtype=np.float32)
        if frame.shape != (FRAME,):
            raise ValueError(f"cần khung {FRAME} mẫu, nhận {frame.shape}")
        x = np.concatenate([self._context, frame])[None, :]
        out, self._h, self._c = self._session.run(None, {"input": x, "h": self._h, "c": self._c})
        self._context = frame[-CONTEXT:].copy()
        return float(np.asarray(out).reshape(-1)[0])
