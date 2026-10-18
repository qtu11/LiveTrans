import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

SENTENCES = [
    "Good morning everyone. Today we will talk about the weather this weekend.",
    "The meeting has been moved to three o'clock tomorrow afternoon.",
]


def _tts(path: Path, text: str) -> None:
    script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile('{path}', $fmt)
$s.Speak('{text.replace("'", "''")}')
$s.Dispose()
"""
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True)


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == 16000 and w.getsampwidth() == 2 and w.getnchannels() == 1
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


@pytest.fixture(scope="session")
def speech_audio(tmp_path_factory) -> np.ndarray:
    """Hai câu tiếng Anh (SAPI), cách nhau 1 s lặng, 16 kHz float32."""
    d = tmp_path_factory.mktemp("tts")
    silence = np.zeros(16000, dtype=np.float32)
    parts = [silence[:8000]]
    for i, text in enumerate(SENTENCES):
        p = d / f"s{i}.wav"
        _tts(p, text)
        parts += [_read_wav(p), silence]
    return np.concatenate(parts)
