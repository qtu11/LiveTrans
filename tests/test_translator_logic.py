from pathlib import Path

from livetrans.translator import WHISPER_TO_NLLB, Translator, nllb_code, split_sentences


def make():
    return Translator(Path("does-not-exist"), cpu_threads=1)  # không load model


def test_codes():
    assert nllb_code("en") == "eng_Latn"
    assert nllb_code("zh") == "zho_Hans"
    assert nllb_code("ja") == "jpn_Jpan"
    assert nllb_code("ko") == "kor_Hang"
    assert nllb_code("vi") == "vie_Latn"
    assert nllb_code("xx") is None
    assert len(WHISPER_TO_NLLB) >= 40


def test_vietnamese_passthrough():
    assert make().translate("Xin chào", "vi") == "Xin chào"


def test_unsupported_language_returns_none():
    assert make().translate("something", "xx") is None


def test_empty_text():
    assert make().translate("   ", "en") == ""


def test_same_language_passthrough_any_target():
    assert make().translate("Hello there", "en", target="en") == "Hello there"


def test_unsupported_target_returns_none():
    assert make().translate("Xin chào", "vi", target="xx") is None


def test_split_sentences():
    assert split_sentences("Xin chào. Bạn khỏe không?  Tôi ổn!") == ["Xin chào.", "Bạn khỏe không?", "Tôi ổn!"]
    assert split_sentences("今日は。明日は？") == ["今日は。明日は？"]  # không có khoảng trắng → giữ nguyên
    assert split_sentences("   ") == []
    assert split_sentences("3.5 triệu đồng") == ["3.5 triệu đồng"]
