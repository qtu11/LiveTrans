@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Tạo môi trường Python .venv ...
    python -m venv .venv || goto :error
)

echo [2/3] Cài thư viện ...
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error

echo [3/3] Tải model (lần đầu khoảng 1,3 GB) ...
".venv\Scripts\python.exe" -m livetrans --download-models || goto :error

echo.
echo Xong! Chạy LiveTranslate.vbs để bắt đầu.
pause
exit /b 0

:error
echo.
echo Có lỗi xảy ra, xem thông báo ở trên.
pause
exit /b 1
