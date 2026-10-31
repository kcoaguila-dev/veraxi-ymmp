"""
Tests for Upstream Audio Gain Staging and Loudness Targeting.
"""

from __future__ import annotations

import io
import json
import struct
import wave
from pathlib import Path


from veraxi_ymmp.audio_normalizer import (
    gain_stage_audio_bytes,
    gain_stage_audio_file,
)
from veraxi_ymmp.config import CompilerConfig
from veraxi_ymmp.constants import (
    DEFAULT_AUDIO_SAMPLE_RATE,
    DEFAULT_SPEECH_TARGET_LUFS,
    DEFAULT_SPEECH_TARGET_TP,
)
from veraxi_ymmp.ir_builder import TimelineIRBuilder
from veraxi_ymmp.ports import NullTTSBackend


def _generate_synthetic_speech_wav(duration_sec: float = 1.5, sample_rate: int = 24000) -> bytes:
    """Generate simple synthetic PCM 16-bit audio bytes for testing."""
    buf = io.BytesIO()
    total_frames = int(duration_sec * sample_rate)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        # Alternate amplitude to emulate speech acoustic energy
        frames = bytearray()
        for i in range(total_frames):
            val = int(8000 if (i // 100) % 2 == 0 else -8000)
            frames.extend(struct.pack("<h", val))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def test_compiler_config_gain_stage_defaults() -> None:
    """Verify CompilerConfig defaults initialize with upstream gain staging enabled."""
    config = CompilerConfig()
    assert config.gain_stage_speech is True
    assert config.target_speech_lufs == DEFAULT_SPEECH_TARGET_LUFS
    assert config.target_speech_tp == DEFAULT_SPEECH_TARGET_TP
    assert config.audio_sample_rate == DEFAULT_AUDIO_SAMPLE_RATE


def test_gain_stage_audio_bytes() -> None:
    """Verify in-memory audio gain staging returns calibrated bytes."""
    raw_wav = _generate_synthetic_speech_wav(duration_sec=1.0, sample_rate=24000)
    staged = gain_stage_audio_bytes(raw_wav, target_i=-16.0, target_tp=-1.5, sample_rate=48000)

    assert isinstance(staged, bytes)
    assert len(staged) > 0

    # Verify output is a valid 48kHz WAV
    with wave.open(io.BytesIO(staged), "rb") as w:
        assert w.getframerate() == 48000
        assert w.getnchannels() == 1
        dur = w.getnframes() / float(w.getframerate())
        assert abs(dur - 1.0) < 0.05


def test_gain_stage_audio_file(tmp_path: Path) -> None:
    """Verify file-based gain staging accurately replaces file in place."""
    wav_path = tmp_path / "test_dialogue.wav"
    raw_wav = _generate_synthetic_speech_wav(duration_sec=2.0, sample_rate=24000)
    wav_path.write_bytes(raw_wav)

    result_path = gain_stage_audio_file(
        wav_path,
        target_i=-16.0,
        target_tp=-1.5,
        sample_rate=48000,
    )
    assert result_path == wav_path
    assert wav_path.exists()

    with wave.open(str(wav_path), "rb") as w:
        assert w.getframerate() == 48000
        dur = w.getnframes() / float(w.getframerate())
        assert abs(dur - 2.0) < 0.05


class MockGainStageTTSBackend(NullTTSBackend):
    def synthesize(self, text: str, speaker_id: int):
        wav = _generate_synthetic_speech_wav(duration_sec=1.2, sample_rate=24000)
        return wav, 1.2, {"speech": text}


def test_ir_builder_synthesize_audio_gain_stages_file(tmp_path: Path) -> None:
    """Verify TimelineIRBuilder gain-stages speech audio and saves metadata."""
    audio_dir = tmp_path / "audio"
    config = CompilerConfig(gain_stage_speech=True, target_speech_lufs=-16.0)
    builder = TimelineIRBuilder(
        template_data={"Timelines": [{"VideoInfo": {"FPS": 60}}]},
        character_templates={},
        face_templates={},
        config=config,
        tts_backend=MockGainStageTTSBackend(),
    )

    length, out_path, query = builder.synthesize_audio(
        idx=1,
        char_name="ずんだもん",
        text="テスト音声なのだ",
        audio_dir=audio_dir,
    )

    assert out_path is not None
    assert out_path.exists()

    # Verify meta.json records gain staging status
    meta_path = out_path.with_suffix(".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta.get("gain_staged") is True
    assert meta.get("target_lufs") == -16.0

    # Verify duration
    with wave.open(str(out_path), "rb") as w:
        assert w.getframerate() == 48000
        dur = w.getnframes() / float(w.getframerate())
        assert abs(dur - 1.2) < 0.05


def test_gain_stage_graceful_fallback(tmp_path: Path) -> None:
    """Verify fallback behavior when file is corrupt."""
    corrupt_path = tmp_path / "corrupt.wav"
    corrupt_path.write_bytes(b"not a real wav header")

    # Should not crash; returns path gracefully
    res = gain_stage_audio_file(corrupt_path)
    assert res == corrupt_path
    assert corrupt_path.read_bytes() == b"not a real wav header"
