import numpy as np

from livetrans.config import VadConfig
from livetrans.segmenter import Final, Partial, Segmenter

# Các test dưới đây tính theo bộ tham số "standard" (lặng 600 ms, tối đa 8 s, xem trước mỗi 2 s)
CFG = VadConfig(min_silence_ms=600, max_segment_s=8.0, partial_interval_s=2.0)

FRAME = 512
DT = FRAME / 16000  # 0.032 s


def run(seg: Segmenter, probs, start_index: int = 0, values=None):
    """Feed one frame per prob; returns (events, last_now)."""
    events = []
    now = 0.0
    for k, p in enumerate(probs):
        i = start_index + k
        now = i * DT
        val = values[k] if values is not None else 0.0
        events += seg.feed(np.full(FRAME, val, dtype=np.float32), p, now)
    return events, now


def finals(events):
    return [e for e in events if isinstance(e, Final)]


def partials(events):
    return [e for e in events if isinstance(e, Partial)]


def test_speech_then_silence_emits_one_final():
    seg = Segmenter("loopback", CFG)
    events, _ = run(seg, [0.9] * 63 + [0.05] * 31)
    fs = finals(events)
    assert len(fs) == 1
    assert fs[0].seg_id == 1
    assert fs[0].source == "loopback"
    dur = len(fs[0].audio) / 16000
    assert 2.0 <= dur <= 2.5


def test_short_blip_dropped():
    seg = Segmenter("mic", CFG)
    events, _ = run(seg, [0.9] * 5 + [0.05] * 30)
    assert finals(events) == []


def test_partials_every_interval():
    seg = Segmenter("mic", CFG)
    events, _ = run(seg, [0.9] * 157)
    ps = partials(events)
    assert len(ps) == 2
    assert {p.seg_id for p in ps} == {1}
    assert len(ps[1].audio) > len(ps[0].audio)
    assert finals(events) == []


def test_max_segment_cut_at_lowest_prob():
    seg = Segmenter("loopback", CFG)
    probs = [0.9] * 312
    probs[225] = 0.4  # ~7.2 s
    events, _ = run(seg, probs)
    fs = finals(events)
    assert len(fs) == 1
    n_frames = len(fs[0].audio) / FRAME
    assert abs(n_frames - 226) <= 1
    rest = seg.flush()
    assert len(rest) == 1 and isinstance(rest[0], Final)
    assert rest[0].seg_id == 2


def test_tick_closes_segment_when_data_stops():
    seg = Segmenter("loopback", CFG)
    events, now = run(seg, [0.9] * 32)
    assert finals(events) == []
    assert seg.tick(now + 0.3) == []
    out = seg.tick(now + 0.7)
    assert len(out) == 1 and isinstance(out[0], Final)
    assert seg.tick(now + 1.5) == []


def test_pre_roll_included():
    seg = Segmenter("mic", CFG)
    probs = [0.05] * 10 + [0.9] * 40 + [0.05] * 25
    values = [i / 1000 for i in range(len(probs))]
    events, _ = run(seg, probs, values=values)
    fs = finals(events)
    assert len(fs) == 1
    # 6 khung đệm trước (khung 4..9) đứng trước khung nói đầu tiên (khung 10)
    assert np.isclose(fs[0].audio[0], 4 / 1000)
    assert np.isclose(fs[0].audio[6 * FRAME], 10 / 1000)


def test_seg_ids_increase_across_segments_and_reset():
    seg = Segmenter("mic", CFG)
    events, _ = run(seg, [0.9] * 20 + [0.05] * 25 + [0.9] * 20 + [0.05] * 25)
    assert [f.seg_id for f in finals(events)] == [1, 2]
    seg.reset()
    events, _ = run(seg, [0.9] * 20 + [0.05] * 25, start_index=200)
    assert [f.seg_id for f in finals(events)] == [3]


def test_default_fast_preset_cuts_long_speech_at_5s():
    seg = Segmenter("loopback", VadConfig())  # mặc định: tối đa 5 s, lặng 450 ms
    events, _ = run(seg, [0.9] * 200)  # 6,4 s nói liền
    fs = finals(events)
    assert len(fs) == 1
    assert len(fs[0].audio) <= 157 * FRAME
    events, _ = run(seg, [0.05] * 15, start_index=200)  # 0,48 s lặng là đủ chốt câu
    assert len(finals(events)) == 1
