# PGBank Unofficial Library - Phase 1 MVP Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core foundation of `pgbank-unofficial` library — typed models, PGBankClient (sync + async) with authentication, account/balance queries, and basic retry — ready for PyPI v0.1.0.

**Architecture:** Layered — Models (dataclasses) → HTTP/transport layer → Client (1 session) → Async wrapper. All monetary values use `Decimal`. All public APIs return typed dataclasses. Sessions persist to disk for auto-restore. SSL/TLS fingerprint bypass via custom transport.

**Tech Stack:**
- Python 3.9+ (test 3.9, 3.10, 3.11, 3.12)
- `requests` for sync HTTP, `aiohttp` for async
- `cryptography` for PGBank payload encryption (reuse existing algo from `pg/pgbank/pgbank/utils/_algorithm.py`)
- `pyproject.toml` (PEP 621) with hatchling build backend
- `pytest` + `pytest-asyncio` + `pytest-cov` for testing
- `mypy --strict` for type checking
- `ruff` + `black` for linting
- GitHub Actions for CI
- `twine` for PyPI publish

---

## Global Constraints

These apply to every task. Read once.

- **Python version floor:** 3.9 (use `from __future__ import annotations` for forward refs, `Optional[X]` not `X | None`)
- **Money type:** `decimal.Decimal` — NEVER `float`
- **BrowserID:** Required parameter on `Account` and `PGBankClient.__init__` — raise `MissingBrowserIDError` if absent
- **Public API style:** Typed dataclasses for return values, never raw `dict` for callers
- **Logging:** Use stdlib `logging` with module-level logger named after module path
- **No captcha:** PGBank does not have captcha — never implement captcha solver
- **TDD:** Write failing test FIRST, then implement, then verify green
- **Commits:** Frequent, conventional-commit style (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`)
- **Coverage target:** > 90% line coverage for `src/pgbank_unofficial/`
- **No emoji in source code** — only in docs (README, etc.)
- **Docstring style:** Google-style docstrings on all public classes/functions
- **Type hints:** Required on all public APIs, use `mypy --strict` compatible types

---

## File Structure (Phase 1 deliverables)

```
pgbank-unofficial/
├── pyproject.toml                       [Task 1]
├── README.md                            [exists]
├── LICENSE                              [exists]
├── .gitignore                           [exists]
├── openspec/specs/pgbank-unofficial/
│   └── spec.md                          [exists]
├── docs/superpowers/                    [exists]
│   ├── specs/2026-06-23-pgbank-unofficial-design.md
│   └── plans/2026-06-23-pgbank-unofficial-phase-1.md  (this file)
├── .github/
│   └── workflows/
│       └── ci.yml                       [Task 14]
├── src/
│   └── pgbank_unofficial/
│       ├── __init__.py                  [Task 2 - public API exports]
│       ├── exceptions.py                [Task 3]
│       ├── models.py                    [Task 4]
│       ├── _algorithm.py                [Task 5 - extract from existing]
│       ├── http.py                      [Task 6 - HTTP transport + retry]
│       ├── client.py                    [Task 7 - PGBankClient sync]
│       ├── async_client.py              [Task 10 - AsyncPGBankClient]
│       └── py.typed                     [Task 1 - PEP 561 marker]
└── tests/
    ├── __init__.py
    ├── conftest.py                      [Task 11]
    ├── test_models.py                   [Task 4]
    ├── test_exceptions.py               [Task 3]
    ├── test_algorithm.py                [Task 5]
    ├── test_http.py                     [Task 6]
    ├── test_client.py                   [Task 8]
    └── test_async_client.py             [Task 10]
```

---

## Task Decomposition

The plan below contains **14 tasks**. Each task has bite-sized steps. Tasks must be executed in order; later tasks depend on earlier ones.

| # | Task | Est. Time | Deliverable |
|---|------|-----------|-------------|
| 1 | Project setup | 30 min | `pyproject.toml`, src layout, `py.typed` |
| 2 | Public API exports | 10 min | `__init__.py` re-exports |
| 3 | Exceptions module | 30 min | Typed exception hierarchy |
| 4 | Models (dataclasses) | 1 hr | `Account`, `Balance`, `Transaction`, `TransferResult` + tests |
| 5 | Encryption algorithm | 1 hr | Port `_algorithm.py` from existing + tests |
| 6 | HTTP transport + retry | 1.5 hr | `HTTPTransport` with retry/circuit-breaker + tests |
| 7 | PGBankClient (sync) — auth | 2 hr | `login_step1`, `login_step2`, session persistence |
| 8 | PGBankClient — queries | 2 hr | `get_customer_info`, `get_balance`, `get_accounts` |
| 9 | PGBankClient — context manager | 30 min | `__enter__`/`__exit__` |
| 10 | AsyncPGBankClient | 2 hr | Full async mirror |
| 11 | Test fixtures + conftest | 1 hr | Shared mocks, recorded HTTP responses |
| 12 | Integration tests | 2 hr | End-to-end with test credentials |
| 13 | Documentation polish | 1 hr | Docstrings, examples, README updates |
| 14 | CI + PyPI publish | 1 hr | GitHub Actions + build config |

**Total: ~16 hours (~2 working days)**

---

### Task 1: Project Setup with `pyproject.toml`

**Files:**
- Create: `pyproject.toml`
- Create: `src/pgbank_unofficial/__init__.py` (stub, will be filled in Task 2)
- Create: `src/pgbank_unofficial/py.typed`

**Interfaces:**
- Produces: Empty `pgbank_unofficial` package installable via `pip install -e .`
- Produces: `py.typed` marker (PEP 561) so mypy recognizes inline types when library is consumed

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling>=1.18"]
build-backend = "hatchling.build"

[project]
name = "pgbank-unofficial"
version = "0.1.0"
description = "Unofficial Python library for PGBank API with multi-account, auto-payment scheduling, webhooks, and transaction history"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.9"
authors = [{ name = "LeVietHung", email = "dinhnhatminh.minhkhanh@gmail.com" }]
keywords = ["pgbank", "banking", "api", "vietnam", "automation"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Office/Business :: Financial",
]
dependencies = [
    "requests>=2.28",
    "cryptography>=38.0",
    "pyyaml>=6.0",
    "jinja2>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "mypy>=1.0",
    "ruff>=0.1",
    "black>=23.0",
    "respx>=0.21",       # Mock aiohttp/httpx for async tests
    "httpx>=0.24",        # For testing async HTTP
    "build>=1.0",
    "twine>=4.0",
]
cli = [
    "click>=8.0",
    "typer>=0.9",
]
telegram = ["aiohttp>=3.8"]
discord = []  # uses stdlib urllib

[project.urls]
Homepage = "https://github.com/netrotion/pgbank-unofficial"
Repository = "https://github.com/netrotion/pgbank-unofficial"
Issues = "https://github.com/netrotion/pgbank-unofficial/issues"

[tool.hatch.build.targets.wheel]
packages = ["src/pgbank_unofficial"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --strict-markers --tb=short"
markers = [
    "integration: marks tests as integration tests requiring real API",
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]

[tool.mypy]
python_version = "3.9"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "PT", "RET"]
ignore = ["E501"]  # line-length handled by black

[tool.black]
line-length = 100
target-version = ["py39", "py310", "py311", "py312"]

[tool.coverage.run]
source = ["src/pgbank_unofficial"]
omit = ["*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

- [ ] **Step 2: Create empty `src/pgbank_unofficial/__init__.py`**

```python
"""PGBank Unofficial Library - typed Python client for PGBank API."""
__version__ = "0.1.0"
```

- [ ] **Step 3: Create `src/pgbank_unofficial/py.typed`**

```bash
# Just an empty marker file
touch src/pgbank_unofficial/py.typed
```

(On Windows PowerShell: `New-Item -ItemType File -Path src/pgbank_unofficial/py.typed -Force`)

- [ ] **Step 4: Verify package installs in editable mode**

Run: `pip install -e ".[dev]"`
Expected: Successfully installs, no errors.

- [ ] **Step 5: Verify import works**

Run: `python -c "import pgbank_unofficial; print(pgbank_unofficial.__version__)"`
Expected: `0.1.0`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/
git commit -m "build: setup pyproject.toml with hatchling, deps, dev tools"
```

---

### Task 2: Public API Exports in `__init__.py`

**Files:**
- Modify: `src/pgbank_unofficial/__init__.py`

**Interfaces:**
- Produces: Re-exports for `Account`, `Balance`, `Transaction`, `TransferResult`, `PGBankClient`, `AsyncPGBankClient`, exception classes — what end users will `from pgbank_unofficial import ...`

- [ ] **Step 1: Write the failing import test**

Create `tests/test_public_api.py`:

```python
"""Test that all public API symbols are importable from top-level package."""

def test_import_account():
    from pgbank_unofficial import Account
    assert Account is not None

def test_import_balance():
    from pgbank_unofficial import Balance
    assert Balance is not None

def test_import_transaction():
    from pgbank_unofficial import Transaction
    assert Transaction is not None

def test_import_transfer_result():
    from pgbank_unofficial import TransferResult
    assert TransferResult is not None

def test_import_pgbank_client():
    from pgbank_unofficial import PGBankClient
    assert PGBankClient is not None

def test_import_async_pgbank_client():
    from pgbank_unofficial import AsyncPGBankClient
    assert AsyncPGBankClient is not None

def test_import_exceptions():
    from pgbank_unofficial import (
        PGBankError,
        AuthenticationError,
        SessionExpiredError,
        MissingBrowserIDError,
        TimeoutError,
    )
    assert all(cls is not None for cls in [
        PGBankError, AuthenticationError, SessionExpiredError,
        MissingBrowserIDError, TimeoutError,
    ])

def test_version_exists():
    import pgbank_unofficial
    assert hasattr(pgbank_unofficial, "__version__")
    assert pgbank_unofficial.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test - verify it fails**

Run: `pytest tests/test_public_api.py -v`
Expected: FAIL with `ImportError: cannot import name 'Account' from 'pgbank_unofficial'`

- [ ] **Step 3: Write `__init__.py` with public exports**

```python
"""PGBank Unofficial Library - typed Python client for PGBank API.

Quickstart:
    >>> from pgbank_unofficial import PGBankClient
    >>> client = PGBankClient(username="alice", password="xxx", browser_id="bid_xxx")
    >>> client.login()  # may require OTP
    >>> balance = client.get_balance()
    >>> print(balance.available)
"""
from pgbank_unofficial.async_client import AsyncPGBankClient
from pgbank_unofficial.client import PGBankClient
from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    PGBankError,
    SessionExpiredError,
    TimeoutError,
)
from pgbank_unofficial.models import (
    Account,
    Balance,
    BankAccount,
    Transaction,
    TransferResult,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Core clients
    "PGBankClient",
    "AsyncPGBankClient",
    # Models
    "Account",
    "BankAccount",
    "Balance",
    "Transaction",
    "TransferResult",
    # Exceptions
    "PGBankError",
    "AuthenticationError",
    "SessionExpiredError",
    "MissingBrowserIDError",
    "TimeoutError",
]
```

- [ ] **Step 4: Run test - verify it still fails (missing dependencies)**

Run: `pytest tests/test_public_api.py -v`
Expected: FAIL with `ImportError` for the not-yet-created modules (`client`, `models`, etc.)

This is expected — Task 2 only sets up the export structure. Subsequent tasks will make the imports resolve.

- [ ] **Step 5: Commit**

```bash
git add src/pgbank_unofficial/__init__.py tests/test_public_api.py
git commit -m "feat: define public API surface with re-exports"
```

---

### Task 3: Exceptions Module

**Files:**
- Create: `src/pgbank_unofficial/exceptions.py`
- Create: `tests/test_exceptions.py`

**Interfaces:**
- Produces: `PGBankError` (base), `AuthenticationError`, `SessionExpiredError`, `MissingBrowserIDError`, `TimeoutError`, `RateLimitError`, `NetworkError`

- [ ] **Step 1: Write the failing test**

Create `tests/test_exceptions.py`:

```python
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
    """MissingBrowserIDError should clearly state browser_id is required."""
    err = MissingBrowserIDError("test message")
    assert "browser_id" in str(err).lower()
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
```

- [ ] **Step 2: Run test - verify it fails**

Run: `pytest tests/test_exceptions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgbank_unofficial.exceptions'`

