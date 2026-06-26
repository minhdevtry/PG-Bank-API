"""Test PGBankClient construction, auth, queries, and context manager.

All tests use mocks — we never hit the real PGBank API in unit tests.
"""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from pgbank_unofficial.client import PGBankClient
from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    PGBankError,
)

# ── Shared fixtures ──────────────────────────────────────────────────────────

FAKE_MOUNT = {
    "serverPubKeyFallback": "fakekey" * 20,  # base64-ish, >100 chars
    "tokenFallback": "default_token_value_" + "x" * 10,  # 20-200 chars
    "someOtherField": "noise",
}


def _make_client(**overrides) -> PGBankClient:
    """Build a PGBankClient with HTTP transport mocked out."""
    defaults = dict(
        username="alice",
        password="secret",
        browser_id="bid_xxx",
        auto_login=False,  # we control login in tests
    )
    defaults.update(overrides)
    with patch("pgbank_unofficial.client.fetch_mount_config", return_value=FAKE_MOUNT):
        return PGBankClient(**defaults)


# ── Construction / validation ────────────────────────────────────────────────


def test_constructor_requires_browser_id():
    """PGBankClient should raise MissingBrowserIDError if browser_id is empty."""
    with patch("pgbank_unofficial.client.fetch_mount_config", return_value=FAKE_MOUNT):
        with pytest.raises(MissingBrowserIDError):
            PGBankClient(username="a", password="b", browser_id="")


def test_constructor_requires_username_and_password():
    """PGBankClient should raise AuthenticationError if creds missing."""
    with patch("pgbank_unofficial.client.fetch_mount_config", return_value=FAKE_MOUNT):
        with pytest.raises(AuthenticationError):
            PGBankClient(username="", password="", browser_id="bid_xxx")


def test_constructor_stores_browser_id():
    """browser_id should be stored and accessible."""
    client = _make_client()
    assert client.browser_id == "bid_xxx"
    client.close()


def test_constructor_starts_unlogged_in():
    """New client should have is_logged_in=False."""
    client = _make_client()
    assert client.is_logged_in is False
    client.close()


def test_constructor_extracts_keys_from_mount():
    """PGBankClient should extract server pubkey and default token from mount."""
    client = _make_client()
    assert client._default_server_pubkey
    assert client._default_token
    client.close()


# ── Session persistence ──────────────────────────────────────────────────────


def test_session_persistence_save_and_load(tmp_path: Path):
    """Saved session should be loadable on next client init."""
    session_file = tmp_path / "session.json"

    with patch("pgbank_unofficial.client.fetch_mount_config", return_value=FAKE_MOUNT):
        client = PGBankClient(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            session_path=session_file,
            auto_login=False,
        )
        client.token = "tok_abc"
        client.cif = "cif_123"
        client.client_id = "cli_456"
        client.user_id = "usr_789"
        client.session_id = "sess_xyz"
        client.full_name = "Alice"
        client.mobile_no = "0901234567"
        client.server_pubkey = "srv_key_123"
        client.is_logged_in = True
        client._save_session()
        client.close()

    # Now reload
    with patch("pgbank_unofficial.client.fetch_mount_config", return_value=FAKE_MOUNT):
        client2 = PGBankClient(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            session_path=session_file,
            auto_login=True,  # should restore
        )
        assert client2.is_logged_in is True
        assert client2.session_id == "sess_xyz"
        assert client2.full_name == "Alice"
        client2.close()


def test_session_load_returns_false_if_no_file(tmp_path: Path):
    """_load_session should return False if file doesn't exist."""
    client = _make_client(session_path=tmp_path / "nonexistent.json")
    assert client._load_session() is False
    client.close()


