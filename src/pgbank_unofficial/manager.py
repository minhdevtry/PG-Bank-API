"""Multi-account manager for PGBank — health checks, batch operations.

``PGBankManager`` is the orchestration layer above :class:`PGBankClient`. It:

- Holds multiple account configurations (credentials + browser_id + proxy)
- Lazily instantiates clients (one per account) on first access
- Provides batch operations: ``health_check_all()``, ``get_all_balances()``
- Caches health snapshots (with TTL) to avoid hammering the API
- Runs health checks in parallel (thread pool) for speed

This is a **simplified** version focused on read-only operations
(balance checks, alive status). For transfer orchestration, see
``AutoPaymentScheduler`` (Phase 2).
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pgbank_unofficial.client import PGBankClient
from pgbank_unofficial.models import Account, BankAccount
from pgbank_unofficial.storage import BaseStorage, SQLiteStorage

logger = logging.getLogger(__name__)


class PGBankManager:
    """Multi-account manager for PGBank.

    Example:
        >>> from pgbank_unofficial import PGBankManager, Account
        >>> mgr = PGBankManager()
        >>> mgr.add_account(Account(
        ...     username="alice", password="...", browser_id="bid_alice",
        ...     nickname="alice-personal",
        ... ))
        >>> mgr.add_account(Account(
        ...     username="bob", password="...", browser_id="bid_bob",
        ...     proxy="http://bob-proxy:8080", nickname="bob-personal",
        ... ))
        >>> for nickname, health in mgr.health_check_all().items():
        ...     print(f"{nickname}: {'ALIVE' if health['alive'] else 'DEAD'}")
    """

    def __init__(
        self,
        *,
        sessions_dir: Optional[str | Path] = None,
        cache_ttl: float = 60.0,  # Health cache TTL in seconds
        max_workers: int = 4,  # Max parallel clients for batch ops
        storage: Optional[BaseStorage] = None,
    ) -> None:
        self._clients: dict[str, PGBankClient] = {}
        self._sessions_dir = Path(sessions_dir) if sessions_dir else None
        self._cache_ttl = cache_ttl
        self._health_cache: dict[str, tuple[datetime, dict]] = {}
        self._lock = threading.RLock()
        self._max_workers = max_workers

        # Default storage is SQLite at ~/.pgbank_unofficial/data.db
        if storage is None:
            db_path = Path.home() / ".pgbank_unofficial" / "data.db"
            self.storage = SQLiteStorage(db_path)
        else:
            self.storage = storage

        # Eagerly load accounts from storage
        self._accounts: dict[str, Account] = {}
        for acc in self.storage.load_accounts():
            self._accounts[acc.nickname] = acc

        # Eagerly load persisted accounts if sessions_dir is set
        if self._sessions_dir:
            self._sessions_dir.mkdir(parents=True, exist_ok=True)

    # ── Account registry ─────────────────────────────────────────────────────

    def add_account(self, account: Account) -> None:
        """Add an account to the manager.

        If a client for this nickname already exists, it's closed and replaced.
        If ``sessions_dir`` is set, a session file is configured.
        """
        with self._lock:
            if account.nickname in self._clients:
                try:
                    self._clients[account.nickname].close()
                except Exception:
                    pass
                del self._clients[account.nickname]
            self._accounts[account.nickname] = account
            self.storage.save_account(account)
            # Invalidate cached health
            self._health_cache.pop(account.nickname, None)
        logger.info(f"added account: {account.nickname}")

    def remove_account(self, nickname: str) -> None:
        with self._lock:
            if nickname in self._clients:
                try:
                    self._clients[nickname].close()
                except Exception:
                    pass
                del self._clients[nickname]
            self._accounts.pop(nickname, None)
            self.storage.remove_account(nickname)
            self._health_cache.pop(nickname, None)

    def get_account(self, nickname: str) -> Optional[Account]:
        return self._accounts.get(nickname)

    def list_accounts(self) -> list[str]:
        """Return all registered nicknames."""
        return list(self._accounts.keys())

    # ── Client lifecycle ──────────────────────────────────────────────────────

    def get_client(self, nickname: str) -> PGBankClient:
        """Get or lazily create the PGBankClient for an account.

        The first call triggers ``auto_login=True`` (if session file is
        available, it's restored; otherwise a fresh login is attempted).
        """
        with self._lock:
            if nickname not in self._accounts:
                raise KeyError(f"account not found: {nickname}")
            if nickname not in self._clients:
                acc = self._accounts[nickname]
                session_path = None
                if self._sessions_dir:
                    session_path = self._sessions_dir / f"{nickname}.json"
                self._clients[nickname] = PGBankClient(
                    username=acc.username,
                    password=acc.password,
                    browser_id=acc.browser_id,
                    proxy=acc.proxy,
                    session_path=session_path,
                    auto_login=True,
                )
            return self._clients[nickname]

    def close_all(self) -> None:
        with self._lock:
            for client in self._clients.values():
                try:
                    client.close()
                except Exception:
                    pass
            self._clients.clear()
            self._health_cache.clear()

    # ── Health checks ────────────────────────────────────────────────────────

    def health_check(self, nickname: str, *, use_cache: bool = True) -> dict[str, Any]:
        """Check health of a single account (with optional cache).

        Returns a dict with keys: alive, cif, full_name, account_count,
        total_balance, currency, last_error, checked_at.
        """
        # Check cache
        if use_cache and nickname in self._health_cache:
            cached_at, cached = self._health_cache[nickname]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age < self._cache_ttl:
                return cached

        try:
            client = self.get_client(nickname)
            snapshot = client.health_check()
        except Exception as e:
            snapshot = {
                "alive": False,
                "cif": None,
                "full_name": None,
                "account_count": 0,
                "total_balance": "0",
                "currency": "VND",
                "last_error": f"{type(e).__name__}: {e}",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        with self._lock:
            self._health_cache[nickname] = (datetime.now(timezone.utc), snapshot)
        return snapshot

    def health_check_all(
        self,
        *,
        use_cache: bool = True,
        parallel: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """Check health of all accounts.

        Returns a dict mapping nickname -> health snapshot.
        Runs in parallel (thread pool) for speed.
        """
        nicknames = self.list_accounts()
        if not nicknames:
            return {}
        if not parallel or len(nicknames) == 1:
            return {n: self.health_check(n, use_cache=use_cache) for n in nicknames}
        results: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(self.health_check, n, use_cache=use_cache): n for n in nicknames
            }
            for fut in as_completed(futures):
                n = futures[fut]
                try:
                    results[n] = fut.result()
                except Exception as e:
                    results[n] = {
                        "alive": False,
                        "last_error": f"{type(e).__name__}: {e}",
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
        return results

    def is_alive(self, nickname: str) -> bool:
        """Quick alive check for one account."""
        return self.health_check(nickname).get("alive", False)

    def alive_accounts(self) -> list[str]:
        """Return nicknames of all currently-alive accounts."""
        return [n for n, h in self.health_check_all(use_cache=False).items() if h.get("alive")]

    def dead_accounts(self) -> list[str]:
        """Return nicknames of all dead accounts."""
        return [n for n, h in self.health_check_all(use_cache=False).items() if not h.get("alive")]

    # ── Batch queries ────────────────────────────────────────────────────────

    def get_all_balances(self, *, use_cache: bool = False) -> dict[str, list[BankAccount]]:
        """Fetch all accounts across all customers (per-account).

        Returns: {nickname: [BankAccount, ...]}
        """
        result: dict[str, list[BankAccount]] = {}
        for nickname in self.list_accounts():
            try:
                client = self.get_client(nickname)
                result[nickname] = client.get_accounts()
            except Exception as e:
                logger.warning(f"get_accounts failed for {nickname}: {e}")
                result[nickname] = []
        return result

    def get_total_balance(self, *, use_cache: bool = True) -> dict[str, Any]:
        """Sum of all account balances across all customers.

        Returns: {nickname: total_balance_decimal_str, ...} + 'total' key
        """
        from decimal import Decimal

        balances = self.get_all_balances()
        totals: dict[str, Any] = {}
        grand = Decimal("0")
        for nickname, accounts in balances.items():
            acc_total = sum((a.balance for a in accounts), Decimal("0"))
            totals[nickname] = str(acc_total)
            grand += acc_total
        totals["total"] = str(grand)
        return totals

    # ── Persistence ──────────────────────────────────────────────────────────

    def save_accounts(self, path: str | Path) -> None:
        """Save account registry to JSON (passwords included — keep file safe!)."""
        data = {"accounts": {nick: acc.to_dict() for nick, acc in self._accounts.items()}}
        Path(path).write_text(json.dumps(data, indent=2))
        logger.info(f"saved {len(self._accounts)} accounts to {path}")

    @classmethod
    def load_accounts(cls, path: str | Path, **kwargs) -> "PGBankManager":
        """Load accounts from a JSON file."""
        mgr = cls(**kwargs)
        data = json.loads(Path(path).read_text())
        for nick, acc_data in data.get("accounts", {}).items():
            acc = Account.from_dict(acc_data)
            if not acc.nickname:
                acc.nickname = nick
            mgr.add_account(acc)
        return mgr

    # ── Context manager ─────────────────────────────────────────────────────

    def __enter__(self) -> "PGBankManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close_all()
