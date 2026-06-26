"""Real-Time Monitoring — BalancePoller and TransactionMonitor.

Polls PGBank balances and transactions at user-defined intervals and dispatches
events when changes are detected.

Components:
    - :class:`BalanceSnapshot` — captured balance at a point in time
    - :class:`BalanceChangedEvent` — emitted when balance changes meaningfully
    - :class:`BalancePoller` — periodically polls all accounts' balances
    - :class:`TransactionMonitor` — periodically detects new transactions

Example:
    >>> from datetime import timedelta
    >>> from decimal import Decimal
    >>> from pgbank_unofficial import PGBankManager, BalancePoller
    >>> mgr = PGBankManager()
    >>> poller = BalancePoller(mgr, poll_interval=timedelta(minutes=5))
    >>> poller.alert_below("alice-acc", amount=Decimal("100000"))
    >>> poller.start()  # Background thread
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from pgbank_unofficial.manager import PGBankManager
    from pgbank_unofficial.webhook import WebhookDispatcher

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────────────────


class BalancePollerError(Exception):
    """Raised when a balance poll operation fails."""


class TransactionPollerError(Exception):
    """Raised when a transaction monitor operation fails."""


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BalanceSnapshot:
    """A captured balance at a point in time.

    Attributes:
        account_nickname: Nickname of the account.
        available: Available balance.
        total: Total balance (may equal available for some accounts).
        currency: Currency code (e.g., "VND").
        timestamp: When this snapshot was taken.
    """

    account_nickname: str
    available: Decimal
    total: Decimal
    currency: str
    timestamp: datetime

    def change_from(self, previous: "BalanceSnapshot") -> Decimal:
        """Compute available balance change vs *previous* snapshot.

        Returns a positive Decimal if balance increased, negative if decreased.
        """
        return self.available - previous.available


@dataclass
class BalanceChangedEvent:
    """Emitted when an account's balance changes meaningfully.

    Attributes:
        snapshot: The new balance snapshot.
        change: available - previous.available
        direction: "increase" | "decrease" | "unchanged"
        previous_snapshot: The previous snapshot (or None if first poll).
        account_nickname: Convenience — snapshot.account_nickname
    """

    snapshot: BalanceSnapshot
    change: Decimal
    direction: str
    previous_snapshot: Optional[BalanceSnapshot] = None
    account_nickname: str = ""

    def __post_init__(self) -> None:
        """Populate account_nickname from snapshot if not provided."""
        if not self.account_nickname and self.snapshot:
            object.__setattr__(self, "account_nickname", self.snapshot.account_nickname)


# ──────────────────────────────────────────────────────────────────────────────
# BalancePoller
# ──────────────────────────────────────────────────────────────────────────────


class BalancePoller:
    """Periodically polls all registered accounts' balances.

    Args:
        manager: :class:`PGBankManager` with registered accounts.
        poll_interval: How often to poll (e.g. ``timedelta(minutes=5)``).
        change_threshold: Minimum |change| in VND to consider a meaningful change.
            Default is 1000 VND.
        dispatcher: Optional :class:`WebhookDispatcher` for event publishing.

    Attributes:
        change_threshold: Configured threshold (read-only access).
    """

    def __init__(
        self,
        manager: "PGBankManager",
        *,
        poll_interval: timedelta,
        change_threshold: Decimal = Decimal("1000"),
        dispatcher: Optional["WebhookDispatcher"] = None,
    ) -> None:
        self._manager = manager
        self._poll_interval = poll_interval
        self.change_threshold = Decimal(change_threshold)
        self._dispatcher = dispatcher
        self._last_snapshots: dict[str, BalanceSnapshot] = {}
        self._below_alerts: list[tuple[str, Decimal]] = []  # (nickname, threshold)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._on_change: Optional[callable] = None  # optional callback

    def on_change(self, callback: callable) -> None:
        """Register a callback for BalanceChangedEvent (sync).

        The callback signature: ``callback(event: BalanceChangedEvent) -> None``
        """
        self._on_change = callback

    def alert_below(self, account_nickname: str, *, amount: Decimal) -> None:
        """Register a balance alert: fire event when balance drops below *amount*.

        Args:
            account_nickname: Target account.
            amount: Threshold in VND.
        """
        with self._lock:
            self._below_alerts.append((account_nickname, Decimal(amount)))

    def _clear_alerts(self) -> None:
        """Remove all registered below-alerts. Useful for tests."""
        with self._lock:
            self._below_alerts.clear()

    def poll(self) -> tuple[list[BalanceSnapshot], list[BalanceSnapshot]]:
        """Poll all accounts and detect balance changes.

        Returns:
            Tuple of (changed_snapshots, unchanged_snapshots).
        """
        nicknames = list(self._manager.list_accounts())
        now = datetime.now()
        new_snapshots: dict[str, BalanceSnapshot] = {}
        changed: list[BalanceSnapshot] = []
        unchanged: list[BalanceSnapshot] = []

        for nick in nicknames:
            try:
                client = self._manager.get_client(nick)
                balance = client.get_balance()
            except Exception as exc:
                logger.warning("Balance poll failed for %s: %s", nick, exc)
                continue

            snapshot = BalanceSnapshot(
                account_nickname=nick,
                available=Decimal(balance.available),
                total=Decimal(balance.total),
                currency=getattr(balance, "currency", "VND") or "VND",
                timestamp=now,
            )
            new_snapshots[nick] = snapshot

            with self._lock:
                prev = self._last_snapshots.get(nick)

            # Determine if changed meaningfully
            if prev is None:
                # First poll — no previous baseline
                direction = "unchanged"
                change = Decimal("0")
            else:
                change = snapshot.change_from(prev)
                if abs(change) >= self.change_threshold:
                    direction = "increase" if change > 0 else "decrease"
                else:
                    direction = "unchanged"
                    change = Decimal("0")

            # Check below-alerts regardless of direction (alert wins)
            below_triggered = self._check_below_alerts(nick, snapshot)
            if below_triggered or direction != "unchanged":
                changed.append(snapshot)
                self._emit_change_event(
                    snapshot=snapshot,
                    previous=prev,
                    change=change,
                    direction=direction,
                )
            else:
                unchanged.append(snapshot)

        with self._lock:
            self._last_snapshots.update(new_snapshots)

        return changed, unchanged

    def _check_below_alerts(self, account_nickname: str, snapshot: BalanceSnapshot) -> bool:
        """Check whether *snapshot* triggers any registered below-alert. Returns True if so."""
        with self._lock:
            alerts = [a for a in self._below_alerts if a[0] == account_nickname]
        for _nick, threshold in alerts:
            if snapshot.available < threshold:
                return True
        return False

    def _emit_change_event(
        self,
        *,
        snapshot: BalanceSnapshot,
        previous: Optional[BalanceSnapshot],
        change: Decimal,
        direction: str,
    ) -> None:
        """Emit a BalanceChangedEvent via dispatcher and on_change callback."""
        event = BalanceChangedEvent(
            snapshot=snapshot,
            previous_snapshot=previous,
            change=change,
            direction=direction,
        )

        # Callback
        if self._on_change is not None:
            try:
                self._on_change(event)
            except Exception:
                logger.exception("on_change callback failed")

        # Webhook dispatcher
        if self._dispatcher is not None:
            try:
                from pgbank_unofficial.webhook import Event  # local import to avoid circular

                webhook_event = Event(
                    type=f"balance.changed.{direction}",
                    timestamp=snapshot.timestamp,
                    data={
                        "account_nickname": snapshot.account_nickname,
                        "available": str(snapshot.available),
                        "total": str(snapshot.total),
                        "currency": snapshot.currency,
                        "change": str(change),
                        "direction": direction,
                    },
                )
                # Fire-and-forget sync dispatch
                self._dispatcher.dispatch_sync(webhook_event)
            except Exception:
                logger.exception("Failed to publish balance change event")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, *, daemon: bool = True) -> None:
        """Start the background polling thread.

        Args:
            daemon: If True, the thread is a daemon (exits when main process exits).
        """
        if self._thread is not None and self._thread.is_alive():
            logger.warning("BalancePoller is already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="pgbank-balance-poller", daemon=daemon
        )
        self._thread.start()
        logger.info(
            "BalancePoller started (interval=%s, threshold=%s)",
            self._poll_interval,
            self.change_threshold,
        )

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.info("BalancePoller stopped")

    def _run_loop(self) -> None:
        """Main polling loop: poll every poll_interval."""
        logger.info("BalancePoller loop started")
        while not self._stop_event.is_set():
            try:
                self.poll()
            except Exception:
                logger.exception("Error in BalancePoller loop")
            self._stop_event.wait(self._poll_interval.total_seconds())
        logger.info("BalancePoller loop exited")


# ──────────────────────────────────────────────────────────────────────────────
# TransactionMonitor
# ──────────────────────────────────────────────────────────────────────────────


class TransactionMonitor:
    """Periodically detects new transactions across all registered accounts.

    Args:
        manager: :class:`PGBankManager` with registered accounts.
        poll_interval: How often to poll (e.g. ``timedelta(minutes=2)``).
        since_delta: How far back to look on first poll (default 30 minutes).
        dispatcher: Optional :class:`WebhookDispatcher` for event publishing.

    Attributes:
        _since_delta: Configured since window (internal).
    """

    def __init__(
        self,
        manager: "PGBankManager",
        *,
        poll_interval: timedelta,
        since_delta: Optional[timedelta] = None,
        dispatcher: Optional["WebhookDispatcher"] = None,
    ) -> None:
        self._manager = manager
        self._poll_interval = poll_interval
        self._since_delta = since_delta if since_delta is not None else timedelta(minutes=30)
        self._dispatcher = dispatcher
        self._seen_ids: dict[str, set[str]] = {}  # nickname -> set of tx IDs
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _detect_new_transactions(self) -> list:
        """Detect new transactions across all accounts since last poll.

        Returns a list of new Transaction objects (across all accounts).
        """
        nicknames = list(self._manager.list_accounts())
        new_transactions: list = []
        cutoff = datetime.now() - self._since_delta

        for nick in nicknames:
            try:
                client = self._manager.get_client(nick)
                # Fetch recent transactions
                history = client.get_transaction_history(from_date=cutoff)
            except Exception as exc:
                logger.warning("Transaction poll failed for %s: %s", nick, exc)
                continue

            with self._lock:
                seen = self._seen_ids.setdefault(nick, set())

            for tx in history:
                tx_id = getattr(tx, "id", None)
                if tx_id is None:
                    continue
                if tx_id not in seen:
                    seen.add(tx_id)
                    new_transactions.append(tx)

        return new_transactions

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, *, daemon: bool = True) -> None:
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("TransactionMonitor is already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="pgbank-tx-monitor", daemon=daemon
        )
        self._thread.start()
        logger.info("TransactionMonitor started (interval=%s)", self._poll_interval)

    def stop(self, *, timeout: float = 5.0) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.info("TransactionMonitor stopped")

    def _run_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("TransactionMonitor loop started")
        while not self._stop_event.is_set():
            try:
                new_txs = self._detect_new_transactions()
                if new_txs and self._dispatcher is not None:
                    for tx in new_txs:
                        self._emit_tx_event(tx)
            except Exception:
                logger.exception("Error in TransactionMonitor loop")
            self._stop_event.wait(self._poll_interval.total_seconds())
        logger.info("TransactionMonitor loop exited")

    def _emit_tx_event(self, tx: Any) -> None:
        """Emit a TransactionEvent via dispatcher."""
        if self._dispatcher is None:
            return
        try:
            from pgbank_unofficial.webhook import Event  # local import to avoid circular

            event = Event(
                type="transaction.detected",
                timestamp=datetime.now(),
                data={
                    "tx_id": getattr(tx, "id", ""),
                    "amount": str(getattr(tx, "amount", "")),
                    "description": getattr(tx, "description", ""),
                    "counterparty": getattr(tx, "counterparty_name", ""),
                    "timestamp": str(getattr(tx, "timestamp", "")),
                },
            )
            self._dispatcher.dispatch_sync(event)
        except Exception:
            logger.exception("Failed to publish transaction event")


__all__ = [
    "BalanceSnapshot",
    "BalanceChangedEvent",
    "BalancePoller",
    "BalancePollerError",
    "TransactionMonitor",
    "TransactionPollerError",
]
