import json

from livetrans.config import (
    CONFIG_VERSION,
    Config,
    VadConfig,
    apply_speed,
    load_config,
    save_config,
    speed_of,
)


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg == Config()
    assert cfg.source_mode == "loopback"
    assert cfg.cpu_threads == 0
    assert cfg.vad.min_silence_ms == 450
    assert cfg.vad.max_segment_s == 5.0
    assert cfg.overlay_autohide is False
    assert cfg.hotkeys.toggle == "Ctrl+Alt+T"


def test_wrong_types_fall_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps({"config_version": CONFIG_VERSION, "cpu_threads": "x", "source_mode": "foo",
                    "vad": {"min_silence_ms": 900}}),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.cpu_threads == 0
    assert cfg.source_mode == "loopback"
    assert cfg.vad.min_silence_ms == 900
    assert cfg.vad.max_segment_s == 5.0


def test_int_accepted_for_float(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"config_version": CONFIG_VERSION, "vad": {"max_segment_s": 6}}), encoding="utf-8")
    assert load_config(p).vad.max_segment_s == 6.0


def test_corrupt_json_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_config(p) == Config()


def test_v1_config_migrates_vad_but_keeps_user_choices(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps({"source_mode": "both", "font_size": "large", "cpu_threads": 4,
                    "vad": {"min_silence_ms": 600, "max_segment_s": 8.0, "partial_interval_s": 2.0}}),
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.source_mode == "both" and cfg.font_size == "large"
    assert cfg.vad == VadConfig()
    assert cfg.cpu_threads == 0
    assert cfg.config_version == CONFIG_VERSION


def test_speed_presets():
    vad = VadConfig()
    assert speed_of(vad) == "fast"
    apply_speed(vad, "standard")
    assert (vad.min_silence_ms, vad.max_segment_s, vad.partial_interval_s) == (600, 8.0, 2.0)
    assert speed_of(vad) == "standard"
    vad.max_segment_s = 6.5
    assert speed_of(vad) is None


def test_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = Config(source_mode="both", font_size="large", overlay_pos=[100, 900], overlay_autohide=True)
    cfg.vad.partial_interval_s = 1.2
    save_config(cfg, p)
    assert load_config(p) == cfg
