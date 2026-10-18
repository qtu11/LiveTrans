"""Hàng đợi ưu tiên cho worker: Final (FIFO) luôn trước Partial (mỗi nguồn chỉ giữ bản mới nhất)."""

from __future__ import annotations

import threading
import time
from collections import deque

from .segmenter import Event, Final, Partial


class WorkQueue:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._finals: deque[Final] = deque()
        self._partials: dict[str, Partial] = {}
        self._finalized: dict[str, int] = {}  # source -> seg_id lớn nhất đã có Final
        self._closed = False

    def put(self, ev: Event) -> None:
        with self._cond:
            if self._closed:
                return
            if isinstance(ev, Final):
                self._finals.append(ev)
                self._finalized[ev.source] = max(ev.seg_id, self._finalized.get(ev.source, 0))
                pending = self._partials.get(ev.source)
                if pending is not None and pending.seg_id <= ev.seg_id:
                    del self._partials[ev.source]
            else:
                if ev.seg_id <= self._finalized.get(ev.source, 0):
                    return
                self._partials.pop(ev.source, None)
                self._partials[ev.source] = ev  # đưa xuống cuối thứ tự
            self._cond.notify()

    def get(self, timeout: float | None) -> Event | None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while True:
                if self._closed:
                    return None
                if self._finals:
                    return self._finals.popleft()
                if self._partials:
                    source = next(iter(self._partials))
                    return self._partials.pop(source)
                if deadline is None:
                    self._cond.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._cond.wait(remaining)

    def pending_finals(self) -> int:
        with self._cond:
            return len(self._finals)

    def clear(self, partials_only: bool = False) -> None:
        with self._cond:
            self._partials.clear()
            if not partials_only:
                self._finals.clear()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