def test_session_load_returns_false_if_invalid_json(tmp_path: Path):
    """_load_session should return False on invalid JSON (and log warning)."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ not valid json")
    client = _make_client(session_path=bad_file)
    assert client._load_session() is False
    client.close()


def test_logout_clears_session_and_deletes_file(tmp_path: Path):
    """logout() should reset state and delete the session file."""
    session_file = tmp_path / "session.json"
    client = _make_client(session_path=session_file)
    client.session_id = "sess_xyz"
    client.is_logged_in = True
    client._save_session()
    assert session_file.exists()
    client.logout()
    assert client.is_logged_in is False
    assert client.session_id == ""
    assert not session_file.exists()
    client.close()


# ── Query methods (require login) ────────────────────────────────────────────


def test_get_customer_info_requires_login():
    """get_customer_info should raise if not logged in."""
    client = _make_client()
    with pytest.raises(PGBankError, match="not logged in"):
        client.get_customer_info()
    client.close()


def test_get_balance_requires_login():
    """get_balance should raise if not logged in."""
    client = _make_client()
    with pytest.raises(PGBankError, match="not logged in"):
        client.get_balance()
    client.close()


def test_get_customer_info_parses_response():
    """get_customer_info should parse the response into typed objects."""
    client = _make_client()
    client.is_logged_in = True
    profile_response = {
        "customer": {
            "cifNo": "cif_123",
            "fullName": "NGUYEN VAN A"
        }
    }
    accounts_response = {
        "code": "00",
        "data": [
            {
                "accountNo": "1234567890",
                "custName": "NGUYEN VAN A",
                "availableBalance": "1000000.50",
                "currency": "VND",
                "accountTypeName": "checking",
            },
            {
                "accountNo": "9876543210",
                "custName": "NGUYEN VAN A",
                "availableBalance": "5000000",
                "currency": "VND",
                "accountTypeName": "savings",
            },
        ]
    }
    with patch.object(client, "_post", side_effect=[profile_response, accounts_response]):
        info = client.get_customer_info()
    assert info.customer_id == "cif_123"
    assert info.customer_name == "NGUYEN VAN A"
    assert len(info.accounts) == 2
    assert info.accounts[0].account_number == "1234567890"
    assert info.accounts[0].balance == Decimal("1000000.50")
    client.close()


def test_get_balance_parses_response():
    """get_balance should parse the response into a Balance object."""
    client = _make_client()
    client.is_logged_in = True
    fake_response = {
        "code": "00",
        "accountNo": "1234567890",
        "availableBalance": "500000",
        "currentBalance": "600000",
        "currency": "VND",
    }
    from pgbank_unofficial._params import MID, SERVICE
    with patch.object(client, "_post", return_value=fake_response) as mock_post:
        bal = client.get_balance("1234567890")
    assert bal.account_number == "1234567890"
    assert bal.available == Decimal("500000")
    assert bal.total == Decimal("600000")
    assert bal.currency == "VND"
    # Verify payload was correct
    call_args = mock_post.call_args
    assert call_args[0][0] == SERVICE["BANK"]  # service
    assert call_args[0][1] == MID["AVAILABLE_BALANCE"]  # mid
    assert call_args[0][2]["accountNumber"] == "1234567890"
    client.close()


def test_get_balance_uses_first_account_when_none_specified():
    """get_balance() with no arg should fall back to first account."""
    client = _make_client()
    client.is_logged_in = True
    accounts_response = {
        "code": "00",
        "data": [
            {
                "accountNo": "first_acc",
                "custName": "T",
                "availableBalance": "1000",
                "currency": "VND",
                "accountTypeName": "checking",
            }
        ],
    }
    balance_response = {
        "code": "00",
        "accountNo": "first_acc",
        "availableBalance": "500",
        "currentBalance": "500",
        "currency": "VND",
    }
    with patch.object(client, "_post", side_effect=[accounts_response, balance_response]):
        bal = client.get_balance()
    assert bal.account_number == "first_acc"
    client.close()


# ── Context manager ──────────────────────────────────────────────────────────


def test_context_manager_enter_returns_self():
    """with client as c: should yield the same client."""
    client = _make_client()
    with client as c:
        assert c is client
    # __exit__ closes transport
    assert client._transport._session is None


def test_context_manager_closes_on_exit():
    """__exit__ should close the transport."""
    client = _make_client()
    # Force session to exist
    client._transport._get_session()
    assert client._transport._session is not None
    with client:
        pass
    assert client._transport._session is None


# ── OTP handling ─────────────────────────────────────────────────────────────


def test_login_step2_cleans_otp_input():
    """login_step2 should strip non-digits from OTP."""
    client = _make_client()
    client.is_logged_in = False
    # Simulate OTP pending
    client._otp_required = True
    client._pending_otp_ref = "fake_ref"
    # _post will raise since we don't mock — but we can test that empty OTP
    # raises AuthenticationError before the network call.
    with pytest.raises(AuthenticationError, match="empty OTP"):
        client.login_step2("---")
    client.close()


def test_login_step2_requires_pending_otp():
    """login_step2 should raise if no pending OTP."""
    client = _make_client()
    with pytest.raises(PGBankError, match="no pending OTP"):
        client.login_step2("123456")
    client.close()


def test_change_password_requires_login():
    """change_password should raise if not logged in."""
    client = _make_client()
    with pytest.raises(PGBankError, match="not logged in"):
        client.change_password("old", "new")
    client.close()


def test_change_password_success():
    """change_password should post request and update password on success."""
    client = _make_client()
    client.is_logged_in = True
    fake_response = {"code": "00", "des": "Success"}
    with patch.object(client, "_post", return_value=fake_response) as mock_post:
        resp = client.change_password("secret", "new_secret")
    assert resp == fake_response
    assert client.password == "new_secret"
    mock_post.assert_called_once()
    client.close()


def test_create_contact():
    """create_contact should validate session, post payload, and handle success."""
    client = _make_client()
    client.is_logged_in = True
    fake_resp = {"code": "00", "des": "Success"}
    
    with patch.object(client, "_post", return_value=fake_resp) as mock_post:
        resp = client.create_contact(
            name="John Doe",
            receiver_account="987654321",
            bank_code="970407",
            bank_name="Techcombank",
            bene_name="JOHN DOE",
        )
    assert resp == fake_resp
    mock_post.assert_called_once()
    client.close()


def test_update_contact():
    """update_contact should patch updated fields and post successfully."""
    client = _make_client()
    client.is_logged_in = True
    fake_resp = {"code": "00"}
    
    with patch.object(client, "_post", return_value=fake_resp) as mock_post:
        resp = client.update_contact(bene_id="123", name="John Re-nick", favourite=True)
    assert resp == fake_resp
    mock_post.assert_called_once()
    # Check that parameters are mapped correctly
    args, kwargs = mock_post.call_args
    payload = args[2]
    assert payload["beneId"] == "123"
    assert payload["name"] == "John Re-nick"
    assert payload["favourite"] is True
    client.close()


def test_delete_contact():
    """delete_contact and remove_contact should format IDs and post successfully."""
    client = _make_client()
    client.is_logged_in = True
    fake_resp = {"code": "00"}
    
    with patch.object(client, "_post", return_value=fake_resp) as mock_post:
        resp = client.delete_contact(bene_ids=[101, 102])
    assert resp == fake_resp
    mock_post.assert_called_once()
    assert mock_post.call_args[0][2]["beneIds"] == "101,102"
    
    # Test remove_contact alias
    with patch.object(client, "_post", return_value=fake_resp) as mock_post2:
        resp2 = client.remove_contact("103")
    assert resp2 == fake_resp
    mock_post2.assert_called_once()
    assert mock_post2.call_args[0][2]["beneIds"] == "103"
    client.close()


