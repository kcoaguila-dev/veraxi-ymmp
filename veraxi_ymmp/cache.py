"""
TTS caching layer to prevent redundant synthesis.
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from .logging import logger


class TTSCache:
    """
    Caches synthesized audio and its duration.
    Provides in-memory caching and optional disk caching.
    """

    def __init__(self, enabled: bool = True, cache_dir: Optional[Path] = None):
        self.enabled = enabled
        self._cache: Dict[Tuple[str, int], Tuple[bytes, float]] = {}
        self.cache_dir = cache_dir

        if self.enabled and self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, text: str, speaker_id: int) -> str:
        """Generate a stable hash for the cache entry."""
        data = f"{speaker_id}:{text}".encode('utf-8')
        return hashlib.sha256(data).hexdigest()

    def get(self, text: str, speaker_id: int) -> Optional[Tuple[bytes, float]]:
        """Retrieve audio bytes and duration from cache."""
        if not self.enabled:
            return None

        key = (text, speaker_id)
        if key in self._cache:
            logger.debug(f"Cache hit (memory) for speaker {speaker_id}: {text[:10]}...")
            return self._cache[key]

        if self.cache_dir:
            hash_key = self._get_cache_key(text, speaker_id)
            wav_path = self.cache_dir / f"{hash_key}.wav"
            meta_path = self.cache_dir / f"{hash_key}.json"

            if wav_path.exists() and meta_path.exists():
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)

                    with open(wav_path, 'rb') as f:
                        wav_bytes = f.read()

                    duration = meta['duration']
                    self._cache[key] = (wav_bytes, duration)
                    logger.debug(f"Cache hit (disk) for speaker {speaker_id}: {text[:10]}...")
                    return (wav_bytes, duration)
                except Exception as e:
                    logger.warning(f"Failed to read from cache disk: {e}")

        return None

    def set(self, text: str, speaker_id: int, wav_bytes: bytes, duration: float) -> None:
        """Store audio bytes and duration into cache."""
        if not self.enabled:
            return

        key = (text, speaker_id)
        self._cache[key] = (wav_bytes, duration)

        if self.cache_dir:
            try:
                hash_key = self._get_cache_key(text, speaker_id)
                wav_path = self.cache_dir / f"{hash_key}.wav"
                meta_path = self.cache_dir / f"{hash_key}.json"

                with open(wav_path, 'wb') as f:
                    f.write(wav_bytes)

                with open(meta_path, 'w', encoding='utf-8') as f:
                    json.dump({'duration': duration, 'text': text, 'speaker_id': speaker_id}, f)
            except Exception as e:
                logger.warning(f"Failed to write to cache disk: {e}")

    def clear(self) -> None:
        """Clear the in-memory cache. Does not delete disk cache."""
        self._cache.clear()