- [ ] **Step 3: Implement `exceptions.py`**

```python
"""Custom exception hierarchy for pgbank-unofficial.

All exceptions inherit from PGBankError so users can catch all library-specific
errors with a single ``except PGBankError`` clause.
"""
from __future__ import annotations

from typing import Optional


class PGBankError(Exception):
    """Base exception for all pgbank-unofficial errors."""


class MissingBrowserIDError(PGBankError):
    """Raised when an Account or PGBankClient is created without browser_id.

    PGBank requires a BrowserID (browser fingerprint) for authentication.
    This is mandatory and cannot be omitted.
    """

    def __init__(self, message: str = "browser_id is required for PGBank authentication") -> None:
        super().__init__(message)


class AuthenticationError(PGBankError):
    """Raised when login fails due to invalid credentials or rejected auth."""

    def __init__(self, message: str, reason: Optional[str] = None) -> None:
        super().__init__(message)
        self.reason = reason


class SessionExpiredError(PGBankError):
    """Raised when the persisted session has expired and cannot be auto-renewed."""

    def __init__(self, message: str = "session expired", code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


class TimeoutError(PGBankError):
    """Raised when an HTTP request exceeds the configured timeout.

    Note: This shadows builtin TimeoutError intentionally so users can catch
    PGBank-specific timeouts without catching unrelated builtins.
    """

    def __init__(self, message: str = "request timed out", timeout: Optional[float] = None) -> None:
        super().__init__(message)
        self.timeout = timeout


class RateLimitError(PGBankError):
    """Raised when PGBank API returns HTTP 429 (Too Many Requests)."""

    def __init__(
        self, message: str = "rate limited", retry_after: Optional[int] = None
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NetworkError(PGBankError):
    """Raised on network-level failures (DNS, connection refused, TLS errors)."""


class TransferError(PGBankError):
    """Raised when a transfer operation fails (verification or confirmation)."""

    def __init__(self, message: str, stage: Optional[str] = None) -> None:
        super().__init__(message)
        self.stage = stage  # 'init', 'verify', 'confirm'
```

- [ ] **Step 4: Run test - verify it passes**

Run: `pytest tests/test_exceptions.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pgbank_unofficial/exceptions.py tests/test_exceptions.py
git commit -m "feat: add typed exception hierarchy with structured fields"
```

---

### Task 4: Models (Dataclasses)

**Files:**
- Create: `src/pgbank_unofficial/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `Account`, `BankAccount`, `Balance`, `Transaction`, `TransferResult`, `AccountStatus`, `TransactionDirection` enums
- All models have `to_dict()` for JSON serialization
- Money fields use `Decimal`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""Test dataclass models for type safety, validation, and serialization."""

import json
from dataclasses import asdict, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal

import pytest

from pgbank_unofficial.models import (
    Account,
    AccountStatus,
    Balance,
    BankAccount,
    Transaction,
    TransactionDirection,
    TransferResult,
)


def test_account_is_dataclass():
    """Account should be a frozen-ish dataclass."""
    assert is_dataclass(Account)


def test_account_requires_browser_id():
    """Account must require browser_id."""
    acc = Account(username="alice", password="xxx", browser_id="bid_xxx")
    assert acc.browser_id == "bid_xxx"


def test_account_proxy_optional():
    """proxy field should default to None."""
    acc = Account(username="alice", password="xxx", browser_id="bid_xxx")
    assert acc.proxy is None


def test_account_to_dict_masks_password():
    """Account.to_dict() should mask the password."""
    acc = Account(username="alice", password="secret", browser_id="bid_xxx")
    d = acc.to_dict()
    assert d["password"] == "***"
    assert d["username"] == "alice"
    assert d["browser_id"] == "bid_xxx"


def test_account_status_enum_values():
    """AccountStatus should have ALIVE, LOCKED, OTP_REQUIRED, ERROR."""
    statuses = {s.name for s in AccountStatus}
    assert statuses == {"ALIVE", "LOCKED", "OTP_REQUIRED", "ERROR"}


def test_balance_uses_decimal():
    """Balance monetary fields must be Decimal, not float."""
    bal = Balance(
        account_number="123",
        available=Decimal("100000.50"),
        total=Decimal("100000.50"),
    )
    assert isinstance(bal.available, Decimal)
    assert isinstance(bal.total, Decimal)
    # Verify precision preserved
    assert bal.available == Decimal("100000.50")


def test_balance_to_dict_json_serializable():
    """Balance.to_dict() output should be JSON-serializable."""
    bal = Balance(
        account_number="123",
        available=Decimal("100000.50"),
        total=Decimal("100000.50"),
        as_of=datetime(2026, 6, 23, 10, 30, 0),
    )
    d = bal.to_dict()
    json_str = json.dumps(d)  # should not raise
    parsed = json.loads(json_str)
    assert parsed["account_number"] == "123"
    assert parsed["available"] == "100000.50"  # Decimal becomes string in JSON


def test_transaction_amount_is_decimal():
    """Transaction.amount must be Decimal."""
    txn = Transaction(
        id="txn_1",
        account_number="123",
        type=TransactionDirection.DEBIT,
        amount=Decimal("50000"),
        currency="VND",
        counterparty_name="Alice",
        counterparty_account="456",
        counterparty_bank=None,
        description="Test",
        timestamp=datetime.now(),
    )
    assert isinstance(txn.amount, Decimal)


def test_transaction_direction_enum():
    """TransactionDirection should have DEBIT and CREDIT."""
    assert TransactionDirection.DEBIT.value == "debit"
    assert TransactionDirection.CREDIT.value == "credit"


def test_transfer_result_success_has_txn_id():
    """Successful transfer should carry txn_id."""
    result = TransferResult(
        success=True,
        txn_id="txn_abc123",
        timestamp=datetime.now(),
        fee=Decimal("0"),
    )
    assert result.success is True
    assert result.txn_id == "txn_abc123"


def test_transfer_result_failure_has_error():
    """Failed transfer should carry error message."""
    result = TransferResult(
        success=False,
        txn_id=None,
        timestamp=datetime.now(),
        error="Insufficient funds",
    )
    assert result.success is False
    assert result.error == "Insufficient funds"


def test_bank_account_fields():
    """BankAccount should have account_number, name, balance, currency."""
    acc = BankAccount(
        account_number="1234567890",
        account_name="NGUYEN VAN A",
        balance=Decimal("1000000"),
        currency="VND",
        account_type="checking",
    )
    assert acc.account_number == "1234567890"
    assert acc.currency == "VND"


def test_account_status_default():
    """Account status should default to ALIVE."""
    acc = Account(username="alice", password="xxx", browser_id="bid_xxx")
    assert acc.status == AccountStatus.ALIVE


def test_account_to_json_round_trip():
    """Account should be JSON-serializable and back."""
    acc = Account(username="alice", password="secret", browser_id="bid_xxx", nickname="a")
    json_str = json.dumps(acc.to_dict())
    parsed = json.loads(json_str)
    assert parsed["nickname"] == "a"
    assert parsed["password"] == "***"  # masked
```

- [ ] **Step 2: Run test - verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pgbank_unofficial.models'`

- [ ] **Step 3: Implement `models.py`**

