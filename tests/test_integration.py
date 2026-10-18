import re
import time

import numpy as np
import pytest

from livetrans.config import VadConfig
from livetrans.segmenter import Final, Partial, Segmenter

pytestmark = pytest.mark.slow

FRAME = 512
DT = FRAME / 16000
VI_DIACRITICS = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.I)


def frames(audio):
    n = len(audio) // FRAME
    return audio[: n * FRAME].reshape(n, FRAME)


def test_vad_separates_speech_and_silence(speech_audio):
    from livetrans.vad import SileroVAD

    vad = SileroVAD()
    probs = np.array([vad.prob(f) for f in frames(speech_audio)])
    assert probs[:10].max() < 0.2  # 0.5 s lặng đầu
    assert (probs > 0.5).sum() > 50


@pytest.fixture(scope="module")
def engines():
    from livetrans.asr import Transcriber
    from livetrans.models import ensure_models, ensure_whisper
    from livetrans.translator import Translator

    wdir, ndir = ensure_models("small")
    asr = Transcriber(wdir, cpu_threads=4, preview_dir=ensure_whisper("base"))
    tr = Translator(ndir, cpu_threads=4)
    asr.load()
    tr.load()
    return asr, tr


def test_vietnamese_to_english(engines):
    _, tr = engines
    text = "Chào anh, cuộc họp hôm nay lùi sang 3 giờ chiều nhé.\nEm sẽ gửi tài liệu qua email trước."
    t0 = time.perf_counter()
    en = tr.translate(text, "vi", target="en")
    print(f"\n  vi->en ({time.perf_counter() - t0:.2f}s): {en!r}")
    assert en and len(en.splitlines()) == 2
    assert not VI_DIACRITICS.search(en)
    assert re.search(r"meeting", en, re.I)


LONG_SENTENCE = (
    "Let me start by thanking Addison for that magnificent introduction and for exemplifying the heart, "
    "excellence and determination that has blossomed right here on the south side for a very long time."
)


def test_continuous_speech_is_assembled_into_one_sentence(tmp_path, engines):
    """Câu nói liền ~11 giây bị cắt cưỡng bức ở 5 giây: phải ra MỘT câu chốt, không mất chữ ở chỗ cắt."""
    from conftest import _read_wav, _tts
    from PySide6.QtWidgets import QApplication

    from livetrans.config import Config
    from livetrans.pipeline import Pipeline
    from livetrans.vad import SileroVAD

    QApplication.instance() or QApplication([])  # QApplication (không phải QCoreApplication) để test sau vẽ được icon
    wav = tmp_path / "long.wav"
    _tts(wav, LONG_SENTENCE)
    audio = np.concatenate([_read_wav(wav), np.zeros(16000, np.float32)])

    asr, tr = engines
    p = Pipeline(Config(source_language="auto"))
    p._asr, p._translator = asr, tr
    p._ready.set()
    p.running = True
    finals, partials = [], []
    p.final_ready.connect(lambda s, i, lang, text, vi: finals.append((text, vi)))
    p.partial_ready.connect(lambda s, i, text, vi: partials.append((text, vi)))

    vad, seg = SileroVAD(), Segmenter("loopback", VadConfig())  # mặc định: cắt cưỡng bức ở 5 giây
    events = []
    for i, f in enumerate(frames(audio)):
        events += seg.feed(f, vad.prob(f), i * DT)
    events += seg.flush()
    cuts = [e for e in events if isinstance(e, Final) and e.cut]
    assert cuts, "câu dài phải bị cắt cưỡng bức ít nhất một lần"
    for e in events:
        if isinstance(e, Final):
            p._process(e)

    print(f"\n  {len(cuts)} lần cắt; bản tạm: {[t for t, _ in partials][-1:]}")
    for text, vi in finals:
        print(f"  CHỐT: {text}\n     => {vi}")
    assert len(finals) == 1
    text = finals[0][0].lower()
    assert "heart" in text and "excellence" in text and "blossomed" in text
    assert "it's been" not in text and "since i" not in text  # không bịa thêm câu ở chỗ cắt
    assert partials, "trong lúc chờ câu xong phải có bản dịch tạm"


def test_full_chain(speech_audio, engines):
    from livetrans.vad import SileroVAD

    asr, tr = engines
    vad = SileroVAD()
    seg = Segmenter("loopback", VadConfig())
    events = []
    for i, f in enumerate(frames(speech_audio)):
        events += seg.feed(f, vad.prob(f), i * DT)
    events += seg.flush()

    fs = [e for e in events if isinstance(e, Final)]
    ps = [e for e in events if isinstance(e, Partial)]
    print(f"\n{len(fs)} Final, {len(ps)} Partial")
    assert len(fs) >= 1

    for p in ps[:2]:
        t0 = time.perf_counter()
        r = asr.transcribe(p.audio, "partial", "loopback")
        print(f"  partial seg{p.seg_id} {len(p.audio)/16000:.1f}s -> {r and r.text!r} ({time.perf_counter()-t0:.2f}s)")

    for f in fs:
        t0 = time.perf_counter()
        r = asr.transcribe(f.audio, "final", "loopback")
        t1 = time.perf_counter()
        assert r is not None
        vi = tr.translate(r.text, r.lang)
        t2 = time.perf_counter()
        print(f"  final seg{f.seg_id} {len(f.audio)/16000:.1f}s [{r.lang} {r.lang_prob:.2f}] {r.text!r}")
        print(f"    -> {vi!r}  (asr {t1-t0:.2f}s, dịch {t2-t1:.2f}s)")
        assert r.lang == "en"
        assert vi and VI_DIACRITICS.search(vi)
