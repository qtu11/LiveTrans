# Build LiveTrans.exe (PyInstaller) và bộ cài dist\LiveTrans-Setup-<version>.exe (Inno Setup 6.7+).
# Chạy: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Chưa có .venv — chạy setup.bat trước." }
& $py -m pip install --quiet "pyinstaller==6.22.3"

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Không thấy Inno Setup 6 — cài bằng: winget install JRSoftware.InnoSetup" }

$version = (& $py -c "import livetrans; print(livetrans.__version__)").Trim()
Write-Host "== LiveTrans $version"

Write-Host "== [1/4] Icon + danh sách model"
& $py packaging\make_icon.py
& $py packaging\gen_models_iss.py

Write-Host "== [2/4] PyInstaller"
& $py -m PyInstaller packaging\LiveTrans.spec --noconfirm --distpath packaging\build\dist --workpath packaging\build\work
if ($LASTEXITCODE -ne 0) { throw "PyInstaller lỗi" }

Write-Host "== [3/4] Kiểm tra nhanh LiveTrans.exe"
$exe = "packaging\build\dist\LiveTrans\LiveTrans.exe"
if (Test-Path "models") { $env:LIVETRANS_MODELS = (Resolve-Path "models").Path }  # có model → thử nạp luôn
$p = Start-Process $exe -ArgumentList "--self-test" -Wait -PassThru -WindowStyle Hidden
Remove-Item Env:LIVETRANS_MODELS -ErrorAction SilentlyContinue
if ($p.ExitCode -ne 0) { throw "LiveTrans.exe --self-test lỗi (exit $($p.ExitCode)), xem %LOCALAPPDATA%\LiveTrans\logs" }

Write-Host "== [4/4] Inno Setup"
# ISCC chỉ đọc đúng tiếng Việt khi file .iss là UTF-8 có BOM
$iss = Join-Path $PSScriptRoot "packaging\LiveTrans.iss"
[IO.File]::WriteAllText($iss, [IO.File]::ReadAllText($iss), [Text.UTF8Encoding]::new($true))
& $iscc "/DAppVersion=$version" $iss
if ($LASTEXITCODE -ne 0) { throw "ISCC lỗi" }
Get-Item "dist\LiveTrans-Setup-$version.exe" | Select-Object FullName, @{n = "MB"; e = { [math]::Round($_.Length / 1MB) } }
