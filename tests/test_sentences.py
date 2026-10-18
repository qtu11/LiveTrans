from livetrans.sentences import SentenceAssembler, join_text, split_complete


def test_natural_pause_commits_immediately():
    sa = SentenceAssembler()
    commits, held = sa.push("loopback", "en", "Hello everyone.", cut=False)
    assert commits == ["Hello everyone."] and held is None


def test_cut_is_held_then_merged_at_pause():
    sa = SentenceAssembler()
    commits, held = sa.push("loopback", "en", "Let me start by thanking Addison for that", cut=True)
    assert commits == [] and held == "Let me start by thanking Addison for that"
    commits, held = sa.push("loopback", "en", "magnificent introduction.", cut=False)
    assert commits == ["Let me start by thanking Addison for that magnificent introduction."]
    assert held is None


def test_false_period_removed_when_continuation_is_lowercase():
    assert join_text("for exemplifying the heart.", "excellence and determination", "en") == \
        "for exemplifying the heart excellence and determination"
    assert join_text("He arrived.", "Then he left.", "en") == "He arrived. Then he left."


def test_cjk_joined_without_space():
    assert join_text("我们明天", "早上九点开会。", "zh") == "我们明天早上九点开会。"


def test_long_chain_commits_complete_sentences_keeps_rest():
    sa = SentenceAssembler(max_parts=3)
    sa.push("mic", "en", "First sentence here. Second one starts", cut=True)
    sa.push("mic", "en", "and keeps going. Third begins", cut=True)
    commits, held = sa.push("mic", "en", "and is not done", cut=True)
    assert commits == ["First sentence here. Second one starts and keeps going."]
    assert held == "Third begins and is not done"


def test_long_chain_without_punctuation_force_commits():
    sa = SentenceAssembler(max_parts=2)
    sa.push("mic", "en", "words words words", cut=True)
    commits, held = sa.push("mic", "en", "more words without end", cut=True)
    assert commits == ["words words words more words without end"] and held is None


def test_language_change_commits_held_first():
    sa = SentenceAssembler()
    sa.push("mic", "en", "an unfinished thought", cut=True)
    commits, held = sa.push("mic", "ja", "こんにちは。", cut=False)
    assert commits == ["an unfinished thought", "こんにちは。"] and held is None
    assert sa.last_langs == ["en", "ja"]


def test_sources_are_independent_and_flush():
    sa = SentenceAssembler()
    sa.push("mic", "en", "mic part", cut=True)
    sa.push("loopback", "en", "speaker part", cut=True)
    assert sa.held("mic").text == "mic part"
    assert sa.flush("loopback") == ["speaker part"]
    assert sa.held("loopback") is None and sa.held("mic") is not None
    sa.clear()
    assert sa.held("mic") is None


def test_split_complete():
    assert split_complete("A b. C d") == ("A b.", "C d")
    assert split_complete("No end here") == ("", "No end here")
    assert split_complete("今日は晴れ。明日は") == ("今日は晴れ。", "明日は")
    assert split_complete("Version 3.5 is out") == ("", "Version 3.5 is out")
