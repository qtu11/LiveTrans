import threading
import time

import numpy as np
from PySide6.QtCore import QCoreApplication

from livetrans.tts import EDGE_RATE, MAX_PENDING, PIPER, SPEEDS, Speaker, boosted, decode_mp3

APP = QCoreApplication.instance() or QCoreApplication([])
VOICE_ONLINE = "vi-VN-HoaiMyNeural"


class FakeEngine:
    def __init__(self, name="piper", fail=False):
        self.name = name
        self.fail = fail
        self.synth = []

    def synthesize(self, text, speed):
        self.synth.append((text, speed))
        if self.fail:
            raise OSError("mất mạng")
        return np.full(100, 10000, dtype=np.int16), 22050


class FakePlayer:
    """Ghi lại (âm thanh đầu, sample rate); có thể chặn để giả lập câu dài."""

    def __init__(self, block: threading.Event | None = None):
        self.block = block
        self.played = []
        self.interrupted = []

    def __call__(self, audio, rate, should_stop):
        self.played.append((int(audio[0]), rate))
        if self.block is not None:
            while not self.block.is_set():
                if should_stop():
                    self.interrupted.append(True)
                    return
                time.sleep(0.01)


def make(engines: dict, player: FakePlayer, **kw) -> Speaker:
    return Speaker(engine_factory=lambda voice: engines[voice], player=player, **kw)


