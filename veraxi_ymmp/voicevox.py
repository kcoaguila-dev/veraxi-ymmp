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
from typing import Any, Dict, List, Tuple, Protocol

import requests



class TTSBackend(Protocol):
    """Protocol defining the interface for TTS backends."""

    def is_available(self) -> bool:
        ...

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float, Dict[str, Any]]:
        ...

    def get_speakers(self) -> List[Dict[str, Any]]:
        ...


class NullTTSBackend:
    """A dummy TTS backend for testing or placeholder generation."""

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float, Dict[str, Any]]:
        return b"", 0.0, {}

    def get_speakers(self) -> List[Dict[str, Any]]:
        return []


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

    DEFAULT_TIMEOUT = 30

    def __init__(self, base_url: str = "http://localhost:50021", timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize VOICEVOX client.

        Args:
            base_url: Base URL of the VOICEVOX Engine.
            timeout: Timeout in seconds for API requests.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def is_available_async(self) -> bool:
        """Async check if the VOICEVOX server is running and accessible."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.is_available)

    async def synthesize_async(self, text: str, speaker_id: int) -> Tuple[bytes, float]:
        """Async version of synthesize."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.synthesize, text, speaker_id)

    def is_available(self) -> bool:
        """
        Check if VOICEVOX Engine is available and responding.

        Returns:
            True if the engine responds to the version endpoint, False otherwise.
        """
        try:
            response = requests.get(f"{self.base_url}/version", timeout=3)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float, Dict[str, Any]]:
        """
        Synthesize speech from text using a specific speaker.

        Args:
            text: Text to synthesize.
            speaker_id: ID of the speaker to use.

        Returns:
            Tuple of (WAV audio bytes, duration in seconds, AudioQuery dictionary).

        Raises:
            VoicevoxError: If synthesis fails at any step.
        """
        try:
            query_res = requests.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
                timeout=30
            )
            query_res.raise_for_status()
            audio_query = query_res.json()
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to create audio_query: {e}")

        try:
            synth_res = requests.post(
                f"{self.base_url}/synthesis",
                params={"speaker": speaker_id},
                json=audio_query,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            synth_res.raise_for_status()
            wav_bytes = synth_res.content
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to synthesize audio: {e}")

        try:
            with wave.open(io.BytesIO(wav_bytes), 'rb') as w:
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
            return res.json()
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to list speakers: {e}")
