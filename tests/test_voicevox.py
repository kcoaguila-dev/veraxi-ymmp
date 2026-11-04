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
    wav_bytes, duration, _ = client.synthesize("こんにちは", 3)

    assert duration == 2.0
    assert wav_bytes == mock_wav

    assert mock_post.call_count == 2
    mock_post.assert_any_call(
        "http://localhost:50021/audio_query",
        params={"text": "こんにちは", "speaker": 3},
        timeout=30
    )
    mock_post.assert_any_call(
        "http://localhost:50021/synthesis",
        params={"speaker": 3},
        json={"fake": "query"},
        headers={"Content-Type": "application/json"},
        timeout=client.timeout
    )

@patch('requests.post')
def test_synthesize_error(mock_post):
    mock_post.side_effect = requests.exceptions.HTTPError("404 Client Error")

    client = VoicevoxClient()
    with pytest.raises(VoicevoxError, match="Failed to create audio_query:"):
        client.synthesize("こんにちは", 3)


@patch('requests.get')
@patch('requests.post')
def test_sync_user_dictionary_success(mock_post, mock_get, tmp_path):
    dict_file = tmp_path / "custom_dict.json"
    dict_file.write_text('[{"surface": "AIインフラ", "pronunciation": "エーアイインフラ", "accent_type": 5}]', encoding='utf-8')

    mock_get_res = Mock()
    mock_get_res.status_code = 200
    mock_get_res.json.return_value = {}
    mock_get.return_value = mock_get_res

    mock_post_res = Mock()
    mock_post_res.status_code = 200
    mock_post.return_value = mock_post_res

    client = VoicevoxClient()
    count = client.sync_user_dictionary(dictionary_path=dict_file)

    assert count == 1
    mock_post.assert_called_once()
    assert client._dictionary_synced is True


@patch('requests.get')
@patch('requests.post')
def test_sync_user_dictionary_skips_existing(mock_post, mock_get, tmp_path):
    dict_file = tmp_path / "custom_dict.json"
    dict_file.write_text('[{"surface": "AIインフラ", "pronunciation": "エーアイインフラ", "accent_type": 5}]', encoding='utf-8')

    mock_get_res = Mock()
    mock_get_res.status_code = 200
    mock_get_res.json.return_value = {
        "word-uuid-1": {
            "surface": "AIインフラ",
            "pronunciation": "エーアイインフラ"
        }
    }
    mock_get.return_value = mock_get_res

    client = VoicevoxClient()
    count = client.sync_user_dictionary(dictionary_path=dict_file)

    assert count == 0
    mock_post.assert_not_called()
    assert client._dictionary_synced is True


def test_sync_user_dictionary_missing_file():
    client = VoicevoxClient()
    count = client.sync_user_dictionary(dictionary_path="nonexistent_dict.json")
    assert count == 0
