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
