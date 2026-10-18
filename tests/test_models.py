import json

from livetrans import models
from livetrans.models import PROFILES, auto_threads, recommend_profile, resolve_profile, whisper_complete


def test_whisper_complete_requires_all_files(tmp_path):
    for name in ("config.json", "model.bin"):
        (tmp_path / name).write_text("x")
    assert not whisper_complete(tmp_path)  # thiếu tokenizer + vocabulary (tải dở)
    (tmp_path / "tokenizer.json").write_text("x")
    assert not whisper_complete(tmp_path)
    (tmp_path / "vocabulary.txt").write_text("x")
    assert whisper_complete(tmp_path)


def test_whisper_complete_missing_dir(tmp_path):
    assert not whisper_complete(tmp_path / "nope")


def test_recommend_profile():
    assert recommend_profile(6, 64) == "accurate"  # i5-9400F, 64 GB
    assert recommend_profile(12, 16) == "accurate"
    assert recommend_profile(8, 4) == "fast"  # thiếu RAM
    assert recommend_profile(4, 8) == "balanced"
    assert recommend_profile(2, 8) == "fast"


def test_profiles_definition():
    assert PROFILES["accurate"].mt == "nllb-1.3B"
    assert PROFILES["fast"].whisper == "base"
    assert all(p.mt in models.MT_MODELS for p in PROFILES.values())


def test_resolve_explicit_quality():
    assert resolve_profile("fast").key == "fast"


def test_resolve_auto_uses_install_choice(tmp_path, monkeypatch):
    f = tmp_path / "install_profile.json"
    f.write_text(json.dumps({"quality": "balanced"}), encoding="utf-8")
    monkeypatch.setattr(models, "INSTALL_PROFILE_PATH", f)
    assert resolve_profile("auto").key == "balanced"


def test_resolve_auto_without_install_file_uses_hardware(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "INSTALL_PROFILE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(models, "total_ram_gb", lambda: 4.0)
    assert resolve_profile("auto").key == "fast"


def test_auto_threads():
    assert auto_threads(6) == 4
    assert auto_threads(4) == 3
    assert auto_threads(2) == 2
    assert auto_threads(32) == 8
