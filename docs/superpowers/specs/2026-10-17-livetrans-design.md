# LiveTrans — Phiên dịch âm thanh thời gian thực (offline) — Thiết kế

- Ngày: 2026-10-17
- Trạng thái: đã duyệt, đã triển khai
- Thư mục dự án: `D:\translate-local`

## 0. Thay đổi so với bản duyệt (phát sinh khi triển khai)

| Thay đổi | Lý do |
|---|---|
| Câu xem trước (Partial) dùng model Whisper `base` riêng (`preview_model`), câu chốt vẫn dùng `small` | Đo trên i5-9400F: encoder `small` ~1,5 s, `base` ~0,5 s → xem trước 0,7 s thay vì ~2 s |
| `Transcriber` tự nhận diện ngôn ngữ trên tensor encoder và cache encoder 1 phần tử | `transcribe(language=None)` của faster-whisper chạy encoder 2 lần → câu chốt từ 3,6 s xuống ~2,1 s |
| Phím chuyển nguồn mặc định `Ctrl+Alt+M` (thay `Ctrl+Alt+S`) | `Ctrl+Alt+S` đã bị ứng dụng khác chiếm trên máy này |
| Một instance PortAudio dùng chung + lock; mỗi thread âm thanh gọi `CoInitializeEx` | Khởi tạo PortAudio song song gây crash (assert `pa_front.c`); WASAPI cần COM trên thread mở stream |
| Ở chế độ Cả hai, loopback không tự mở lại khi im lặng | Không thể khởi tạo lại PortAudio khi stream micro đang mở |
| Thêm `paths.py`, `work_queue.py`, `app.py` | Tách hàng đợi để test không cần Qt; ghép nối UI riêng khỏi `__main__` |

Kết quả đo thực tế: câu chốt ~3,1 s sau khi người nói ngắt câu (lặng 0,6 s + ASR ~2,1 s + dịch ~0,5 s).

### Bản 0.2 (yêu cầu bổ sung)

