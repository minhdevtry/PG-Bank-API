"""Tests for the SQLite persistence layer and storage backends."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import pytest

from pgbank_unofficial.models import Account
from pgbank_unofficial.scheduler import Job, CronTrigger, IntervalTrigger, JobRun, TransferAction
from pgbank_unofficial.storage import MemoryStorage, SQLiteStorage
from pgbank_unofficial.manager import PGBankManager
from pgbank_unofficial.scheduler import AutoPaymentScheduler


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


class TestMemoryStorage:
    """Verify in-memory storage functionality."""

    def test_account_ops(self):
        storage = MemoryStorage()
        acc = Account(username="alice", password="p", browser_id="bid", nickname="alice-acc")
        
        storage.save_account(acc)
        assert storage.get_account("alice-acc") == acc
        assert storage.load_accounts() == [acc]

        storage.remove_account("alice-acc")
        assert storage.get_account("alice-acc") is None
        assert storage.load_accounts() == []


class TestSQLiteStorage:
    """Verify SQLiteStorage persistence functionality."""

    def test_account_ops(self, temp_db):
        storage = SQLiteStorage(temp_db)
        acc = Account(username="bob", password="p1", browser_id="bid_bob", proxy="http://proxy", nickname="bob-acc")
        
        storage.save_account(acc)
        loaded = storage.get_account("bob-acc")
        assert loaded is not None
        assert loaded.username == "bob"
        assert loaded.password == "p1"
        assert loaded.browser_id == "bid_bob"
        assert loaded.proxy == "http://proxy"
        assert loaded.nickname == "bob-acc"

        all_accs = storage.load_accounts()
        assert len(all_accs) == 1
        assert all_accs[0].username == "bob"

        storage.remove_account("bob-acc")
        assert storage.get_account("bob-acc") is None
        assert len(storage.load_accounts()) == 0

    def test_job_ops(self, temp_db):
        storage = SQLiteStorage(temp_db)
        action = TransferAction(to_account="999", amount=Decimal("50000"), description="test-pay")
        trigger = CronTrigger("0 9 * * *", jitter_seconds=10)
        job = Job(name="Rent", trigger=trigger, action=action, account_nickname="bob-acc", dry_run=True, daily_limit=Decimal("10000000"))

        storage.save_job(job)

        raw = storage.get_job(job.id)
        assert raw is not None
        assert raw.name == "Rent"
        assert raw.account_nickname == "bob-acc"
        assert raw.dry_run is True

        # Load jobs
        from pgbank_unofficial.scheduler import _default_action_loader
        loaded_jobs = storage.load_jobs(_default_action_loader)
        assert len(loaded_jobs) == 1
        loaded_job = loaded_jobs[0]
        assert loaded_job.id == job.id
        assert loaded_job.name == "Rent"
        assert isinstance(loaded_job.trigger, CronTrigger)
        assert loaded_job.trigger.expression == "0 9 * * *"
        assert loaded_job.trigger.jitter_seconds == 10
        assert isinstance(loaded_job.action, TransferAction)
        assert loaded_job.action.to_account == "999"
        assert loaded_job.action.amount == Decimal("50000")
        assert loaded_job.account_nickname == "bob-acc"
        assert loaded_job.dry_run is True
        assert loaded_job.daily_limit == Decimal("10000000")

        storage.remove_job(job.id)
        assert len(storage.load_jobs(_default_action_loader)) == 0

    def test_job_run_history(self, temp_db):
        storage = SQLiteStorage(temp_db)
        run = JobRun(
            job_id="job-123",
            started_at=datetime(2026, 6, 23, 12, 0, 0),
            finished_at=datetime(2026, 6, 23, 12, 0, 5),
            success=True,
            error=None,
            dry_run=False,
            triggered_by="scheduler"
        )
        storage.add_job_run(run)
        
        runs = storage.get_job_runs("job-123")
        assert len(runs) == 1
        assert runs[0].job_id == "job-123"
        assert runs[0].success is True
        assert runs[0].duration == timedelta(seconds=5)
        assert runs[0].triggered_by == "scheduler"


class TestManagerSchedulerStorageIntegration:
    """Verify integration between manager, scheduler and storage backend."""

    def test_manager_uses_passed_storage(self, temp_db):
        storage = SQLiteStorage(temp_db)
        mgr = PGBankManager(storage=storage)
        assert mgr.storage == storage

        acc = Account(username="user", password="pwd", browser_id="browser", nickname="user-nick")
        mgr.add_account(acc)
        
        # Verify it went to SQLite DB
        loaded_acc = storage.get_account("user-nick")
        assert loaded_acc is not None
        assert loaded_acc.username == "user"

        # Verify new manager with same storage loads it
        mgr2 = PGBankManager(storage=storage)
        assert "user-nick" in mgr2.list_accounts()

    def test_scheduler_persists_runs_and_state(self, temp_db):
        storage = SQLiteStorage(temp_db)
        mgr = PGBankManager(storage=storage)
        scheduler = AutoPaymentScheduler(mgr)

        action = TransferAction(to_account="111", amount=Decimal("1000"))
        trigger = IntervalTrigger(seconds=60)
        job = Job(name="IntervalPay", trigger=trigger, action=action, account_nickname="user-nick")

        scheduler.add_job(job)
        
        # Verify job is persisted
        persisted_jobs = storage.load_jobs(lambda t, a: action)
        assert len(persisted_jobs) == 1
        assert persisted_jobs[0].id == job.id

        # Trigger manual run to verify run record is saved to SQLite
        run = scheduler.run_job_now(job.id, dry_run=True)
        assert run.success is True

        # Check SQLite db for runs
        runs = storage.get_job_runs(job.id)
        assert len(runs) == 1
        assert runs[0].dry_run is True
        assert runs[0].success is True
