"""Ghép các mẩu nhận dạng thành câu trước khi dịch.

Segmenter cắt cưỡng bức khi người nói chưa dừng (``Final.cut``). Mẩu đó thường dừng giữa câu, Whisper lại hay
thêm dấu chấm ở cuối → dịch riêng từng mẩu sẽ sai nghĩa. Ở đây mẩu bị cắt được giữ lại và ghép với mẩu kế tiếp;
câu chỉ được "chốt" (dịch chính thức, đọc to) khi người nói ngừng thật, hoặc khi chuỗi quá dài.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NO_SPACE_LANGS = {"zh", "yue", "ja", "th", "lo", "km", "my"}
_TERMINAL = ".!?…。！？"
# Kết thúc câu: dấu câu rồi khoảng trắng (Latin…) hoặc dấu câu kiểu CJK (không cần khoảng trắng)
_BOUNDARY = re.compile(r"(?:[.!?…](?=\s)|[。！？])")


def join_text(left: str, right: str, lang: str) -> str:
    left, right = left.strip(), right.strip()
    if not left:
        return right
    if not right:
        return left
    if lang in NO_SPACE_LANGS:
        return left + right
    # Whisper hay thêm "." ở chỗ bị cắt; mẩu sau viết thường → câu chưa kết thúc
    if left[-1] == "." and not left.endswith("...") and right[0].islower():
        left = left[:-1]
    return f"{left} {right}"


def split_complete(text: str) -> tuple[str, str]:
    """(các câu đã trọn vẹn, phần còn dở). Dấu câu ở cuối chuỗi không tính (có thể do bị cắt)."""
    last = None
    for m in _BOUNDARY.finditer(text):
        if m.end() < len(text.rstrip()):
            last = m
    if last is None:
        return "", text.strip()
    return text[: last.end()].strip(), text[last.end() :].strip()


@dataclass
class Held:
    lang: str
    text: str
    parts: int = 1


@dataclass
class SentenceAssembler:
    max_parts: int = 3  # ~15 giây nói liền với mẩu 5 giây
    max_chars: int = 300
    _held: dict[str, Held] = field(default_factory=dict)
    last_langs: list[str] = field(default_factory=list)  # ngôn ngữ của từng câu trong lần push gần nhất

    def held(self, source: str) -> Held | None:
        return self._held.get(source)

    def push(self, source: str, lang: str, text: str, cut: bool) -> tuple[list[str], str | None]:
        """Thêm một mẩu đã nhận dạng. Trả về (các câu cần chốt, phần đang giữ hoặc None)."""
        commits: list[str] = []
        self.last_langs = []
        held = self._held.pop(source, None)
        if held is not None and held.lang != lang:
            commits.append(held.text)
            self.last_langs.append(held.lang)
            held = None
        merged = join_text(held.text, text, lang) if held else text.strip()
        parts = held.parts + 1 if held else 1

        if not cut:
            if merged:
                commits.append(merged)
                self.last_langs.append(lang)
            return commits, None

        if parts >= self.max_parts or len(merged) >= self.max_chars:
            done, rest = split_complete(merged)
            if not done:  # không có ranh giới câu nào → chốt cả đoạn để không trễ mãi
                done, rest = merged, ""
            commits.append(done)
            self.last_langs.append(lang)
            merged, parts = rest, 1
        if merged:
            self._held[source] = Held(lang, merged, parts)
            return commits, merged
        return commits, None

    def flush(self, source: str) -> list[str]:
        held = self._held.pop(source, None)
        return [held.text] if held else []

    def clear(self) -> None:
        self._held.clear()
