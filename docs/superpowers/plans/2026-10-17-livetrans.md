# LiveTrans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tool chạy nền trên Windows nghe loa/micro, nhận dạng giọng nói đa ngôn ngữ và dịch sang tiếng Việt offline, hiện phụ đề trên overlay.

**Architecture:** Mỗi nguồn âm thanh (PyAudioWPatch) → Silero VAD streaming → `Segmenter` (máy trạng thái thuần) phát `Partial`/`Final` → `WorkQueue` ưu tiên Final → một worker thread chạy faster-whisper + NLLB (CTranslate2) → Qt signal → overlay/tray (PySide6).

**Tech Stack:** Python 3.14, faster-whisper 1.2.1, ctranslate2 4.x, sentencepiece, PyAudioWPatch, PyAV (`av`), onnxruntime, PySide6-Essentials 6.12, numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-livetrans-design.md`

**Execution:** Native (người dùng yêu cầu "code cho tôi"). Thư mục không phải git repo → bỏ các bước commit.

## Global Constraints

- Chỉ CPU: `device="cpu"`, `compute_type="int8"`, mặc định `cpu_threads=4`.
- Âm thanh nội bộ: float32 mono 16 kHz; khung VAD 512 mẫu (32 ms), ngữ cảnh 64 mẫu.
- Tham số VAD mặc định: `start_threshold=0.5, end_threshold=0.35, min_silence_ms=600, min_speech_ms=250, max_segment_s=8, pre_roll_ms=200, partial_interval_s=2.0`.
- Model: `Systran/faster-whisper-<size>` và `JustFrederik/nllb-200-distilled-600M-ct2-int8`, lưu ở `models/`.
- Ngôn ngữ đích cố định `vie_Latn`; Whisper `vi` → giữ nguyên văn.
- Mọi chuỗi giao diện bằng tiếng Việt có dấu.
- Phím tắt mặc định: `Ctrl+Alt+T` (bật/tắt), `Ctrl+Alt+H` (overlay), `Ctrl+Alt+S` (nguồn).
- Log: `logs/livetrans.log`, RotatingFileHandler 1 MB × 3.

## Review Focus

1. Loopback WASAPI ngừng gửi dữ liệu khi im lặng → đoạn đang nói phải được chốt bằng `tick()` theo đồng hồ (test ở Task 2).
2. Âm nhạc/tiếng ồn khiến Whisper sinh câu ảo → bị lọc (test ở Task 4).
3. Thiết bị 44,1 kHz hoặc 6 kênh → downmix + resample ra đúng độ dài 16 kHz (test ở Task 7).
4. Nói liên tục không ngắt (bài hát, bài giảng) → cắt ở `max_segment_s` tại khung xác suất thấp nhất (test ở Task 2).
5. Ngôn ngữ phát hiện là `vi` hoặc không có trong bảng mã → nguyên văn / `None`, không crash (test ở Task 5).

---

### Task 1: Khung dự án + cấu hình

**Files:** Create `requirements.txt`, `requirements-dev.txt`, `livetrans/__init__.py`, `livetrans/paths.py`, `livetrans/config.py`, `tests/test_config.py`

**Interfaces — Produces:**
- `paths.APP_DIR, MODELS_DIR, LOGS_DIR, CONFIG_PATH: Path`
- `config.VadConfig`, `config.HotkeyConfig`, `config.Config` (dataclass, trường như spec §5)
- `config.load_config(path: Path) -> Config`, `config.save_config(cfg: Config, path: Path) -> None`

- [ ] Test: `test_missing_file_returns_defaults`, `test_wrong_types_fall_back` (`{"cpu_threads": "x", "source_mode": "foo", "vad": {"min_silence_ms": 900}}` → `cpu_threads == 4`, `source_mode == "loopback"`, `vad.min_silence_ms == 900`), `test_roundtrip`.
- [ ] Tạo venv, cài requirements, chạy test → FAIL → viết code → PASS.

### Task 2: Segmenter

**Files:** Create `livetrans/segmenter.py`, `tests/test_segmenter.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) Partial(source: str, seg_id: int, audio: np.ndarray)`; `Final(...)` cùng trường.
- `Segmenter(source: str, cfg: VadConfig, sample_rate=16000, frame_size=512)`
- `feed(frame: np.ndarray, prob: float, now: float) -> list[Partial | Final]`, `tick(now: float) -> list[...]`, `flush() -> list[...]`, `reset() -> None`

Quy tắc (spec §3.3): đếm lặng bắt đầu khi `prob < end_threshold`, reset khi `prob >= start_threshold`; Final bỏ phần lặng đuôi, giữ 3 khung đệm; cắt `max_segment_s` tại argmin xác suất trong 1,5 s cuối, phần dư thành đoạn mới `seg_id+1`.

- [ ] Tests (khung = 32 ms, `now = i * 0.032`):
  - `test_speech_then_silence_emits_one_final` — 2 s nói (prob 0.9) + 1 s lặng (0.05) → đúng 1 Final, `seg_id == 1`, độ dài audio ∈ [2.0 s, 2.5 s].
  - `test_short_blip_dropped` — 5 khung nói (160 ms) + lặng → không có Final.
  - `test_partials_every_interval` — 5 s nói liên tục → Partial tại ~2 s và ~4 s (2 Partial), cùng `seg_id`.
  - `test_max_segment_cut_at_lowest_prob` — 10 s nói, khung tại 7,2 s có prob 0.4 → Final đầu kết thúc tại khung đó (±1 khung), đoạn tiếp theo `seg_id == 2`.
  - `test_tick_closes_segment_when_data_stops` — 1 s nói rồi không feed; `tick(now + 0.7)` → 1 Final.
  - `test_pre_roll_included` — 10 khung lặng rồi nói → audio Final bắt đầu bằng ≥ 6 khung trước mốc nói.
- [ ] FAIL → code → PASS.

### Task 3: WorkQueue

**Files:** Create `livetrans/work_queue.py`, `tests/test_work_queue.py`

**Interfaces — Produces:** `WorkQueue.put(ev)`, `get(timeout: float | None) -> Partial | Final | None`, `clear()`, `close()` (thread-safe, `threading.Condition`).

- [ ] Tests: `test_final_before_partial`, `test_partial_replaced_by_newer_same_source`, `test_partial_dropped_after_final_same_segment` (Final seg 3 rồi Partial seg 3 → bị bỏ), `test_get_timeout_returns_none`, `test_close_unblocks_get`.
- [ ] FAIL → code → PASS.

### Task 4: ASR

**Files:** Create `livetrans/asr.py`, `tests/test_asr_filters.py`

**Interfaces — Produces:**
- `AsrResult(text: str, lang: str, lang_prob: float)`
- `is_hallucination(text: str) -> bool`, `collapse_repeats(text: str) -> str` (regex `(\D{1,25}?)\1{3,}` → `\1`)
- `StickyLanguage(threshold=0.6).choose(source, detected, prob) -> str`, `.get(source) -> str | None`
- `Transcriber(model_dir: Path, cpu_threads: int, forced_language: str | None)`; `.load()`; `.transcribe(audio, mode: "final" | "partial", source: str) -> AsrResult | None`

- [ ] Tests: `"Thanks for watching!"` → ảo; `"字幕由Amara.org社区提供"` → ảo; `"Hello everyone, welcome back"` → không; `collapse_repeats("go go go go go now") == "go now"`; `collapse_repeats("谢谢谢谢谢谢") == "谢"`; `collapse_repeats("1000000 dollars") == "1000000 dollars"`; sticky: (en, 0.9) rồi (de, 0.3) → `en`; (de, 0.8) → `de`; nguồn mới (fr, 0.3) → `fr`.
- [ ] FAIL → code → PASS.

### Task 5: Translator

**Files:** Create `livetrans/translator.py`, `tests/test_translator_logic.py`

**Interfaces — Produces:** `WHISPER_TO_NLLB: dict[str, str]`, `nllb_code(lang) -> str | None`, `Translator(model_dir, cpu_threads)`, `.load()`, `.translate(text, whisper_lang) -> str | None`.

- [ ] Tests (không nạp model): `translate("Xin chào", "vi") == "Xin chào"`; `translate("x", "xx") is None`; `nllb_code("en") == "eng_Latn"`, `"zh" → "zho_Hans"`, `"ja" → "jpn_Jpan"`; chuỗi rỗng → `""`.
- [ ] FAIL → code → PASS.

### Task 6: VAD + tải model + test tích hợp

**Files:** Create `livetrans/vad.py`, `livetrans/models.py`, `tests/conftest.py`, `tests/test_integration.py`

**Interfaces — Produces:** `SileroVAD().prob(frame512) -> float`, `.reset()`; `models.ensure_models(whisper_size, progress: Callable[[str], None]) -> tuple[Path, Path]`, `models.models_present(size) -> bool`.

- [ ] Test `@pytest.mark.slow`: wav tiếng Anh tạo bằng SAPI (fixture) → VAD: có khung > 0.5 trong lời nói, khung lặng < 0.2; pipeline đầy đủ VAD→Segmenter→Transcriber→Translator → ≥ 1 Final, `lang == "en"`, bản dịch có ký tự tiếng Việt có dấu; in độ trễ.
- [ ] Chạy `python -m livetrans --download-models` rồi `pytest -m slow -s` → PASS.

### Task 7: Bắt âm thanh

**Files:** Create `livetrans/audio_capture.py`, `tests/test_audio_convert.py`

**Interfaces — Produces:** `to_mono(data: bytes, channels: int) -> np.ndarray`; `Resampler(rate_in: int).process(mono: np.ndarray) -> np.ndarray` (16 kHz); `AudioSource(kind: "loopback" | "mic", on_audio, on_status)`, `.start()`, `.stop()`.

- [ ] Tests: 6 kênh 44 100 Hz × 1 s → `to_mono` dài 44 100; qua `Resampler` cộng dồn nhiều khối 10 ms → tổng ≈ 16 000 (±1 %); 16 kHz → giữ nguyên.
- [ ] FAIL → code → PASS; chạy thử `python -m livetrans.audio_capture` (in RMS 5 s) với loa đang phát.

### Task 8: Phím tắt + chạy một bản

**Files:** Create `livetrans/hotkeys.py`, `livetrans/single_instance.py`, `tests/test_hotkeys_parse.py`

**Interfaces — Produces:** `parse_hotkey(s) -> tuple[int, int]` (đã OR `MOD_NOREPEAT`); `GlobalHotkeys(bindings: dict[str, str])` (QObject, `triggered = Signal(str)`), `.start() -> list[str]` (tên phím lỗi), `.stop()`; `single_instance.acquire() -> handle | None`.

- [ ] Tests: `"Ctrl+Alt+T"` → `(0x4003, 0x54)`; `"ctrl+shift+F5"` → `(0x4006, 0x74)`; `"Ctrl+"` và `"Ctrl+Alt+Foo"` → `ValueError`.
- [ ] FAIL → code → PASS.

### Task 9: Pipeline

**Files:** Create `livetrans/pipeline.py`

**Interfaces — Consumes:** Task 2–7. **Produces:** `Pipeline(cfg)` (QObject) với signal `status_changed(str)`, `running_changed(bool)`, `final_ready(str, int, str, str, str)` (source, seg_id, lang, text, translation), `partial_ready(str, int, str)`, `segment_dropped(str, int)`, `models_failed(str)`, `device_error(str)`; phương thức `start()`, `pause()`, `toggle()`, `set_source_mode(mode)`, `retry_models()`, `shutdown()`; thuộc tính `running: bool`.

- [ ] Viết code (worker nạp model khi khởi động; ticker 100 ms gọi `tick()`; mỗi nguồn có một lock).
- [ ] Kiểm tra bằng `python -m livetrans --console` (Task 10).

### Task 10: Giao diện + ghép nối + script chạy

**Files:** Create `livetrans/ui/__init__.py`, `ui/icon.py`, `ui/overlay.py`, `ui/tray.py`, `livetrans/app.py`, `livetrans/__main__.py`, `setup.bat`, `LiveTranslate.vbs`, `README.md`

**Interfaces — Produces:** `Overlay.show_final/show_partial/drop_segment/show_status/set_font_size/set_source_labels`, signal `menu_requested(QPoint)`, `moved(int, int)`; `Tray` với signal cho từng mục menu; `app.main(argv) -> int`.

- [ ] Chạy app, phát video YouTube → overlay hiện phụ đề; thử 3 phím tắt, kéo overlay, đổi nguồn, thoát → không lỗi trong log.
