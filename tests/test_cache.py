from veraxi_ymmp.cache import TTSCache
import json

def test_cache_memory():
    cache = TTSCache(enabled=True)
    cache.set("hello", 1, b"wavdata", 1.5)

    assert cache.get("hello", 1) == (b"wavdata", 1.5)
    assert cache.get("hello", 2) is None
    assert cache.get("world", 1) is None

    cache.clear()
    assert cache.get("hello", 1) is None

def test_cache_disabled():
    cache = TTSCache(enabled=False)
    cache.set("hello", 1, b"wavdata", 1.5)

    assert cache.get("hello", 1) is None

def test_cache_disk(tmp_path):
    cache = TTSCache(enabled=True, cache_dir=tmp_path)

    # Store
    cache.set("hello", 1, b"wavdata", 1.5)

    # Check disk write
    hash_key = cache._get_cache_key("hello", 1)
    wav_path = tmp_path / f"{hash_key}.wav"
    meta_path = tmp_path / f"{hash_key}.json"

    assert wav_path.exists()
    assert meta_path.exists()

    with open(wav_path, "rb") as f:
        assert f.read() == b"wavdata"

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
        assert meta["duration"] == 1.5
        assert meta["text"] == "hello"
        assert meta["speaker_id"] == 1

    # Clear memory cache
    cache.clear()
    assert cache.get("hello", 1) == (b"wavdata", 1.5)
