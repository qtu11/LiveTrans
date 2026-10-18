"""Dịch văn bản gõ tay (Việt → Anh) trên thread riêng, chỉ giữ yêu cầu mới nhất."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from .translator import Translator

log = logging.getLogger(__name__)

# Văn bản gõ tay không cần nhanh như phụ đề → beam lớn hơn cho bản dịch đầy đủ, tự nhiên hơn.
TEXT_BEAM = 5
TEXT_REPETITION_PENALTY = 1.0


class TextTranslateService(QObject):
    finished = Signal(int, str, str)  # request_id, source text, translation
    failed = Signal(int, str)  # request_id, lỗi

    def __init__(self, get_translator: Callable[[], Translator | None], src: str = "vi", tgt: str = "en"):
        super().__init__()
        self._get_translator = get_translator
        self.src, self.tgt = src, tgt
        self._cond = threading.Condition()
        self._pending: tuple[int, str] | None = None
        self._next_id = 0
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="text-translate", daemon=True)
        self._thread.start()

    def request(self, text: str) -> int:
        """Xếp yêu cầu dịch; yêu cầu cũ chưa chạy sẽ bị thay thế. Trả về id."""
        with self._cond:
            self._next_id += 1
            self._pending = (self._next_id, text)
            self._cond.notify()
            return self._next_id

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify()
        self._thread.join(timeout=3)

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._pending is None and not self._closed:
                    self._cond.wait()
                if self._closed:
                    return
                req_id, text = self._pending
                self._pending = None
            translator = self._get_translator()
            if translator is None or not translator.loaded:
                self.failed.emit(req_id, "Model dịch đang được nạp, thử lại sau giây lát…")
                continue
            try:
                out = translator.translate(
                    text, self.src, target=self.tgt,
                    beam_size=TEXT_BEAM, repetition_penalty=TEXT_REPETITION_PENALTY,
                )
            except Exception as e:
                log.exception("dịch văn bản lỗi")
                self.failed.emit(req_id, f"Lỗi khi dịch: {e}")
                continue
            self.finished.emit(req_id, text, out or "")