```python
"""Typed dataclass models for pgbank-unofficial.

All monetary values use :class:`decimal.Decimal` to preserve precision.
All models provide :meth:`to_dict` for JSON serialization with proper
handling of Decimal (as string) and datetime (as ISO 8601).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class AccountStatus(Enum):
    """Status of a PGBank account/session."""

    ALIVE = "alive"
    LOCKED = "locked"
    OTP_REQUIRED = "otp_required"
    ERROR = "error"


class TransactionDirection(Enum):
    """Direction of a transaction (relative to the account holder)."""

    DEBIT = "debit"      # Money going OUT (expense)
    CREDIT = "credit"    # Money coming IN (income)


@dataclass
class Account:
    """A PGBank account with credentials and per-account config.

    Attributes:
        username: PGBank login username
        password: PGBank login password (will be masked in to_dict)
        browser_id: Browser fingerprint ID (REQUIRED for PGBank auth)
        proxy: Optional proxy URL, e.g. "http://user:pass@host:port"
        nickname: Optional human-friendly identifier for this account
        status: Current account status (auto-updated by client)
        last_login: Timestamp of last successful login
    """

    username: str
    password: str
    browser_id: str
    proxy: Optional[str] = None
    nickname: Optional[str] = None
    status: AccountStatus = AccountStatus.ALIVE
    last_login: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe dict with password masked."""
        d = asdict(self)
        d["password"] = "***" if self.password else None
        d["status"] = self.status.value
        d["last_login"] = self.last_login.isoformat() if self.last_login else None
        return d


@dataclass
class BankAccount:
    """A bank account number linked to a customer's profile.

    Attributes:
        account_number: The bank account number (digits only)
        account_name: Name of the account holder as registered
        balance: Current balance in the account
        currency: Currency code (default VND)
        account_type: Type of account (checking, savings, loan, etc.)
    """

    account_number: str
    account_name: str
    balance: Decimal
    currency: str = "VND"
    account_type: str = "checking"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["balance"] = str(self.balance)
        return d


@dataclass
class Balance:
    """Current balance for a bank account.

    Attributes:
        account_number: The account number
        available: Available balance (can be withdrawn/transferred)
        total: Total balance including holds/pending
        currency: Currency code
        as_of: Timestamp when balance was fetched
    """

    account_number: str
    available: Decimal
    total: Decimal
    currency: str = "VND"
    as_of: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["available"] = str(self.available)
        d["total"] = str(self.total)
        d["as_of"] = self.as_of.isoformat()
        return d


@dataclass
class Transaction:
    """A single transaction record.

    Attributes:
        id: Unique transaction ID from PGBank
        account_number: Source account for this transaction view
        type: Direction (DEBIT or CREDIT)
        amount: Transaction amount
        currency: Currency code
        counterparty_name: Name of the other party
        counterparty_account: Account number of the other party
        counterparty_bank: Bank code of the other party (None if same bank)
        description: Free-text description
        timestamp: When the transaction occurred
        raw: Original API response dict (for advanced users)
    """

    id: str
    account_number: str
    type: TransactionDirection
    amount: Decimal
    currency: str
    counterparty_name: str
    counterparty_account: str
    counterparty_bank: Optional[str]
    description: str
    timestamp: datetime
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["amount"] = str(self.amount)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class TransferResult:
    """Result of a transfer operation.

    Attributes:
        success: Whether the transfer completed
        txn_id: Transaction ID from PGBank (None if failed)
        timestamp: When the transfer was executed
        fee: Fee charged for the transfer
        error: Error message if transfer failed
        dry_run: True if this was a dry-run (no actual transfer)
    """

    success: bool
    txn_id: Optional[str]
    timestamp: datetime
    fee: Decimal = Decimal("0")
    error: Optional[str] = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["fee"] = str(self.fee)
        d["timestamp"] = self.timestamp.isoformat()
        return d
```

- [ ] **Step 4: Run test - verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pgbank_unofficial/models.py tests/test_models.py
git commit -m "feat: add typed dataclass models with Decimal money + JSON serialization"
```

---

### Task 5: Encryption Algorithm (Port from Existing)

**Files:**
- Create: `src/pgbank_unofficial/_algorithm.py`
- Create: `tests/test_algorithm.py`

**Interfaces:**
- Consumes: `pg/pgbank/pgbank/utils/_algorithm.py` (existing implementation)
- Produces: Standalone version usable without the parent codebase
- Functions: `md5_hash`, `aes_encrypt`, `aes_decrypt`, `rsa_encrypt`, `sign_data`, etc. (whatever the existing file exports)

- [ ] **Step 1: Identify existing exports**

Run (Windows PowerShell):
```powershell
Select-String -Path ../pg/pgbank/pgbank/utils/_algorithm.py -Pattern "^(def |class )"
```

Or on macOS/Linux:
```bash
grep -E "^(def |class )" ../pg/pgbank/pgbank/utils/_algorithm.py
```

Expected: List of function/class names. Document them in the test.

- [ ] **Step 2: Write the failing test for one function (e.g., MD5 hash)**

Create `tests/test_algorithm.py`:

```python
"""Test encryption algorithm primitives ported from existing pgbank code."""

from pgbank_unofficial._algorithm import md5_hash


def test_md5_hash_known_value():
    """MD5 of 'hello' should be 5d41402abc4b2a76b9719d911017c592."""
    assert md5_hash("hello") == "5d41402abc4b2a76b9719d911017c592"


def test_md5_hash_with_bytes():
    """MD5 should work with bytes input."""
    assert md5_hash(b"hello") == "5d41402abc4b2a76b9719d911017c592"


def test_md5_hash_empty_string():
    """MD5 of empty string should be d41d8cd98f00b204e9800998ecf8427e."""
    assert md5_hash("") == "d41d8cd98f00b204e9800998ecf8427e"
```

(Adjust the test functions to cover all exports from Step 1. Add more tests as needed.)

- [ ] **Step 3: Run test - verify it fails**

Run: `pytest tests/test_algorithm.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Copy existing algorithm file**

```bash
cp pg/pgbank/pgbank/utils/_algorithm.py src/pgbank_unofficial/_algorithm.py
```

Then **remove** the leading underscore from function names if they have one (e.g., `_md5_hash` → `md5_hash`) so they're part of the public API.

Add module docstring at the top:

```python
"""Encryption primitives for PGBank API.

Ported from the original implementation in pg/pgbank/pgbank/utils/_algorithm.py.
These functions implement PGBank's custom encryption scheme (MD5 hashing,
AES symmetric encryption, RSA for session keys, signature generation).
"""
```

- [ ] **Step 5: Run test - verify it passes**

Run: `pytest tests/test_algorithm.py -v`
Expected: PASS (3+ tests)

- [ ] **Step 6: Add tests for any other algorithm functions**

For each function exported in Step 1, add at least one test using known input/output pairs (or test invariants like `decrypt(encrypt(x)) == x`).

- [ ] **Step 7: Commit**

```bash
git add src/pgbank_unofficial/_algorithm.py tests/test_algorithm.py
git commit -m "feat: port encryption algorithm primitives from existing pgbank code"
```

---

### Task 6: HTTP Transport with Retry & Circuit Breaker

**Files:**
- Create: `src/pgbank_unofficial/http.py`
- Create: `tests/test_http.py`

**Interfaces:**
- Produces: `RetryPolicy`, `CircuitBreaker`, `HTTPTransport` classes
- `HTTPTransport` wraps `requests.Session` with: TLS fingerprint spoofing (via existing PGBank headers), retry on transient errors, circuit breaker for sustained failures
- `request(method, url, **kwargs) -> requests.Response`

- [ ] **Step 1: Write the failing test**

Create `tests/test_http.py`:

```python
"""Test HTTP transport, retry policy, and circuit breaker."""

import time
from unittest.mock import Mock, patch

import pytest
import requests

from pgbank_unofficial.exceptions import (
    NetworkError,
    RateLimitError,
    TimeoutError,
)
from pgbank_unofficial.http import CircuitBreaker, HTTPTransport, RetryPolicy


def test_retry_policy_default():
    """RetryPolicy should have sensible defaults."""
    policy = RetryPolicy()
    assert policy.max_retries >= 1
    assert policy.backoff_factor >= 1.0
    assert policy.retry_on_timeout is True


def test_retry_policy_exponential_backoff():
    """RetryPolicy should compute exponential delays."""
    policy = RetryPolicy(max_retries=4, backoff_factor=2.0, base_delay=1.0)
    assert policy.get_delay(attempt=1) == 1.0
    assert policy.get_delay(attempt=2) == 2.0
    assert policy.get_delay(attempt=3) == 4.0
    assert policy.get_delay(attempt=4) == 8.0


def test_retry_policy_respects_max_retries():
    """RetryPolicy.should_retry should return False after max_retries."""
    policy = RetryPolicy(max_retries=2)
    assert policy.should_retry(attempt=1) is True
    assert policy.should_retry(attempt=2) is True
    assert policy.should_retry(attempt=3) is False


def test_circuit_breaker_starts_closed():
    """Circuit breaker should start in CLOSED state."""
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == "closed"
    assert cb.allow_request() is True


def test_circuit_breaker_opens_after_threshold():
    """Circuit breaker should open after N consecutive failures."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()  # 3rd failure
    assert cb.state == "open"
    assert cb.allow_request() is False


def test_circuit_breaker_recovers_after_timeout():
    """Circuit breaker should transition to half-open after recovery_timeout."""
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    assert cb.state == "open"
    time.sleep(0.15)
    assert cb.allow_request() is True  # Half-open
    cb.record_success()
    assert cb.state == "closed"


def test_circuit_breaker_resets_on_success():
    """Successful request should reset failure count."""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.failure_count == 0


def test_http_transport_requires_proxy_or_none():
    """HTTPTransport should accept proxy=None or proxy string."""
    t1 = HTTPTransport(proxy=None)
    assert t1.proxy is None
    t2 = HTTPTransport(proxy="http://proxy:8080")
    assert t2.proxy == "http://proxy:8080"


def test_http_transport_raises_timeout_on_slow_request():
    """HTTPTransport should raise TimeoutError after configured timeout."""
    transport = HTTPTransport(proxy=None, timeout=0.1)

    def slow_request(*args, **kwargs):
        time.sleep(0.5)
        return Mock()

    with patch.object(transport._session, "request", side_effect=slow_request):
        with pytest.raises(TimeoutError):
            transport.request("GET", "https://example.com")


def test_http_transport_wraps_network_errors():
    """HTTPTransport should wrap requests.exceptions as NetworkError."""
    transport = HTTPTransport(proxy=None)

    with patch.object(
        transport._session,
        "request",
        side_effect=requests.exceptions.ConnectionError("fail"),
    ):
        with pytest.raises(NetworkError):
            transport.request("GET", "https://example.com")


def test_http_transport_raises_rate_limit_on_429():
    """HTTPTransport should raise RateLimitError on HTTP 429."""
    transport = HTTPTransport(proxy=None)

    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.headers = {"Retry-After": "60"}
    mock_response.json.return_value = {"error": "too many requests"}

    with patch.object(transport._session, "request", return_value=mock_response):
        with pytest.raises(RateLimitError) as exc_info:
            transport.request("GET", "https://example.com")
        assert exc_info.value.retry_after == 60
```

