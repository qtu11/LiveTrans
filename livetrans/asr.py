"""Nhận dạng giọng nói bằng faster-whisper (CPU, int8) + lọc câu ảo."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Câu Whisper hay "bịa" ra khi gặp nhạc / tiếng ồn / im lặng.
_EXACT = {
    "you",
    "bye",
    "thank you",
    "thanks",
    "thank you for watching",
    "thanks for watching",
    "thank you so much for watching",
    "thank you very much for watching",
    "thank you for listening",
    "please subscribe",
    "subscribe",
    "ご視聴ありがとうございました",
    "ありがとうございました",
    "시청해주셔서 감사합니다",
    "감사합니다",
    "谢谢观看",
    "谢谢大家",
    "cảm ơn các bạn đã theo dõi",
    "cảm ơn các bạn đã xem video",
}
_CONTAINS = [
    "amara.org",
    "字幕由",
    "字幕志愿者",
    "明镜与点点",
    "请不吝点赞",
    "订阅转发",
    "チャンネル登録",
    "subscribe to my channel",
    "like and subscribe",
    "ghiền mì gõ",
    "subscribe cho kênh",
    "đăng ký kênh",
    "sous-titres réalisés par",
    "untertitel im auftrag",
    "untertitelung des zdf",
    "mbc 뉴스",
]
_STRIP = re.compile(r"[\s\W_]+", re.UNICODE)
_REPEAT = re.compile(r"(\D{1,25}?)\1{3,}")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    return _STRIP.sub(" ", text).strip()


def is_hallucination(text: str) -> bool:
    norm = _normalize(text)
    if not norm:
        return True
    if norm in _EXACT:
        return True
    lowered = unicodedata.normalize("NFC", text).casefold()
    return any(marker in lowered for marker in _CONTAINS)


def collapse_repeats(text: str) -> str:
    """Gộp cụm ký tự lặp liên tiếp ≥ 4 lần thành 1 (không đụng tới chữ số)."""
    text = _REPEAT.sub(r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


class StickyLanguage:
    """Giữ ngôn ngữ chắc chắn gần nhất theo từng nguồn để chống nhận diện sai ở câu ngắn."""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self._langs: dict[str, str] = {}

    def get(self, source: str) -> str | None:
        return self._langs.get(source)

    def choose(self, source: str, detected: str, prob: float) -> str:
        if prob >= self.threshold:
            self._langs[source] = detected
            return detected
        return self._langs.get(source, detected)


@dataclass(frozen=True)
class AsrResult:
    text: str
    lang: str
    lang_prob: float


def _make_model(model_dir: Path, cpu_threads: int):
    """WhisperModel có bộ nhớ đệm 1 phần tử cho encoder.

    ``transcribe(language=None)`` của faster-whisper chạy encoder 2 lần (nhận diện ngôn ngữ rồi giải mã).
    Ta tự nhận diện ngôn ngữ trên đúng tensor mà ``generate_segments`` sẽ encode, rồi gọi ``transcribe``
    với ngôn ngữ cố định → lần encode thứ hai trúng cache.
    """
    import hashlib

    from faster_whisper import WhisperModel

    class _CachedEncodeWhisper(WhisperModel):
        _enc_key = None
        _enc_out = None

        def encode(self, features):
            arr = np.ascontiguousarray(features)
            key = (arr.shape, hashlib.blake2b(arr.tobytes(), digest_size=16).digest())
            if key != self._enc_key:
                self._enc_out = super().encode(features)
                self._enc_key = key
            return self._enc_out

    return _CachedEncodeWhisper(
        str(model_dir), device="cpu", compute_type="int8", cpu_threads=cpu_threads, num_workers=1
    )


class Transcriber:
    """``final`` dùng model chính; ``partial`` dùng model xem trước (nhẹ hơn) nếu có."""

    def __init__(
        self,
        model_dir: Path,
        cpu_threads: int,
        forced_language: str | None = None,
        preview_dir: Path | None = None,
    ):
        self.model_dir = Path(model_dir)
        self.preview_dir = Path(preview_dir) if preview_dir else None
        self.cpu_threads = cpu_threads
        self.forced_language = forced_language
        self.sticky = StickyLanguage()
        self._model = None
        self._preview = None

    def load(self) -> None:
        self._model = _make_model(self.model_dir, self.cpu_threads)
        if self.preview_dir and self.preview_dir != self.model_dir:
            self._preview = _make_model(self.preview_dir, self.cpu_threads)
        else:
            self._preview = self._model

    @staticmethod
    def _detect(model, audio: np.ndarray) -> tuple[str, float]:
        from faster_whisper.audio import pad_or_trim

        features = model.feature_extractor(audio)
        content = features[:, : min(model.feature_extractor.nb_max_frames, features.shape[-1] - 1)]
        enc = model.encode(pad_or_trim(content))
        token, prob = model.model.detect_language(enc)[0][0]
        return token[2:-2], float(prob)

    @staticmethod
    def _run(model, audio: np.ndarray, language: str, mode: str) -> str:
        final = mode == "final"
        segments, _ = model.transcribe(
            audio,
            language=language,
            beam_size=3 if final else 1,
            best_of=3 if final else 1,
            temperature=[0.0, 0.4, 0.8] if final else 0.0,
            without_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        parts = []
        for seg in segments:
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                continue
            parts.append(seg.text.strip())
        return " ".join(p for p in parts if p)

    def transcribe(self, audio: np.ndarray, mode: str, source: str) -> AsrResult | None:
        if self._model is None:
            raise RuntimeError("Transcriber chưa được load()")
        model = self._model if mode == "final" else self._preview
        prob = 1.0
        if self.forced_language:
            lang = self.forced_language
        elif mode == "partial" and self.sticky.get(source):
            lang = self.sticky.get(source)
        else:
            detected, prob = self._detect(model, audio)
            lang = self.sticky.choose(source, detected, prob) if mode == "final" else detected
            if lang != detected:
                log.debug("ngôn ngữ %s (%.2f) không chắc, dùng lại %s", detected, prob, lang)

        text = collapse_repeats(self._run(model, audio, lang, mode))
        if is_hallucination(text):
            return None
        return AsrResult(text=text, lang=lang, lang_prob=prob)
