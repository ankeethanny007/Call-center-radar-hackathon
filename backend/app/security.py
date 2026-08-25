"""Small deployment-safe access controls for API and locally served audio.

Production can place the API behind an identity-aware proxy instead. When
API_ACCESS_TOKEN is configured, this module provides a minimal server-to-server
gate and short-lived HMAC URLs for browser audio playback without exposing the
token itself to the client.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import Header, HTTPException, status

from .config import settings

ApiKey = Annotated[str | None, Header(alias="X-API-Key")]


def token_is_valid(candidate: str | None) -> bool:
    return bool(settings.api_access_token and candidate and hmac.compare_digest(candidate, settings.api_access_token))


def require_api_access(x_api_key: ApiKey = None) -> None:
    """Protect persisted PII/transcript routes when a deployment token is configured."""
    if settings.api_access_token and not token_is_valid(x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API authentication is required")


def _media_signature(relative_path: str, expires_at: int) -> str:
    if not settings.api_access_token:
        raise RuntimeError("No media-signing secret is configured")
    message = f"{expires_at}:{relative_path}".encode()
    return hmac.new(settings.api_access_token.encode(), message, hashlib.sha256).hexdigest()


def signed_media_query(relative_path: str) -> str:
    """Return a URL query fragment or an empty string for unsecured local development."""
    if not settings.api_access_token:
        return ""
    expires_at = int(time.time()) + max(1, settings.media_url_ttl_seconds)
    return f"?expires={expires_at}&signature={_media_signature(relative_path, expires_at)}"


def require_media_access(
    audio_path: str,
    expires: int | None = None,
    signature: str | None = None,
    x_api_key: ApiKey = None,
) -> None:
    """Accept an API header or a short-lived signed browser audio URL."""
    if not settings.api_access_token or token_is_valid(x_api_key):
        return
    if expires is not None and signature and expires >= int(time.time()):
        expected = _media_signature(audio_path, expires)
        if hmac.compare_digest(signature, expected):
            return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Audio authentication is required")
