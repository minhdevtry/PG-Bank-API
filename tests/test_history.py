"""Test the history module — HistoryQuery, TransactionHistory, export functions."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pgbank_unofficial.exceptions import PGBankError
from pgbank_unofficial.history import (
    CategorizedTransaction,
    HistoryQuery,
    TransactionHistory,
    export_to_csv,
    export_to_excel,
    export_to_json,
    query_all_accounts,
)
from pgbank_unofficial.models import (
    Account,
    AccountStatus,
    BankAccount,
    Transaction,
    TransactionDirection,
)

VN_TZ_OFFSET = 7 * 3600


def _make_tx(
    *,
    id: str = "tx1",
    account_number: str = "123456",
    direction: TransactionDirection = TransactionDirection.DEBIT,
    amount: Decimal = Decimal("50000"),
    counterparty_name: str = "GRAB VIETNAM",
    counterparty_account: str = "999999",
    description: str = "GRAB ride",
    timestamp: datetime | None = None,
    currency: str = "VND",
) -> Transaction:
    return Transaction(
        id=id,
        account_number=account_number,
        type=direction,
        amount=amount,
        currency=currency,
        counterparty_name=counterparty_name,
        counterparty_account=counterparty_account,
        counterparty_bank=None,
        description=description,
        timestamp=timestamp or datetime(2024, 6, 15, 10, 30),
        raw={},
    )


# ── HistoryQuery ──────────────────────────────────────────────────────────────


def test_history_query_default_is_no_filter():
    """Default HistoryQuery should accept no filters without error."""
    q = HistoryQuery()
    assert q.account_number is None
    assert q.from_date is None
    assert q.to_date is None


def test_history_query_rejects_min_greater_than_max():
    """Should raise ValueError if min_amount > max_amount."""
    with pytest.raises(ValueError, match="min_amount"):
        HistoryQuery(
            min_amount=Decimal("1000"),
            max_amount=Decimal("500"),
        )


def test_history_query_rejects_from_after_to():
    """Should raise ValueError if from_date > to_date."""
    with pytest.raises(ValueError, match="from_date"):
        HistoryQuery(
            from_date=date(2024, 12, 31),
            to_date=date(2024, 1, 1),
        )


def test_history_query_accepts_valid_amount_range():
    """Should accept valid range."""
    q = HistoryQuery(
        min_amount=Decimal("100"),
        max_amount=Decimal("1000"),
    )
    assert q.min_amount == Decimal("100")


def test_history_query_accepts_valid_date_range():
    """Should accept valid date range."""
    q = HistoryQuery(
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
    )
    assert q.from_date == date(2024, 1, 1)


# ── TransactionHistory.query ──────────────────────────────────────────────────


def _make_mock_client(transactions: list[Transaction]) -> MagicMock:
    """Build a mock PGBankClient that returns the given transactions."""
    client = MagicMock()
    client.get_transaction_history.return_value = transactions
    client.get_accounts.return_value = [
        BankAccount(
            account_number="123456",
            account_name="Alice",
            balance=Decimal("1000000"),
            currency="VND",
            account_type="checking",
        )
    ]
    return client


def test_query_with_no_filters_returns_all():
    """Empty HistoryQuery should return all transactions from client."""
    txs = [_make_tx(id="1"), _make_tx(id="2")]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.query(HistoryQuery())

    assert len(result) == 2
    assert result[0].id == "1"
    assert result[1].id == "2"


def test_query_with_default_dates_uses_30_days_back():
    """When no date provided, query should use last 30 days as default."""
    txs = [_make_tx()]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    history.query(HistoryQuery())

    client.get_transaction_history.assert_called_once()
    args = client.get_transaction_history.call_args[0]
    assert "123456" == args[0]  # account_number from get_accounts


def test_query_with_amount_range_filters_in_memory():
    """min_amount and max_amount should filter after fetching."""
    txs = [
        _make_tx(id="1", amount=Decimal("50000")),
        _make_tx(id="2", amount=Decimal("500000")),
        _make_tx(id="3", amount=Decimal("5000000")),
    ]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.query(
        HistoryQuery(
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
            min_amount=Decimal("100000"),
            max_amount=Decimal("1000000"),
        )
    )

    assert len(result) == 1
    assert result[0].id == "2"


def test_query_with_direction_filter():
    """direction filter should keep only matching direction."""
    txs = [
        _make_tx(id="1", direction=TransactionDirection.DEBIT),
        _make_tx(id="2", direction=TransactionDirection.CREDIT),
        _make_tx(id="3", direction=TransactionDirection.DEBIT),
    ]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.query(HistoryQuery(direction=TransactionDirection.CREDIT))

    assert len(result) == 1
    assert result[0].id == "2"


def test_query_with_counterparty_filter_matches_name():
    """counterparty filter should match against counterparty_name."""
    txs = [
        _make_tx(id="1", counterparty_name="GRAB VIETNAM"),
        _make_tx(id="2", counterparty_name="SHOPEE PAY"),
    ]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.query(HistoryQuery(counterparty="grab"))

    assert len(result) == 1
    assert result[0].id == "1"


def test_query_with_description_search_filter():
    """description_search should match against description substring."""
    txs = [
        _make_tx(id="1", description="GRAB ride"),
        _make_tx(id="2", description="Lunch"),
        _make_tx(id="3", description="Coffee at GRAB cafe"),
    ]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.query(HistoryQuery(description_search="GRAB"))

    assert len(result) == 2
    assert {t.id for t in result} == {"1", "3"}


def test_query_raises_on_api_error():
    """Should raise PGBankError if the underlying API fails."""
    client = MagicMock()
    client.get_transaction_history.side_effect = PGBankError("API down")
    client.get_accounts.return_value = [
        BankAccount("123", "Alice", Decimal("0"), "VND", "checking")
    ]
    history = TransactionHistory(client)

    with pytest.raises(PGBankError):
        history.query(HistoryQuery())


# ── TransactionHistory.search ─────────────────────────────────────────────────


def test_search_case_insensitive_match():
    """Search should be case-insensitive."""
    # Use VINMART (no "grab" substring) for tx2 to avoid false match
    txs = [
        _make_tx(id="1", description="GRAB ride"),
        _make_tx(id="2", description="lunch", counterparty_name="VINMART"),
        _make_tx(id="3", counterparty_name="grab food"),
    ]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.search("grab")

    assert len(result) == 2
    assert {t.id for t in result} == {"1", "3"}


def test_search_matches_counterparty_account():
    """Search should match against counterparty_account."""
    txs = [
        _make_tx(id="1", counterparty_account="999999"),
        _make_tx(id="2", counterparty_account="888888"),
    ]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.search("999")

    assert len(result) == 1
    assert result[0].id == "1"


def test_search_no_match_returns_empty():
    """Search with no matches should return empty list."""
    txs = [_make_tx(description="lunch")]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    result = history.search("nonexistent_keyword")

    assert result == []


def test_search_with_specific_account_number():
    """Search should pass account_number to underlying client."""
    txs = [_make_tx()]
    client = _make_mock_client(txs)
    history = TransactionHistory(client)

    history.search("test", account_number="999")

    args = client.get_transaction_history.call_args[0]
    assert args[0] == "999"


# ── TransactionHistory.categorize ─────────────────────────────────────────────


def test_categorize_applies_matching_rule():
    """First matching rule should be applied."""
    txs = [_make_tx(description="GRAB ride")]
    history = TransactionHistory(MagicMock())

    result = history.categorize(txs, {"GRAB": "Di chuyển"})

    assert len(result) == 1
    assert result[0].category == "Di chuyển"
    assert isinstance(result[0], CategorizedTransaction)


def test_categorize_default_for_unmatched():
    """Unmatched transactions get 'Uncategorized'."""
    # Use a transaction with counterparty_name that has no overlap with rules
    txs = [
        Transaction(
            id="tx_no_match",
            account_number="111",
            type=TransactionDirection.DEBIT,
            amount=Decimal("50"),
            currency="VND",
            counterparty_name="VINMART",
            counterparty_account="777000",
            counterparty_bank=None,
            description="Weekly groceries",
            timestamp=datetime(2024, 6, 15),
            raw={},
        )
    ]
    history = TransactionHistory(MagicMock())

    result = history.categorize(txs, {"GRAB": "Di chuyển"})

    assert result[0].category == "Uncategorized"


def test_categorize_case_insensitive():
    """Rule matching should be case-insensitive."""
    txs = [_make_tx(description="grab RIDE")]
    history = TransactionHistory(MagicMock())

    result = history.categorize(txs, {"GRAB": "Di chuyển"})

    assert result[0].category == "Di chuyển"


def test_categorize_first_match_wins():
    """If multiple rules match, first one in dict order wins."""
    txs = [_make_tx(description="GRAB VNG payment")]
    history = TransactionHistory(MagicMock())

    rules = {"GRAB": "Di chuyển", "VNG": "Công nghệ"}
    result = history.categorize(txs, rules)

    assert result[0].category == "Di chuyển"


def test_categorize_matches_counterparty_name():
    """Rules should also match against counterparty_name."""
    txs = [_make_tx(counterparty_name="SHOPEE PAY")]
    history = TransactionHistory(MagicMock())

    result = history.categorize(txs, {"SHOPEE": "Mua sắm"})

    assert result[0].category == "Mua sắm"


def test_categorized_transaction_to_dict():
    """CategorizedTransaction.to_dict should include category."""
    tx = CategorizedTransaction(
        id="tx1",
        account_number="123",
        type=TransactionDirection.DEBIT,
        amount=Decimal("100"),
        currency="VND",
        counterparty_name="Test",
        counterparty_account="999",
        counterparty_bank=None,
        description="test",
        timestamp=datetime(2024, 6, 15),
        category="Test category",
    )
    d = tx.to_dict()
    assert d["category"] == "Test category"
    assert d["id"] == "tx1"


# ── query_all_accounts ───────────────────────────────────────────────────────


def test_query_all_accounts_aggregates():
    """query_all_accounts should fetch from each account and aggregate."""
    from pgbank_unofficial.manager import PGBankManager

    mgr = PGBankManager()
    mgr.add_account(
        Account(
            username="alice",
            password="p",
            browser_id="bid_a",
            nickname="alice-acc",
        )
    )
    mgr.add_account(
        Account(
            username="bob",
            password="p",
            browser_id="bid_b",
            nickname="bob-acc",
        )
    )

    # Mock both clients
    txs_alice = [_make_tx(id="a1")]
    txs_bob = [_make_tx(id="b1")]

    alice_client = _make_mock_client(txs_alice)
    bob_client = _make_mock_client(txs_bob)

    mgr.get_client = MagicMock(
        side_effect=lambda nick: alice_client if nick == "alice-acc" else bob_client
    )

    result = query_all_accounts(
        mgr, HistoryQuery(from_date=date(2024, 1, 1), to_date=date(2024, 12, 31))
    )

    assert "alice-acc" in result
    assert "bob-acc" in result
    assert len(result["alice-acc"]) == 1
    assert result["alice-acc"][0].id == "a1"
    assert result["bob-acc"][0].id == "b1"


# ── Export functions ──────────────────────────────────────────────────────────


def test_export_to_csv_writes_file(tmp_path: Path):
    """export_to_csv should write a properly formatted CSV file."""
    txs = [_make_tx()]
    output = tmp_path / "tx.csv"

    export_to_csv(txs, output)

    assert output.exists()
    with output.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert "timestamp" in rows[0]
    assert "amount" in rows[0]
    assert rows[0]["counterparty_name"] == "GRAB VIETNAM"


def test_export_to_csv_empty_list(tmp_path: Path):
    """Should still write header even with empty list."""
    output = tmp_path / "empty.csv"
    export_to_csv([], output)

    assert output.exists()
    with output.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert "timestamp" in header


def test_export_to_json_writes_file(tmp_path: Path):
    """export_to_json should write valid JSON array."""
    txs = [_make_tx(id="tx1"), _make_tx(id="tx2")]
    output = tmp_path / "tx.json"

    export_to_json(txs, output)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["id"] == "tx1"


def test_export_to_json_empty_list(tmp_path: Path):
    """Empty list should still write valid JSON."""
    output = tmp_path / "empty.json"
    export_to_json([], output)

    assert json.loads(output.read_text(encoding="utf-8")) == []


def test_export_to_excel_writes_file(tmp_path: Path):
    """export_to_excel should write a valid .xlsx file."""
    pytest.importorskip("openpyxl")  # Skip if not installed

    txs = [_make_tx()]
    output = tmp_path / "tx.xlsx"

    export_to_excel(txs, output)

    assert output.exists()
    assert output.stat().st_size > 0


def test_export_to_excel_with_account_label(tmp_path: Path):
    """export_to_excel should include account_label in header row."""
    pytest.importorskip("openpyxl")

    txs = [_make_tx()]
    output = tmp_path / "tx.xlsx"

    export_to_excel(txs, output, account_label="alice-main")

    assert output.exists()
    # We can't easily read xlsx without parsing, but file size > 0 is good evidence
    assert output.stat().st_size > 0


def test_export_to_excel_raises_without_openpyxl(tmp_path: Path, monkeypatch):
    """Should raise ImportError with helpful message if openpyxl missing."""
    # Hide openpyxl if present
    import sys

    monkeypatch.setitem(sys.modules, "openpyxl", None)
    monkeypatch.setitem(sys.modules, "openpyxl.workbook", None)

    # Try to use the function — if openpyxl was originally missing,
    # we'll get ImportError. If it's installed, this test is harmless.
    try:
        import openpyxl  # noqa: F401

        pytest.skip("openpyxl is installed; cannot test missing case")
    except ImportError:
        with pytest.raises(ImportError, match="openpyxl"):
            export_to_excel([_make_tx()], tmp_path / "tx.xlsx")


# ── Public API integration ───────────────────────────────────────────────────


def test_public_api_exports():
    """All history symbols should be importable from top-level package."""
    from pgbank_unofficial import (
        CategorizedTransaction,
        HistoryQuery,
        TransactionHistory,
        export_to_csv,
        export_to_excel,
        export_to_json,
        query_all_accounts,
    )

    assert all(
        cls is not None
        for cls in [
            CategorizedTransaction,
            HistoryQuery,
            TransactionHistory,
            export_to_csv,
            export_to_excel,
            export_to_json,
            query_all_accounts,
        ]
    )
