"""Test the HTTP transport layer (CircuitBreaker + HTTPTransport)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from pgbank_unofficial.http import (
    CircuitBreaker,
    CircuitState,
    HTTPTransport,
    fetch_mount_config,
)

# ── CircuitBreaker tests ─────────────────────────────────────────────────────


def test_circuit_breaker_starts_closed():
    """A new circuit breaker should be CLOSED."""
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.is_open() is False


def test_circuit_breaker_opens_after_threshold():
    """Circuit should open after failure_threshold consecutive failures."""
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is False
    cb.record_failure()
    assert cb.is_open() is True


def test_circuit_breaker_success_resets_failures():
    """A success should reset the failure counter."""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_half_open_after_cooldown():
    """After cooldown elapses, circuit should transition to HALF_OPEN."""
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is True
    # Wait for cooldown
    import time

    time.sleep(0.15)
    # Next is_open() check should transition to HALF_OPEN
    assert cb.is_open() is False
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_breaker_half_open_success_closes():
    """A success in HALF_OPEN should close the circuit."""
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
    cb.record_failure()
    cb.record_failure()
    import time

    time.sleep(0.15)
    cb.is_open()  # trigger HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_half_open_failure_reopens():
    """A failure in HALF_OPEN should re-open the circuit."""
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
    cb.record_failure()
    cb.record_failure()
    import time

    time.sleep(0.15)
    cb.is_open()  # trigger HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


# ── HTTPTransport tests ──────────────────────────────────────────────────────


def test_transport_default_config():
    """HTTPTransport with no args should have sensible defaults."""
    t = HTTPTransport()
    assert t.timeout == 30.0
    assert t.max_retries == 3
    assert t.proxy is None
    assert t.circuit_breaker.state == CircuitState.CLOSED


def test_transport_session_lazy_init():
    """HTTPTransport should not create session until first use."""
    t = HTTPTransport()
    assert t._session is None
    # Force session creation via a mocked request
    with patch.object(t, "_request") as mock_req:
        mock_resp = MagicMock()
        mock_req.return_value = mock_resp
        t.get("https://example.com")


def test_transport_circuit_breaker_blocks_when_open():
    """Transport should raise ConnectionError when circuit is open."""
    t = HTTPTransport()
    # Use a high cooldown so the circuit stays OPEN for the duration of the test.
    # (time.monotonic() is monotonic since boot, not Unix epoch — setting
    # last_failure_at to 0 would make cooldown look "long elapsed".)
    t.circuit_breaker.cooldown_seconds = 1e9  # ~31 years
    t.circuit_breaker.state = CircuitState.OPEN
    t.circuit_breaker.last_failure_at = 0
    with pytest.raises(ConnectionError, match="circuit breaker"):
        t.get("https://example.com")


def test_transport_timeout_translates_to_our_timeout_error():
    """requests.Timeout should become pgbank_unofficial.TimeoutError after Task 3 import works."""
    # Note: pgbank_unofficial.exceptions.TimeoutError is a custom class
    from pgbank_unofficial.exceptions import TimeoutError as PgTimeoutError

    t = HTTPTransport()
    with patch.object(t, "_get_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_session_factory.return_value = mock_session
        mock_session.request.side_effect = requests.exceptions.Timeout("slow")
        with pytest.raises(PgTimeoutError):
            t.get("https://example.com")


def test_transport_close_resets_session():
    """close() should reset session to None so a new one is built next call."""
    t = HTTPTransport()
    # Force session creation
    t._get_session()
    assert t._session is not None
    t.close()
    assert t._session is None


def test_transport_context_manager():
    """HTTPTransport should work as a context manager."""
    with HTTPTransport() as t:
        assert t is not None


def test_transport_proxy_passed_to_request():
    """When proxy is set, it should be forwarded to requests."""
    t = HTTPTransport(proxy="http://proxy.example.com:8080")
    with patch.object(t, "_get_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.request.return_value = mock_resp
        mock_session_factory.return_value = mock_session
        t.get("https://example.com")
        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs["proxies"] == {
            "http": "http://proxy.example.com:8080",
            "https": "http://proxy.example.com:8080",
        }


def test_transport_no_proxy_means_no_proxies_kwarg():
    """When proxy is None, proxies kwarg should also be None."""
    t = HTTPTransport()
    with patch.object(t, "_get_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.request.return_value = mock_resp
        mock_session_factory.return_value = mock_session
        t.get("https://example.com")
        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs["proxies"] is None


def test_transport_success_records_circuit_breaker():
    """A successful request should call record_success on circuit breaker."""
    t = HTTPTransport()
    with patch.object(t, "_get_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.request.return_value = mock_resp
        mock_session_factory.return_value = mock_session
        t.get("https://example.com")
    assert t.circuit_breaker.failure_count == 0


def test_transport_connection_error_records_failure():
    """A ConnectionError should call record_failure on circuit breaker."""
    t = HTTPTransport()
    with patch.object(t, "_get_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_session.request.side_effect = requests.exceptions.ConnectionError("refused")
        mock_session_factory.return_value = mock_session
        with pytest.raises(ConnectionError):
            t.get("https://example.com")
    assert t.circuit_breaker.failure_count == 1


# ── fetch_mount_config tests ─────────────────────────────────────────────────


def test_fetch_mount_config_caches_result():
    """fetch_mount_config should cache the result process-wide."""
    fake_mount = {"key1": "value1", "key2": "value2"}

    # Reset the global cache first (tests may run in arbitrary order)
    import pgbank_unofficial.http as http_mod

    http_mod._mount_cache = None

    with patch.object(HTTPTransport, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_mount
        mock_get.return_value = mock_resp

        # Need to pass a transport instance
        transport = HTTPTransport()
        result1 = fetch_mount_config(transport)
        result2 = fetch_mount_config(transport)
        assert result1 is result2  # same dict (cached)
        # Only one HTTP call
        assert mock_get.call_count == 1
