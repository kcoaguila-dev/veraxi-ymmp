"""
VOICEVOX Engine client for text-to-speech synthesis.

Provides a Python interface to the VOICEVOX HTTP API for:
- Checking engine availability
- Synthesizing speech from text
- Listing available speakers
"""

from __future__ import annotations

import io
import asyncio
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import requests  # type: ignore

from veraxi_ymmp.core.logging import logger
from veraxi_ymmp.core.ports import NullTTSBackend as NullTTSBackend, TTSBackend as TTSBackend


class VoicevoxError(Exception):
    """Exception raised when VOICEVOX API operations fail."""

    pass


class VoicevoxClient:
    """
    Client for interacting with VOICEVOX Engine API.

    The VOICEVOX Engine provides a REST API for speech synthesis.
    This client encapsulates the API calls and handles errors.

    Attributes:
        base_url: Base URL of the VOICEVOX Engine (default: http://localhost:50021)
        timeout: Default timeout for API requests in seconds (default: 30)
    """

    DEFAULT_TIMEOUT = 120

    def __init__(self, base_url: str = "http://localhost:50021", timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize VOICEVOX client.

        Args:
            base_url: Base URL of the VOICEVOX Engine.
            timeout: Timeout in seconds for API requests.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._dictionary_synced = False

    async def is_available_async(self) -> bool:
        """Async check if the VOICEVOX server is running and accessible."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.is_available)

    async def synthesize_async(
        self,
        text: str,
        speaker_id: int,
        speed_scale: Optional[float] = None,
        clamp_silence: bool = True,
        **kwargs: Any,
    ) -> Tuple[bytes, float, Dict[str, Any]]:
        """Async version of synthesize."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.synthesize, text, speaker_id, speed_scale, clamp_silence
        )

    def ensure_started(self) -> bool:
        """Attempts to start VOICEVOX if it's not currently available."""
        if self.is_available():
            return True

        import os
        import subprocess
        import time
        from pathlib import Path

        logger.info("VOICEVOX is not running. Attempting to start it automatically...")

        # Explicit override first (works on every OS), then per-OS defaults.
        possible_paths = []
        env_path = os.environ.get("VOICEVOX_PATH", "")
        if env_path:
            possible_paths.append(Path(env_path))
        if os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            if local_app_data:
                possible_paths += [
                    Path(local_app_data) / "Programs" / "VOICEVOX" / "run.exe",
                    Path(local_app_data) / "Programs" / "VOICEVOX" / "VOICEVOX.exe",
                ]
            possible_paths += [
                Path("C:/Program Files/VOICEVOX/run.exe"),
                Path("C:/Program Files/VOICEVOX/VOICEVOX.exe"),
            ]
        else:
            possible_paths += [
                Path.home() / ".local" / "share" / "voicevox" / "run",
                Path("/opt/voicevox_engine/run"),
                Path("/opt/voicevox/run"),
                Path("/usr/local/bin/voicevox_engine"),
            ]

        exe_path = None
        for p in possible_paths:
            if p.exists():
                exe_path = p
                break

        if not exe_path:
            logger.warning("Could not find VOICEVOX executable automatically.")
            return False

        logger.info("Found VOICEVOX at %s, launching...", exe_path)
        try:
            # Launch in background without blocking
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            subprocess.Popen([str(exe_path)], creationflags=creationflags)

            # Wait for it to become available
            for _ in range(30):
                time.sleep(1)
                if self.is_available():
                    logger.info("VOICEVOX started successfully!")
                    return True

            logger.warning("VOICEVOX process launched, but API didn't become available in time.")
            return False

        except Exception as e:
            logger.error("Failed to launch VOICEVOX: %s", e)
            return False

    def is_available(self) -> bool:
        """
        Check if VOICEVOX Engine is available and responding.

        Returns:
            True if the engine responds to the version endpoint, False otherwise.
        """
        try:
            response = requests.get(f"{self.base_url}/version", timeout=3)
            return bool(response.status_code == 200)
        except requests.exceptions.RequestException:
            return False

    def sync_user_dictionary(
        self, dictionary_path: Optional[Union[str, Path]] = None
    ) -> int:
        """
        Synchronizes declarative user dictionary words into the running VOICEVOX engine.
        Uses /user_dict and /user_dict_word to register proper pronunciations, accent types,
        and POS types natively into OpenJTalk/MeCab.
        """
        import json
        from pathlib import Path

        if dictionary_path is None:
            candidates = [
                Path("assets/dictionary/tts_dictionary.json"),
                Path(__file__).resolve().parent.parent.parent / "assets" / "dictionary" / "tts_dictionary.json",
            ]
            for c in candidates:
                if c.exists():
                    dictionary_path = c
                    break

        if dictionary_path is None or not Path(dictionary_path).exists():
            return 0

        try:
            with open(dictionary_path, "r", encoding="utf-8-sig") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                return 0
        except Exception as e:
            logger.warning("Failed to read TTS dictionary %s: %s", dictionary_path, e)
            return 0

        try:
            res = requests.get(f"{self.base_url}/user_dict", timeout=5)
            existing_dict = res.json() if res.status_code == 200 else {}
        except Exception:
            return 0

        existing_words = {
            v.get("surface"): v.get("pronunciation")
            for v in existing_dict.values()
            if isinstance(v, dict)
        }

        synced_count = 0
        for entry in entries:
            surface = entry.get("surface")
            pronunciation = entry.get("pronunciation")
            if not surface or not pronunciation:
                continue

            if existing_words.get(surface) == pronunciation:
                continue

            params: Dict[str, Union[str, int]] = {
                "surface": surface,
                "pronunciation": pronunciation,
                "accent_type": entry.get("accent_type", 0),
                "priority": entry.get("priority", 8),
            }
            if "word_type" in entry:
                params["word_type"] = entry["word_type"]

            try:
                post_res = requests.post(
                    f"{self.base_url}/user_dict_word",
                    params=params,
                    timeout=5,
                )
                if post_res.status_code == 200:
                    synced_count += 1
            except Exception as reg_err:
                logger.debug("Failed to register %s to VOICEVOX user_dict: %s", surface, reg_err)

        self._dictionary_synced = True
        if synced_count > 0:
            logger.info("Synchronized %d words into VOICEVOX user dictionary.", synced_count)
        return synced_count

    def get_audio_query(self, text: str, speaker_id: int) -> Dict[str, Any]:
        """Fetch AudioQuery dictionary for text without synthesizing audio."""
        from veraxi_ymmp.audio.phonetics import tune_audio_query_pitch

        if not self._dictionary_synced and self.is_available():
            try:
                self.sync_user_dictionary()
            except Exception as e:
                logger.debug("User dictionary auto-sync skipped: %s", e)

        try:
            params: Dict[str, Union[str, int]] = {"text": text, "speaker": speaker_id}
            res = requests.post(f"{self.base_url}/audio_query", params=params, timeout=30)
            res.raise_for_status()
            return tune_audio_query_pitch(cast(Dict[str, Any], res.json()))
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to fetch audio_query: {e}")

    def synthesize(
        self,
        text: str,
        speaker_id: int,
        speed_scale: Optional[float] = None,
        clamp_silence: bool = True,
        **kwargs: Any,
    ) -> Tuple[bytes, float, Dict[str, Any]]:
        """
        Synthesize speech from text using a specific speaker.

        Args:
            text: Text to synthesize.
            speaker_id: ID of the speaker to use.
            speed_scale: Optional speech speed multiplier (e.g. 1.18 for rapid ping-pong).
            clamp_silence: If True, reduces leading and trailing phoneme silence to 0.02s.

        Returns:
            Tuple of (WAV audio bytes, duration in seconds, AudioQuery dictionary).

        Raises:
            VoicevoxError: If synthesis fails at any step.
        """
        from veraxi_ymmp.audio.phonetics import tune_audio_query_pitch

        try:
            params: Dict[str, Union[str, int]] = {"text": text, "speaker": speaker_id}
            query_res = requests.post(f"{self.base_url}/audio_query", params=params, timeout=30)
            query_res.raise_for_status()
            audio_query = tune_audio_query_pitch(cast(Dict[str, Any], query_res.json()))
            if speed_scale is not None and speed_scale > 0.0:
                audio_query["speedScale"] = float(speed_scale)
            if clamp_silence:
                if "prePhonemeLength" in audio_query:
                    audio_query["prePhonemeLength"] = min(float(audio_query["prePhonemeLength"]), 0.06)
                if "postPhonemeLength" in audio_query:
                    audio_query["postPhonemeLength"] = min(float(audio_query["postPhonemeLength"]), 0.06)
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to create audio_query: {e}")

        try:
            synth_res = requests.post(
                f"{self.base_url}/synthesis",
                params={"speaker": speaker_id},
                json=audio_query,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            synth_res.raise_for_status()
            wav_bytes = synth_res.content
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to synthesize audio: {e}")

        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                duration = frames / float(rate)
        except wave.Error as e:
            raise VoicevoxError(f"Failed to parse returned wav file: {e}")

        return wav_bytes, duration, audio_query

    def get_speakers(self) -> List[Dict[str, Any]]:
        """
        Get list of available speakers from VOICEVOX Engine.

        Returns:
            List of speaker dictionaries, each containing name, speaker_uuid, and styles.

        Raises:
            VoicevoxError: If the request fails.
        """
        try:
            res = requests.get(f"{self.base_url}/speakers", timeout=5)
            res.raise_for_status()
            return cast(List[Dict[str, Any]], res.json())
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to list speakers: {e}")
