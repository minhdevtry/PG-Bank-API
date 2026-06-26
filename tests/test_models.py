"""Test dataclass models for type safety, validation, and serialization."""

import json
from dataclasses import is_dataclass
from datetime import datetime
from decimal import Decimal

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
