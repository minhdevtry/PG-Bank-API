"""Test AsyncPGBankClient — async mirror of sync PGBankClient tests."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pgbank_unofficial.async_client import AsyncPGBankClient
from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    PGBankError,
)
from pgbank_unofficial.models import BankAccount

FAKE_MOUNT = {
    "serverPubKeyFallback": "fakekey" * 20,
    "tokenFallback": "default_token_value_" + "x" * 10,
}


def _make_client(**overrides) -> AsyncPGBankClient:
    """Build an AsyncPGBankClient without triggering mount fetch."""
    # We patch the mount fetch via a different approach since the async
    # client fetches it inline. We patch httpx.Client used for the sync fetch.
    defaults = dict(
        username="alice",
        password="secret",
        browser_id="bid_xxx",
        auto_login=False,
    )
    defaults.update(overrides)
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_MOUNT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        return AsyncPGBankClient(**defaults)


# ── Construction ─────────────────────────────────────────────────────────────


def test_constructor_requires_browser_id():
    """AsyncPGBankClient should raise MissingBrowserIDError if browser_id empty."""
    with pytest.raises(MissingBrowserIDError):
        AsyncPGBankClient(username="a", password="b", browser_id="")


def test_constructor_requires_username_password():
    """AsyncPGBankClient should raise AuthenticationError if creds missing."""
    with pytest.raises(AuthenticationError):
        AsyncPGBankClient(username="", password="", browser_id="bid_xxx")


def test_constructor_starts_unlogged_in():
    """New client should have is_logged_in=False."""
    client = _make_client()
    assert client.is_logged_in is False
    assert client.browser_id == "bid_xxx"


# ── Async context manager ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_context_manager_enter_returns_self():
    """async with client as c: should yield the same client."""
    client = _make_client()
    async with client as c:
        assert c is client
    # After exit, client should be closed
    assert client._client is None


@pytest.mark.asyncio
async def test_async_context_manager_closes_on_exit():
    """__aexit__ should close the httpx client."""
    client = _make_client()
    # Force client to be created
    await client._ensure_client()
    assert client._client is not None
    async with client:
        pass
    assert client._client is None


# ── Query methods ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_customer_info_requires_login():
    """get_customer_info should raise if not logged in."""
    client = _make_client()
    with pytest.raises(PGBankError, match="not logged in"):
        await client.get_customer_info()


@pytest.mark.asyncio
async def test_get_balance_requires_login():
    """get_balance should raise if not logged in."""
    client = _make_client()
    with pytest.raises(PGBankError, match="not logged in"):
        await client.get_balance()


@pytest.mark.asyncio
async def test_get_customer_info_parses_response():
    """get_customer_info should parse the response into typed objects."""
    client = _make_client()
    client.is_logged_in = True
    profile_response = {
        "customer": {
            "cifNo": "cif_async",
            "fullName": "TRAN THI B"
        }
    }
    accounts_response = {
        "code": "00",
        "data": [
            {
                "accountNo": "111",
                "custName": "TRAN THI B",
                "availableBalance": "2000000",
                "currency": "VND",
                "accountTypeName": "checking",
            },
        ]
    }
    with patch.object(client, "_post", new=AsyncMock(side_effect=[profile_response, accounts_response])):
        info = await client.get_customer_info()
    assert info.customer_id == "cif_async"
    assert info.customer_name == "TRAN THI B"
    assert len(info.accounts) == 1
    assert info.accounts[0].balance == Decimal("2000000")


@pytest.mark.asyncio
async def test_get_balance_parses_response():
    """get_balance should parse the response into a Balance object."""
    client = _make_client()
    client.is_logged_in = True
    fake_response = {
        "code": "00",
        "accountNo": "111",
        "availableBalance": "100000",
        "currentBalance": "150000",
        "currency": "VND",
    }
    with patch.object(client, "_post", new=AsyncMock(return_value=fake_response)):
        bal = await client.get_balance("111")
    assert bal.account_number == "111"
    assert bal.available == Decimal("100000")
    assert bal.total == Decimal("150000")
    assert bal.currency == "VND"


# ── Session persistence ──────────────────────────────────────────────────────


def test_session_persistence_save_and_load(tmp_path: Path):
    """Saved session should be loadable on next client init."""
    session_file = tmp_path / "async_session.json"

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_MOUNT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = AsyncPGBankClient(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            session_path=session_file,
            auto_login=False,
        )
        client.token = "tok_abc"
        client.cif = "cif_123"
        client.session_id = "sess_xyz"
        client.full_name = "Alice"
        client.is_logged_in = True
        client._save_session()

    # Reload
    with patch("httpx.Client.get") as mock_get2:
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = FAKE_MOUNT
        mock_resp2.raise_for_status = MagicMock()
        mock_get2.return_value = mock_resp2

        client2 = AsyncPGBankClient(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            session_path=session_file,
            auto_login=False,
        )
        assert client2._load_session() is True
        assert client2.is_logged_in is True
        assert client2.session_id == "sess_xyz"


def test_async_client_custom_storage_backend():
    """AsyncPGBankClient should use a custom storage backend for save/load."""
    saved_entries = {}

    class CapturingStorage:
        def save_session(self, username, data):
            saved_entries["saved"] = (username, data)

        def load_session(self, username):
            return None

        def delete_session(self, username):
            saved_entries["deleted"] = username

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_MOUNT
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = AsyncPGBankClient(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            session_storage=CapturingStorage(),
            auto_login=False,
        )
        client.session_id = "sess_async_999"
        client._save_session()
        assert "saved" in saved_entries
        username, data = saved_entries["saved"]
        assert username == "alice"
        assert data["sessionId"] == "sess_async_999"
        client.logout()
        assert saved_entries.get("deleted") == "alice"


# ── Auth helpers ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_step2_requires_pending_otp():
    """login_step2 should raise if no pending OTP."""
    client = _make_client()
    with pytest.raises(PGBankError, match="no pending OTP"):
        await client.login_step2("123456")


@pytest.mark.asyncio
async def test_change_password_requires_login():
    """change_password should raise if not logged in."""
    client = _make_client()
    with pytest.raises(PGBankError, match="not logged in"):
        await client.change_password("old", "new")


@pytest.mark.asyncio
async def test_change_password_success():
    """change_password should post request and update password on success."""
    client = _make_client()
    client.is_logged_in = True
    fake_response = {"code": "00", "des": "Success"}
    with patch.object(client, "_post", new=AsyncMock(return_value=fake_response)) as mock_post:
        resp = await client.change_password("secret", "new_secret")
    assert resp == fake_response
    assert client.password == "new_secret"
    mock_post.assert_called_once()


def test_logout(tmp_path: Path):
    """logout should clear session and delete session file."""
    session_file = tmp_path / "async_session.json"
    client = _make_client(session_path=session_file)
    client.is_logged_in = True
    client.session_id = "sess_123"
    client._save_session()
    assert session_file.exists()

    client.logout()
    assert client.is_logged_in is False
    assert client.session_id == ""
    assert not session_file.exists()


@pytest.mark.asyncio
async def test_is_alive_success():
    """is_alive should return True if get_accounts returns accounts."""
    client = _make_client()
    client.is_logged_in = True
    fake_accounts = [
        BankAccount(account_number="111", account_name="Alice", balance=Decimal("100"))
    ]
    with patch.object(client, "get_accounts", new=AsyncMock(return_value=fake_accounts)):
        alive = await client.is_alive()
    assert alive is True


@pytest.mark.asyncio
async def test_is_alive_failure_and_relogin_success():
    """is_alive should retry login and get_accounts if first attempt fails."""
    client = _make_client()
    client.is_logged_in = True
    fake_accounts = [
        BankAccount(account_number="111", account_name="Alice", balance=Decimal("100"))
    ]
    mock_get_accounts = AsyncMock(side_effect=[Exception("stale session"), fake_accounts])
    mock_login = AsyncMock()
    with patch.object(client, "get_accounts", mock_get_accounts), \
         patch.object(client, "login", mock_login):
        alive = await client.is_alive()
    assert alive is True
    assert mock_get_accounts.call_count == 2
    mock_login.assert_called_once()


@pytest.mark.asyncio
async def test_health_check():
    """health_check should return health status summary."""
    client = _make_client()
    client.is_logged_in = True
    fake_accounts = [
        BankAccount(account_number="111", account_name="Alice", balance=Decimal("100"), currency="VND")
    ]
    with patch.object(client, "get_accounts", new=AsyncMock(return_value=fake_accounts)):
        hc = await client.health_check()
    assert hc["alive"] is True
    assert hc["account_count"] == 1
    assert hc["total_balance"] == "100"
    assert hc["currency"] == "VND"


@pytest.mark.asyncio
async def test_get_config():
    """get_config should post config utility query."""
    client = _make_client()
    client.is_logged_in = True
    fake_resp = {"config": "val"}
    with patch.object(client, "_post", new=AsyncMock(return_value=fake_resp)):
        conf = await client.get_config()
    assert conf == fake_resp


@pytest.mark.asyncio
async def test_create_contact_async():
    """create_contact should validate session, post payload, and handle success."""
    client = _make_client()
    client.is_logged_in = True
    fake_resp = {"code": "00", "des": "Success"}
    
    with patch.object(client, "_post", new=AsyncMock(return_value=fake_resp)) as mock_post:
        resp = await client.create_contact(
            name="John Doe",
            receiver_account="987654321",
            bank_code="970407",
            bank_name="Techcombank",
            bene_name="JOHN DOE",
        )
    assert resp == fake_resp
    mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_update_contact_async():
    """update_contact should patch updated fields and post successfully."""
    client = _make_client()
    client.is_logged_in = True
    fake_resp = {"code": "00"}
    
    with patch.object(client, "_post", new=AsyncMock(return_value=fake_resp)) as mock_post:
        resp = await client.update_contact(bene_id="123", name="John Re-nick", favourite=True)
    assert resp == fake_resp
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    payload = args[2]
    assert payload["beneId"] == "123"
    assert payload["name"] == "John Re-nick"
    assert payload["favourite"] is True


@pytest.mark.asyncio
async def test_delete_contact_async():
    """delete_contact and remove_contact should format IDs and post successfully."""
    client = _make_client()
    client.is_logged_in = True
    fake_resp = {"code": "00"}
    
    with patch.object(client, "_post", new=AsyncMock(return_value=fake_resp)) as mock_post:
        resp = await client.delete_contact(bene_ids=[101, 102])
    assert resp == fake_resp
    mock_post.assert_called_once()
    assert mock_post.call_args[0][2]["beneIds"] == "101,102"
    
    # Test remove_contact alias
    with patch.object(client, "_post", new=AsyncMock(return_value=fake_resp)) as mock_post2:
        resp2 = await client.remove_contact("103")
    assert resp2 == fake_resp
    mock_post2.assert_called_once()
    assert mock_post2.call_args[0][2]["beneIds"] == "103"


