# LiveTrans — Phiên dịch âm thanh thời gian thực (offline)

Tool chạy nền trên Windows: nghe âm thanh **loa hệ thống** (YouTube, phim, Zoom/Meet…) và/hoặc **micro**,
tự nhận diện ngôn ngữ (Anh, Nhật, Trung, Hàn, Pháp… ~75 ngôn ngữ) và dịch sang **tiếng Việt**. Kết quả hiện
trên một thanh phụ đề luôn nổi. Kèm ô **gõ tiếng Việt → tiếng Anh** để chat với người nước ngoài.
Chạy hoàn toàn trên máy (CPU), không gửi dữ liệu ra ngoài.

## Cài đặt cho người dùng

Chạy **`LiveTrans-Setup-<phiên bản>.exe`** (không cần quyền admin):

1. Chọn thư mục cài (mặc định `%LOCALAPPDATA%\Programs\LiveTrans`).
2. Chọn **chất lượng dịch** — bộ cài tự đề xuất theo CPU/RAM của máy:

   | Chế độ | Nhận dạng giọng nói | Dịch | Tải về | Phù hợp |
   |---|---|---|---|---|
   | Chính xác nhất | Whisper small | NLLB-200 1.3B | ~2,0 GB | CPU ≥ 6 luồng, RAM ≥ 8 GB |
   | Cân bằng | Whisper small | NLLB-200 600M | ~1,3 GB | CPU 4–5 luồng |
   | Nhanh | Whisper base | NLLB-200 600M | ~0,8 GB | Máy yếu / laptop cũ |

3. Bộ cài tải model từ Hugging Face (có thanh tiến trình, kiểm tra SHA256). Nếu mất mạng, có thể cài tiếp —
   app sẽ tự tải model khi chạy lần đầu.
4. Tuỳ chọn: shortcut Desktop, tự chạy khi khởi động Windows.

Gỡ cài đặt: **Settings → Apps → LiveTrans → Uninstall** (xoá cả model đã tải).

## Sử dụng

Mở **LiveTrans** (shortcut Desktop / Start Menu) → cửa sổ LiveTrans gồm 4 tab:

- **Dịch trực tiếp** — nút lớn **Bắt đầu / Dừng dịch**, chọn nguồn âm thanh (Loa / Micro / Cả hai),
  **chất lượng dịch**, **tốc độ phụ đề** (Nhanh: câu ≤ 5 giây; Chuẩn: câu ≤ 8 giây), thời gian xử lý thực tế,
  và **Giọng đọc**: bật "Đọc to bản dịch tiếng Việt" (`Ctrl+Alt+R`), tốc độ đọc, âm lượng, nút Nghe thử.
- **Gõ Việt → Anh** — ô nhập tiếng Việt, bản tiếng Anh tự hiện; `Enter` để copy.
- **Lịch sử** — mọi câu đã dịch (copy được).
- **Cài đặt** — ẩn/hiện phụ đề, bản dịch tạm, tự ẩn phụ đề, cỡ chữ, ngôn ngữ người nói, tự chạy cùng Windows.

Đóng cửa sổ thì app vẫn chạy nền (icon **VI** ở khay hệ thống — có thể nằm trong mục **^**); mở lại shortcut
LiveTrans hoặc nhấp icon để hiện cửa sổ. Nút **Thoát LiveTrans** để tắt hẳn.
Thanh phụ đề luôn hiển thị khi đang dịch (kéo chuột để đổi vị trí).

| Phím tắt | Chức năng |
|---|---|
| `Ctrl+Alt+T` | Bật / tạm dừng dịch |
| `Ctrl+Alt+H` | Ẩn / hiện phụ đề |
| `Ctrl+Alt+M` | Đổi nguồn: Loa → Micro → Cả hai |
| `Ctrl+Alt+V` | Mở ô gõ tiếng Việt → English |
| `Ctrl+Alt+R` | Bật / tắt giọng đọc bản dịch |

**Phụ đề:** khi người nói đang nói, dòng chữ nghiêng là câu gốc + **bản dịch tạm** (cập nhật ~1,5 giây/lần).
Khi người nói ngắt câu (hoặc sau tối đa 5 giây), bản dịch chính thức (chữ lớn) xuất hiện sau ~2–4 giây
tuỳ máy và chế độ chất lượng.

