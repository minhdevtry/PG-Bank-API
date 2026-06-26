"""Custom exception hierarchy for pgbank-unofficial.

All exceptions inherit from PGBankError so users can catch all library-specific
errors with a single ``except PGBankError`` clause.
"""

from __future__ import annotations

from typing import Optional


class PGBankError(Exception):
    """Base exception for all pgbank-unofficial errors."""

    def __init__(self, message: str = "", code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


class MissingBrowserIDError(PGBankError):
    """Raised when an Account or PGBankClient is created without browser_id.

    PGBank requires a BrowserID (browser fingerprint) for authentication.
    This is mandatory and cannot be omitted.
    """

    def __init__(self, message: str = "browser_id is required for PGBank authentication") -> None:
        super().__init__(message)


class AuthenticationError(PGBankError):
    """Raised when login fails due to invalid credentials or rejected auth."""

    def __init__(
        self, message: str, reason: Optional[str] = None, code: Optional[str] = None
    ) -> None:
        super().__init__(message, code=code)
        self.reason = reason


class SessionExpiredError(PGBankError):
    """Raised when the persisted session has expired and cannot be auto-renewed."""

    def __init__(self, message: str = "session expired", code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


class TimeoutError(PGBankError):  # noqa: A001 (intentional shadow of builtin for library API)
    """Raised when an HTTP request exceeds the configured timeout.

    Note: This shadows builtin TimeoutError intentionally so users can catch
    PGBank-specific timeouts without catching unrelated builtins.
    """

    def __init__(self, message: str = "request timed out", timeout: Optional[float] = None) -> None:
        super().__init__(message)
        self.timeout = timeout


class RateLimitError(PGBankError):
    """Raised when PGBank API returns HTTP 429 (Too Many Requests)."""

    def __init__(self, message: str = "rate limited", retry_after: Optional[int] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NetworkError(PGBankError):
    """Raised on network-level failures (DNS, connection refused, TLS errors)."""


class TransferError(PGBankError):
    """Raised when a transfer operation fails (verification or confirmation)."""

    def __init__(self, message: str, stage: Optional[str] = None) -> None:
        super().__init__(message)
        self.stage = stage  # 'init', 'verify', 'confirm'
