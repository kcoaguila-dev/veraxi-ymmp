"""Unit tests for YouTube OAuth2 authentication flow and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from google.oauth2.credentials import Credentials

from veraxi_ymmp.youtube_auth import (
    authenticate_youtube,
    load_credentials,
    refresh_credentials,
)


@pytest.fixture
def mock_flow():
    with patch("veraxi_ymmp.youtube_auth.InstalledAppFlow") as mock:
        flow_instance = MagicMock()
        mock.from_client_secrets_file.return_value = flow_instance
        yield flow_instance


@pytest.fixture
def dummy_secrets(tmp_path: Path) -> Path:
    p = tmp_path / "client_secrets.json"
    p.write_text('{"installed": {"client_id": "test_id", "client_secret": "test_secret"}}')
    return p


@pytest.fixture
def dummy_token_data():
    return {
        "token": "test_token",
        "refresh_token": "test_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test_id",
        "client_secret": "test_secret",
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    }


def test_auth_flow_writes_token_to_tmp_path(mock_flow, dummy_secrets, tmp_path: Path):
    """Test that auth flow successfully writes credentials to the specified token path."""
    token_out = tmp_path / "test_token.json"

    mock_creds = MagicMock(spec=Credentials)
    mock_creds.token = "fake_token"
    mock_creds.refresh_token = "fake_refresh_token"
    mock_creds.token_uri = "https://oauth2.googleapis.com/token"
    mock_creds.client_id = "test_id"
    mock_creds.client_secret = "test_secret"
    mock_creds.scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    mock_flow.run_local_server.return_value = mock_creds

    result_path = authenticate_youtube(
        client_secrets_path=dummy_secrets,
        token_out_path=token_out,
    )

    assert result_path == token_out
    assert token_out.exists()

    data = json.loads(token_out.read_text(encoding="utf-8"))
    assert data["token"] == "fake_token"
    assert data["refresh_token"] == "fake_refresh_token"


def test_auth_flow_no_browser(mock_flow, dummy_secrets, tmp_path: Path):
    """Test console auth flow without opening a browser."""
    token_out = tmp_path / "test_token_console.json"

    mock_creds = MagicMock(spec=Credentials)
    mock_creds.token = "fake_token_console"
    mock_creds.refresh_token = "fake_refresh_token_console"
    mock_creds.token_uri = "https://oauth2.googleapis.com/token"
    mock_creds.client_id = "test_id"
    mock_creds.client_secret = "test_secret"
    mock_creds.scopes = []

    mock_flow.run_console.return_value = mock_creds

    authenticate_youtube(
        client_secrets_path=dummy_secrets,
        token_out_path=token_out,
        no_browser=True,
    )

    assert mock_flow.run_console.called
    assert not mock_flow.run_local_server.called

    data = json.loads(token_out.read_text(encoding="utf-8"))
    assert data["token"] == "fake_token_console"


def test_refresh_and_persist_token(tmp_path: Path, dummy_token_data):
    """Test refreshing credentials and persisting the new token."""
    token_path = tmp_path / "youtube_token.json"
    token_path.write_text(json.dumps(dummy_token_data))

    creds = load_credentials(token_path)

    with patch.object(Credentials, "expired", return_value=True, new_callable=PropertyMock) as mock_expired:
        with patch.object(creds, "refresh") as mock_refresh:
            def side_effect(request):
                creds.token = "new_refreshed_token"
                mock_expired.return_value = False
            mock_refresh.side_effect = side_effect

            refreshed_creds = refresh_credentials(creds, token_path)

            assert mock_refresh.called
            assert refreshed_creds.token == "new_refreshed_token"
            assert not refreshed_creds.expired

            # Verify persistence
            saved_data = json.loads(token_path.read_text(encoding="utf-8"))
            assert saved_data["token"] == "new_refreshed_token"


def test_env_json_source_not_persisted(tmp_path: Path):
    """Test that refreshed credentials aren't saved if no token path is provided."""
    creds = Credentials(
        token="old_token",
        refresh_token="old_refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test_id",
        client_secret="test_secret",
    )

    with patch.object(Credentials, "expired", return_value=True, new_callable=PropertyMock) as mock_expired:
        with patch.object(creds, "refresh") as mock_refresh:
            def side_effect(request):
                creds.token = "new_memory_token"
                mock_expired.return_value = False
            mock_refresh.side_effect = side_effect

            refreshed_creds = refresh_credentials(creds, token_path=None)

            assert mock_refresh.called
            assert refreshed_creds.token == "new_memory_token"