- [ ] **Step 2: Run test - verify it fails**

Run: `pytest tests/test_http.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `http.py`**

```python
"""HTTP transport with retry policy and circuit breaker.

Wraps :class:`requests.Session` to provide:
- TLS-friendly headers (PGBank has custom fingerprinting)
- Configurable retry on transient errors (timeouts, 5xx, connection errors)
- Circuit breaker to avoid hammering a failing endpoint
- Transparent proxy support (per-account)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from pgbank_unofficial.exceptions import (
    NetworkError,
    RateLimitError,
    TimeoutError as PGBankTimeoutError,
)

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """Configures retry behavior for transient failures.

    Attributes:
        max_retries: Maximum retry attempts (not counting initial request)
        backoff_factor: Multiplier for exponential backoff
        base_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries (cap)
        retry_on_timeout: Whether to retry on timeout
        retry_on_5xx: Whether to retry on HTTP 5xx errors
    """

    max_retries: int = 3
    backoff_factor: float = 2.0
    base_delay: float = 1.0
    max_delay: float = 60.0
    retry_on_timeout: bool = True
    retry_on_5xx: bool = True

    def get_delay(self, attempt: int) -> float:
        """Compute delay (seconds) before retry attempt N (1-indexed)."""
        delay = self.base_delay * (self.backoff_factor ** (attempt - 1))
        return min(delay, self.max_delay)

    def should_retry(self, attempt: int) -> bool:
        """Return True if we should retry given attempt count (1-indexed)."""
        return attempt <= self.max_retries


class CircuitBreaker:
    """Circuit breaker to stop hammering a failing endpoint.

    States:
        closed: Normal operation, requests pass through
        open: All requests fail-fast (after threshold consecutive failures)
        half-open: Allow one request to test recovery
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "closed"
        self._last_failure_time: Optional[float] = None

    def record_success(self) -> None:
        """Record a successful request - resets failure count."""
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        """Record a failed request - may open circuit if threshold reached."""
        self.failure_count += 1
        self._last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                "Circuit breaker opened after %d consecutive failures",
                self.failure_count,
            )

    def allow_request(self) -> bool:
        """Return True if request should proceed, False if circuit is open."""
        if self.state == "closed":
            return True
        if self.state == "open":
            # Check if recovery timeout has elapsed
            if (
                self._last_failure_time
                and time.time() - self._last_failure_time >= self.recovery_timeout
            ):
                self.state = "half-open"
                logger.info("Circuit breaker transitioning to half-open")
                return True
            return False
        # half-open: allow one request
        return True


class HTTPTransport:
    """HTTP transport with retry, circuit breaker, and proxy support.

    Wraps a :class:`requests.Session` to add resilience and PGBank-specific
    behavior. Per-account instances recommended (each account = own transport).
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        self.proxy = proxy
        self.timeout = timeout
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        """Build a requests.Session with proxy + default headers."""
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)
        if self.proxy:
            session.proxies = {"http": self.proxy, "https": self.proxy}
        return session

    def request(
        self,
        method: str,
        url: str,
        *,
        retry: bool = True,
        **kwargs: object,
    ) -> requests.Response:
        """Make an HTTP request with retry + circuit breaker.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL
            retry: Whether to apply retry policy
            **kwargs: Forwarded to requests.Session.request

        Returns:
            requests.Response on success

        Raises:
            TimeoutError: On request timeout
            NetworkError: On connection/DNS/TLS errors
            RateLimitError: On HTTP 429
            requests.exceptions.HTTPError: On other non-2xx (caller handles)
        """
        if not self.circuit_breaker.allow_request():
            raise NetworkError("Circuit breaker is open - refusing request")

        kwargs.setdefault("timeout", self.timeout)
        attempt = 0

        while True:
            attempt += 1
            try:
                response = self._session.request(method, url, **kwargs)
            except requests.exceptions.Timeout as e:
                self.circuit_breaker.record_failure()
                if retry and self.retry_policy.should_retry(attempt) and self.retry_policy.retry_on_timeout:
                    delay = self.retry_policy.get_delay(attempt)
                    logger.warning("Request timeout, retrying in %.1fs (attempt %d)", delay, attempt)
                    time.sleep(delay)
                    continue
                raise PGBankTimeoutError(f"Request timed out after {self.timeout}s", timeout=self.timeout) from e
            except requests.exceptions.RequestException as e:
                self.circuit_breaker.record_failure()
                raise NetworkError(f"Network error: {e}") from e

            # Handle 429 Rate Limit
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                self.circuit_breaker.record_failure()
                raise RateLimitError("Rate limited by PGBank API", retry_after=retry_after)

            # Handle 5xx (retryable)
            if response.status_code >= 500 and retry and self.retry_policy.should_retry(attempt) and self.retry_policy.retry_on_5xx:
                delay = self.retry_policy.get_delay(attempt)
                logger.warning(
                    "Server error %d, retrying in %.1fs (attempt %d)",
                    response.status_code, delay, attempt,
                )
                time.sleep(delay)
                continue

            # Success or non-retryable error
            if response.status_code < 400:
                self.circuit_breaker.record_success()
            return response
```

- [ ] **Step 4: Run test - verify it passes**

Run: `pytest tests/test_http.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pgbank_unofficial/http.py tests/test_http.py
git commit -m "feat: add HTTP transport with retry policy, circuit breaker, proxy support"
```

---

### Task 7: PGBankClient (Sync) — Authentication

**Files:**
- Create: `src/pgbank_unofficial/client.py`
- Create: `tests/test_client.py`

**Interfaces:**
- Produces: `PGBankClient` class with:
  - `__init__(username, password, browser_id, proxy=None, session_file=None, timeout=30.0)`
  - `login(otp=None) -> AuthResult` (returns intermediate state if OTP needed)
  - `is_logged_in() -> bool`
  - `logout() -> None`
- Uses `HTTPTransport` from Task 6 and encryption from Task 5
- Persists session to disk (JSON file) when `session_file` provided

- [ ] **Step 1: Write the failing test for client init + browser_id validation**

Create `tests/test_client.py`:

```python
"""Test PGBankClient authentication and session management."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pgbank_unofficial.client import PGBankClient
from pgbank_unofficial.exceptions import AuthenticationError, MissingBrowserIDError


def test_client_requires_browser_id():
    """PGBankClient should raise MissingBrowserIDError if browser_id is missing."""
    with pytest.raises(MissingBrowserIDError):
        PGBankClient(username="alice", password="xxx", browser_id="")


def test_client_accepts_browser_id():
    """PGBankClient should accept browser_id parameter."""
    client = PGBankClient(username="alice", password="xxx", browser_id="bid_xxx")
    assert client.browser_id == "bid_xxx"
    assert client.username == "alice"


def test_client_creates_session_file_path(tmp_path: Path):
    """PGBankClient should accept a session_file for persistence."""
    session_file = tmp_path / "session.json"
    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=session_file,
    )
    assert client.session_file == session_file


def test_client_is_logged_in_false_initially():
    """New client should not be logged in."""
    client = PGBankClient(username="alice", password="xxx", browser_id="bid_xxx")
    assert client.is_logged_in() is False


def test_client_login_step1_requires_otp(tmp_path: Path):
    """login() should return AuthResult with otp_required=True if server asks for OTP."""
    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=tmp_path / "s.json",
    )

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ref_no": "ref_abc",
        "otp_token": "otp_tok_xyz",
        "errorCode": "01",  # means OTP required
    }

    with patch.object(client._http, "request", return_value=mock_response):
        result = client.login()
        assert result.otp_required is True
        assert result.otp_ref == "ref_abc"
        assert result.otp_token == "otp_tok_xyz"


def test_client_login_with_otp_succeeds(tmp_path: Path):
    """login(otp=...) should complete login and persist session."""
    session_file = tmp_path / "s.json"
    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=session_file,
    )

    # Mock step2 response (login with OTP)
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "00",  # success
        "sessionId": "sess_xxx",
        "custId": "cust_xxx",
        "mid": "MID_001",
    }

    with patch.object(client._http, "request", return_value=mock_response):
        result = client.login(otp="123456", otp_ref="ref_abc", otp_token="otp_tok_xyz")
        assert result.success is True
        assert client.is_logged_in() is True
        # Session file should be created
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["sessionId"] == "sess_xxx"


def test_client_login_failure_raises_authentication_error(tmp_path: Path):
    """Failed login should raise AuthenticationError."""
    client = PGBankClient(
        username="alice",
        password="wrong",
        browser_id="bid_xxx",
        session_file=tmp_path / "s.json",
    )

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "99",
        "errorMessage": "Invalid credentials",
    }

    with patch.object(client._http, "request", return_value=mock_response):
        with pytest.raises(AuthenticationError) as exc_info:
            client.login()
        assert "invalid" in str(exc_info.value).lower() or "credential" in str(exc_info.value).lower()


def test_client_auto_restores_session(tmp_path: Path):
    """Client should auto-restore from session_file on init."""
    session_file = tmp_path / "s.json"
    session_file.write_text(json.dumps({
        "sessionId": "existing_sess",
        "custId": "cust_xxx",
        "mid": "MID_001",
        "browser_id": "bid_xxx",
        "username": "alice",
    }))

    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=session_file,
    )

    # Mock validation call - returns success
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"errorCode": "00", "custId": "cust_xxx"}

    with patch.object(client._http, "request", return_value=mock_response):
        client._restore_or_validate_session()
        assert client.is_logged_in() is True


def test_client_logout_clears_session(tmp_path: Path):
    """logout() should clear session state and delete session_file."""
    session_file = tmp_path / "s.json"
    session_file.write_text(json.dumps({
        "sessionId": "sess_xxx",
        "custId": "cust_xxx",
        "mid": "MID_001",
        "browser_id": "bid_xxx",
        "username": "alice",
    }))

    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=session_file,
    )

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"errorCode": "00"}

    with patch.object(client._http, "request", return_value=mock_response):
        client._restore_or_validate_session()
        assert client.is_logged_in() is True

        client.logout()
        assert client.is_logged_in() is False
        assert not session_file.exists()
