"""Typed dataclass models for pgbank-unofficial.

All monetary values use :class:`decimal.Decimal` to preserve precision.
All models provide :meth:`to_dict` for JSON serialization with proper
handling of Decimal (as string) and datetime (as ISO 8601).
"""

from __future__ import annotations

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

    DEBIT = "debit"  # Money going OUT (expense)
    CREDIT = "credit"  # Money coming IN (income)


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
        return asdict(self)
