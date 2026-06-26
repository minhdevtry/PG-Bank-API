"""HTTP transport for PGBank API.

Features:
- Session-level connection pooling
- Configurable retry policy with exponential backoff
- Circuit breaker (opens after N consecutive failures, closes after cooldown)
- Proxy support (per-request)
- Timeouts (connect, read)
- Mount config fetching (with caching)

This module is transport-only. Request signing, encryption, and response
decryption happen at the :class:`PGBankClient` layer.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pgbank_unofficial._algorithm import MOUNT_URL, ORIGIN
from pgbank_unofficial.exceptions import TimeoutError as PGBankTimeoutError

logger = logging.getLogger(__name__)


# ── Circuit Breaker ───────────────────────────────────────────────────────────


class CircuitState(Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing — reject all requests
    HALF_OPEN = "half_open"  # Cooldown elapsed — allow one test request


@dataclass
class CircuitBreaker:
    """Circuit breaker to stop hammering a failing endpoint.

    After ``failure_threshold`` consecutive failures, the circuit opens and
    rejects requests for ``cooldown_seconds``. After cooldown, transitions to
    HALF_OPEN — the next request is allowed as a probe. If it succeeds, the
    circuit closes; if it fails, it opens again.
    """

    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_at: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def is_open(self) -> bool:
        """Return True if the circuit is currently rejecting requests."""
        with self._lock:
            if self.state == CircuitState.OPEN:
                # Check if cooldown has elapsed
                if time.monotonic() - self.last_failure_at >= self.cooldown_seconds:
                    logger.info("circuit-breaker: transitioning OPEN -> HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    return False
                return True
            return False

    def record_success(self) -> None:
        """Record a successful request — close the circuit if half-open."""
        with self._lock:
            if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("circuit-breaker: transitioning %s -> CLOSED", self.state.value)
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request — open the circuit if threshold reached."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_at = time.monotonic()
            if self.state == CircuitState.HALF_OPEN:
                logger.warning("circuit-breaker: HALF_OPEN probe failed -> OPEN")
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    logger.warning(
                        "circuit-breaker: %d consecutive failures -> OPEN",
                        self.failure_count,
                    )
                self.state = CircuitState.OPEN


# ── HTTP Transport ────────────────────────────────────────────────────────────


@dataclass
class HTTPTransport:
    """Synchronous HTTP transport with retry and circuit breaker.

    Example:
        >>> transport = HTTPTransport(proxy="http://user:pass@host:port", timeout=30)
        >>> response = transport.get("https://api.example.com/data")
        >>> data = response.json()
    """

    proxy: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 0.5
    verify_ssl: bool = True
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    _session: Optional[requests.Session] = field(default=None, init=False, repr=False)
    _session_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _get_session(self) -> requests.Session:
        """Lazily build a Session with retry-aware adapter."""
        if self._session is not None:
            return self._session
        with self._session_lock:
            if self._session is not None:
                return self._session
            session = requests.Session()
            retry_cfg = Retry(
                total=self.max_retries,
                backoff_factor=self.backoff_factor,
                status_forcelist=(500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"]),
            )
            adapter = HTTPAdapter(max_retries=retry_cfg, pool_connections=10, pool_maxsize=20)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._session = session
            return session

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> requests.Response:
        """Execute an HTTP request with circuit breaker and error handling."""
        if self.circuit_breaker.is_open():
            raise ConnectionError("circuit breaker is open — too many recent failures")

        session = self._get_session()
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        try:
            response = session.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                data=data,
                params=params,
                timeout=self.timeout,
                proxies=proxies,
                verify=self.verify_ssl,
            )
            self.circuit_breaker.record_success()
            return response
        except requests.exceptions.Timeout as e:
            self.circuit_breaker.record_failure()
            raise PGBankTimeoutError(f"request to {url} timed out after {self.timeout}s") from e
        except requests.exceptions.ConnectionError as e:
            self.circuit_breaker.record_failure()
            raise ConnectionError(f"connection error for {url}: {e}") from e
        except requests.exceptions.RequestException:
            self.circuit_breaker.record_failure()
            raise

    def get(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> requests.Response:
        return self._request("GET", url, headers=headers, params=params)

    def post(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
    ) -> requests.Response:
        return self._request("POST", url, headers=headers, json=json, data=data)

    def close(self) -> None:
        """Close the underlying session."""
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> HTTPTransport:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ── Mount config (cached) ────────────────────────────────────────────────────

_mount_cache: Optional[dict[str, Any]] = None
_mount_lock = threading.Lock()


def fetch_mount_config(transport: HTTPTransport) -> dict[str, Any]:
    """Fetch and cache PGBank's mount.json configuration.

    The mount config contains the server's public key and default Bearer token.
    Result is cached process-wide (PGBank keys rotate rarely).
    """
    global _mount_cache
    if _mount_cache is not None:
        return _mount_cache
    with _mount_lock:
        if _mount_cache is not None:
            return _mount_cache
        response = transport.get(
            MOUNT_URL,
            headers={
                "accept": "*/*",
                "origin": ORIGIN,
                "referer": ORIGIN + "/",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36",
            },
        )
        _mount_cache = response.json()
        logger.debug("fetched mount config: keys=%s", list(_mount_cache.keys()))
        return _mount_cache