| Thay đổi | Chi tiết |
|---|---|
| Ô **gõ tiếng Việt → English** | `ui/compose.py` + `text_translate.py`: cửa sổ luôn nổi (`Ctrl+Alt+V`), tự dịch sau 600 ms ngừng gõ (NLLB beam 5, repetition_penalty 1.0 — đo cho bản dịch đủ ý hơn beam 2), `Enter` copy vào clipboard rồi ẩn. Dùng chung Translator với phụ đề, chạy thread riêng. |
| **Chế độ chất lượng** (`models.PROFILES`) | `fast` (base + NLLB 600M), `balanced` (small/base + 600M), `accurate` (small/base + **NLLB 1.3B**). `quality: auto` → lựa chọn lúc cài (`install_profile.json`) → nếu không có thì theo CPU/RAM. Đổi được trong tray, nạp lại model trên worker thread. |
| Chọn model dịch | Đo trên i5-9400F: NLLB 600M 0,69 s/câu (sai từ, bỏ sót vế), **NLLB 1.3B 1,12 s/câu (đúng nghĩa nhất)**, MADLAD-400 3B 1,87 s/câu (nhiều lỗi nghĩa) → chọn 1.3B cho `accurate`. |
| **Dịch tạm câu đang nói** | Partial: ASR (base) → hiện câu gốc → NLLB beam 1 → hiện bản dịch tạm; bỏ qua nếu đã có Final chờ. |
| Cảnh báo máy chậm | Trung vị thời gian xử lý Final > 5 s (5 câu) hoặc ≥ 3 Final chờ → balloon gợi ý hạ chất lượng. |
| `cpu_threads: 0` | Tự động = số luồng CPU − 1 (2…8). |
| **Cửa sổ chính (0.3)** | Người dùng không tìm thấy icon khay → `ui/main_window.py`: tab Dịch trực tiếp (nút Bắt đầu/Dừng, nguồn, chất lượng, tốc độ phụ đề, thời gian xử lý), Gõ Việt → Anh (`ComposeWidget` nhúng), Lịch sử, Cài đặt (phụ đề, ngôn ngữ người nói, tự chạy cùng Windows qua HKCU\\…\\Run). Mở app lần nữa → `QLocalServer` báo bản đang chạy hiện cửa sổ; `--minimized` khi tự khởi động. Đóng cửa sổ = ẩn xuống khay. |
| **Nhanh hơn + phụ đề không tự ẩn (0.3)** | Mặc định cắt câu ≤ 5 s, lặng 450 ms, xem trước mỗi 1,5 s (preset "fast"; "standard" = 8 s/600 ms/2 s); `overlay_autohide=false`; `config_version=2` để config cũ nhận giá trị mới; `auto_threads` ≈ 70% luồng (đo: 4–6 luồng như nhau, nhiều luồng hơn chỉ tranh CPU với trình duyệt). |
| **Giọng đọc (0.4)** | `tts.py`: Piper offline, chỉ giọng `vi_VN-vais1000-medium` (các giọng vi 0.2.0 thiếu ký hiệu thanh điệu dạng số của espeak-ng → mất dấu). Đọc bản dịch của câu chốt có ngôn ngữ ≠ vi; hàng đợi tối đa 2 câu (bỏ câu cũ nếu đọc không kịp); phát qua PortAudio dùng chung. Bật giọng đọc → nguồn Loa dùng `process_loopback.py` (WASAPI `VAD\Process_Loopback`, EXCLUDE_TARGET_PROCESS_TREE cho tiến trình LiveTrans, PCM 16 kHz mono) để không thu lại giọng đọc; lỗi kích hoạt → quay về loopback thường. Đo: biên độ tone 440 Hz của chính tiến trình 0,053 (loopback thường) → 0,002 (process loopback). Bộ cài tải giọng (63 MB) cho mọi chế độ. |
| **Giao diện "cabin phiên dịch" (0.5)** | `ui/theme.py` + `ui/widgets.py`: nền xanh đêm `#10141F`/`#181D2B`, điểm nhấn duy nhất là đèn ON AIR hổ phách `#FFB547` (thở nhẹ khi đang nghe; tắt nếu Windows tắt hiệu ứng), đỏ `#F0565B` cho Dừng; **mã màu ngôn ngữ**: câu gốc nước ngoài xanh lạnh `#8FB4E8`, tiếng Việt kem `#FFE3B3` — dùng nhất quán ở màn hình cabin, Lịch sử, ô Gõ Việt → Anh và thanh phụ đề. Chữ: Bahnschrift SemiCondensed (trạng thái, nhãn), Segoe UI Variable (nội dung), Cascadia Mono (giờ, số liệu, phím tắt), icon Segoe Fluent. Không viết hoa toàn bộ chữ tiếng Việt (dấu chồng bị cắt). Thanh bên + trang; màn hình cabin hiện câu gốc + bản dịch mới nhất (cả bản dịch tạm). |
| **Desktop app + setup.exe** | PyInstaller onedir (`packaging/LiveTrans.spec`) + Inno Setup 6.7 (`packaging/LiveTrans.iss`): cài theo user, trang chọn chất lượng (tự đề xuất theo CPU/RAM), tải model khi cài (URL ghim commit + SHA256, `packaging/gen_models_iss.py`), shortcut, tự khởi động (tuỳ chọn), gỡ cài đặt. Bản cài: config/log ở `%LOCALAPPDATA%\LiveTrans`, model cạnh exe. `build.ps1` build + `--self-test`. |

## 1. Mục tiêu

Tool chạy nền trên Windows 11, nghe âm thanh (loa hệ thống và/hoặc micro), tự nhận diện ngôn ngữ nguồn,
dịch sang tiếng Việt và hiển thị phụ đề trên một overlay luôn nổi, **hoàn toàn offline**.

### Yêu cầu từ người dùng
| # | Yêu cầu |
|---|---|
| R1 | Nguồn âm thanh chọn được: Loa hệ thống / Micro / Cả hai |
| R2 | Tự nhận diện ngôn ngữ nguồn (đa ngôn ngữ) → dịch sang tiếng Việt |
| R3 | Chạy offline hoàn toàn trên máy (không gửi dữ liệu ra ngoài, trừ lần tải model đầu tiên) |
| R4 | Hiển thị bằng overlay phụ đề + icon khay hệ thống (tray) |
| R5 | Phím tắt toàn cục |
| R6 | Cơ chế "cắt theo khoảng lặng + xem trước câu gốc" (phương án C) |

### Giả định (đã được người dùng xác nhận)
- Dùng cá nhân, phi thương mại (NLLB-200 theo giấy phép CC-BY-NC 4.0).
- Chấp nhận độ trễ ~2–4 giây sau mỗi câu.
- Không lưu bản ghi ra file.
- Ở chế độ "Cả hai", mỗi câu được gắn nhãn nguồn `[Loa]` / `[Mic]`.

