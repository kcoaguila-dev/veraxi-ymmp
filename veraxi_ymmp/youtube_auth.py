"""YouTube Authentication Infrastructure Module.

Provides OAuth2 bootstrap and credential management for YouTube Data API v3 and YouTube Analytics API v2.
Handles token saving and loading from `~/.veraxi-ymmp/youtube_token.json` with secure permissions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .logging import logger

# YouTube OAuth Scopes
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_default_token_path() -> Path:
    """Return the default path to the YouTube token."""
    config_dir = Path.home() / ".veraxi-ymmp"
    config_dir.mkdir(parents=True, exist_ok=True)
    # restrict permissions on the config dir if POSIX
    if os.name == "posix":
        config_dir.chmod(0o700)
    return config_dir / "youtube_token.json"


def authenticate_youtube(
    client_secrets_path: Path,
    token_out_path: Optional[Path] = None,
    monetary: bool = False,
    no_browser: bool = False,
) -> Path:
    """Bootstrap YouTube OAuth2 authentication and write the token to disk."""
    if not client_secrets_path.exists():
        raise FileNotFoundError(f"Client secrets file not found: {client_secrets_path}")

    scopes = list(YOUTUBE_SCOPES)
    if monetary:
        scopes.append("https://www.googleapis.com/auth/yt-analytics-monetary.readonly")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secrets_path), scopes
    )

    if no_browser:
        credentials = flow.run_console()
    else:
        credentials = flow.run_local_server(port=0)

    out_path = token_out_path or get_default_token_path()

    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }

    tmp_path = out_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(token_data, f)

    if os.name == "posix":
        tmp_path.chmod(0o600)

    os.replace(tmp_path, out_path)

    logger.info(f"YouTube authentication successful. Token saved to {out_path}")
    return out_path


def load_credentials(token_path: Path) -> Any:
    """Load credentials from a token file."""
    if not token_path.exists():
        raise FileNotFoundError(f"Token file not found: {token_path}")

    with open(token_path, "r", encoding="utf-8") as f:
        token_data = json.load(f)

    return Credentials.from_authorized_user_info(token_data, YOUTUBE_SCOPES)


def refresh_credentials(credentials: Credentials, token_path: Optional[Path] = None) -> Credentials:
    """Refresh expired credentials and optionally persist the refreshed token."""
    if credentials.expired and credentials.refresh_token:
        logger.info("Refreshing expired YouTube credentials.")
        credentials.refresh(Request())

        if token_path:
            token_data = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
            }
            tmp_path = token_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(token_data, f)
            if os.name == "posix":
                tmp_path.chmod(0o600)
            os.replace(tmp_path, token_path)

    return credentials