def wait_for(pred, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        APP.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_speaks_in_order_with_speed_and_volume():
    eng, player = FakeEngine(), FakePlayer()
    sp = make({PIPER: eng}, player, speed="fast", volume=0.5)
    sp.say("một")
    assert wait_for(lambda: len(player.played) == 1)
    sp.say("hai")  # câu trước đã đọc xong → không bị tụt lại → giữ tốc độ đã chọn
    assert wait_for(lambda: len(player.played) == 2)
    sp.close()
    assert eng.synth == [("một", "fast"), ("hai", "fast")]
    assert SPEEDS["fast"] < 1
    assert player.played == [(5000, 22050), (5000, 22050)]  # âm lượng 0,5


def test_backlog_keeps_newest_when_behind():
    gate = threading.Event()
    eng, player = FakeEngine(), FakePlayer(block=gate)
    sp = make({PIPER: eng}, player)
    sp.say("câu 1")
    assert wait_for(lambda: len(player.played) == 1)  # đang đọc câu 1
    for i in range(2, 9):
        sp.say(f"câu {i}")
    assert wait_for(lambda: any(t == "câu 8" for t, _ in eng.synth))
    gate.set()
    assert wait_for(lambda: len(player.played) == 1 + MAX_PENDING)
    time.sleep(0.1)
    sp.close()
    assert len(player.played) == 1 + MAX_PENDING  # chỉ đọc câu 1 + 2 câu mới nhất


def test_prefetch_synthesizes_next_while_playing():
    gate = threading.Event()
    eng, player = FakeEngine(), FakePlayer(block=gate)
    sp = make({PIPER: eng}, player)
    sp.say("câu 1")
    assert wait_for(lambda: len(player.played) == 1)
    sp.say("câu 2")
    assert wait_for(lambda: len(eng.synth) == 2)  # đã tổng hợp sẵn câu 2 trong lúc câu 1 còn đọc
    assert len(player.played) == 1
    gate.set()
    sp.close()


def test_reads_faster_when_behind():
    gate = threading.Event()
    eng, player = FakeEngine(), FakePlayer(block=gate)
    sp = make({PIPER: eng}, player, speed="fast")
    sp.say("câu 1")
    assert wait_for(lambda: len(player.played) == 1)  # đang đọc câu 1
    sp.say("câu 2")  # tới khi máy còn đang đọc → tổng hợp nhanh hơn một bậc
    assert wait_for(lambda: len(eng.synth) == 2)
    gate.set()
    sp.close()
    assert eng.synth == [("câu 1", "fast"), ("câu 2", "faster")]
    assert boosted("rush") == "rush" and boosted("slow") == "normal"


def test_stop_speaking_interrupts_and_clears():
    gate = threading.Event()
    eng, player = FakeEngine(), FakePlayer(block=gate)
    sp = make({PIPER: eng}, player)
    sp.say("dài")
    assert wait_for(lambda: len(player.played) == 1)
    sp.say("tiếp")
    sp.stop_speaking()
    assert wait_for(lambda: player.interrupted == [True])
    gate.set()
    time.sleep(0.15)
    sp.close()
    assert len(player.played) == 1


def test_online_failure_falls_back_to_piper():
    online, offline, player = FakeEngine(VOICE_ONLINE, fail=True), FakeEngine(), FakePlayer()
    states = []
    sp = make({VOICE_ONLINE: online, PIPER: offline}, player, voice=VOICE_ONLINE)
    sp.state_changed.connect(lambda s, d: states.append(s))
    sp.say("xin chào")
    assert wait_for(lambda: len(player.played) == 1)
    sp.close()
    assert online.synth and offline.synth == [("xin chào", "fast")]
    assert "fallback" in states


def test_online_cooldown_skips_online_then_retries():
    online, offline, player = FakeEngine(VOICE_ONLINE, fail=True), FakeEngine(), FakePlayer()
    now = [100.0]
    sp = make({VOICE_ONLINE: online, PIPER: offline}, player, voice=VOICE_ONLINE, clock=lambda: now[0])
    sp.say("một")
    assert wait_for(lambda: len(player.played) == 1)
    sp.say("hai")  # trong 45 giây sau lỗi → không thử online
    assert wait_for(lambda: len(player.played) == 2)
    assert len(online.synth) == 1
    now[0] += 46  # hết thời gian chờ → thử online lại
    online.fail = False
    sp.say("ba")
    assert wait_for(lambda: len(player.played) == 3)
    sp.close()
    assert [t for t, _ in online.synth] == ["một", "ba"]
    assert [t for t, _ in offline.synth] == ["một", "hai"]


def test_set_voice_switches_engine():
    a, b, player = FakeEngine(), FakeEngine(VOICE_ONLINE), FakePlayer()
    sp = make({PIPER: a, VOICE_ONLINE: b}, player)
    sp.say("một")
    assert wait_for(lambda: len(player.played) == 1)
    sp.set_voice(VOICE_ONLINE)
    sp.say("hai")
    assert wait_for(lambda: len(player.played) == 2)
    sp.close()
    assert [t for t, _ in a.synth] == ["một"] and [t for t, _ in b.synth] == ["hai"]


def test_unknown_voice_falls_back_to_piper():
    assert Speaker(voice="không-có").voice == PIPER


def test_load_error_reported():
    states = []

    def boom(voice):
        raise RuntimeError("không có file giọng")

    sp = Speaker(engine_factory=boom, player=FakePlayer())
    sp.state_changed.connect(lambda s, d: states.append((s, d)))
    sp.start()
    assert wait_for(lambda: any(s == "error" for s, _ in states))
    sp.close()
    assert "không có file giọng" in [d for s, d in states if s == "error"][0]


def test_empty_text_ignored():
    eng, player = FakeEngine(), FakePlayer()
    sp = make({PIPER: eng}, player)
    sp.say("   ")
    time.sleep(0.1)
    sp.close()
    assert eng.synth == []


def test_decode_mp3_roundtrip():
    import io

    import av

    buf = io.BytesIO()
    with av.open(buf, "w", format="mp3") as out:
        stream = out.add_stream("mp3", rate=EDGE_RATE)
        stream.layout = "mono"
        tone = (np.sin(np.arange(EDGE_RATE) * 2 * np.pi * 440 / EDGE_RATE) * 8000).astype(np.int16)
        frame = av.AudioFrame.from_ndarray(tone.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = EDGE_RATE
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    audio = decode_mp3(buf.getvalue())
    assert audio.dtype == np.int16
    assert abs(len(audio) - EDGE_RATE) < EDGE_RATE * 0.1
    assert np.abs(audio).max() > 4000
