import threading
import time

from PySide6.QtCore import QCoreApplication

from livetrans.text_translate import TEXT_BEAM, TextTranslateService

# Signal phát từ thread nền được chuyển qua hàng đợi sự kiện Qt → cần event loop để nhận.
APP = QCoreApplication.instance() or QCoreApplication([])


class FakeTranslator:
    loaded = True

    def __init__(self, delay=0.0):
        self.delay = delay
        self.calls = []
        self.started = threading.Event()

    def translate(self, text, lang, target="vi", beam_size=2, repetition_penalty=1.1):
        self.started.set()
        self.calls.append((text, lang, target, beam_size))
        time.sleep(self.delay)
        return f"EN:{text}"


def collect(service):
    done, failed, ev = [], [], threading.Event()
    service.finished.connect(lambda rid, src, out: (done.append((rid, src, out)), ev.set()))
    service.failed.connect(lambda rid, msg: (failed.append((rid, msg)), ev.set()))
    return done, failed, ev


def wait_for(pred, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        APP.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_translates_vi_to_en_with_text_beam():
    tr = FakeTranslator()
    s = TextTranslateService(lambda: tr)
    done, failed, _ = collect(s)
    rid = s.request("Xin chào")
    assert wait_for(lambda: done)
    s.close()
    assert done == [(rid, "Xin chào", "EN:Xin chào")]
    assert tr.calls == [("Xin chào", "vi", "en", TEXT_BEAM)]
    assert failed == []


def test_only_latest_pending_request_runs():
    tr = FakeTranslator(delay=0.2)
    s = TextTranslateService(lambda: tr)
    done, _, _ = collect(s)
    s.request("một")
    assert tr.started.wait(1)  # "một" đang dịch
    s.request("hai")
    last = s.request("ba")  # "hai" bị thay thế trước khi chạy
    assert wait_for(lambda: any(r == last for r, *_ in done))
    s.close()
    assert [c[0] for c in tr.calls] == ["một", "ba"]


def test_reports_when_model_not_ready():
    s = TextTranslateService(lambda: None)
    done, failed, _ = collect(s)
    rid = s.request("Xin chào")
    assert wait_for(lambda: failed)
    s.close()
    assert failed[0][0] == rid and "nạp" in failed[0][1]
    assert done == []