### Tiêu chí thành công
1. Mở video YouTube tiếng Anh/Nhật/Trung → phụ đề tiếng Việt xuất hiện trên overlay trong ≤ ~4 giây sau khi
   người nói ngắt câu.
2. Khi đang có người nói, câu gốc tạm thời hiện dưới dạng chữ mờ trong khoảng 2 giây một lần.
3. Video vẫn phát mượt trong lúc tool chạy (tool dùng mặc định 4 luồng CPU).
4. Cắm/rút tai nghe hoặc đổi thiết bị mặc định không làm tool crash; tool tự mở lại luồng âm thanh.
5. Phím tắt toàn cục hoạt động khi đang ở bất kỳ ứng dụng nào.

### Ngoài phạm vi (YAGNI)
Lưu bản ghi, khởi động cùng Windows, dịch sang ngôn ngữ khác ngoài tiếng Việt, giao diện cài đặt đồ hoạ
(cấu hình qua `config.json`), click-through overlay, đóng gói `.exe`.

## 2. Môi trường mục tiêu

- CPU Intel i5-9400F (6 nhân/6 luồng), RAM 64 GB, GPU GT 420 (không dùng được CUDA) → **chỉ dùng CPU**.
- Windows 11 Pro, Python 3.14.4 (đã kiểm tra: mọi thư viện dưới đây có wheel `cp314`/`abi3` cho win_amd64).

### Thư viện
| Thư viện | Vai trò |
|---|---|
| `faster-whisper` 1.2.x (kéo theo `ctranslate2`, `onnxruntime`, `av`, `tokenizers`, `huggingface_hub`) | ASR + Silero VAD (ONNX) + resample (PyAV) |
| `sentencepiece` | Tokenizer cho NLLB |
| `PyAudioWPatch` | Bắt âm thanh WASAPI loopback (loa) và micro |
| `PySide6` | Overlay, tray, vòng lặp sự kiện |
| `numpy` | Xử lý buffer âm thanh |
| `pytest` (dev) | Kiểm thử |

### Model (tải lần đầu vào `models/`)
| Model | Nguồn Hugging Face | Dung lượng |
|---|---|---|
| Whisper small (CTranslate2 int8) | `Systran/faster-whisper-small` | ~480 MB |
| NLLB-200 distilled 600M (CTranslate2 int8) | `JustFrederik/nllb-200-distilled-600M-ct2-int8` (`model.bin`, `sentencepiece.bpe.model`, `shared_vocabulary.txt`, `config.json`) | ~620 MB |

Kích thước Whisper đổi được qua cấu hình (`base` nhanh hơn / `medium` chính xác hơn nhưng chậm).

## 3. Kiến trúc

```
livetrans/
  __init__.py
  __main__.py          # điểm vào: python -m livetrans
  config.py            # dataclass Config, load/save config.json
  models.py            # tải & định vị model (huggingface_hub.snapshot_download)
  audio_capture.py     # AudioSource: loopback / mic → khối float32 16 kHz mono
  vad.py               # bọc Silero VAD ONNX của faster-whisper → xác suất theo khung 512 mẫu
  segmenter.py         # máy trạng thái: khung + xác suất → sự kiện Partial / Final
  asr.py               # Transcriber (faster-whisper) + lọc câu ảo + ngôn ngữ "dính"
  translator.py        # NLLB CTranslate2 + sentencepiece, bảng mã Whisper→NLLB
  pipeline.py          # điều phối: nguồn → segmenter → hàng đợi ưu tiên → worker → Qt signal
  hotkeys.py           # RegisterHotKey qua ctypes, thread riêng có message loop
  single_instance.py   # named mutex chống chạy 2 bản
  ui/
    overlay.py         # cửa sổ phụ đề
    tray.py            # QSystemTrayIcon + menu
    icon.py            # vẽ icon bằng QPainter (không cần file ảnh)
tests/
config.json            # tạo tự động lần đầu
requirements.txt
setup.bat              # tạo .venv, cài thư viện, tải model
LiveTranslate.vbs      # chạy bằng pythonw, không có console
```

Mỗi module có một trách nhiệm và giao diện nhỏ:

