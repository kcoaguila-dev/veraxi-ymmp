import pytest
from unittest.mock import patch, Mock
import io
import wave
from veraxi_ymmp.voicevox import VoicevoxClient, VoicevoxError
import requests

def create_mock_wav(frames, rate):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b'\x00' * 2 * frames)
    return buf.getvalue()

@patch('requests.get')
def test_is_available_true(mock_get):
    mock_get.return_value.status_code = 200
    client = VoicevoxClient()
    assert client.is_available() is True

@patch('requests.get')
def test_is_available_false(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError()
    client = VoicevoxClient()
    assert client.is_available() is False

@patch('requests.post')
def test_synthesize_success(mock_post):
    mock_query_res = Mock()
    mock_query_res.json.return_value = {"fake": "query"}
    mock_query_res.raise_for_status.return_value = None

    mock_synth_res = Mock()
    mock_synth_res.raise_for_status.return_value = None
    # 2 seconds of audio at 24000 Hz
    mock_wav = create_mock_wav(48000, 24000)
    mock_synth_res.content = mock_wav

    mock_post.side_effect = [mock_query_res, mock_synth_res]

    client = VoicevoxClient()
    wav_bytes, duration = client.synthesize("こんにちは", 3)

    assert duration == 2.0
    assert wav_bytes == mock_wav

    assert mock_post.call_count == 2
    mock_post.assert_any_call(
        "http://localhost:50021/audio_query",
        params={"text": "こんにちは", "speaker": 3},
        timeout=10
    )
    mock_post.assert_any_call(
        "http://localhost:50021/synthesis",
        params={"speaker": 3},
        json={"fake": "query"},
        headers={"Content-Type": "application/json"},
        timeout=30
    )

@patch('requests.post')
def test_synthesize_error(mock_post):
    mock_post.side_effect = requests.exceptions.HTTPError("404 Client Error")

    client = VoicevoxClient()
    with pytest.raises(VoicevoxError, match="Failed to create audio_query:"):
        client.synthesize("こんにちは", 3)
