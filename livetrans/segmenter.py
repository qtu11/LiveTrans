"""Máy trạng thái cắt câu theo xác suất VAD (không I/O).

Nhận từng khung (512 mẫu @ 16 kHz) kèm xác suất có tiếng nói, phát ra:
- ``Partial``: toàn bộ audio của đoạn đang nói, mỗi ``partial_interval_s``.
- ``Final``: đoạn đã chốt (lặng đủ lâu, hết dữ liệu, hoặc chạm ``max_segment_s``).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from .config import VadConfig


@dataclass(frozen=True, eq=False)
class Partial:
    source: str
    seg_id: int
    audio: np.ndarray


@dataclass(frozen=True, eq=False)
class Final:
    source: str
    seg_id: int
    audio: np.ndarray
    cut: bool = False  # True: cắt cưỡng bức ở max_segment_s, người nói chưa dừng (thường giữa câu)


Event = Partial | Final

_TAIL_PAD_FRAMES = 3
_CUT_WINDOW_S = 1.5


class Segmenter:
    def __init__(self, source: str, cfg: VadConfig, sample_rate: int = 16000, frame_size: int = 512):
        self.source = source
        self.cfg = cfg
        frame_s = frame_size / sample_rate
        self._pre_roll_frames = max(0, round(cfg.pre_roll_ms / 1000 / frame_s))
        self._min_silence_frames = max(1, math.ceil(cfg.min_silence_ms / 1000 / frame_s))
        self._min_speech_frames = max(1, math.ceil(cfg.min_speech_ms / 1000 / frame_s))
        self._max_frames = max(2, int(cfg.max_segment_s / frame_s))
        self._cut_window = max(1, int(_CUT_WINDOW_S / frame_s))
        self._seg_counter = 0
        self.reset()

    # ------------------------------------------------------------------ API
    def reset(self) -> None:
        """Bỏ đoạn đang dở (dùng khi tạm dừng / đổi nguồn). seg_id vẫn tăng tiếp."""
        self._pre: deque[np.ndarray] = deque(maxlen=self._pre_roll_frames)
        self._in_speech = False
        self._frames: list[np.ndarray] = []
        self._probs: list[float] = []
        self._silence = 0
        self._counting = False
        self._speech_frames = 0
        self._partial_sent = False
        self._last_partial = 0.0
        self._last_data = 0.0
        self._seg_id = 0

    def feed(self, frame: np.ndarray, prob: float, now: float) -> list[Event]:
        self._last_data = now
        if not self._in_speech:
            if prob >= self.cfg.start_threshold:
                self._start_segment(frame, prob, now)
            else:
                self._pre.append(frame)
            return []

        self._frames.append(frame)
        self._probs.append(prob)
        self._update_silence(prob)

        if self._silence >= self._min_silence_frames:
            return self._finish(trim=self._silence)
        if len(self._frames) >= self._max_frames:
            return self._cut(now)
        if now - self._last_partial >= self.cfg.partial_interval_s:
            self._last_partial = now
            self._partial_sent = True
            return [Partial(self.source, self._seg_id, np.concatenate(self._frames))]
        return []

    def tick(self, now: float) -> list[Event]:
        """Gọi định kỳ: chốt đoạn khi nguồn ngừng gửi dữ liệu (loopback im lặng)."""
        if self._in_speech and now - self._last_data >= self.cfg.min_silence_ms / 1000:
            return self._finish(trim=self._silence)
        return []

    def flush(self) -> list[Event]:
        if self._in_speech:
            return self._finish(trim=self._silence)
        return []

    # ------------------------------------------------------------ internals
    def _start_segment(self, frame: np.ndarray, prob: float, now: float) -> None:
        pre = list(self._pre)
        self._pre.clear()
        self._frames = pre + [frame]
        self._probs = [0.0] * len(pre) + [prob]
        self._in_speech = True
        self._speech_frames = 1
        self._silence = 0
        self._counting = False
        self._partial_sent = False
        self._last_partial = now
        self._seg_counter += 1
        self._seg_id = self._seg_counter

    def _update_silence(self, prob: float) -> None:
        if prob >= self.cfg.start_threshold:
            self._speech_frames += 1
            self._counting = False
            self._silence = 0
        elif prob < self.cfg.end_threshold:
            self._counting = True
        if self._counting:
            self._silence += 1

    def _finish(self, trim: int) -> list[Event]:
        keep = min(len(self._frames), len(self._frames) - trim + _TAIL_PAD_FRAMES)
        events: list[Event] = []
        if self._speech_frames >= self._min_speech_frames or self._partial_sent:
            events.append(Final(self.source, self._seg_id, np.concatenate(self._frames[:keep])))
        tail = self._frames[-self._pre_roll_frames:] if self._pre_roll_frames else []
        self._in_speech = False
        self._frames = []
        self._probs = []
        self._silence = 0
        self._counting = False
        self._speech_frames = 0
        self._pre.extend(tail)
        return events

    def _cut(self, now: float) -> list[Event]:
        n = len(self._frames)
        start = max(1, n - self._cut_window)
        idx = start + int(np.argmin(self._probs[start:]))
        event = Final(self.source, self._seg_id, np.concatenate(self._frames[: idx + 1]), cut=True)

        self._frames = self._frames[idx + 1 :]
        self._probs = self._probs[idx + 1 :]
        self._seg_counter += 1
        self._seg_id = self._seg_counter
        self._speech_frames = 0
        self._silence = 0
        self._counting = False
        self._partial_sent = False
        for p in self._probs:
            self._update_silence(p)
        self._last_partial = now
        if not self._frames:
            self._in_speech = False
        return [event]