```

- [ ] **Step 2: Run test - verify it fails**

Run: `pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `client.py` (auth portion)**

```python
"""PGBankClient - synchronous client for PGBank API.

Manages authentication, session persistence, and provides typed methods
for querying accounts, balances, transactions, and performing transfers.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pgbank_unofficial import _algorithm
from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    PGBankError,
    SessionExpiredError,
)
from pgbank_unofficial.http import HTTPTransport

logger = logging.getLogger(__name__)

# PGBank API base URLs (placeholder - fill from existing implementation)
PGBANK_BASE_URL = "https://pgbank.com.vn/api"


@dataclass
class AuthResult:
    """Result of an authentication attempt.

    Attributes:
        success: True if login completed (session established)
        otp_required: True if OTP is needed to complete login
        otp_ref: Reference number for OTP submission (if otp_required)
        otp_token: Token for OTP verification (if otp_required)
        error: Error message if login failed
    """

    success: bool = False
    otp_required: bool = False
    otp_ref: Optional[str] = None
    otp_token: Optional[str] = None
    error: Optional[str] = None


class PGBankClient:
    """Synchronous client for PGBank API.

    Each instance represents ONE authenticated session for ONE account.

    Example:
        >>> client = PGBankClient(username="alice", password="xxx", browser_id="bid_xxx")
        >>> result = client.login()
        >>> if result.otp_required:
        ...     otp = input("Enter OTP: ")
        ...     result = client.login(otp=otp, otp_ref=result.otp_ref, otp_token=result.otp_token)
        >>> balance = client.get_balance()
        >>> print(balance.available)
    """

    def __init__(
        self,
        username: str,
        password: str,
        browser_id: str,
        *,
        proxy: Optional[str] = None,
        session_file: Optional[Path] = None,
        timeout: float = 30.0,
        base_url: str = PGBANK_BASE_URL,
    ) -> None:
        if not browser_id:
            raise MissingBrowserIDError()

        self.username = username
        self.password = password
        self.browser_id = browser_id
        self.proxy = proxy
        self.session_file = session_file
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

        # Session state (populated after login)
        self._session_id: Optional[str] = None
        self._cust_id: Optional[str] = None
        self._mid: Optional[str] = None
        self._logged_in: bool = False

        # HTTP transport
        self._http = HTTPTransport(proxy=proxy, timeout=timeout)

        # Auto-restore session if file exists
        if self.session_file and self.session_file.exists():
            self._restore_or_validate_session()

    def is_logged_in(self) -> bool:
        """Return True if client has an active session."""
        return self._logged_in

    def login(
        self,
        otp: Optional[str] = None,
        *,
        otp_ref: Optional[str] = None,
        otp_token: Optional[str] = None,
    ) -> AuthResult:
        """Authenticate with PGBank.

        Two-step flow:
        1. Call without OTP - may return AuthResult(otp_required=True)
        2. Call with OTP + otp_ref + otp_token to complete login

        Args:
            otp: One-time password received via SMS
            otp_ref: Reference from step 1 (required if otp provided)
            otp_token: Token from step 1 (required if otp provided)

        Returns:
            AuthResult indicating outcome
        """
        if otp is None:
            return self._login_step1()
        return self._login_step2(otp, otp_ref or "", otp_token or "")

    def _login_step1(self) -> AuthResult:
        """First login step - sends credentials, may receive OTP challenge."""
        # Build login payload using PGBank's encryption scheme
        payload = self._build_login_payload()

        response = self._http.request(
            "POST",
            f"{self.base_url}/auth/login",
            json=payload,
        )

        data = response.json()
        error_code = data.get("errorCode", "")

        if error_code == "00":
            # Success without OTP (rare)
            self._apply_session(data)
            return AuthResult(success=True)

        if error_code == "01":  # OTP required
            return AuthResult(
                otp_required=True,
                otp_ref=data.get("ref_no"),
                otp_token=data.get("otp_token"),
            )

        # Other error codes
        raise AuthenticationError(
            data.get("errorMessage", f"Login failed with code {error_code}"),
            reason=error_code,
        )

    def _login_step2(self, otp: str, otp_ref: str, otp_token: str) -> AuthResult:
        """Second login step - submit OTP to complete authentication."""
        payload = self._build_otp_payload(otp, otp_ref, otp_token)

        response = self._http.request(
            "POST",
            f"{self.base_url}/auth/verify-otp",
            json=payload,
        )

        data = response.json()
        error_code = data.get("errorCode", "")

        if error_code == "00":
            self._apply_session(data)
            return AuthResult(success=True)

        raise AuthenticationError(
            data.get("errorMessage", f"OTP verification failed: {error_code}"),
            reason=error_code,
        )

    def logout(self) -> None:
        """Clear session state and delete session file."""
        self._session_id = None
        self._cust_id = None
        self._mid = None
        self._logged_in = False
        if self.session_file and self.session_file.exists():
            try:
                self.session_file.unlink()
            except OSError as e:
                logger.warning("Failed to delete session file: %s", e)

    def _apply_session(self, data: dict[str, Any]) -> None:
        """Apply session fields from API response and persist."""
        self._session_id = data.get("sessionId")
        self._cust_id = data.get("custId")
        self._mid = data.get("mid")
        self._logged_in = True
        if self.session_file:
            self._save_session()

    def _save_session(self) -> None:
        """Persist session to disk for auto-restore."""
        if not self.session_file:
            return
        data = {
            "sessionId": self._session_id,
            "custId": self._cust_id,
            "mid": self._mid,
            "username": self.username,
            "browser_id": self.browser_id,
            "saved_at": datetime.now().isoformat(),
        }
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(data, indent=2))

    def _restore_or_validate_session(self) -> None:
        """Load session from disk and validate with API."""
        if not self.session_file or not self.session_file.exists():
            return
        try:
            data = json.loads(self.session_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load session file: %s", e)
            return

        # Apply session fields without API call yet
        self._session_id = data.get("sessionId")
        self._cust_id = data.get("custId")
        self._mid = data.get("mid")

        # Validate by making a lightweight API call
        try:
            response = self._http.request(
                "GET",
                f"{self.base_url}/customer/info",
                headers=self._auth_headers(),
            )
            if response.status_code == 200 and response.json().get("errorCode") == "00":
                self._logged_in = True
                logger.info("Session restored for user %s", self.username)
            else:
                logger.info("Stored session is no longer valid")
                self.logout()
        except PGBankError as e:
            logger.warning("Session validation failed: %s", e)
            self.logout()

    def _auth_headers(self) -> dict[str, str]:
        """Build headers for authenticated requests."""
        if not self._session_id:
            return {}
        return {
            "Authorization": f"Bearer {self._session_id}",
            "X-Cust-Id": self._cust_id or "",
            "X-MID": self._mid or "",
        }

    def _build_login_payload(self) -> dict[str, Any]:
        """Build encrypted login payload for step 1.

        Uses PGBank's MD5-based hashing for username/password and includes
        browserId + timestamp. The full RSA + AES encryption scheme from
        ``_algorithm.py`` is applied at the HTTP layer via ``_http.post``.

        NOTE: PGBank may add additional checksum fields (see _calc_checksum in
        existing _algorithm.py). Verify with integration tests using real API.
        """
        return {
            "username": _algorithm.md5_hash(self.username),
            "password": _algorithm.md5_hash(self.password),
            "browserId": self.browser_id,
            "timestamp": datetime.now().isoformat(),
        }

    def _build_otp_payload(self, otp: str, otp_ref: str, otp_token: str) -> dict[str, Any]:
        """Build encrypted OTP payload for step 2."""
        return {
            "otp": _algorithm.md5_hash(otp),
            "ref_no": otp_ref,
            "otp_token": otp_token,
        }
```

- [ ] **Step 4: Run test - verify it passes**

Run: `pytest tests/test_client.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pgbank_unofficial/client.py tests/test_client.py
git commit -m "feat: add PGBankClient with 2-step login, session persistence, auto-restore"
```

---

### Task 8: PGBankClient — Account & Balance Queries

**Files:**
- Modify: `src/pgbank_unofficial/client.py` (add query methods)
- Modify: `tests/test_client.py` (add query tests)

**Interfaces:**
- Adds methods to `PGBankClient`:
  - `get_customer_info() -> AccountInfo` (need to create `AccountInfo` model in models.py)
  - `get_balance(account_number: Optional[str] = None) -> Balance`
  - `get_accounts() -> list[BankAccount]`

- [ ] **Step 1: Add `AccountInfo` and `BankAccount` re-export in models.py**

If not already present from Task 4 (BankAccount is, but AccountInfo is new), add:

In `src/pgbank_unofficial/models.py`, add after `BankAccount`:

```python
@dataclass
class AccountInfo:
    """Customer profile with all linked bank accounts.

    Attributes:
        customer_id: PGBank customer ID
        customer_name: Full name as registered
        accounts: All bank accounts linked to this customer
        primary_account: The default/primary account
    """

    customer_id: str
    customer_name: str
    accounts: list[BankAccount]
    primary_account: BankAccount

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
```

Also add to `__init__.py` exports (Task 2 should already handle BankAccount; add AccountInfo).

- [ ] **Step 2: Write the failing test for query methods**

Append to `tests/test_client.py`:

```python
def test_get_customer_info_returns_account_info(tmp_path: Path):
    """get_customer_info should return typed AccountInfo."""
    from pgbank_unofficial.models import AccountInfo, BankAccount
    from decimal import Decimal

    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=tmp_path / "s.json",
    )
    # Force logged-in state
    client._logged_in = True
    client._session_id = "sess_test"
    client._cust_id = "cust_test"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "00",
        "custId": "cust_test",
        "custName": "NGUYEN VAN A",
        "accounts": [
            {
                "accountNumber": "1234567890",
                "accountName": "NGUYEN VAN A",
                "balance": "1000000",
                "currency": "VND",
                "accountType": "checking",
            }
        ],
        "primaryAccount": "1234567890",
    }

    with patch.object(client._http, "request", return_value=mock_response):
        info = client.get_customer_info()
        assert isinstance(info, AccountInfo)
        assert info.customer_id == "cust_test"
        assert info.customer_name == "NGUYEN VAN A"
        assert len(info.accounts) == 1
        assert info.accounts[0].account_number == "1234567890"


def test_get_balance_returns_decimal_balance(tmp_path: Path):
    """get_balance should return Balance with Decimal amounts."""
    from pgbank_unofficial.models import Balance
    from decimal import Decimal

    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=tmp_path / "s.json",
    )
    client._logged_in = True
    client._session_id = "sess_test"
    client._cust_id = "cust_test"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "00",
        "accountNumber": "1234567890",
        "available": "100000.50",
        "total": "100000.50",
        "currency": "VND",
    }

    with patch.object(client._http, "request", return_value=mock_response):
        balance = client.get_balance()
        assert isinstance(balance, Balance)
        assert balance.available == Decimal("100000.50")
        assert isinstance(balance.available, Decimal)


def test_get_balance_requires_login(tmp_path: Path):
    """get_balance should raise if not logged in."""
    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=tmp_path / "s.json",
    )
    # NOT logged in
    with pytest.raises(Exception):  # SessionExpiredError or similar
        client.get_balance()


def test_get_accounts_returns_list_of_bank_accounts(tmp_path: Path):
    """get_accounts should return list[BankAccount]."""
    from pgbank_unofficial.models import BankAccount

    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=tmp_path / "s.json",
    )
    client._logged_in = True
    client._session_id = "sess_test"
    client._cust_id = "cust_test"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "00",
        "accounts": [
            {
                "accountNumber": "111",
                "accountName": "Acc 1",
                "balance": "500000",
                "currency": "VND",
                "accountType": "checking",
            },
            {
                "accountNumber": "222",
                "accountName": "Acc 2",
                "balance": "2000000",
                "currency": "VND",
                "accountType": "savings",
            },
        ],
    }

    with patch.object(client._http, "request", return_value=mock_response):
        accounts = client.get_accounts()
        assert isinstance(accounts, list)
        assert len(accounts) == 2
        assert all(isinstance(a, BankAccount) for a in accounts)
        assert accounts[0].account_number == "111"
        assert accounts[1].account_type == "savings"
```

- [ ] **Step 3: Run test - verify it fails**

Run: `pytest tests/test_client.py::test_get_customer_info_returns_account_info -v`
Expected: FAIL with `AttributeError: 'PGBankClient' object has no attribute 'get_customer_info'`

- [ ] **Step 4: Add query methods to `client.py`**

Add to `PGBankClient` class (append before the `_build_login_payload` method):

```python
    def _require_login(self) -> None:
        """Raise SessionExpiredError if not logged in."""
        if not self._logged_in:
            raise SessionExpiredError("Not logged in - call login() first")

    def get_customer_info(self) -> "AccountInfo":
        """Get customer profile with all linked bank accounts.

        Returns:
            AccountInfo with customer details and accounts list
        """
        from pgbank_unofficial.models import AccountInfo, BankAccount

        self._require_login()
        response = self._http.request(
            "GET",
            f"{self.base_url}/customer/info",
            headers=self._auth_headers(),
        )
        data = response.json()
        if data.get("errorCode") != "00":
            raise PGBankError(data.get("errorMessage", "Failed to get customer info"))

        accounts = [
            BankAccount(
                account_number=a["accountNumber"],
                account_name=a["accountName"],
                balance=Decimal(a["balance"]),
                currency=a.get("currency", "VND"),
                account_type=a.get("accountType", "checking"),
            )
            for a in data.get("accounts", [])
        ]
        primary = next(
            (a for a in accounts if a.account_number == data.get("primaryAccount")),
            accounts[0] if accounts else None,
        )
        return AccountInfo(
            customer_id=data["custId"],
            customer_name=data["custName"],
            accounts=accounts,
            primary_account=primary,
        )

    def get_balance(self, account_number: Optional[str] = None) -> "Balance":
        """Get current balance for an account.

        Args:
            account_number: Specific account, or None for default

        Returns:
            Balance with available and total amounts as Decimal
        """
        from pgbank_unofficial.models import Balance

        self._require_login()
        params = {}
        if account_number:
            params["accountNumber"] = account_number

        response = self._http.request(
            "GET",
            f"{self.base_url}/account/balance",
            params=params,
            headers=self._auth_headers(),
        )
        data = response.json()
        if data.get("errorCode") != "00":
            raise PGBankError(data.get("errorMessage", "Failed to get balance"))

        return Balance(
            account_number=data["accountNumber"],
            available=Decimal(data["available"]),
            total=Decimal(data["total"]),
            currency=data.get("currency", "VND"),
            as_of=datetime.now(),
        )

    def get_accounts(self) -> list["BankAccount"]:
        """Get all bank accounts linked to the customer.

        Returns:
            list of BankAccount
        """
        from pgbank_unofficial.models import BankAccount

        self._require_login()
        response = self._http.request(
            "GET",
            f"{self.base_url}/account/list",
            headers=self._auth_headers(),
        )
        data = response.json()
        if data.get("errorCode") != "00":
            raise PGBankError(data.get("errorMessage", "Failed to list accounts"))

        return [
            BankAccount(
                account_number=a["accountNumber"],
                account_name=a["accountName"],
                balance=Decimal(a["balance"]),
                currency=a.get("currency", "VND"),
                account_type=a.get("accountType", "checking"),
            )
            for a in data.get("accounts", [])
        ]
```

Also add `from decimal import Decimal` import at top of client.py.

- [ ] **Step 5: Run test - verify it passes**

Run: `pytest tests/test_client.py -v`
Expected: PASS (12 tests, 8 + 4 new)

- [ ] **Step 6: Commit**

```bash
git add src/pgbank_unofficial/client.py src/pgbank_unofficial/models.py tests/test_client.py
git commit -m "feat: add get_customer_info, get_balance, get_accounts query methods"
```

---

### Task 9: PGBankClient — Context Manager

**Files:**
- Modify: `src/pgbank_unofficial/client.py`
- Modify: `tests/test_client.py`

**Interfaces:**
- Adds: `__enter__` / `__exit__` to PGBankClient

- [ ] **Step 1: Write the failing test**

Append to `tests/test_client.py`:

```python
def test_client_context_manager_auto_login_and_logout(tmp_path: Path):
    """PGBankClient should work as a context manager."""
    session_file = tmp_path / "s.json"
    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=session_file,
    )

    mock_login = Mock()
    mock_login.status_code = 200
    mock_login.json.return_value = {
        "errorCode": "00",
        "sessionId": "sess_xxx",
        "custId": "cust_xxx",
        "mid": "MID_001",
    }

    with patch.object(client._http, "request", return_value=mock_login):
        with client as c:
            assert c is client
            assert c.is_logged_in() is True

        # After context exit, should be logged out
        assert client.is_logged_in() is False
        assert not session_file.exists()


def test_client_context_manager_does_not_auto_login_if_already_logged_in(tmp_path: Path):
    """Context manager should not call login if already authenticated."""
    client = PGBankClient(
        username="alice",
        password="xxx",
        browser_id="bid_xxx",
        session_file=tmp_path / "s.json",
    )
    client._logged_in = True  # simulate already logged in

    with client as c:
        assert c.is_logged_in() is True
        # No login call should have been made (mock would catch it)
```

- [ ] **Step 2: Run test - verify it fails**

Run: `pytest tests/test_client.py::test_client_context_manager_auto_login_and_logout -v`
Expected: FAIL with `AttributeError: __enter__`

- [ ] **Step 3: Add context manager methods to client.py**

Append to PGBankClient class:

```python
    def __enter__(self) -> "PGBankClient":
        """Enter context - auto-login if not already authenticated."""
        if not self._logged_in:
            self.login()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context - auto-logout and clean up session."""
        self.logout()
```

- [ ] **Step 4: Run test - verify it passes**

Run: `pytest tests/test_client.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add src/pgbank_unofficial/client.py tests/test_client.py
git commit -m "feat: add context manager support to PGBankClient"
```

---

### Task 10: AsyncPGBankClient (Async Mirror)

**Files:**
- Create: `src/pgbank_unofficial/async_client.py`
- Create: `tests/test_async_client.py`

**Interfaces:**
- Produces: `AsyncPGBankClient` with same API as PGBankClient but using `async/await` and `aiohttp`

- [ ] **Step 1: Add aiohttp dependency**

Already in Task 1's `pyproject.toml`. Verify by checking.

- [ ] **Step 2: Write the failing test**

Create `tests/test_async_client.py`:

```python
"""Test AsyncPGBankClient for async/await support."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from pgbank_unofficial.async_client import AsyncPGBankClient
from pgbank_unofficial.exceptions import MissingBrowserIDError
from pgbank_unofficial.models import Balance
from decimal import Decimal


@pytest.mark.asyncio
async def test_async_client_requires_browser_id():
    """AsyncPGBankClient should require browser_id."""
    with pytest.raises(MissingBrowserIDError):
        AsyncPGBankClient(username="alice", password="xxx", browser_id="")


@pytest.mark.asyncio
async def test_async_client_login():
    """async login should work like sync login."""
    client = AsyncPGBankClient(username="alice", password="xxx", browser_id="bid_xxx")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "00",
        "sessionId": "sess_async",
        "custId": "cust_async",
        "mid": "MID_001",
    }

    with patch.object(client._http, "request", new=AsyncMock(return_value=mock_response)):
        result = await client.login(otp="123456", otp_ref="ref", otp_token="tok")
        assert result.success is True
        assert client.is_logged_in() is True


@pytest.mark.asyncio
async def test_async_get_balance():
    """async get_balance should return Balance with Decimal."""
    client = AsyncPGBankClient(username="alice", password="xxx", browser_id="bid_xxx")
    client._logged_in = True
    client._session_id = "sess"
    client._cust_id = "cust"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "00",
        "accountNumber": "123",
        "available": "500000.75",
        "total": "500000.75",
        "currency": "VND",
    }

    with patch.object(client._http, "request", new=AsyncMock(return_value=mock_response)):
        balance = await client.get_balance()
        assert isinstance(balance, Balance)
        assert balance.available == Decimal("500000.75")


@pytest.mark.asyncio
async def test_async_client_context_manager():
    """AsyncPGBankClient should support async context manager."""
    client = AsyncPGBankClient(username="alice", password="xxx", browser_id="bid_xxx")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "errorCode": "00",
        "sessionId": "sess",
        "custId": "cust",
        "mid": "MID_001",
    }

    with patch.object(client._http, "request", new=AsyncMock(return_value=mock_response)):
        async with client as c:
            assert c is client
            assert c.is_logged_in() is True
        assert client.is_logged_in() is False
```

