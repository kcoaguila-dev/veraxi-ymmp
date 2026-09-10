import os
import pytest
from unittest.mock import AsyncMock
from pathlib import Path
from veraxi_ymmp.async_compiler import AsyncYMMPCompiler
from veraxi_ymmp.config import CompilerConfig
from veraxi_ymmp.voicevox import TTSBackend

class MockAsyncTTSBackend:
    def is_available(self):
        return True

    async def is_available_async(self):
        return True

    def synthesize(self, text, speaker_id):
        return b"sync_wav", 1.0

    async def synthesize_async(self, text, speaker_id):
        return b"async_wav", 1.0

@pytest.mark.asyncio
async def test_compile_async(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    output_path = tmp_path / "output_async.ymmp"

    script = [
        { "character": "ゆっくり霊夢", "text": "こんにちは" },
        { "character": "ゆっくり魔理沙", "text": "こんばんは" }
    ]

    config = CompilerConfig(use_tts=True, speaker_map={"ゆっくり霊夢": 10})
    backend = MockAsyncTTSBackend()

    compiler = AsyncYMMPCompiler(
        template_path=template_path,
        config=config,
        tts_backend=backend
    )

    result = await compiler.compile_async(script, output_path)

    assert result.output_path == output_path
    assert result.voice_item_count == 2
    assert result.tachie_item_count == 2  # Based on template fixtures
    assert result.item_count == 4

    # Each synthesizes 1 second, at 60fps = 60 frames, so 120 frames total for 2 items
    assert result.total_frames == 120
    assert result.total_duration_seconds == 2.0
    assert len(result.audio_files) == 2


@pytest.mark.asyncio
async def test_compile_async_director_script(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    output_path = tmp_path / "output_async_director.ymmp"

    script = [
        {
            "character": "ゆっくり霊夢",
            "text": "こんにちは",
            "emotion": "happy",
            "motion": "jump",
            "bgm": "theme.mp3",
            "sfx": "bang.wav"
        }
    ]

    config = CompilerConfig(use_tts=True, speaker_map={"ゆっくり霊夢": 10})
    backend = MockAsyncTTSBackend()

    compiler = AsyncYMMPCompiler(
        template_path=template_path,
        config=config,
        tts_backend=backend
    )

    result = await compiler.compile_async(script, output_path)

    assert result.output_path == output_path
    assert len(result.warnings) == 4
    assert any("Emotion 'happy'" in w for w in result.warnings)
    assert any("Motion 'jump'" in w for w in result.warnings)
    assert any("BGM 'theme.mp3'" in w for w in result.warnings)
    assert any("SFX 'bang.wav'" in w for w in result.warnings)

@pytest.mark.asyncio
async def test_compile_async_diagnostics_reset(tmp_path):
    template_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'sample_template.ymmp')
    output_path = tmp_path / "output_async_director_1.ymmp"
    output_path_2 = tmp_path / "output_async_director_2.ymmp"

    script_director = [
        {
            "character": "ゆっくり霊夢",
            "text": "こんにちは",
            "emotion": "happy",
            "motion": "jump",
            "bgm": "theme.mp3",
            "sfx": "bang.wav"
        }
    ]

    script_writer = [
        {
            "character": "ゆっくり霊夢",
            "text": "こんにちは"
        }
    ]

    config = CompilerConfig(use_tts=True, speaker_map={"ゆっくり霊夢": 10})
    backend = MockAsyncTTSBackend()

    compiler = AsyncYMMPCompiler(
        template_path=template_path,
        config=config,
        tts_backend=backend
    )

    # First compilation issues warnings
    result1 = await compiler.compile_async(script_director, output_path)
    assert len(result1.warnings) == 4

    # Second compilation with normal writer script should have NO warnings
    result2 = await compiler.compile_async(script_writer, output_path_2)
    assert len(result2.warnings) == 0
