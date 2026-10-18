# PyInstaller spec — build bằng: python -m PyInstaller packaging/LiveTrans.spec --noconfirm
# Kết quả: packaging/build/dist/LiveTrans/LiveTrans.exe (onedir, không console)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "packaging" / "build"

datas = collect_data_files("faster_whisper")  # assets/silero_vad_v6.onnx
# Giọng đọc Piper: chỉ cần dữ liệu espeak-ng (bỏ dữ liệu tiếng Hebrew/Arabic ~25 MB)
datas += collect_data_files("piper", includes=["espeak-ng-data/**/*"])
binaries = collect_dynamic_libs("ctranslate2")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["pyaudiowpatch", "sentencepiece", "piper", "piper.espeakbridge"],
    excludes=["tkinter", "pytest", "IPython", "matplotlib", "PyInstaller", "setuptools", "pip"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiveTrans",
    console=False,
    icon=str(BUILD / "LiveTrans.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LiveTrans", upx=False)
