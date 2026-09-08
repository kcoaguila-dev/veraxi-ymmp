import argparse
from pathlib import Path
from veraxi_ymmp.config import CompilerConfig
from veraxi_ymmp.constants import DEFAULT_FPS

def test_compiler_config_defaults():
    config = CompilerConfig()
    assert config.fps == DEFAULT_FPS
    assert config.use_tts is False
    assert config.use_cache is True
    assert config.cache_dir is None

def test_compiler_config_from_cli_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tts", action="store_true")
    parser.add_argument("--voicevox-url", default="http://localhost:50021")
    parser.add_argument("--default-speaker", type=int, default=3)
    parser.add_argument("--bom", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--cache-dir", type=str)

    args = parser.parse_args(["--tts", "--default-speaker", "10", "--no-cache", "--cache-dir", "/tmp/cache"])

    config = CompilerConfig.from_cli_args(args)

    assert config.use_tts is True
    assert config.default_speaker_id == 10
    assert config.use_cache is False
    assert config.cache_dir == Path("/tmp/cache")
    assert config.use_bom is False
