from livetrans.asr import StickyLanguage, collapse_repeats, is_hallucination


def test_hallucinations_detected():
    for text in [
        "Thanks for watching!",
        "Thank you for watching.",
        "字幕由Amara.org社区提供",
        "ご視聴ありがとうございました",
        "Please subscribe to my channel",
        "Hãy subscribe cho kênh Ghiền Mì Gõ để không bỏ lỡ những video hấp dẫn",
        "...",
        "",
    ]:
        assert is_hallucination(text), text


def test_real_speech_not_hallucination():
    for text in [
        "Hello everyone, welcome back to the show.",
        "今日はいい天気ですね",
        "We need to thank you for watching the kids last night.",
    ]:
        assert not is_hallucination(text), text


def test_collapse_repeats():
    assert collapse_repeats("go go go go go now") == "go now"
    assert collapse_repeats("谢谢谢谢谢谢") == "谢"
    assert collapse_repeats("1000000 dollars") == "1000000 dollars"
    assert collapse_repeats("I think I think we should go") == "I think I think we should go"
    assert collapse_repeats("  hello  ") == "hello"


def test_sticky_language():
    s = StickyLanguage(threshold=0.6)
    assert s.get("loopback") is None
    assert s.choose("loopback", "en", 0.9) == "en"
    assert s.choose("loopback", "de", 0.3) == "en"
    assert s.choose("loopback", "de", 0.8) == "de"
    assert s.get("loopback") == "de"
    assert s.choose("mic", "fr", 0.3) == "fr"
    assert s.get("mic") is None