**Giọng đọc (lồng tiếng):** khi bật, mỗi câu tiếng nước ngoài sau khi dịch sẽ được đọc to bằng tiếng Việt
(giọng Piper `vi_VN-vais1000-medium`, offline). Nếu đọc không kịp, câu cũ được bỏ qua để luôn bám theo câu mới
nhất. Với nguồn **Loa**, LiveTrans bắt âm thanh hệ thống **trừ tiếng của chính nó** (WASAPI process loopback,
Windows 10 2004+) nên giọng đọc không bị dịch lại. Với **Micro**, nên đeo tai nghe.

**Gõ tiếng Việt → English:** `Ctrl+Alt+V` (hoặc tab Gõ Việt → Anh) → gõ tiếng Việt (Unikey/EVKey bình thường)
→ bản tiếng Anh tự hiện khi ngừng gõ → `Enter` để copy (cửa sổ tự ẩn) → `Ctrl+V` dán vào Zoom/Teams/Messenger.
`Shift+Enter` xuống dòng, `Esc` ẩn.

Nếu máy xử lý không kịp, app sẽ báo và gợi ý chọn chất lượng thấp hơn.

## Cấu hình — `%LOCALAPPDATA%\LiveTrans\config.json`

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `quality` | `auto` | `auto` (theo lựa chọn khi cài / theo máy) · `accurate` · `balanced` · `fast` |
| `source_mode` | `loopback` | `loopback` (loa) / `mic` / `both` |
| `cpu_threads` | `0` | `0` = tự động (số luồng CPU − 1) |
| `translate_preview` | `true` | Dịch tạm câu đang nói (tắt nếu máy yếu) |
| `overlay_visible` / `overlay_autohide` | `true` / `false` | Hiện phụ đề / tự ẩn khi im lặng |
| `source_language` | `auto` | Cố định ngôn ngữ nguồn, ví dụ `"en"`, `"ja"` |
| `font_size` | `medium` | `small` / `medium` / `large` |
| `compose_hide_after_copy` | `true` | Ô gõ Việt → Anh tự xoá + ẩn sau khi copy |
| `tts_enabled` / `tts_speed` / `tts_volume` | `false` / `fast` / `0.9` | Giọng đọc: bật/tắt, tốc độ (`slow`/`normal`/`fast`/`faster`), âm lượng 0–1 |
| `hotkeys` | xem trên | Ví dụ `"Ctrl+Shift+F9"` |
| `vad.*` | | Ngưỡng cắt câu: `min_silence_ms` (450), `max_segment_s` (5), `partial_interval_s` (1.5)… |

Sửa xong thì thoát app và mở lại. Log: `%LOCALAPPDATA%\LiveTrans\logs\livetrans.log`.

## Dành cho nhà phát triển

```
.\setup.bat                      # tạo .venv, cài thư viện, tải model (chạy từ mã nguồn)
.venv\Scripts\python.exe -m livetrans --console   # chạy kèm log
.venv\Scripts\python.exe -m pytest               # unit test (thêm -m slow -s cho test tích hợp, cần model)
powershell -ExecutionPolicy Bypass -File build.ps1  # build dist\LiveTrans-Setup-<ver>.exe
```

`build.ps1` cần Inno Setup 6.7+ (`winget install JRSoftware.InnoSetup`). Các bước: tạo icon → sinh danh sách
model (URL Hugging Face ghim commit + SHA256) → PyInstaller → `LiveTrans.exe --self-test` → Inno Setup.

## Giới hạn

- Chạy trên CPU. Model mạnh hơn (Whisper large-v3, NLLB 3.3B) cần GPU NVIDIA mới kịp thời gian thực — chưa hỗ trợ.
- Model dịch NLLB-200 theo giấy phép CC-BY-NC 4.0 (chỉ dùng phi thương mại).
- Ở chế độ "Cả hai", khi đổi loa mặc định (cắm tai nghe) app chỉ bám theo thiết bị mới sau khi tạm dừng/bật lại.
