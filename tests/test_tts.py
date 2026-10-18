import threading
import time

import numpy as np
from PySide6.QtCore import QCoreApplication

from livetrans.tts import MAX_PENDING, SPEEDS, Speaker

APP = QCoreApplication.instance() or QCoreApplication([])


class FakeEngine:
    sample_rate = 22050

    def __init__(self, block: threading.Event | None = None):
        self.block = block
        self.synth = []
        self.played = []
        self.interrupted = []

    def synthesize(self, text, length_scale):
        self.synth.append((text, length_scale))
        return np.full(100, 10000, dtype=np.int16)

    def play(self, audio, should_stop):
        self.played.append(int(audio[0]))
        if self.block is not None:
            while not self.block.is_set():
                if should_stop():
                    self.interrupted.append(True)
                    return
                time.sleep(0.01)


def wait_for(pred, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        APP.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_speaks_in_order_with_speed_and_volume():
    eng = FakeEngine()
    sp = Speaker(speed="fast", volume=0.5, engine_factory=lambda: eng)
    sp.say("một")
    sp.say("hai")
    assert wait_for(lambda: len(eng.played) == 2)
    sp.close()
    assert [t for t, _ in eng.synth] == ["một", "hai"]
    assert eng.synth[0][1] == SPEEDS["fast"]
    assert eng.played == [5000, 5000]  # âm lượng 0,5


def test_backlog_drops_oldest_when_behind():
    gate = threading.Event()
    eng = FakeEngine(block=gate)
    sp = Speaker(engine_factory=lambda: eng)
    sp.say("câu 1")
    assert wait_for(lambda: len(eng.played) == 1)  # đang đọc câu 1
    for i in range(2, 7):
        sp.say(f"câu {i}")
    gate.set()
    assert wait_for(lambda: len(eng.synth) == 1 + MAX_PENDING)
    sp.close()
    assert [t for t, _ in eng.synth] == ["câu 1", "câu 5", "câu 6"]


def test_stop_speaking_interrupts_and_clears():
    gate = threading.Event()
    eng = FakeEngine(block=gate)
    sp = Speaker(engine_factory=lambda: eng)
    sp.say("dài")
    sp.say("tiếp")
    assert wait_for(lambda: len(eng.played) == 1)
    sp.stop_speaking()
    assert wait_for(lambda: eng.interrupted == [True])
    gate.set()
    time.sleep(0.1)
    sp.close()
    assert [t for t, _ in eng.synth] == ["dài"]


def test_load_error_reported():
    states = []

    def boom():
        raise RuntimeError("không có file giọng")

    sp = Speaker(engine_factory=boom)
    sp.state_changed.connect(lambda s, d: states.append((s, d)))
    sp.say("xin chào")
    assert wait_for(lambda: any(s == "error" for s, _ in states))
    sp.close()
    assert "không có file giọng" in [d for s, d in states if s == "error"][0]


def test_empty_text_ignored():
    eng = FakeEngine()
    sp = Speaker(engine_factory=lambda: eng)
    sp.say("   ")
    time.sleep(0.1)
    sp.close()
    assert eng.synth == []