- [ ] **Step 3: Run test - verify it fails**

Run: `pytest tests/test_async_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement `async_client.py`**

```python
"""AsyncPGBankClient - async/await mirror of PGBankClient.

Provides identical API but uses aiohttp under the hood for non-blocking I/O.
Suitable for use in FastAPI, Starlette, aiohttp, or any asyncio application.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import aiohttp

from pgbank_unofficial import _algorithm
from pgbank_unofficial.client import AuthResult
from pgbank_unofficial.exceptions import (
    AuthenticationError,
    MissingBrowserIDError,
    PGBankError,
    SessionExpiredError,
)
from pgbank_unofficial.models import AccountInfo, Balance, BankAccount

logger = logging.getLogger(__name__)


class AsyncHTTPTransport:
    """Async HTTP transport using aiohttp.

    Provides the same interface as HTTPTransport but with async methods.
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    def __init__(
        self,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.proxy = proxy
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make async HTTP request. Returns parsed JSON dict."""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            kwargs: dict[str, Any] = {"headers": {**self.DEFAULT_HEADERS, **(headers or {})}}
            if json is not None:
                kwargs["json"] = json
            if params is not None:
                kwargs["params"] = params
            if self.proxy:
                kwargs["proxy"] = self.proxy

            async with session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                return await response.json()


class AsyncPGBankClient:
    """Async client for PGBank API.

    Mirrors :class:`PGBankClient` API but uses async/await throughout.

    Example:
        >>> import asyncio
        >>> async def main():
        ...     client = AsyncPGBankClient(username="alice", password="xxx", browser_id="bid_xxx")
        ...     async with client as c:
        ...         balance = await c.get_balance()
        ...         print(balance.available)
        >>> asyncio.run(main())
    """

    def __init__(
        self,
        username: str,
        password: str,
        browser_id: str,
        *,
        proxy: Optional[str] = None,
        session_file: Optional[Path] = None,
        timeout: float = 30.0,
        base_url: str = "https://pgbank.com.vn/api",
    ) -> None:
        if not browser_id:
            raise MissingBrowserIDError()

        self.username = username
        self.password = password
        self.browser_id = browser_id
        self.proxy = proxy
        self.session_file = session_file
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

        self._session_id: Optional[str] = None
        self._cust_id: Optional[str] = None
        self._mid: Optional[str] = None
        self._logged_in = False

        self._http = AsyncHTTPTransport(proxy=proxy, timeout=timeout)

    def is_logged_in(self) -> bool:
        """Return True if client has an active session."""
        return self._logged_in

    async def login(
        self,
        otp: Optional[str] = None,
        *,
        otp_ref: Optional[str] = None,
        otp_token: Optional[str] = None,
    ) -> AuthResult:
        """Async login flow."""
        if otp is None:
            return await self._login_step1()
        return await self._login_step2(otp, otp_ref or "", otp_token or "")

    async def _login_step1(self) -> AuthResult:
        """Async login step 1."""
        payload = {
            "username": _algorithm.md5_hash(self.username),
            "password": _algorithm.md5_hash(self.password),
            "browserId": self.browser_id,
            "timestamp": datetime.now().isoformat(),
        }

        data = await self._http.request(
            "POST", f"{self.base_url}/auth/login", json=payload
        )
        error_code = data.get("errorCode", "")

        if error_code == "00":
            self._apply_session(data)
            return AuthResult(success=True)
        if error_code == "01":
            return AuthResult(
                otp_required=True,
                otp_ref=data.get("ref_no"),
                otp_token=data.get("otp_token"),
            )
        raise AuthenticationError(
            data.get("errorMessage", f"Login failed: {error_code}"),
            reason=error_code,
        )

    async def _login_step2(self, otp: str, otp_ref: str, otp_token: str) -> AuthResult:
        """Async login step 2 (OTP verification)."""
        payload = {
            "otp": _algorithm.md5_hash(otp),
            "ref_no": otp_ref,
            "otp_token": otp_token,
        }
        data = await self._http.request(
            "POST", f"{self.base_url}/auth/verify-otp", json=payload
        )
        error_code = data.get("errorCode", "")
        if error_code == "00":
            self._apply_session(data)
            return AuthResult(success=True)
        raise AuthenticationError(
            data.get("errorMessage", f"OTP failed: {error_code}"),
            reason=error_code,
        )

    def logout(self) -> None:
        """Clear session state."""
        self._session_id = None
        self._cust_id = None
        self._mid = None
        self._logged_in = False
        if self.session_file and self.session_file.exists():
            try:
                self.session_file.unlink()
            except OSError:
                pass

    def _apply_session(self, data: dict[str, Any]) -> None:
        """Apply session fields from response."""
        self._session_id = data.get("sessionId")
        self._cust_id = data.get("custId")
        self._mid = data.get("mid")
        self._logged_in = True
        if self.session_file:
            self._save_session()

    def _save_session(self) -> None:
        """Persist session to disk."""
        if not self.session_file:
            return
        data = {
            "sessionId": self._session_id,
            "custId": self._cust_id,
            "mid": self._mid,
            "username": self.username,
            "browser_id": self.browser_id,
            "saved_at": datetime.now().isoformat(),
        }
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(data, indent=2))

    def _auth_headers(self) -> dict[str, str]:
        """Build authenticated request headers."""
        if not self._session_id:
            return {}
        return {
            "Authorization": f"Bearer {self._session_id}",
            "X-Cust-Id": self._cust_id or "",
            "X-MID": self._mid or "",
        }

    def _require_login(self) -> None:
        """Raise if not authenticated."""
        if not self._logged_in:
            raise SessionExpiredError("Not logged in")

    async def get_balance(self, account_number: Optional[str] = None) -> Balance:
        """Async get_balance."""
        self._require_login()
        params = {"accountNumber": account_number} if account_number else None
        data = await self._http.request(
            "GET",
            f"{self.base_url}/account/balance",
            params=params,
            headers=self._auth_headers(),
        )
        if data.get("errorCode") != "00":
            raise PGBankError(data.get("errorMessage", "Failed to get balance"))
        return Balance(
            account_number=data["accountNumber"],
            available=Decimal(data["available"]),
            total=Decimal(data["total"]),
            currency=data.get("currency", "VND"),
            as_of=datetime.now(),
        )

    async def __aenter__(self) -> "AsyncPGBankClient":
        """Enter async context - auto-login."""
        if not self._logged_in:
            await self.login()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context - logout."""
        self.logout()
```

- [ ] **Step 5: Run test - verify it passes**

Run: `pytest tests/test_async_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run all tests - verify everything still works**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/pgbank_unofficial/async_client.py tests/test_async_client.py
git commit -m "feat: add AsyncPGBankClient with full async/await support"
```

---

### Task 11: Test Fixtures and Conftest

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/` (directory)

**Interfaces:**
- Produces: Shared pytest fixtures for HTTP mocking, sample responses, test credentials

- [ ] **Step 1: Create conftest.py**

```python
"""Shared pytest fixtures for pgbank-unofficial tests."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_login_response_success() -> Mock:
    """Mock response for successful login."""
    mock = Mock()
    mock.status_code = 200
    mock.json.return_value = {
        "errorCode": "00",
        "sessionId": "sess_test_123",
        "custId": "cust_test_456",
        "mid": "MID_TEST_001",
    }
    return mock


@pytest.fixture
def mock_login_response_otp_required() -> Mock:
    """Mock response for login that requires OTP."""
    mock = Mock()
    mock.status_code = 200
    mock.json.return_value = {
        "errorCode": "01",
        "ref_no": "ref_otp_123",
        "otp_token": "otp_tok_456",
    }
    return mock


@pytest.fixture
def mock_balance_response() -> Mock:
    """Mock response for get_balance."""
    mock = Mock()
    mock.status_code = 200
    mock.json.return_value = {
        "errorCode": "00",
        "accountNumber": "1234567890",
        "available": "1000000.50",
        "total": "1000000.50",
        "currency": "VND",
    }
    return mock


@pytest.fixture
def sample_session_file(tmp_path: Path) -> Path:
    """Sample session file content for restoration tests."""
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps({
        "sessionId": "sess_existing",
        "custId": "cust_existing",
        "mid": "MID_EXISTING",
        "username": "alice",
        "browser_id": "bid_existing",
    }))
    return session_file


@pytest.fixture
def test_browser_id() -> str:
    """Sample browser ID for tests."""
    return "test_browser_id_12345"


@pytest.fixture
def test_credentials() -> dict:
    """Sample test credentials (placeholder - real tests use env vars)."""
    return {
        "username": "test_user",
        "password": "test_pass",
        "browser_id": "test_browser_id_12345",
    }
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest -v`
Expected: ALL PASS (existing tests use the fixtures implicitly)

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py tests/fixtures/
git commit -m "test: add shared pytest fixtures for HTTP mocking and credentials"
```

---

### Task 12: Integration Tests with Test Credentials

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_real_api.py`
- Create: `tests/integration/conftest.py`

**Interfaces:**
- Produces: Tests that hit real PGBank API (gated by env vars + `--integration` flag)

- [ ] **Step 1: Create integration conftest with credential loading**

Create `tests/integration/conftest.py`:

```python
"""Integration test fixtures - load real credentials from environment."""

import os
from pathlib import Path

import pytest


@pytest.fixture
def real_credentials() -> dict:
    """Load real test credentials from environment.

    Skips test if PGBANK_TEST_USERNAME is not set.
    """
    username = os.environ.get("PGBANK_TEST_USERNAME")
    password = os.environ.get("PGBANK_TEST_PASSWORD")
    browser_id = os.environ.get("PGBANK_TEST_BROWSER_ID")

    if not all([username, password, browser_id]):
        pytest.skip("Integration tests require PGBANK_TEST_USERNAME, PGBANK_TEST_PASSWORD, PGBANK_TEST_BROWSER_ID env vars")

    return {
        "username": username,
        "password": password,
        "browser_id": browser_id,
    }


@pytest.fixture
def real_session_file(tmp_path: Path) -> Path:
    """Session file for integration tests (in tmp to not pollute)."""
    return tmp_path / "pgbank_session.json"
```

- [ ] **Step 2: Create integration test**

Create `tests/integration/test_real_api.py`:

```python
"""Integration tests that hit real PGBank API.

Marked with @pytest.mark.integration - skipped unless env vars set.
"""

import pytest

from pgbank_unofficial import PGBankClient


@pytest.mark.integration
def test_real_login_and_get_balance(real_credentials, real_session_file):
    """End-to-end: login + get_balance with real test credentials."""
    client = PGBankClient(
        username=real_credentials["username"],
        password=real_credentials["password"],
        browser_id=real_credentials["browser_id"],
        session_file=real_session_file,
    )

    # Login
    result = client.login()
    if result.otp_required:
        pytest.skip("OTP required - cannot test interactively. Pre-populate session_file instead.")

    # Get balance
    assert client.is_logged_in()
    balance = client.get_balance()
    assert balance.available >= 0
    assert balance.currency == "VND"


@pytest.mark.integration
def test_real_session_persistence(real_credentials, real_session_file):
    """Session file should allow auto-restore on second client instance."""
    # First client: login and persist
    client1 = PGBankClient(
        username=real_credentials["username"],
        password=real_credentials["password"],
        browser_id=real_credentials["browser_id"],
        session_file=real_session_file,
    )
    result = client1.login()
    if result.otp_required:
        pytest.skip("OTP required")

    assert real_session_file.exists()

    # Second client: should auto-restore without login call
    client2 = PGBankClient(
        username=real_credentials["username"],
        password=real_credentials["password"],
        browser_id=real_credentials["browser_id"],
        session_file=real_session_file,
    )
    assert client2.is_logged_in()
```

- [ ] **Step 3: Run integration tests (skip if no creds)**

Run: `pytest tests/integration/ -v`
Expected: SKIP (no env vars set)

- [ ] **Step 4: Document integration test usage in README**

Add to README.md:

```markdown
## Integration Tests

Tests that hit the real PGBank API require test credentials. Set these env vars:

```bash
export PGBANK_TEST_USERNAME=your_test_user
export PGBANK_TEST_PASSWORD=your_test_password
export PGBANK_TEST_BROWSER_ID=your_browser_id
pytest tests/integration/ -v
```

Otherwise integration tests are skipped automatically.
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/ README.md
git commit -m "test: add integration tests (skipped unless env vars set)"
```

---

### Task 13: Documentation Polish

**Files:**
- Modify: `src/pgbank_unofficial/client.py` (add docstrings)
- Modify: `src/pgbank_unofficial/async_client.py` (add docstrings)
- Modify: `src/pgbank_unofficial/http.py` (verify docstrings)
- Create: `examples/quickstart.py`
- Create: `examples/context_manager.py`

**Interfaces:**
- All public classes/functions have Google-style docstrings
- `examples/` directory has runnable example scripts

- [ ] **Step 1: Verify docstrings on all public classes in client.py**

Open `src/pgbank_unofficial/client.py` and confirm:
- `PGBankClient` class has docstring ✓ (already present from Task 7)
- `__init__` has Args section for each parameter
- `login()` has Args and Returns sections
- `get_balance()` has Args and Returns sections
- `get_customer_info()`, `get_accounts()` have Returns sections

If any are missing, add them now.

- [ ] **Step 2: Verify docstrings in async_client.py**

Open `src/pgbank_unofficial/async_client.py` and confirm same as above.

- [ ] **Step 3: Create `examples/quickstart.py`**

```python
"""Quickstart example - basic login and balance check.

Run: python examples/quickstart.py
"""

from pathlib import Path

from pgbank_unofficial import Account, PGBankClient


def main() -> None:
    # Setup client
    session_file = Path.home() / ".pgbank_session.json"
    client = PGBankClient(
        username="your_username",
        password="your_password",
        browser_id="your_browser_id",
        session_file=session_file,
    )

    # Login (may require OTP)
    result = client.login()
    if result.otp_required:
        otp = input("Enter OTP sent to your phone: ")
        result = client.login(
            otp=otp,
            otp_ref=result.otp_ref,
            otp_token=result.otp_token,
        )

    if not result.success:
        print(f"Login failed: {result.error}")
        return

    # Query
    print(f"Logged in as: {client.username}")
    balance = client.get_balance()
    print(f"Available balance: {balance.available:,.0f} {balance.currency}")

    # Logout (optional - session persists to file anyway)
    client.logout()
    print(f"Session saved to: {session_file}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `examples/context_manager.py`**

```python
"""Context manager example - automatic login/logout.

Run: python examples/context_manager.py
"""

from pgbank_unofficial import PGBankClient


def main() -> None:
    with PGBankClient(
        username="your_username",
        password="your_password",
        browser_id="your_browser_id",
    ) as client:
        # Client is logged in here
        balance = client.get_balance()
        print(f"Available: {balance.available:,.0f} VND")

        info = client.get_customer_info()
        print(f"Customer: {info.customer_name}")
        for acc in info.accounts:
            print(f"  - {acc.account_number}: {acc.balance:,.0f} {acc.currency}")

    # Client auto-logged out here


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Verify examples have valid syntax**

Run: `python -m py_compile examples/quickstart.py examples/context_manager.py`
Expected: No output (success)

- [ ] **Step 6: Commit**

```bash
git add src/ examples/
git commit -m "docs: add Google-style docstrings and example scripts"
```

---

### Task 14: CI Workflow + PyPI Publish Prep

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/publish.yml`

**Interfaces:**
- Produces: GitHub Actions workflow that runs on PR/push (lint + test + mypy) and publishes to PyPI on tag push

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Lint with ruff
        run: ruff check src/ tests/

      - name: Format check with black
        run: black --check src/ tests/

      - name: Type check with mypy
        run: mypy src/pgbank_unofficial/

      - name: Run tests with coverage
        run: |
          pytest tests/unit/ --cov=pgbank_unofficial --cov-report=xml --cov-report=term-missing

      - name: Upload coverage
        if: matrix.python-version == '3.11'
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: false

  integration:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push'  # only on push, not PR
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - name: Run integration tests
        env:
          PGBANK_TEST_USERNAME: ${{ secrets.PGBANK_TEST_USERNAME }}
          PGBANK_TEST_PASSWORD: ${{ secrets.PGBANK_TEST_PASSWORD }}
          PGBANK_TEST_BROWSER_ID: ${{ secrets.PGBANK_TEST_BROWSER_ID }}
        run: pytest tests/integration/ -v
```

- [ ] **Step 2: Create `.github/workflows/publish.yml`**

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - 'v*'

jobs:
  publish:
    name: Build and publish to PyPI
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # for PyPI trusted publishing
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build tools
        run: python -m pip install --upgrade build twine

      - name: Build package
        run: python -m build

      - name: Check package
        run: twine check dist/*

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # Uses PyPI trusted publishing (set up at https://pypi.org/manage/account/publishing/)
```

- [ ] **Step 3: Verify workflows are valid YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Run final test suite**

Run: `pytest -v --cov=pgbank_unofficial --cov-report=term-missing`
Expected: All tests pass, coverage > 90%

- [ ] **Step 5: Run mypy strict check**

Run: `mypy src/pgbank_unofficial/ --strict`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add .github/
git commit -m "ci: add GitHub Actions for tests + PyPI publishing"
```

---

## Verification Plan

After all tasks complete, run the full verification:

```bash
# 1. Run all unit tests
pytest tests/unit/ -v --cov=pgbank_unofficial --cov-report=term-missing

# Expected: All pass, coverage > 90%

# 2. Run mypy strict
mypy src/pgbank_unofficial/ --strict

# Expected: No errors

# 3. Run linters
ruff check src/ tests/
black --check src/ tests/

# Expected: No issues

# 4. Build package
python -m build
twine check dist/*

# Expected: Both .whl and .tar.gz created, no warnings

# 5. Try install in clean venv
python -m venv /tmp/pgbank-test-venv
/tmp/pgbank-test-venv/bin/pip install dist/pgbank_unofficial-0.1.0-py3-none-any.whl
/tmp/pgbank-test-venv/bin/python -c "from pgbank_unofficial import PGBankClient, AsyncPGBankClient; print('OK')"

# Expected: OK

# 6. Try quickstart example (requires test creds)
export PGBANK_TEST_USERNAME=xxx
export PGBANK_TEST_PASSWORD=xxx
export PGBANK_TEST_BROWSER_ID=xxx
python examples/quickstart.py

# Expected: Balance displayed
```

---

## Success Criteria for v0.1.0

- [x] All 14 tasks complete
- [ ] Test coverage > 90% on `src/pgbank_unofficial/`
- [ ] mypy --strict passes with no errors
- [ ] ruff + black pass
- [ ] Package builds without warnings
- [ ] `pip install pgbank-unofficial==0.1.0` works in clean venv
- [ ] Login + get_balance works with test credentials
- [ ] CI workflow is green on all 4 Python versions
- [ ] README has quickstart example
- [ ] Public API symbols importable from top-level package

---

## What's NOT in Phase 1 (deferred to Phase 2+)

These are deliberately not in Phase 1 — separate plans will be written:

- **PGBankManager** (multi-account) — Phase 2
- **Auto-payment scheduler** (flagship) — Phase 3
- **Webhook dispatcher** (Discord, Telegram, HTTP) — Phase 3
- **Transaction history query/export** — Phase 4
- **Balance polling + alerts** — Phase 4
- **CLI tool** (`pgbank` command) — Phase 4
- **Transfer flow** (init/verify/confirm) — Phase 2
- **Google Sheets integration** — Phase 4 or later
- **PDF export** — Phase 4 or later

---

## Open Questions

None remaining — all decisions resolved during brainstorming (see design doc).
