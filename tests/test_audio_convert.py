import numpy as np

from livetrans.audio_capture import Resampler, to_mono


def test_to_mono_averages_channels():
    data = np.array([[0.2, 0.4], [1.0, -1.0], [0.0, 0.5]], dtype=np.float32)
    out = to_mono(data.tobytes(), 2)
    assert out.dtype == np.float32
    assert np.allclose(out, [0.3, 0.0, 0.25])


def test_to_mono_six_channels_length():
    data = np.zeros((44100, 6), dtype=np.float32)
    assert len(to_mono(data.tobytes(), 6)) == 44100


def test_resampler_44100_to_16000_streaming():
    r = Resampler(44100)
    t = np.arange(44100) / 44100
    mono = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    total = 0
    for i in range(0, 44100, 441):  # khối 10 ms
        total += len(r.process(mono[i : i + 441]))
    assert abs(total - 16000) <= 160
    out = r.process(mono[:441])
    assert out.dtype == np.float32


def test_resampler_48000():
    r = Resampler(48000)
    total = sum(len(r.process(np.zeros(960, np.float32))) for _ in range(50))  # 1 s
    assert abs(total - 16000) <= 160


def test_resampler_passthrough_16k():
    r = Resampler(16000)
    x = np.ones(512, np.float32)
    assert r.process(x) is x
