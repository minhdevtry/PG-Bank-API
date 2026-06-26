"""Test exception hierarchy and behavior."""

import pytest

from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    NetworkError,
    PGBankError,
    RateLimitError,
    SessionExpiredError,
    TimeoutError,
)


def test_pgbank_error_is_base():
    """All custom exceptions should inherit from PGBankError."""
    assert issubclass(AuthenticationError, PGBankError)
    assert issubclass(SessionExpiredError, PGBankError)
    assert issubclass(MissingBrowserIDError, PGBankError)
    assert issubclass(TimeoutError, PGBankError)
    assert issubclass(RateLimitError, PGBankError)
    assert issubclass(NetworkError, PGBankError)


def test_pgbank_error_is_exception():
    """PGBankError should be a regular Exception subclass."""
    assert issubclass(PGBankError, Exception)


def test_missing_browser_id_error_message():
    """MissingBrowserIDError default message should mention browser_id."""
    err = MissingBrowserIDError()
    assert "browser_id" in str(err).lower()


def test_missing_browser_id_error_custom_message():
    """MissingBrowserIDError should accept and preserve custom message."""
    err = MissingBrowserIDError("test message")
    assert "test message" in str(err)


def test_authentication_error_carries_reason():
    """AuthenticationError should optionally carry a reason field."""
    err = AuthenticationError("invalid credentials", reason="WRONG_PASSWORD")
    assert err.reason == "WRONG_PASSWORD"
    assert "invalid credentials" in str(err)


def test_session_expired_error_has_code():
    """SessionExpiredError should carry the original error code."""
    err = SessionExpiredError("expired", code="SESSION_TIMEOUT")
    assert err.code == "SESSION_TIMEOUT"


def test_timeout_error_has_timeout_value():
    """TimeoutError should carry the timeout value for debugging."""
    err = TimeoutError("request timed out", timeout=30.0)
    assert err.timeout == 30.0


def test_rate_limit_error_carries_retry_after():
    """RateLimitError should carry Retry-After hint."""
    err = RateLimitError("rate limited", retry_after=60)
    assert err.retry_after == 60


def test_can_catch_all_pgbank_errors():
    """Catching PGBankError should catch all custom errors."""
    with pytest.raises(PGBankError):
        raise AuthenticationError("test")
    with pytest.raises(PGBankError):
        raise MissingBrowserIDError("test")
