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


def get_default_client_secrets_path() -> Path:
    """Return the default path to client_secrets.json."""
    config_dir = Path.home() / ".veraxi-ymmp"
    config_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        config_dir.chmod(0o700)
    return config_dir / "client_secrets.json"


def resolve_client_secrets_path(explicit_path: Optional[Path] = None) -> Optional[Path]:
    """Resolve client_secrets.json path following the priority chain."""
    if explicit_path and explicit_path.exists():
        return explicit_path

    env_path = os.getenv("VERAXI_YOUTUBE_CLIENT_SECRETS") or os.getenv("YOUTUBE_CLIENT_SECRETS")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    try:
        default_path = get_default_client_secrets_path()
        if default_path.exists():
            return default_path
    except (RuntimeError, KeyError):
        pass

    return None


def save_client_secrets(raw_json_or_dict: Any, target_path: Optional[Path] = None) -> Path:
    """Validate and atomically persist client_secrets.json to disk."""
    if isinstance(raw_json_or_dict, str):
        try:
            data = json.loads(raw_json_or_dict)
        except Exception as e:
            raise ValueError(f"Invalid JSON string provided for client_secrets: {e}") from e
    elif isinstance(raw_json_or_dict, dict):
        data = raw_json_or_dict
    else:
        raise ValueError("client_secrets must be a JSON string or dict")

    # Validate schema: must contain 'installed' or 'web' with client_id and client_secret
    app_info = data.get("installed") or data.get("web")
    if not isinstance(app_info, dict) or not app_info.get("client_id") or not app_info.get("client_secret"):
        raise ValueError("Invalid client_secrets format: must contain 'installed' or 'web' object with 'client_id' and 'client_secret'")

    out_path = target_path or get_default_client_secrets_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    if os.name == "posix":
        tmp_path.chmod(0o600)
    os.replace(tmp_path, out_path)
    return out_path


def revoke_token(token_path: Optional[Path] = None) -> bool:
    """Remove/revoke the stored token file."""
    path = token_path or get_default_token_path()
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError as e:
            logger.warning(f"Failed to delete token file {path}: {e}")
            return False
    return False


def get_auth_status(token_path: Optional[Path] = None, client_secrets_path: Optional[Path] = None) -> dict[str, Any]:
    """Inspect and return current YouTube OAuth authentication status."""
    resolved_secrets = resolve_client_secrets_path(client_secrets_path)
    has_secrets = resolved_secrets is not None and resolved_secrets.exists()

    resolved_token = token_path
    if not resolved_token:
        env_token = os.getenv("VERAXI_YOUTUBE_TOKEN_PATH") or os.getenv("YOUTUBE_TOKEN_PATH")
        if env_token and Path(env_token).exists():
            resolved_token = Path(env_token)
        else:
            try:
                def_tok = get_default_token_path()
                if def_tok.exists():
                    resolved_token = def_tok
            except (RuntimeError, KeyError):
                pass

    has_token = resolved_token is not None and resolved_token.exists()
    authenticated = False
    expired = False
    scopes: list[str] = []

    if has_token and resolved_token:
        try:
            creds = load_credentials(resolved_token)
            scopes = getattr(creds, "scopes", []) or []
            expired = getattr(creds, "expired", False)
            # If we have refresh_token or it's not expired, it is authenticated/usable
            if getattr(creds, "refresh_token", None) or not expired:
                authenticated = True
        except Exception as e:
            logger.debug(f"Could not load token {resolved_token}: {e}")
            has_token = False

    return {
        "has_client_secrets": has_secrets,
        "has_token": has_token,
        "authenticated": authenticated,
        "expired": expired,
        "scopes": scopes,
        "client_secrets_path": str(resolved_secrets) if resolved_secrets else None,
        "token_path": str(resolved_token) if resolved_token else None,
    }


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