### 3.1 `audio_capture.AudioSource`
- `AudioSource(kind: "loopback" | "mic", on_audio: Callable[[np.ndarray], None])`, `start()`, `stop()`.
- Loopback: thiết bị loopback tương ứng với loa mặc định (`PyAudio.get_default_wasapi_loopback()`).
  Mic: thiết bị input mặc định WASAPI.
- Mở stream ở định dạng gốc của thiết bị (thường 48 kHz, 2 kênh), callback đưa dữ liệu vào thread
  resample dùng `av.AudioResampler(format="flt", layout="mono", rate=16000)` → gọi `on_audio(float32[])`.
- Lỗi stream / thiết bị mặc định thay đổi (kiểm tra mỗi 2 s) → đóng và mở lại; báo trạng thái qua callback
  `on_status(str)`.
- Loopback trên WASAPI không gửi dữ liệu khi không có âm thanh phát ra → segmenter coi "không có dữ liệu"
  trong > 0,6 s như khoảng lặng (dùng đồng hồ, không chỉ đếm khung).

### 3.2 `vad.SileroVAD`
- Dùng file `faster_whisper/assets/silero_vad_v6.onnx` đi kèm faster-whisper, tự mở
  `onnxruntime.InferenceSession` (1 luồng). Mỗi khung 512 mẫu (32 ms): `input` = 64 mẫu cuối của khung trước +
  512 mẫu khung hiện tại (shape `(1, 576)`), truyền `h`/`c` (shape `(1, 1, 128)`) của lần gọi trước và
  giữ `h`/`c` trả về → streaming có trạng thái. (Hàm `SileroVADModel.__call__` của thư viện chỉ chạy
  theo lô cho cả file nên không dùng trực tiếp.)
- `prob(frame: np.ndarray[512]) -> float`, `reset()`.
- Mỗi nguồn có một instance riêng (trạng thái không dùng chung).

### 3.3 `segmenter.Segmenter`
Máy trạng thái thuần (không I/O, test được bằng xác suất giả):
- Tham số (trong config): `start_threshold=0.5`, `end_threshold=0.35`, `min_silence_ms=600`,
  `min_speech_ms=250`, `max_segment_s=8`, `pre_roll_ms=200`, `partial_interval_s=2.0`.
- `feed(frame, prob, now) -> list[Event]`; `Event = Partial(source, audio, seg_id) | Final(source, audio, seg_id)`.
- IDLE → SPEECH khi `prob ≥ start_threshold` (giữ 200 ms đệm trước).
- Trong SPEECH: mỗi `partial_interval_s` phát `Partial` với toàn bộ audio đoạn hiện tại.
- SPEECH → phát `Final` khi lặng liên tục ≥ `min_silence_ms`, hoặc khi đoạn đạt `max_segment_s`
  (cắt tại khung có xác suất thấp nhất trong 1,5 s cuối, phần còn lại chuyển sang đoạn mới).
- Đoạn ngắn hơn `min_speech_ms` bị bỏ.

### 3.4 `asr.Transcriber`
- `WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=N)`.
- `transcribe(audio, mode: "final" | "partial", lang_hint: str | None) -> AsrResult(text, lang, lang_prob)`.
  - final: `beam_size=3`, partial: `beam_size=1`, `without_timestamps=True`.
  - `vad_filter=False` (đã cắt đoạn), `condition_on_previous_text=False`.
- Ngôn ngữ "dính" theo nguồn: nếu `lang_prob < 0.6` và nguồn đã có ngôn ngữ chắc chắn trước đó → dùng lại
  ngôn ngữ đó (transcribe lại với `language=` cố định). Partial luôn dùng ngôn ngữ dính nếu có.
- Lọc câu ảo: bỏ đoạn có `no_speech_prob > 0.6` và `avg_logprob < -1.0`; bỏ câu khớp danh sách câu ảo phổ biến
  ("Thanks for watching", "Subscribe…", "ご視聴ありがとうございました", "字幕由…", "Hãy subscribe cho kênh…"…);
  gộp các cụm từ lặp lại liên tiếp quá 3 lần.

### 3.5 `translator.Translator`
- `ctranslate2.Translator(path, device="cpu", compute_type="int8", inter_threads=1, intra_threads=N)` +
  `sentencepiece.SentencePieceProcessor`.
