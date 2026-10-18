"""Ghép nối pipeline + overlay + tray + phím tắt."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler

from .config import SOURCE_MODES, Config, load_config, save_config
from .paths import CONFIG_PATH, LOGS_DIR

log = logging.getLogger("livetrans")

SOURCE_NAMES = {"loopback": "Loa hệ thống", "mic": "Micro", "both": "Loa + Micro"}


def setup_logging(console: bool) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(LOGS_DIR / "livetrans.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    for noisy in ("faster_whisper", "httpx", "httpcore", "httpx2", "httpcore2", "huggingface_hub", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class App:
    def __init__(self, cfg: Config):
        from PySide6.QtWidgets import QApplication

        from . import __version__, autostart
        from .hotkeys import GlobalHotkeys
        from .pipeline import Pipeline
        from .text_translate import TextTranslateService
        from .tts import Speaker
        from .ui.compose import ComposeWidget
        from .ui.main_window import MainWindow
        from .ui.overlay import Overlay
        from .ui.tray import Tray

        self.cfg = cfg
        self.pipeline = Pipeline(cfg)
        self.overlay = Overlay(cfg.font_size, cfg.overlay_width_ratio, cfg.overlay_pos, cfg.overlay_autohide)
        self.overlay.set_source_labels(cfg.source_mode == "both")
        if not cfg.overlay_visible:
            self.overlay.set_user_visible(False)
        self.tray = Tray(cfg.source_mode, cfg.font_size, cfg.quality, cfg.hotkeys)
        self.tray.set_overlay_visible(cfg.overlay_visible)
        self.tray.set_tts_enabled(cfg.tts_enabled)
        self.speaker = Speaker(cfg.tts_speed, cfg.tts_volume)
        self.text_service = TextTranslateService(lambda: self.pipeline.translator, src="vi", tgt="en")
        self.compose = ComposeWidget(self.text_service, cfg.compose_hide_after_copy, cfg.hotkeys.compose)
        self.window = MainWindow(
            cfg, self.compose, __version__,
            autostart_supported=autostart.supported(),
            autostart_enabled=autostart.supported() and autostart.is_enabled(),
        )
        self.hotkeys = GlobalHotkeys(
            {
                "toggle": cfg.hotkeys.toggle,
                "overlay": cfg.hotkeys.overlay,
                "source": cfg.hotkeys.source,
                "compose": cfg.hotkeys.compose,
                "speak": cfg.hotkeys.speak,
            }
        )
        self._tray_hint_shown = False

        p, o, t, w = self.pipeline, self.overlay, self.tray, self.window
        p.final_ready.connect(o.show_final)
        p.final_ready.connect(self._on_final)
        p.partial_ready.connect(o.show_partial)
        p.partial_ready.connect(w.show_partial)
        p.segment_dropped.connect(o.drop_segment)
        p.status_changed.connect(self._on_status)
        p.running_changed.connect(self._on_running)
        p.models_failed.connect(self._on_models_failed)
        p.device_error.connect(self._on_device_error)
        p.slow_warning.connect(self._on_slow)
        p.final_timing.connect(w.add_timing)

        t.open_requested.connect(lambda: w.bring_to_front())
        t.toggle_requested.connect(p.toggle)
        t.quality_selected.connect(self.set_quality)
        t.source_selected.connect(self.set_source)
        t.overlay_toggle_requested.connect(self.toggle_overlay)
        t.font_size_selected.connect(self.set_font_size)
        t.retry_requested.connect(self._retry_models)
        t.compose_requested.connect(lambda: w.bring_to_front("compose"))
        t.tts_toggled.connect(self.set_tts)
        t.quit_requested.connect(QApplication.quit)

        w.tts_toggled.connect(self.set_tts)
        w.tts_speed_selected.connect(self.set_tts_speed)
        w.tts_volume_changed.connect(self.set_tts_volume)
        w.tts_test_requested.connect(lambda: self._speak("Xin chào, đây là giọng đọc của LiveTrans.", force=True))
        self.speaker.state_changed.connect(self._on_tts_state)

        w.toggle_requested.connect(p.toggle)
        w.source_selected.connect(self.set_source)
        w.quality_selected.connect(self.set_quality)
        w.speed_selected.connect(self.set_speed)
        w.overlay_visible_changed.connect(self.set_overlay_visible)
        w.overlay_autohide_changed.connect(self.set_overlay_autohide)
        w.preview_changed.connect(self.set_preview)
        w.font_size_selected.connect(self.set_font_size)
        w.source_language_selected.connect(self.set_source_language)
        w.autostart_changed.connect(self.set_autostart)
        w.open_logs_requested.connect(lambda: os.startfile(LOGS_DIR))
        w.hidden_to_tray.connect(self._on_hidden_to_tray)
        w.quit_requested.connect(QApplication.quit)

        self.compose.copied.connect(self._on_copied)
        self.compose.escaped.connect(w.hide)
        self.compose.hide_after_copy_changed.connect(self._on_compose_option)
        o.menu_requested.connect(lambda pos: t.menu.popup(pos))
        o.moved.connect(self._on_overlay_moved)
        self.hotkeys.triggered.connect(self._on_hotkey)

    def start(self, show_window: bool = True) -> None:
        self.tray.show()
        if show_window:
            self.window.bring_to_front()
        failed = self.hotkeys.start()
        if failed:
            self.tray.notify("LiveTrans", "Không đăng ký được phím tắt: " + ", ".join(failed))
        self.pipeline.start_engine()
        self.pipeline.start()
        if self.cfg.tts_enabled:
            self.speaker.start()  # nạp giọng đọc sẵn

    def shutdown(self) -> None:
        log.info("đang thoát")
        self.speaker.close()
        self.text_service.close()
        self.pipeline.shutdown()
        self.hotkeys.stop()
        self.save()
        self.tray.hide()

    def save(self) -> None:
        try:
            save_config(self.cfg, CONFIG_PATH)
        except OSError:
            log.exception("không lưu được config")

    # ------------------------------------------------------------ handlers
    def _on_status(self, text: str, sticky: bool) -> None:
        self.tray.set_status(text)
        self.window.set_status(text)
        self.overlay.show_status(text, sticky)

    def _on_running(self, running: bool) -> None:
        self.tray.set_running(running)
        self.window.set_running(running)
        if not running:
            self.overlay.clear()

    def _on_final(self, source: str, seg_id: int, lang: str, text: str, translation: str) -> None:
        self.window.add_history(SOURCE_NAMES.get(source, source), lang, text, translation)
        if lang != "vi" and translation:
            self._speak(translation)

    def _speak(self, text: str, force: bool = False) -> None:
        if force or self.cfg.tts_enabled:
            self.speaker.say(text)

    def _on_tts_state(self, state: str, detail: str) -> None:
        labels = {"loading": "Đang nạp giọng đọc…", "ready": "Sẵn sàng", "speaking": "🔊 Đang đọc…"}
        self.window.set_tts_state(labels.get(state, detail))
        if state == "error":
            self.tray.notify("LiveTrans", detail)

    def set_tts(self, enabled: bool) -> None:
        if enabled == self.cfg.tts_enabled:
            return
        log.info("giọng đọc: %s", "bật" if enabled else "tắt")
        self.cfg.tts_enabled = enabled
        self.tray.set_tts_enabled(enabled)
        self.window.set_tts_enabled(enabled)
        if enabled:
            self.speaker.start()
        else:
            self.speaker.stop_speaking()
            self.window.set_tts_state("")
        self.overlay.show_status("Đã bật giọng đọc" if enabled else "Đã tắt giọng đọc")
        self.pipeline.restart_sources()  # nguồn Loa đổi sang/khỏi chế độ bỏ qua tiếng của LiveTrans
        self.save()

    def set_tts_speed(self, speed: str) -> None:
        self.cfg.tts_speed = speed
        self.speaker.speed = speed
        self.save()

    def set_tts_volume(self, volume: float) -> None:
        self.cfg.tts_volume = volume
        self.speaker.volume = volume
        self.save()

    def _on_slow(self, message: str) -> None:
        self.tray.notify("LiveTrans", message)
        self.window.show_warning(message)

    def _on_models_failed(self, err: str) -> None:
        self.tray.set_retry_visible(True)
        self.tray.notify("LiveTrans", f"Không tải được model: {err}")

    def _retry_models(self) -> None:
        self.tray.set_retry_visible(False)
        self.pipeline.retry_models()

    def _on_device_error(self, text: str) -> None:
        self.tray.notify("LiveTrans", text)
        self.overlay.show_status(text)

    def _on_hidden_to_tray(self) -> None:
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.notify(
                "LiveTrans vẫn đang chạy",
                "Mở lại bằng icon VI ở khay hệ thống (góc phải thanh taskbar, có thể nằm trong mục ^) "
                "hoặc mở shortcut LiveTrans.",
            )

    def _on_copied(self, english: str, hide: bool) -> None:
        self.overlay.show_status("Đã copy bản tiếng Anh — Ctrl+V để dán")
        if hide:
            self.window.hide()

    def _on_hotkey(self, name: str) -> None:
        log.info("phím tắt: %s", name)
        if name == "toggle":
            self.pipeline.toggle()
        elif name == "overlay":
            self.toggle_overlay()
        elif name == "source":
            modes = list(SOURCE_MODES)
            self.set_source(modes[(modes.index(self.cfg.source_mode) + 1) % len(modes)])
        elif name == "speak":
            self.set_tts(not self.cfg.tts_enabled)
        elif name == "compose":
            if self.window.isVisible() and self.window.isActiveWindow() and self.window.current_page() == "compose":
                self.window.hide()
            else:
                self.window.bring_to_front("compose")

    def _on_compose_option(self, hide_after_copy: bool) -> None:
        self.cfg.compose_hide_after_copy = hide_after_copy
        self.save()

    def _on_overlay_moved(self, x: int, bottom: int) -> None:
        self.cfg.overlay_pos = [x, bottom]
        self.save()

    def set_source(self, mode: str) -> None:
        if mode == self.cfg.source_mode:
            return
        self.pipeline.set_source_mode(mode)
        self.tray.set_source(mode)
        self.window.set_source(mode)
        self.overlay.set_source_labels(mode == "both")
        self.overlay.show_status(f"Nguồn: {SOURCE_NAMES[mode]}")
        self.save()

    def set_quality(self, quality: str) -> None:
        if quality == self.cfg.quality:
            return
        log.info("đổi chất lượng: %s", quality)
        self.cfg.quality = quality
        self.tray.set_quality(quality)
        self.window.set_quality(quality)
        self.save()
        self.pipeline.reload_models()

    def set_speed(self, name: str) -> None:
        from .config import apply_speed

        log.info("tốc độ phụ đề: %s", name)
        apply_speed(self.cfg.vad, name)
        self.pipeline.restart_sources()
        self.save()

    def set_source_language(self, lang: str) -> None:
        self.pipeline.set_source_language(lang)
        self.save()

    def set_preview(self, enabled: bool) -> None:
        self.cfg.translate_preview = enabled
        self.save()

    def set_overlay_autohide(self, autohide: bool) -> None:
        self.cfg.overlay_autohide = autohide
        self.overlay.set_autohide(autohide)
        self.save()

    def set_autostart(self, enabled: bool) -> None:
        from . import autostart

        try:
            autostart.set_enabled(enabled)
        except OSError:
            log.exception("không đổi được tự khởi động")

    def set_font_size(self, size: str) -> None:
        self.cfg.font_size = size
        self.overlay.set_font_size(size)
        self.tray.set_font_size(size)
        self.window.set_font_size(size)
        self.overlay.show_status("Cỡ chữ đã đổi")
        self.save()

    def set_overlay_visible(self, visible: bool) -> None:
        self.cfg.overlay_visible = visible
        self.overlay.set_user_visible(visible)
        self.tray.set_overlay_visible(visible)
        self.window.set_overlay_visible(visible)
        self.save()

    def toggle_overlay(self) -> None:
        self.set_overlay_visible(not self.overlay.is_user_visible())


def self_test(cfg: Config) -> int:
    """Kiểm tra thư viện native nạp được (dùng sau khi build exe). Có model thì chạy thử ASR + dịch."""
    try:
        import ctranslate2
        import numpy as np
        import pyaudiowpatch
        from PySide6.QtWidgets import QApplication

        from .audio_capture import Resampler
        from .models import auto_threads, mt_dir, profile_present, resolve_profile, whisper_dir
        from .ui.icon import make_icon
        from .vad import SileroVAD

        prob = SileroVAD().prob(np.zeros(512, np.float32))
        resampled = len(Resampler(48000).process(np.zeros(4800, np.float32)))
        pa = pyaudiowpatch.PyAudio()
        devices = pa.get_device_count()
        pa.terminate()
        _qt = QApplication.instance() or QApplication([])
        make_icon(True)
        log.info("self-test: vad=%.3f resample=%d devices=%d ct2=%s", prob, resampled, devices, ctranslate2.__version__)
        profile = resolve_profile(cfg.quality)
        if profile_present(profile):
            from .asr import Transcriber
            from .translator import Translator

            threads = cfg.cpu_threads or auto_threads()
            asr = Transcriber(whisper_dir(profile.whisper), threads, preview_dir=whisper_dir(profile.preview))
            asr.load()
            asr.transcribe(np.zeros(16000, np.float32), "final", "selftest")
            tr = Translator(mt_dir(profile.mt), threads)
            tr.load()
            log.info("self-test [%s]: dịch thử %r", profile.key, tr.translate("Hello, how are you?", "en"))
        else:
            log.info("self-test: chưa có model của chế độ %s, bỏ qua bước nạp model", profile.key)
        from .tts import voice_present

        if voice_present():
            from .tts import _PiperEngine

            engine = _PiperEngine()
            audio = engine.synthesize("Xin chào.", 1.0)
            log.info("self-test: giọng đọc tạo %.2f giây âm thanh", len(audio) / engine.sample_rate)
        else:
            log.info("self-test: chưa có giọng đọc, bỏ qua")
        log.info("self-test OK")
        return 0
    except Exception:
        log.exception("self-test lỗi")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="livetrans", description="Phiên dịch âm thanh thời gian thực sang tiếng Việt")
    parser.add_argument("--console", action="store_true", help="in log ra console")
    parser.add_argument("--download-models", action="store_true", help="chỉ tải model rồi thoát")
    parser.add_argument("--self-test", action="store_true", help="kiểm tra thư viện/model rồi thoát")
    parser.add_argument("--minimized", action="store_true", help="chạy nền, không mở cửa sổ (khi tự khởi động)")
    args = parser.parse_args(argv)

    # pythonw không có stdout/stderr → thư viện ghi log/progress sẽ lỗi.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if not args.console and not args.download_models:
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

    setup_logging(args.console or args.download_models)
    cfg = load_config(CONFIG_PATH)

    if args.self_test:
        return self_test(cfg)

    if args.download_models:
        from .models import ensure_profile, resolve_profile

        profile = resolve_profile(cfg.quality)
        print(f"Chế độ chất lượng: {profile.label}")
        ensure_profile(profile, print)
        print("Đã có đủ model.")
        return 0

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from . import single_instance
    from .ui.icon import make_icon

    qt_app = QApplication(sys.argv[:1])
    mutex = single_instance.acquire()  # giữ tham chiếu đến khi thoát
    if mutex is None:
        shown = single_instance.activate_running_instance()
        log.info("LiveTrans đã chạy rồi → %s", "hiện cửa sổ bản đang chạy" if shown else "không liên lạc được")
        return 0
    activation = single_instance.ActivationServer()

    qt_app.setApplicationName("LiveTrans")
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setWindowIcon(make_icon(True))
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("không có khay hệ thống")

    app = App(cfg)
    activation.activated.connect(lambda: app.window.bring_to_front())
    app.start(show_window=not args.minimized)
    if not CONFIG_PATH.exists():
        app.save()

    signal.signal(signal.SIGINT, lambda *_: qt_app.quit())
    keepalive = QTimer()  # cho Python xử lý Ctrl+C
    keepalive.start(250)
    keepalive.timeout.connect(lambda: None)

    log.info("LiveTrans đã khởi động (nguồn=%s)", cfg.source_mode)
    try:
        return qt_app.exec()
    finally:
        app.shutdown()
