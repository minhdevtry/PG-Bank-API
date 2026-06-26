"""Shared pytest fixtures for pgbank-unofficial tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Re-export common fixtures so individual test files can pick what they need.

FAKE_MOUNT_CONFIG: dict[str, Any] = {
    # PGBank's mount.json keys are obfuscated and version-dependent.
    # We use a stable shape that satisfies the client's extraction logic.
    "serverPubKeyFallback": "a" * 200,  # 200 chars, looks like a base64 key
    "tokenFallback": "default_token_" + "x" * 10,  # between 20-200 chars
}


@pytest.fixture
def fake_mount() -> dict[str, Any]:
    """Return a stable fake mount config dict."""
    return FAKE_MOUNT_CONFIG.copy()


@pytest.fixture
def mock_mount_config(fake_mount):
    """Patch fetch_mount_config to return fake_mount."""
    with patch(
        "pgbank_unofficial.client.fetch_mount_config",
        return_value=fake_mount,
    ):
        yield fake_mount


@pytest.fixture
def mock_async_mount_config(fake_mount):
    """Patch httpx.Client.get (used by async client) to return fake_mount."""
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_mount
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        yield fake_mount


@pytest.fixture
def client_factory(mock_mount_config):
    """Factory fixture that builds a PGBankClient with sensible defaults."""

    def _make(**overrides):
        from pgbank_unofficial import PGBankClient

        defaults = dict(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            auto_login=False,
        )
        defaults.update(overrides)
        return PGBankClient(**defaults)

    return _make


@pytest.fixture
def async_client_factory(mock_async_mount_config):
    """Factory fixture that builds an AsyncPGBankClient with sensible defaults."""

    def _make(**overrides):
        from pgbank_unofficial import AsyncPGBankClient

        defaults = dict(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            auto_login=False,
        )
        defaults.update(overrides)
        return AsyncPGBankClient(**defaults)

    return _make


@pytest.fixture
def session_path(tmp_path: Path) -> Path:
    """Return a fresh session file path inside tmp_path."""
    return tmp_path / "session.json"


@pytest.fixture
def persisted_session(session_path: Path) -> dict[str, Any]:
    """Write a fake persisted session and return its data."""
    data = {
        "token": "tok_abc",
        "cif": "cif_123",
        "clientId": "cli_456",
        "userId": "usr_789",
        "sessionId": "sess_xyz",
        "fullName": "Alice",
        "mobileNo": "0901234567",
        "serverPubKey": "srv_key_123",
    }
    session_path.write_text(json.dumps(data))
    return data


@pytest.fixture
def mock_transport():
    """Patch HTTPTransport to return mock responses easily."""
    with patch("pgbank_unofficial.client.HTTPTransport") as mock_transport_cls:
        instance = MagicMock()
        mock_transport_cls.return_value = instance
        yield instance