- `translate(text, whisper_lang) -> str | None`:
  - `whisper_lang == "vi"` → trả về nguyên văn.
  - Không có trong bảng mã → `None` (UI chỉ hiện câu gốc).
  - Token nguồn: `[src_code] + sp.encode(text, out_type=str) + ["</s>"]`; `target_prefix=[["vie_Latn"]]`;
    `beam_size=2`, `max_decoding_length=256`; bỏ token mã ngôn ngữ đầu ra rồi `sp.decode`.
- Bảng mã Whisper→NLLB cho khoảng 40 ngôn ngữ phổ biến (en→eng_Latn, zh→zho_Hans, ja→jpn_Jpan, ko→kor_Hang,
  fr→fra_Latn, de→deu_Latn, es→spa_Latn, ru→rus_Cyrl, th→tha_Thai, id→ind_Latn, …).

### 3.6 `pipeline.Pipeline` (QObject)
- Quản lý các `AudioSource` + `SileroVAD` + `Segmenter` theo chế độ nguồn (`loopback` / `mic` / `both`).
- Hàng đợi ưu tiên dùng chung cho một worker thread:
  - `Final` xếp hàng FIFO và luôn được xử lý trước.
  - `Partial`: mỗi nguồn chỉ giữ bản mới nhất; bỏ nếu `Final` của cùng `seg_id` đã có.
  - Quá tải (≥ 3 `Final` đang chờ) → tạm ngừng xử lý `Partial` cho tới khi hàng đợi < 2.
- Worker: Final → ASR(final) → Translator → `final_ready(source, seg_id, lang, text, translation)`;
  Partial → ASR(partial) → `partial_ready(source, seg_id, text)`.
- Signal trạng thái: `status_changed(str)` ("Đang tải model…", "Đang nghe", "Tạm dừng", lỗi).
- API: `start()`, `pause()`, `set_source_mode(mode)`, `shutdown()`.
- Model được nạp trong worker thread lúc khởi động (UI không bị đứng).

### 3.7 `hotkeys.GlobalHotkeys`
- Thread riêng: `RegisterHotKey(None, id, MOD_CONTROL|MOD_ALT|MOD_NOREPEAT, vk)` + vòng `GetMessageW`;
  khi nhận `WM_HOTKEY` → phát Qt signal (thread-safe qua queued connection).
- Mặc định: `Ctrl+Alt+T` bật/tắt dịch, `Ctrl+Alt+H` ẩn/hiện overlay, `Ctrl+Alt+S` chuyển nguồn Loa → Mic → Cả hai.
- Đăng ký thất bại (bị chiếm) → trả danh sách phím lỗi để tray báo; phím khác vẫn hoạt động.
- Dừng: `PostThreadMessageW(WM_QUIT)` rồi `UnregisterHotKey`.

## 4. Giao diện

### 4.1 Overlay (`ui/overlay.py`)
- `QWidget` với cờ `FramelessWindowHint | WindowStaysOnTopHint | Tool`, `WA_TranslucentBackground`;
  vẽ hình chữ nhật bo góc màu đen alpha ~70%.
- Rộng mặc định 60% màn hình chính, căn giữa, cách đáy 8%; chiều cao tự co giãn theo nội dung.
- Nội dung: tối đa 2 mục gần nhất, mỗi mục gồm:
  - dòng gốc: chữ nhỏ màu xám, có nhãn `[EN]` (và `[Loa]`/`[Mic]` khi ở chế độ Cả hai);
  - dòng dịch: chữ lớn màu trắng, có viền tối cho dễ đọc.
  - Ngôn ngữ chưa hỗ trợ dịch → chỉ hiện dòng gốc.
- Dòng xem trước (Partial): chữ nghiêng, xám mờ, nằm dưới cùng; bị thay bằng mục Final khi đoạn đó chốt.
- Kéo chuột trái để di chuyển; vị trí lưu vào config khi thả chuột.
- Chuột phải → mở cùng menu với tray.
- Không có nội dung mới trong 8 s → mờ dần còn 0 (vẫn hiện thông báo trạng thái khi có).
- Cỡ chữ: Nhỏ / Vừa / Lớn (dòng dịch 18 / 24 / 32 pt).

### 4.2 Tray (`ui/tray.py`)
- Icon vẽ bằng QPainter (chữ "VI" trên nền tròn; xám khi tạm dừng, xanh khi đang nghe).
- Tooltip = trạng thái hiện tại.
- Menu: Bắt đầu/Tạm dừng · Nguồn ▸ (Loa hệ thống / Micro / Cả hai — radio) · Hiện/Ẩn phụ đề ·
  Cỡ chữ ▸ (Nhỏ/Vừa/Lớn) · Thử lại tải model (chỉ hiện khi tải lỗi) · Thoát.
