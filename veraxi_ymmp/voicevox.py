import requests
import wave
import io
import json
from typing import Tuple

class VoicevoxError(Exception):
    pass

class VoicevoxClient:
    def __init__(self, base_url: str = "http://localhost:50021"):
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/version", timeout=3)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def synthesize(self, text: str, speaker_id: int) -> Tuple[bytes, float]:
        try:
            query_res = requests.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
                timeout=10
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
                timeout=30
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

        return wav_bytes, duration

    def get_speakers(self):
        try:
            res = requests.get(f"{self.base_url}/speakers", timeout=5)
            res.raise_for_status()
            return res.json()
        except requests.exceptions.RequestException as e:
            raise VoicevoxError(f"Failed to list speakers: {e}")
