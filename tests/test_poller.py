"""Tests for the poller module — BalancePoller and TransactionMonitor."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from pgbank_unofficial.poller import (
    BalanceChangedEvent,
    BalancePoller,
    BalancePollerError,
    BalanceSnapshot,
    TransactionMonitor,
    TransactionPollerError,
)

VN_TZ = timezone(timedelta(hours=7))


# ──────────────────────────────────────────────────────────────────────────────
# BalanceSnapshot
# ──────────────────────────────────────────────────────────────────────────────


class TestBalanceSnapshot:
    def test_snapshot_stores_account_and_balance(self):
        """BalanceSnapshot should store account, balance, and timestamp."""
        snapshot = BalanceSnapshot(
            account_nickname="alice-acc",
            available=Decimal("10000000"),
            total=Decimal("10000000"),
            currency="VND",
            timestamp=datetime.now(tz=VN_TZ),
        )
        assert snapshot.account_nickname == "alice-acc"
        assert snapshot.available == Decimal("10000000")
        assert snapshot.total == Decimal("10000000")

    def test_snapshot_change_detected(self):
        """change_from should return positive Decimal when balance decreased."""
        prev = BalanceSnapshot(
            account_nickname="alice-acc",
            available=Decimal("10000000"),
            total=Decimal("10000000"),
            currency="VND",
            timestamp=datetime.now(tz=VN_TZ),
        )
        later = BalanceSnapshot(
            account_nickname="alice-acc",
            available=Decimal("9000000"),
            total=Decimal("9000000"),
            currency="VND",
            timestamp=datetime.now(tz=VN_TZ),
        )
        change = later.change_from(prev)
        assert change == Decimal("-1000000")


# ──────────────────────────────────────────────────────────────────────────────
# BalanceChangedEvent
# ──────────────────────────────────────────────────────────────────────────────


class TestBalanceChangedEvent:
    def test_event_stores_fields(self):
        """Event should store snapshot, change, and direction."""
        snapshot = BalanceSnapshot(
            account_nickname="alice-acc",
            available=Decimal("9000000"),
            total=Decimal("9000000"),
            currency="VND",
            timestamp=datetime.now(tz=VN_TZ),
        )
        event = BalanceChangedEvent(
            snapshot=snapshot,
            change=Decimal("-1000000"),
            direction="decrease",
        )
        assert event.account_nickname == "alice-acc"
        assert event.change == Decimal("-1000000")
        assert event.direction == "decrease"


# ──────────────────────────────────────────────────────────────────────────────
# BalancePoller
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_manager():
    """A mock PGBankManager with two accounts."""
    mgr = MagicMock()
    mgr.list_accounts.return_value = ["alice-acc", "bob-acc"]
    mock_alice_client = MagicMock()
    mock_alice_client.get_balance.return_value = MagicMock(
        available=Decimal("10000000"),
        total=Decimal("10000000"),
        account_number="123456",
        currency="VND",
    )
    mock_bob_client = MagicMock()
    mock_bob_client.get_balance.return_value = MagicMock(
        available=Decimal("5000000"),
        total=Decimal("5000000"),
        account_number="789012",
        currency="VND",
    )
    mgr.get_client.side_effect = lambda nick: {
        "alice-acc": mock_alice_client,
        "bob-acc": mock_bob_client,
    }.get(nick)
    return mgr


@pytest.fixture
def dispatcher():
    """A mock WebhookDispatcher."""
    return MagicMock()


class TestBalancePollerInit:
    def test_default_threshold_is_1000(self):
        """Default change_threshold should be 1000 VND."""
        poller = BalancePoller(MagicMock(), poll_interval=timedelta(minutes=5))
        assert poller.change_threshold == Decimal("1000")

    def test_custom_threshold(self):
        """Custom threshold should be respected."""
        poller = BalancePoller(
            MagicMock(),
            poll_interval=timedelta(minutes=5),
            change_threshold=Decimal("50000"),
        )
        assert poller.change_threshold == Decimal("50000")

    def test_dispatcher_defaults_to_none(self):
        """Dispatcher should default to None."""
        poller = BalancePoller(MagicMock(), poll_interval=timedelta(minutes=5))
        assert poller._dispatcher is None


class TestBalancePollerPoll:
    def test_poll_fetches_all_accounts(self, mock_manager):
        """poll() should call get_balance for every registered account."""
        poller = BalancePoller(mock_manager, poll_interval=timedelta(minutes=5))
        poller.poll()

        assert mock_manager.get_client.call_count == 2
        mock_manager.get_client.assert_any_call("alice-acc")
        mock_manager.get_client.assert_any_call("bob-acc")

    def test_poll_returns_snapshots(self, mock_manager):
        """poll() should return all snapshots via the unchanged list (first poll = no baseline)."""
        poller = BalancePoller(mock_manager, poll_interval=timedelta(minutes=5))
        changed, unchanged = poller.poll()
        snapshots = list(changed) + list(unchanged)

        assert len(snapshots) == 2
        nicknames = {s.account_nickname for s in snapshots}
        assert nicknames == {"alice-acc", "bob-acc"}

    def test_poll_updates_last_snapshots(self, mock_manager):
        """poll() should store snapshots as last known state."""
        poller = BalancePoller(mock_manager, poll_interval=timedelta(minutes=5))
        poller.poll()

        assert poller._last_snapshots["alice-acc"].available == Decimal("10000000")
        assert poller._last_snapshots["bob-acc"].available == Decimal("5000000")

    def test_poll_handles_account_error_gracefully(self, mock_manager):
        """poll() should continue if one account raises."""
        def get_client_side_effect(nick):
            if nick == "bob-acc":
                raise BalancePollerError("network timeout")
            client = MagicMock()
            client.get_balance.return_value = MagicMock(
                available=Decimal("10000000"),
                total=Decimal("10000000"),
                account_number="123456",
                currency="VND",
            )
            return client

        mock_manager.get_client.side_effect = get_client_side_effect
        poller = BalancePoller(mock_manager, poll_interval=timedelta(minutes=5))
        changed, unchanged = poller.poll()
        snapshots = list(changed) + list(unchanged)

        # Should still return alice's snapshot (bob was errored out)
        assert len(snapshots) == 1
        assert snapshots[0].account_nickname == "alice-acc"


class TestBalancePollerDetectChange:
    def test_change_detected_above_threshold(self, mock_manager):
        """Should detect change when difference exceeds threshold."""
        # Use persistent mock clients so we can mutate balance between polls
        mock_alice = MagicMock()
        mock_alice.get_balance.return_value = MagicMock(
            available=Decimal("10000000"),
            total=Decimal("10000000"),
            account_number="123456",
            currency="VND",
        )
        mock_bob = MagicMock()
        mock_bob.get_balance.return_value = MagicMock(
            available=Decimal("5000000"),
            total=Decimal("5000000"),
            account_number="789012",
            currency="VND",
        )

        def get_client_for(nick):
            return {"alice-acc": mock_alice, "bob-acc": mock_bob}.get(nick, MagicMock())

        mock_manager.get_client.side_effect = get_client_for
        poller = BalancePoller(
            mock_manager,
            poll_interval=timedelta(minutes=5),
            change_threshold=Decimal("1000"),
        )
        # First poll to establish baseline (both at original balances)
        poller.poll()
        # Change alice's balance in mock only
        mock_alice.get_balance.return_value.available = Decimal("8500000")
        # Second poll
        changed, unchanged = poller.poll()

        # Only alice changed (from 10M to 8.5M, exceeds threshold)
        alice_changed = [s for s in changed if s.account_nickname == "alice-acc"]
        assert len(alice_changed) == 1
        assert alice_changed[0].available == Decimal("8500000")
        # Bob should be in unchanged
        bob_unchanged = [s for s in unchanged if s.account_nickname == "bob-acc"]
        assert len(bob_unchanged) == 1

    def test_change_not_detected_below_threshold(self, mock_manager):
        """Should not detect change when difference is below threshold."""
        poller = BalancePoller(
            mock_manager,
            poll_interval=timedelta(minutes=5),
            change_threshold=Decimal("5000000"),
        )
        poller.poll()
        # Tiny change below threshold
        mock_manager.get_client.return_value.get_balance.return_value.available = Decimal("9999999")
        changed, unchanged = poller.poll()

        alice_changed = next((s for s in changed if s.account_nickname == "alice-acc"), None)
        assert alice_changed is None  # Not detected as changed

    def test_no_change_when_balances_equal(self, mock_manager):
        """Same balance should not trigger change detection."""
        poller = BalancePoller(mock_manager, poll_interval=timedelta(minutes=5))
        poller.poll()
        changed, unchanged = poller.poll()

        assert len(changed) == 0


class TestBalancePollerAlert:
    def test_alert_below_registers_alert(self):
        """alert_below should register a balance alert."""
        poller = BalancePoller(MagicMock(), poll_interval=timedelta(minutes=5))
        poller.alert_below("alice-acc", amount=Decimal("1000000"))

        assert ("alice-acc", Decimal("1000000")) in poller._below_alerts

    def test_alert_below_triggers_when_balance_drops(self):
        """Alert should fire when balance drops below threshold on poll."""
        mock_mgr = MagicMock()
        mock_client = MagicMock()
        mock_client.get_balance.return_value = MagicMock(
            available=Decimal("800000"),
            total=Decimal("800000"),
            account_number="123456",
            currency="VND",
        )
        mock_mgr.list_accounts.return_value = ["alice-acc"]
        mock_mgr.get_client.return_value = mock_client

        poller = BalancePoller(mock_mgr, poll_interval=timedelta(minutes=5))
        poller.alert_below("alice-acc", amount=Decimal("1000000"))
        changed, unchanged = poller.poll()

        assert len(changed) == 1
        assert changed[0].account_nickname == "alice-acc"

    def test_alert_below_no_trigger_when_above(self):
        """Alert should not fire when balance is above threshold."""
        mock_mgr = MagicMock()
        mock_client = MagicMock()
        mock_client.get_balance.return_value = MagicMock(
            available=Decimal("2000000"),
            total=Decimal("2000000"),
            account_number="123456",
            currency="VND",
        )
        mock_mgr.list_accounts.return_value = ["alice-acc"]
        mock_mgr.get_client.return_value = mock_client

        poller = BalancePoller(mock_mgr, poll_interval=timedelta(minutes=5))
        poller.alert_below("alice-acc", amount=Decimal("1000000"))
        changed, unchanged = poller.poll()

        assert len(changed) == 0


class TestBalancePollerLifecycle:
    def test_start_stop_manages_thread(self):
        """start() should start a daemon thread; stop() should stop it."""
        mock_mgr = MagicMock()
        mock_mgr.list_accounts.return_value = []
        poller = BalancePoller(mock_mgr, poll_interval=timedelta(seconds=0))
        poller.start()
        assert poller._thread is not None
        assert poller._thread.is_alive() is True

        poller.stop()
        assert poller._thread.is_alive() is False

    def test_stop_is_idempotent(self):
        """stop() should be safe to call multiple times."""
        mock_mgr = MagicMock()
        mock_mgr.list_accounts.return_value = []
        poller = BalancePoller(mock_mgr, poll_interval=timedelta(seconds=0))
        poller.start()
        poller.stop()
        poller.stop()  # Should not raise


# ──────────────────────────────────────────────────────────────────────────────
# TransactionMonitor
# ──────────────────────────────────────────────────────────────────────────────


class TestTransactionMonitorInit:
    def test_default_since_delta_is_30_minutes(self):
        """Default _since_delta should be 30 minutes."""
        mon = TransactionMonitor(MagicMock(), poll_interval=timedelta(minutes=2))
        assert mon._since_delta == timedelta(minutes=30)

    def test_custom_since_delta(self):
        """Custom since_delta should be respected."""
        mon = TransactionMonitor(
            MagicMock(),
            poll_interval=timedelta(minutes=2),
            since_delta=timedelta(hours=2),
        )
        assert mon._since_delta == timedelta(hours=2)


class TestTransactionMonitorDetect:
    def test_detect_new_transactions(self):
        """Should detect transactions not seen in previous poll."""
        mock_client = MagicMock()
        now = datetime.now(tz=VN_TZ)
        # First poll returns one transaction
        first_tx = MagicMock()
        first_tx.id = "tx1"
        first_tx.timestamp = now - timedelta(minutes=10)
        mock_client.get_transaction_history.return_value = [first_tx]

        mock_mgr = MagicMock()
        mock_mgr.list_accounts.return_value = ["alice-acc"]
        mock_mgr.get_client.return_value = mock_client

        mon = TransactionMonitor(mock_mgr, poll_interval=timedelta(minutes=2))
        new = mon._detect_new_transactions()
        assert len(new) == 1

        # Second poll returns two transactions (one new)
        second_tx = MagicMock()
        second_tx.id = "tx2"
        second_tx.timestamp = now - timedelta(minutes=1)
        mock_client.get_transaction_history.return_value = [first_tx, second_tx]
        new2 = mon._detect_new_transactions()
        assert len(new2) == 1  # Only tx2 is new


class TestTransactionMonitorPublicAPI:
    def test_public_api_exports(self):
        """All poller symbols should be importable from top-level package."""
        from pgbank_unofficial import (
            BalanceChangedEvent,
            BalancePoller,
            BalanceSnapshot,
            TransactionMonitor,
        )

        assert BalancePoller is not None
        assert TransactionMonitor is not None
        assert BalanceSnapshot is not None
        assert BalanceChangedEvent is not None