- Thông báo dạng balloon cho: lỗi thiết bị, lỗi phím tắt, lỗi tải model.

## 5. Cấu hình (`config.json`)

```json
{
  "source_mode": "loopback",
  "whisper_model": "small",
  "cpu_threads": 4,
  "source_language": "auto",
  "font_size": "medium",
  "overlay_pos": null,
  "overlay_width_ratio": 0.6,
  "hotkeys": {"toggle": "Ctrl+Alt+T", "overlay": "Ctrl+Alt+H", "source": "Ctrl+Alt+S"},
  "vad": {"start_threshold": 0.5, "end_threshold": 0.35, "min_silence_ms": 600,
          "min_speech_ms": 250, "max_segment_s": 8, "pre_roll_ms": 200, "partial_interval_s": 2.0}
}
```
Khoá thiếu hoặc sai kiểu → dùng giá trị mặc định và ghi log cảnh báo.
`source_language` khác `"auto"` (ví dụ `"en"`) → bỏ bước nhận diện ngôn ngữ.

## 6. Xử lý lỗi

| Tình huống | Xử lý |
|---|---|
| Thiết bị âm thanh lỗi / đổi / không có | Đóng và mở lại sau 2 s; balloon báo một lần; các nguồn khác vẫn chạy |
| Tải model thất bại | Overlay + tooltip báo lỗi; menu "Thử lại tải model"; không crash |
| Exception trong worker | Ghi `logs/livetrans.log` (RotatingFileHandler 1 MB × 3), bỏ đoạn đó, chạy tiếp |
| Quá tải CPU | Tạm ngừng Partial (mục 3.6) |
| Phím tắt bị chiếm | Balloon báo phím lỗi; phím khác vẫn hoạt động |
| Chạy bản thứ hai | Named mutex `Local\LiveTransSingleton` → bản thứ hai thoát ngay |
| Thoát | Dừng nguồn âm thanh → dừng worker (chờ tối đa 3 s) → huỷ phím tắt → lưu config |

## 7. Cài đặt & chạy

- `setup.bat`: `python -m venv .venv` → `pip install -r requirements.txt` → `python -m livetrans --download-models`.
- `LiveTranslate.vbs`: chạy `.venv\Scripts\pythonw.exe -m livetrans` với cửa sổ ẩn (không có console).
- `python -m livetrans --console`: chạy kèm log ra console để gỡ lỗi.

## 8. Kiểm thử

### Unit (pytest, nhanh, không cần model)
- `segmenter`: chuỗi xác suất giả → kiểm tra điểm Final, bỏ đoạn quá ngắn, cắt tại `max_segment_s`,
  nhịp Partial, pre-roll, timeout khi loopback ngừng gửi dữ liệu.
- `asr` (phần thuần): bộ lọc câu ảo, gộp lặp, logic ngôn ngữ dính.
- `translator`: bảng mã, nhánh `vi` → nguyên văn, ngôn ngữ không hỗ trợ → `None`.
- `pipeline` (hàng đợi ưu tiên): Final trước Partial, Partial cũ bị thay thế, ngưỡng quá tải.
- `config`: đọc file thiếu khoá hoặc sai kiểu.

### Tích hợp (đánh dấu `@pytest.mark.slow`, cần model)
- Tạo wav tiếng Anh bằng Windows SAPI (System.Speech) → `Segmenter` + `Transcriber` + `Translator` →
  có ít nhất 1 Final, ngôn ngữ `en`, bản dịch tiếng Việt không rỗng và chứa ký tự có dấu.
- Đo và in độ trễ (thời điểm kết thúc câu → có bản dịch) trên máy thật.
- `Translator` dịch một câu tiếng Anh/Nhật mẫu → kết quả tiếng Việt hợp lý.

### Thủ công
- Phát video YouTube (EN, JA, ZH) → quan sát overlay, độ trễ, chữ xem trước.
- Chế độ Micro và Cả hai (nhãn `[Loa]`/`[Mic]`).
- Ba phím tắt; kéo overlay; đổi cỡ chữ; cắm/rút tai nghe; thoát từ tray.
